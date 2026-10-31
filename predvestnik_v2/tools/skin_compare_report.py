"""Turn the inspected S16 concepts and measured scene inventory into the audit document."""
import argparse
import collections
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDINGS = ROOT / "docs/roadmap/findings"
TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")
DECISIONS = {"keep": "оставить", "refine": "довести детали", "redraw": "перерисовать"}


def anchor(path, pattern):
    for number, line in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, line):
            return f"[{path}:{number}](../../../{path}#L{number})"
    raise ValueError(f"Source anchor not found: {path}: {pattern}")


def sources(sid):
    catalog = anchor("core/skins_v3_catalog.py", rf'_skin\("{sid}"')
    for part in (35, 36, 37, 38, 48, 53):
        path = f"FastAPI/static/app.{part}.js"
        try:
            scene = anchor(path, rf"_scAdd\(['\"]{sid}['\"]")
            return [catalog, scene]
        except ValueError:
            continue
    raise ValueError(f"No scene for {sid}")


def detail_sources(sid, particle):
    particle_css = "skins-exclusive-v3.css" if particle in ("star", "drop") else "appearance-stage-v3.css"
    refs = [anchor(f"FastAPI/static/{particle_css}", rf"\.ap-pt-{re.escape(particle)}\b"),
            anchor("bot/chat/skin_card_draw.py", r"^def _particle")]
    specific = {
        "sakura_bud": [("tools/scene_art_a.py", r"^def bud\(")],
        "hanami": [("tools/scene_art_b.py", r"^def blossoms"), ("FastAPI/static/app.36.js", r"dot rise.*l: '14%'.*dy: '280px'")],
        "sakura_storm": [("tools/scene_art_c.py", r"^PETAL"), ("tools/scene_art_c.py", r"^def petal_vortex")],
        "void": [("tools/scene_art_c.py", r"^def void_spiral"), ("FastAPI/static/skin-signatures-v3.css", r"sg-shadow")],
        "midnight_comet": [("tools/scene_art_c.py", r"^def great_comet")],
        "phantom_carriage": [("tools/scene_art_g.py", r"^def _wheel")],
        "polar_express": [("tools/scene_art_g.py", r"^def _track")],
    }
    refs.extend(anchor(path, pattern) for path, pattern in specific.get(sid, []))
    return refs


def luminance(value):
    color = value.lstrip("#")
    channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    lo, hi = sorted((luminance(a), luminance(b)))
    return round((hi + .05) / (lo + .05), 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=FINDINGS / "D2-cosmetics-audit.md")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8").removeprefix("const COMPARE=").removesuffix(";"))
    plan = json.loads((FINDINGS / "D2-cosmetics-plan.json").read_text(encoding="utf-8"))
    skins = manifest["skins"]
    if set(plan) != set(skins) or len(skins) != 42:
        raise ValueError("Audit must cover all 42 catalog ids")
    for item in plan.values():
        if len(item["tiers"]) != 7 or any(not text.strip() for text in item["tiers"]):
            raise ValueError("Every concept needs all seven tier decisions")
    counts = collections.Counter(item["decision"] for item in plan.values())
    art = {}
    for letter in "abcdefg":
        path = ROOT / f"FastAPI/static/skin-scene-{letter}-v3.css"
        text = path.read_text(encoding="utf-8")
        for name, rule in re.findall(r"\.i-([\w-]+)\s*(\{[^}]+\})", text):
            art[name] = (letter, len(rule.encode("utf-8")))
    lines = ["# D2 · Все 42 образа: проверка и предложения S16", "",
             f"Базовая линия «до»: `{manifest['before']['revision']}`. «После»: `{manifest['after']['revision']}`.",
             "Это текущие одинаковые образы, **не нарисованные улучшения**. Ни id, ни тиры, ни цены, ни владение не менялись.",
             f"Предложено: **{counts['keep']} оставить, {counts['refine']} довести детали, {counts['redraw']} перерисовать**.", "",
             "## Как проверено", "",
             f"Снято {len(manifest['coverage'])} пар: 42×7×4 поверхности в полном режиме; ещё профильная сцена в mid/low/reduced/calm и редком кадре.",
             "Сравнение — по исходным RGB до WebP, без порога и маскирования. Один Chromium, 390 px, масштаб 1, CPU raster/sRGB;",
             "зерно имеет одинаковый seed, CSS стоит в одинаковой фазе, canvas заморожен. Одинаковые источники обязаны давать ровно 0%.",
             "Шрифты — локальный Onest 400/500/700; вес 300 заменён 400. Это ограничение стенда, не смена шрифта продукта.",
             "Профиль — **его сцена с настоящим renderProfileHome**, без остальной страницы; топ — настоящая строка, ник — общий renderer.",
             "Карточка Telegram — настоящий skin_card.compose с activity_graph.render и фиксированными данными. Статичная матрица не оценивает видео SSS и реальную скорость телефона.",
             "Устройства задают CSS-режим, а не измеренную скорость реального телефона. reduced-motion снят без no-fx; calm — отдельно без reduced-motion. Производительность проверяется при реализации S17–S20.",
             "Код и файлы шрифтов каждой ревизии закреплены хешами в manifest.js. Движение можно включить отдельно, его кадр не выдаётся за pixel diff.", "",
             "## Критерии и сводка", "",
             "Оценка 1–5 — насколько рисунок передаёт обещанный сюжет; это дизайнерская оценка по кадрам и исходникам, не автоматическая метрика.",
             "D и C оцениваются отдельно по кадрам: передача сюжета, а не яркость; в плане сохранены отдельные оценки и отличие от соседей по набору.",
             "Фильтр стенда использует общую оценку концепта: у Бездны она 2 из-за D–A, хотя на SSS рисунок оценивается в 5. Это не среднее арифметическое тиров.",
             "Контраст в таблице — ink/dim на базовом bg из токенов. Он не доказывает контраст градиентных букв поверх рисунка: это отдельная визуальная проверка.",
             "Вес — уникальные SVG-правила сцены и gzip целиком запрашиваемых буквенных CSS. Общие стили и шрифты в этот вес не включены.", "",
             "| Образ | Оценки D / C / SSS | Решение | Слои / арты | SVG КБ / загрузка gzip КБ | Контраст ink / dim | Сессия |",
             "|---|---|---|---|---|---|---|"]
    metrics = {}
    for sid, skin in skins.items():
        layers = manifest["scenes"][sid]
        names = {name for layer in layers for name in re.findall(r"\bi-([\w-]+)", layer[1])}
        missing = names - set(art)
        if missing:
            raise ValueError(f"Unknown scene pictures: {sid}: {missing}")
        letters = {art[name][0] for name in names}
        unique = sum(art[name][1] for name in names) / 1024
        transfer = sum(len(gzip.compress((ROOT / f"FastAPI/static/skin-scene-{letter}-v3.css").read_text(encoding="utf-8").encode(), mtime=0)) for letter in letters) / 1024
        ink = contrast(skin["tokens"]["--v3-ink"], skin["tokens"]["--v3-bg"])
        dim = contrast(skin["tokens"]["--v3-dim"], skin["tokens"]["--v3-bg"])
        item = plan[sid]
        early = f"{item['early_scores']['D']} / {item['early_scores']['C']}"
        sss = 5 if sid == "void" else item["score"]
        metrics[sid] = (layers, names, letters, unique, transfer, ink, dim)
        lines.append(f"| {skin['name']} (`{sid}`) | {early} / {sss} | {DECISIONS[item['decision']]} | {len(layers)} / {len(names)} | {unique:.1f} / {transfer:.1f} | {ink} / {dim} | {item['session']} |")
    lines += ["", "## Общие примитивы: сделать один раз", "",
              "| Примитив | Единый контур | Где применяется | Ограничение |", "|---|---|---|---|",
              "| Лепесток / пятилистник / бутон | Выемка, дуга оси, пять лепестков и тычинки; закрытый бутон отдельной формой | scene_kit, scene_art_b/c/g, appearance-stage petal, skin_card_draw._particle | Сакура не смешивается с острым лотосом; не менять sig_from |",
              "| Лист / лист лотоса | Центральная жилка или радиальный разрез | forest, lotus_pond, CSS leaf, Telegram leaf | Два размера, прежнее число частиц |",
              "| Снежинка | Шесть лучей с ответвлениями | frost, snow_globe, зимние сцены, Telegram snow | На малом размере оставить первый порядок веток |",
              "| Пламя / протуберанец | Открытый язык и возвращающаяся петля — разные формы | inferno, solar, pumpkin, witch, CSS/Pillow | Не добавлять свечение поверх текста |",
              "| Звезда / искра / стружка | Вогнутые лучи, узкий световой разлом, короткая металлическая стружка | spark/glint/star/ember и карточки | Не выдавать одну восьмиконечную фигуру за все материалы |",
              "| Волна / пена / капля | Дуга гребня, разрыв пены, капля с бликом | harbor, ryujin, lotus, alchemist, Telegram ring/drop | Статичный малый вариант для топа |",
              "| Перо | Стержень и разрывы бородок | raven_masquerade, CSS-маска, Telegram | Перо остаётся узнаваемым при 12 px |",
              "| Грань / стеклянное сердце | Три крупных плана, один тёмный | glass_heart, ruby, Telegram | Не шум из множества микротреугольников |",
              "| Спираль / дым / туман | Сужающиеся кривые вместо крупных полигональных лент | void, phantom, scene_art_c/g | Не clip-path polygon на движущемся предке |",
              "| Бант / тяжёлая капля | Сохранить нынешние персональные силуэты | scarlet_star / crimson_dark | Эталон ранней различимости; не размножать по другим образам |", "",
              "Точки сверки: " + anchor("tools/scene_kit.py", r"^def poly") + "; " +
              anchor("tools/scene_art_b.py", r"^def blossoms") + "; " +
              anchor("tools/scene_art_c.py", r"^PETAL") + "; " +
              anchor("FastAPI/static/appearance-stage-v3.css", r"\.ap-pt") + "; " +
              anchor("bot/chat/skin_card_draw.py", r"^def _particle") + ".", "",
              "В S17 единый источник контура должен порождать SVG/маску и Pillow-версию; supersampling 3–4× только внутри декора, потом уменьшение.",
              "Не менять рамку, размеры текста, порядок информации, пороги открытия деталей, число слоёв или частиц ради украшения.", "",
              "## Карточки предложений"]
    for sid, skin in skins.items():
        item = plan[sid]
        layers, names, letters, unique, transfer, ink, dim = metrics[sid]
        peers = [other["name"] for oid, other in skins.items() if oid != sid and other["kinds"]["pt"] == skin["kinds"]["pt"]]
        lines += ["", f"### {skin['name']} · `{sid}`", "",
                  f"**{DECISIONS[item['decision']].capitalize()} · {item['session']}.** Название обещает: «{skin['blurb']}».", "",
                  "**Где проверено:** " + "; ".join(sources(sid)) + ".",
                  "**Формы, которые сверять:** " + "; ".join(detail_sources(sid, skin['kinds']['pt'])) + ".",
                  f"Общие виды: `{skin['kinds']}`. Такая же частица встречается у: {', '.join(peers[:5]) or 'других образов не найдена'}.",
                  f"В сцене {len(layers)} слоёв, {len(names)} разных картинок; {unique:.1f} КБ уникальных правил, {transfer:.1f} КБ gzip загружаемых групп {','.join(sorted(letters))}.", "",
                  f"**Узнаваемость D / C:** {item['early_scores']['D']} / {item['early_scores']['C']} из 5. {item['identity']}", "",
                  f"**Что сейчас:** {item['issue']}", f"**Предложение:** {item['proposal']}", "",
                  "| Тир | Предлагаемая правка |", "|---|---|"]
        lines += [f"| {tier} | {change} |" for tier, change in zip(TIERS, item["tiers"])]
        lines += ["", "**Все поверхности:** " + item["surfaces"], "",
                  "**Гейт:** заменить форму/силуэт в прежнем слое; не расширять композицию. Mid — без новых w2; low/reduced — статичный узнаваемый силуэт."]
    lines += ["", "## Порядок S17–S20 и бюджеты", "",
              "S17 — общая библиотека + ранние мотивы у forest, dune, lotus_pond, frost, copper, inferno (6 образов). Общие формы проверяются на всех 42.",
              "S18 — sakura_bud, hanami, sakura_storm и void (4). Деталь sig остаётся на прежнем тире; ранний намёк — часть фона, не перенос привилегии.",
              "S19 — threshold, midnight_comet, raven_masquerade, phantom_carriage, gingerbread_house, polar_express, rose_letter, glass_heart (8).",
              "S20 — оставшиеся 24: 15 лёгких доводок и 9 без перерисовки; затем согласованность ника/аватара/топа/Telegram и токенов интерфейса.", "",
              "Бюджеты реализации: ≤24 слоёв, ≤15 движущихся без w2, без новых бесконечных анимаций вне образов; прирост SVG ≤10% на образ,",
              "мобильные BUDGET anims≤95/passes≤14/area≤24/bmf≤24; Telegram ≤0,9 с на картинку, видео ≤3 с. В этой сессии скорость реального телефона/видео не измерялась.",
              "Отдельная контрольная точка после каждого общего примитива: 42×D/C/SSS, high/mid/low/reduced, все поверхности и прежние тесты. Все цены/id/пороги неизменны.", "",
              "## Что должен согласовать владелец", "",
              "Отметить у каждого образа: оставить / довести детали / перерисовать, либо прислать исключения. Принятие этого плана не означает принятия будущей картинки:",
              "S17–S20 всё равно показывают настоящее «после» до выпуска. Нынешний стенд намеренно показывает 0% — улучшений в production-коде ещё нет.", ""]
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Audit: {len(skins)} concepts, {len(plan) * 7} tier decisions -> {args.out}")


if __name__ == "__main__":
    main()
