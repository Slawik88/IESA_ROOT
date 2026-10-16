"""Negative and boundary proofs for the owner-selected mechanics wave."""
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import pets_v2 as pets, rhythm_analysis, rhythm_v2 as rhythm, official_updates
from services import rhythm_v2 as rhythm_service
from services.mafia_review import project


def main():
    fx = pets.build_effects(None, ())
    args = dict(kind="trek", hours=3, route="forest", before_raw=490, repeats=0,
                favorite=False, stars=0, effects=fx)
    q = pets.departure_forecast(**args, paired=True)
    assert q["min"] == q["max"]
    total = pets.pool_credit(490, pets.RUN_XP[3] * (1 + pets.PAIR_COMPANION_SHARE))
    assert abs(q["min"]["pool_total"] - total) < .01
    assert abs(q["min"]["credited"] + q["min"]["companion"] - total) < .02
    assert pets.departure_forecast(**{**args, "before_raw":1000})["max"]["credited"] == 0
    repeat = pets.departure_forecast(**{**args, "repeats":2})
    assert repeat["base_raw"] == round(pets.RUN_XP[3] * pets.REPEAT_DECAY ** 2, 2)
    expedition = pets.departure_forecast(**{**args, "kind":"expedition"})
    assert set(expedition["paths"]) == set(pets.PATHS)
    assert expedition["min"]["credited"] <= expedition["max"]["credited"]
    assert expedition["excludes_random_finds"] and "chance" not in json.dumps(expedition)
    try:
        pets.departure_forecast(**{**args,"kind":"watch","hours":12,"route":None}, paired=True)
        raise AssertionError("paired watch allowed")
    except pets.PetV2PolicyError:
        pass
    stats = rhythm_analysis.fresh()
    for signal in range(1, 1700):
        rhythm_analysis.record(stats, signal=signal, chunk_size=20, window=1000, correct=True, elapsed=700, streak=signal)
    rhythm_analysis.record(stats, signal=1700, chunk_size=20, window=1000, correct=False, timeout=True, hearts_lost=1)
    analysis = rhythm_analysis.summary(stats, correct=1699, mistakes=1)
    assert len(analysis["chunks"]) == rhythm_analysis.MAX_CHUNKS + 1
    assert analysis["best_streak"] == 1699 and analysis["timeouts"] == 1 and analysis["response_ms"] == 700
    assert not rhythm_analysis.summary(None, correct=5, mistakes=5)["complete"]
    state = {"health":6,"perks":rhythm.normalize_perks(None),"next_signal_no":21,"combo":3}
    before = copy.deepcopy(state)
    preview = rhythm_service._perk_preview("iron_heart", state)
    assert preview["after"]["health"] == rhythm.MAX_HEALTH and preview["after"]["health"]-preview["before"]["health"] == 1
    assert state == before and "rune" not in json.dumps(preview) and "seed" not in json.dumps(preview)
    data = {"match":{"id":1,"winner":"town","vote_mode":"secret","started_at":None,"finished_at":None},
            "players":[{"user_id":9234567,"join_order":1,"display_name":"<Alice>","role":"detective","alive":True},
                       {"user_id":9234568,"join_order":2,"display_name":"Bob","role":"mafia","alive":False}],
            "events":[{"payload_json":{"previous_phase":"voting","previous_number":3,"eliminated_user_id":9234568,
                                         "private_checks":[{"user_id":9234567,"is_mafia":True}]},"created_at":"now"}],
            "ballots":[{"phase_number":3,"user_id":9234567,"target_user_id":9234568}],"has_more":False}
    review = project(data,page=0)
    assert review["timeline"][0]["votes"] == [{"target":"p2","count":1}]
    assert not review["timeline"][0]["ballots"]
    assert all(word not in json.dumps(review) for word in ("private_checks","9234567","9234568","is_mafia"))
    data["match"]["vote_mode"]="open"
    assert project(data,page=0)["timeline"][0]["ballots"] == [{"voter":"p1","target":"p2"}]
    assert official_updates.BOT_USERNAME == "IIIPredvestnikIIIBot" and official_updates.THREAD_ID == 4
    print("OK: forecast cap/pair/risk, bounded timing, exact gift, private Mafia projection and official identity")


if __name__ == "__main__":
    main()
