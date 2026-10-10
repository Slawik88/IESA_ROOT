#!/usr/bin/env python3
"""Система риска экспедиций (pets v2): шанс исхода и выгодность путей.
gap = Выдержка питомца − Сложность события. Запуск: python3 tools/pets_v2_decision_sim.py"""
PATHS = {  # (сдвиг gap, награда успех/частично/провал, потеря энергии при провале)
    "careful": (+8, (0.8, 0.6, 0.4)),
    "steady": (0, (1.1, 0.7, 0.25)),
    "bold": (-8, (1.8, 0.7, 0.0)),
}
PARTIAL_BAND = 25


def chance(gap: float, path: str) -> float:
    return max(5.0, min(95.0, 50 + 3.5 * (gap + PATHS[path][0])))


def outcome_probs(p: float) -> tuple[float, float, float]:
    partial = min(PARTIAL_BAND, 100 - p)
    return p / 100, partial / 100, (100 - p - partial) / 100


def expected(gap: float, path: str) -> float:
    ps, pp, pf = outcome_probs(chance(gap, path))
    ok, part, fail = PATHS[path][1]
    return ps * ok + pp * part + pf * fail


def band(p: float) -> str:
    return ("Надёжно" if p >= 85 else "Скорее удастся" if p >= 65 else
            "Как повезёт" if p >= 40 else "Рискованно" if p >= 20 else "Отчаянно")


if __name__ == "__main__":
    print("gap | осторожно: шанс/ожид. | ровно | рискованно | лучший")
    for gap in range(-12, 17, 2):
        row, best = [], max(PATHS, key=lambda x: expected(gap, x))
        for path in PATHS:
            p = chance(gap, path)
            row.append(f"{p:>3.0f}% {band(p):<14} {expected(gap, path):.2f}")
        print(f"{gap:>3} | " + " | ".join(row) + f" | {best}")
