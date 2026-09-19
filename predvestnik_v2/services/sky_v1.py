"""Server-authoritative Harbinger Sky route allocation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from core.feats_v1 import FEATS, FEATS_VERSION, feat_definition_digest
from core.scar_map_v1 import POLICY_VERSION as SCAR_POLICY_VERSION
from core.sky_v1 import DEFINITION_DIGEST, NODE_BY_ID, POLICY_VERSION, SIGIL_IDS, can_allocate, path_budget, public_view
from infrastructure.repositories import feats_v1 as feat_repo
from infrastructure.repositories import gameplay_events as event_repo
from infrastructure.repositories import reconstruction as reconstruction_repo
from infrastructure.repositories import sky_v1 as repo
from services import feats_v1, scar_map_v1


class SkyConflict(RuntimeError):
    pass


class SkyRuleError(ValueError):
    pass


def _fingerprint(action: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"action": action, "policy_version": POLICY_VERSION,
                            "definition_digest": DEFINITION_DIGEST, **payload},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_action_id(action_id: str) -> str:
    value = str(action_id or "").strip()
    if not 8 <= len(value) <= 96:
        raise SkyRuleError("invalid_action_id")
    return value


async def _locked_context(db, user_id: int, source: str) -> tuple[int, int, str]:
    receipts = await feat_repo.list_receipts(db, int(user_id))
    definitions = {str(item["id"]): item for item in FEATS}
    for feat_id, receipt in receipts.items():
        feat = definitions.get(feat_id)
        if (not feat or receipt["feat_version"] != FEATS_VERSION or
                receipt["definition_digest"] != feat_definition_digest(feat)):
            raise RuntimeError("Chronicle feat receipt definition conflict")
    row, created = await scar_map_v1._ensure_active(db, int(user_id))
    if created:
        await scar_map_v1._start_event(db, int(user_id), row, source)
    cycle_no = int(row["cycle_no"])
    return len(receipts), cycle_no, f"{SCAR_POLICY_VERSION}:{cycle_no}"


def _view(row, completed_feats: int, cycle_no: int, cycle_key: str, *, replayed: bool = False):
    allocated, sigil, revision, eclipse_key = repo.decode(row)
    result = public_view(
        allocated=allocated, active_sigil=sigil, revision=revision,
        completed_feats=completed_feats, eclipse_cycle_key=eclipse_key,
        current_cycle_no=cycle_no, current_cycle_key=cycle_key,
    )
    if replayed:
        result["replayed"] = True
    return result


async def overview(db, user_id: int, *, source: str = "mini_app") -> dict[str, Any]:
    await feats_v1.get_user_feats(db, int(user_id))
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, int(user_id))
        completed_feats, cycle_no, cycle_key = await _locked_context(db, int(user_id), source)
        row = await repo.get_state(db, int(user_id))
        return _view(row, completed_feats, cycle_no, cycle_key)


async def _replay(db, *, user_id: int, action_id: str, fingerprint: str) -> bool:
    receipt = await repo.get_action(db, user_id, action_id)
    if not receipt:
        return False
    if receipt["fingerprint"] != fingerprint:
        raise SkyConflict("action_id_conflict")
    return True


async def allocate(db, *, user_id: int, node_id: str, expected_revision: int,
                   action_id: str, source: str) -> dict[str, Any]:
    action_id = _validate_action_id(action_id)
    fingerprint = _fingerprint("allocate", {"node_id": node_id, "expected_revision": int(expected_revision)})
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, int(user_id))
        completed_feats, cycle_no, cycle_key = await _locked_context(db, int(user_id), source)
        replay = await _replay(db, user_id=int(user_id), action_id=action_id, fingerprint=fingerprint)
        if replay:
            return _view(await repo.get_state(db, int(user_id)), completed_feats, cycle_no, cycle_key, replayed=True)
        allocated, sigil, revision, eclipse_key = repo.decode(await repo.get_state(db, int(user_id)))
        if revision != int(expected_revision):
            raise SkyConflict("revision_conflict")
        allowed, reason = can_allocate(allocated, str(node_id), path_budget(completed_feats))
        if not allowed:
            raise SkyRuleError(str(reason))
        allocated.add(str(node_id))
        row = await repo.save_state(
            db, user_id=int(user_id), expected_revision=revision, allocated=allocated,
            active_sigil=sigil, eclipse_cycle_key=eclipse_key,
        )
        response = _view(row, completed_feats, cycle_no, cycle_key)
        await event_repo.record_event(
            db, user_id=int(user_id), event_name="sky_node_allocated",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
            payload={"policy_version": POLICY_VERSION, "node_id": str(node_id),
                     "branch": NODE_BY_ID[str(node_id)]["branch"],
                     "allocated_count": len(allocated), "path_slots": response["path_slots"]},
            idempotency_key=f"sky:{POLICY_VERSION}:{user_id}:{action_id}",
        )
        await repo.record_action(db, user_id=int(user_id), action_id=action_id,
                                 fingerprint=fingerprint, response=response)
        return response


async def select_sigil(db, *, user_id: int, node_id: str | None,
                       expected_revision: int, action_id: str, source: str) -> dict[str, Any]:
    action_id = _validate_action_id(action_id)
    normalized = str(node_id) if node_id else None
    fingerprint = _fingerprint("sigil", {"node_id": normalized, "expected_revision": int(expected_revision)})
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, int(user_id))
        completed_feats, cycle_no, cycle_key = await _locked_context(db, int(user_id), source)
        replay = await _replay(db, user_id=int(user_id), action_id=action_id, fingerprint=fingerprint)
        if replay:
            return _view(await repo.get_state(db, int(user_id)), completed_feats, cycle_no, cycle_key, replayed=True)
        allocated, _, revision, eclipse_key = repo.decode(await repo.get_state(db, int(user_id)))
        if revision != int(expected_revision):
            raise SkyConflict("revision_conflict")
        if normalized is not None and (normalized not in SIGIL_IDS or normalized not in allocated):
            raise SkyRuleError("sigil_not_unlocked")
        row = await repo.save_state(
            db, user_id=int(user_id), expected_revision=revision, allocated=allocated,
            active_sigil=normalized, eclipse_cycle_key=eclipse_key,
        )
        response = _view(row, completed_feats, cycle_no, cycle_key)
        await event_repo.record_event(
            db, user_id=int(user_id), event_name="sky_sigil_selected",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
            payload={"policy_version": POLICY_VERSION, "node_id": normalized},
            idempotency_key=f"sky:{POLICY_VERSION}:{user_id}:{action_id}",
        )
        await repo.record_action(db, user_id=int(user_id), action_id=action_id,
                                 fingerprint=fingerprint, response=response)
        return response


async def eclipse(db, *, user_id: int, expected_revision: int,
                  action_id: str, source: str) -> dict[str, Any]:
    action_id = _validate_action_id(action_id)
    fingerprint = _fingerprint("eclipse", {"expected_revision": int(expected_revision)})
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, int(user_id))
        completed_feats, cycle_no, cycle_key = await _locked_context(db, int(user_id), source)
        replay = await _replay(db, user_id=int(user_id), action_id=action_id, fingerprint=fingerprint)
        if replay:
            return _view(await repo.get_state(db, int(user_id)), completed_feats, cycle_no, cycle_key, replayed=True)
        allocated, _, revision, eclipse_key = repo.decode(await repo.get_state(db, int(user_id)))
        if revision != int(expected_revision):
            raise SkyConflict("revision_conflict")
        if not allocated:
            raise SkyRuleError("nothing_to_reset")
        if eclipse_key == cycle_key:
            raise SkyRuleError("eclipse_already_used")
        row = await repo.save_state(
            db, user_id=int(user_id), expected_revision=revision, allocated=set(),
            active_sigil=None, eclipse_cycle_key=cycle_key,
        )
        response = _view(row, completed_feats, cycle_no, cycle_key)
        await event_repo.record_event(
            db, user_id=int(user_id), event_name="sky_eclipse_used",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
            payload={"policy_version": POLICY_VERSION, "cycle_no": cycle_no},
            idempotency_key=f"sky:{POLICY_VERSION}:{user_id}:{action_id}",
        )
        await repo.record_action(db, user_id=int(user_id), action_id=action_id,
                                 fingerprint=fingerprint, response=response)
        return response
