"""Explicit post-match projection. Private night targets/checks are never public."""
from collections import Counter

from infrastructure.repositories import mafia_v1 as repo


def project(data: dict, *, page: int) -> dict:
    match = data["match"]
    ordered = sorted(data["players"], key=lambda p: int(p["join_order"]))
    refs = {int(p["user_id"]): f"p{i + 1}" for i, p in enumerate(ordered)}
    people = [{"ref": refs[int(p["user_id"])], "name": str(p["display_name"] or "Игрок")[:100],
               "role": p["role"], "survived": bool(p["alive"])} for p in ordered]
    timeline = []
    for event in data["events"]:
        raw = repo.load(event["payload_json"]) or {}
        phase, number = raw.get("previous_phase"), raw.get("previous_number")
        if phase not in {"night", "discussion", "voting"} or type(number) is not int or number < 1:
            continue
        eliminated = refs.get(raw.get("eliminated_user_id"))
        row = {"phase": phase, "number": number, "round": (number + 2) // 3,
               "eliminated": eliminated, "at": str(event["created_at"]), "votes": [], "ballots": []}
        if phase == "voting":
            votes = [a for a in data["ballots"] if int(a["phase_number"]) == number]
            totals = Counter(refs.get(a["target_user_id"]) for a in votes)
            row["votes"] = [{"target": target, "count": count} for target, count in sorted(totals.items(), key=lambda item: (-item[1], item[0] or ''))]
            if match["vote_mode"] == "open":
                row["ballots"] = [{"voter": refs.get(a["user_id"]), "target": refs.get(a["target_user_id"])} for a in votes]
            row["participated"] = len(votes)
        timeline.append(row)
    return {"match_id": int(match["id"]), "winner": match["winner"], "vote_mode": match["vote_mode"],
            "started_at": str(match["started_at"]), "finished_at": str(match["finished_at"]),
            "players": people, "timeline": timeline, "page": page, "has_more": data["has_more"],
            "history_available": bool(timeline),
            "disclosure": "Роли раскрываются после финала. Ночные цели, лечение и личные проверки не публикуются. В тайном голосовании показаны только суммы."}


async def review(db, *, user_id: int, match_id: int, page: int = 0) -> dict | None:
    if not 0 <= page <= 1000:
        return None
    data = await repo.review_data(db, user_id=user_id, match_id=match_id, page=page)
    return project(data, page=page) if data else None
