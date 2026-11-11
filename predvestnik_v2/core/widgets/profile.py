"""Что Telegram молча вырезает из виджета (профиль 1, https://core.telegram.org/bots/widgets.md#what-widgets-support).

Вырезанное не даёт ошибки: виджет просто работает не так, как задумано, и этого не видно до запуска в Telegram.
Поэтому каждый шаблон проверяется этими правилами в tools/test_telegram_widgets_contract.py.

Сверх профиля — два наших правила: без `opacity` меньше единицы и без фильтров/размытых теней (такие элементы
Telegram считает «тяжёлыми»: больше 16 сразу — и виджет останавливается), приглушать цветом; без кошелька TON
(платежи в виджетах — решение владельца).
"""
from __future__ import annotations

import re

_I = re.I

HTML_RULES = (   # по разметке без тел <script>/<style> и по строкам внутри JS
    ("форма или поле ввода", r"<(?:input|select|option|optgroup|textarea|label|fieldset|legend|datalist|output|form)\b", _I),
    ("медиа, вставки, служебные теги", r"<(?:progress|meter|dialog|audio|video|source|track|iframe|frame|object|embed|link|meta|base|portal|template|slot|math|fencedframe)\b", _I),
    ("ruby и устаревшие теги", r"<(?:ruby|rt|rp|bdi|bdo|center|font|big|tt|strike|nobr|marquee|blink)\b", _I),
    ("вырезаемый тег SVG", r"<(?:clipPath|mask|pattern|marker|foreignObject|animate|animateTransform|animateMotion|set|image|fe[A-Z][A-Za-z]*)\b", 0),
    ("внешний скрипт", r"<script\b[^>]*\bsrc\s*=", _I),
    ("скрипт-модуль", r"<script\b[^>]*\btype\s*=\s*[\"']?module", _I),
    ("картинка не data:", r"<img\b[^>]*\bsrc\s*=(?!\s*[\"']?data:image/(?:png|jpeg|gif|webp)[;,])", _I),
    ("вырезаемый атрибут", r"<[a-z][^>]*\s(?:contenteditable|draggable|tabindex|autofocus|accesskey|spellcheck|inputmode|enterkeyhint|autocapitalize|popover|popovertarget|align|valign|bgcolor|cellpadding|cellspacing|face|nowrap|background)(?=[\s=>/])", _I),
    ("устаревший border/color", r"<(?:table|td|th|tr|img|font|hr|div|p|span)\b[^>]*\s(?:border|color)\s*=", _I),
    ("ссылка не https", r"<a\b[^>]*\bhref\s*=(?!\s*[\"']?(?:https://|#))", _I),
    ("url() в атрибуте SVG", r"\s(?:clip-path|mask|filter|marker-(?:start|mid|end))\s*=\s*[\"']?url\(", _I),
)
CSS_RULES = (   # по <style>, style="…" и строкам внутри JS
    ("единицы от высоты (vh…)", r"(?<![\w#-])\d*\.?\d+(?:vh|dvh|svh|lvh|vb|vi|dvb|svb|lvb|cqh|cqw|cqi|cqb|cqmin|cqmax)\b", 0),
    ("прокрутка внутри виджета", r"\boverflow(?:-[xy]|-inline|-block)?\s*:\s*(?:auto|scroll|overlay)\b", _I),
    ("position: sticky", r"\bposition\s*:\s*(?:-webkit-)?sticky\b", _I),
    ("вырезаемый display", r"\bdisplay\s*:\s*(?:contents|flow-root|list-item|-webkit-box|-webkit-inline-box|ruby)\b", _I),
    ("логические свойства", r"(?<![\w-])(?:(?:margin|padding|border|inset|scroll-margin|scroll-padding)-(?:inline|block)(?:-start|-end)?(?:-width|-color|-style)?|(?:min-|max-)?(?:inline|block)-size|border-(?:start|end)-(?:start|end)-radius)\s*:", _I),
    ("колонки", r"(?<![\w-])(?:columns|column-count|column-width|column-rule(?:-\w+)?|column-span|column-fill|column-gap)\s*:", _I),
    ("3D-преобразования", r"\b(?:rotate[XYZ]|rotate3d|translateZ|translate3d|scaleZ|scale3d|matrix3d|perspective)\s*\(|(?<![\w-])(?:perspective(?:-origin)?|transform-style|backface-visibility)\s*:", 0),
    ("фильтр (тяжёлый элемент)", r"(?<![\w-])(?:-webkit-)?(?:backdrop-)?filter\s*:", _I),
    ("размытая тень (тяжёлый элемент)", r"box-shadow\s*:[^;}\"]*?-?\d+(?:px)?\s+-?\d+(?:px)?\s+[1-9]", _I),
    ("opacity меньше 1 (тяжёлый элемент)", r"(?<![\w-])opacity\s*:\s*(?:0?\.\d+|0)(?![\d.])", _I),
    ("обрезка, маска, наложение", r"(?<![\w-])(?:clip-path|-webkit-clip-path|mask(?:-image|-size|-position|-repeat|-mode|-composite|-border)?|-webkit-mask(?:-[\w-]+)?|mix-blend-mode|background-blend-mode|isolation)\s*:", _I),
    ("вырезаемое оформление текста", r"(?<![\w-])(?:text-shadow|-webkit-line-clamp|line-clamp|writing-mode|text-orientation|-webkit-text-stroke|-webkit-text-fill-color)\s*:", _I),
    ("градиентный текст", r"(?<![\w-])(?:-webkit-)?background-clip\s*:\s*text\b", _I),
    ("вырезаемая функция цвета", r"(?<![\w-])(?:oklch|oklab|lab|lch|hwb|color|color-mix|device-cmyk|contrast-color)\s*\(", _I),
    ("env() кроме safe-area", r"\benv\((?!\s*safe-area-inset-(?:top|right|bottom|left)\b)", _I),
    ("url() не data:", r"\b(?:url|image-set|-webkit-image-set)\((?!\s*[\"']?(?:data:image/(?:png|jpeg|gif|webp)[;,]|#))", _I),
    ("вырезаемое @-правило", r"@(?:import|font-face|container|layer|property|namespace|counter-style|starting-style|scope|page|font-feature-values|font-palette-values|position-try|view-transition|document)\b", _I),
    ("вырезаемое условие @media", r"@media[^{]*\b(?:hover|any-hover|pointer|any-pointer|resolution|print|height|min-height|max-height|display-mode|prefers-contrast|forced-colors|color-gamut|dynamic-range)\b", _I),
    ("вырезаемый селектор", r":(?:has|host|host-context|focus|focus-visible|focus-within|checked|indeterminate|valid|invalid|required|optional|placeholder-shown|target|scope|default|autofill|read-only|read-write|user-invalid|in-range|out-of-range|modal|popover-open|fullscreen|disabled|enabled)\b|::(?:first-letter|first-line|marker|placeholder|slotted|part|selection|backdrop|file-selector-button|cue|highlight|target-text)\b", 0),
    ("вложенный CSS (&)", r"(?:^|[{;\s])&(?=[\s.:#\[>+~&])", 0),
    ("шрифт по имени", r"(?<![\w-])font-family\s*:\s*[^;}\"]*?(?<![\w-])(?!(?:system-ui|sans-serif|serif|monospace|ui-sans-serif|ui-serif|ui-monospace|ui-rounded|-apple-system|inherit|initial|unset|var)\b)[A-Za-z'\"][\w' -]*", _I),
    ("touch-action кроме auto/pan-y/none", r"(?<![\w-])touch-action\s*:(?!\s*(?:auto|pan-y|none)\s*(?:[;}\"!]|$))", _I),
    ("user-select кроме none/text/auto", r"(?<![\w-])(?:-webkit-)?user-select\s*:(?!\s*(?:none|text|auto)\s*(?:[;}\"!]|$))", _I),
)
JS_RULES = (   # по <script> и обработчикам on*="…"
    ("сеть (её в виджете нет)", r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|RTCPeerConnection|sendBeacon|importScripts|BroadcastChannel|SharedWorker|Worker|serviceWorker)\b", 0),
    ("динамический import", r"(?<![\w.$])import\s*\(", 0),
    ("переход по адресу", r"(?<![\w$])(?:(?:window|document|self|top)\.)?location\s*(?:[.=\[])|(?<![\w$.])history\s*\.", 0),
    ("window.open (нужен openLink)", r"\bwindow\.open\s*\(", 0),
    ("alert/confirm/prompt/print", r"(?<![\w$.])(?:window\.)?(?:alert|confirm|prompt|print)\s*\(", 0),
    ("API устройства", r"\bnavigator\.(?:clipboard|share|canShare|vibrate|geolocation|mediaDevices|permissions|wakeLock)\b|\bNotification\b|\bgetUserMedia\b", 0),
    ("компоненты, файлы, полный экран", r"\battachShadow\b|\bcustomElements\b|\bBlob\b|\bFileReader\b|\bcreateObjectURL\b|\brequestFullscreen\b", 0),
    ("фокус", r"\.(?:focus|blur|select)\s*\(\s*\)|\bactiveElement\b", 0),
    ("вырезаемое в canvas", r"\b(?:getImageData|putImageData|createImageData|toDataURL|toBlob|captureStream|createPattern|createConicGradient|globalCompositeOperation|shadowBlur|shadowColor|shadowOffset[XY]|OffscreenCanvas|transferControlToOffscreen)\b|\.filter\s*=(?!=)|getContext\(\s*[\"'](?:webgl2?|experimental-webgl|bitmaprenderer|webgpu)", 0),
    ("события, которых нет (касания, клавиши, прокрутка)", r"[\"'](?:touchstart|touchmove|touchend|touchcancel|keydown|keyup|keypress|beforeinput|input|wheel|mousewheel|scroll|scrollend|focus|blur|focusin|focusout|paste|copy|cut|drag\w*|drop)[\"']|\bon(?:touch\w+|key\w+|wheel|scroll|focus|blur|input|beforeinput|paste|copy|drag\w*|drop)\s*=", 0),
    ("чужое API Telegram", r"\bTelegramWidget\.sendMessage\b|\bTelegram\.WebApp\b|\bwindow\.Telegram\b", 0),
    ("кошелёк TON (решение владельца)", r"\bwallet\b|\bsendTransaction\b|\bsignData\b", 0),
)


def _compiled(rules):
    return tuple((name, re.compile(pattern, flags | re.M)) for name, pattern, flags in rules)


_HTML, _CSS, _JS = _compiled(HTML_RULES), _compiled(CSS_RULES), _compiled(JS_RULES)
_STRING = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`[^`]*`")


def _split(source: str) -> tuple[str, str, str, list[str]]:
    styles = re.findall(r"<style\b[^>]*>(.*?)</style>", source, re.S | re.I)
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", source, re.S | re.I)
    bare = re.sub(r"(<(script|style)\b[^>]*>).*?(</\2>)", r"\1\3", source, flags=re.S | re.I)
    inline_css = re.findall(r"\sstyle\s*=\s*(\"[^\"]*\"|'[^']*')", bare, re.I)
    inline_js = re.findall(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", bare, re.I)
    strings = [s for code in scripts + inline_js for s in _STRING.findall(code)]
    return bare, "\n".join(styles + inline_css + strings), "\n".join(scripts + inline_js), strings


def problems(source: str) -> list[str]:
    """Нарушения профиля: «правило: найденный кусок». Пусто — Telegram покажет виджет целиком."""
    bare, css, js, strings = _split(source)
    found = []
    for name, rule in _HTML:
        for text in (bare, *strings):
            found += [f"{name}: {m.group(0)[:50]}" for m in rule.finditer(text)]
    for name, rule in _CSS:
        found += [f"{name}: {m.group(0)[:50]}" for m in rule.finditer(css)]
    for name, rule in _JS:
        found += [f"{name}: {m.group(0)[:50]}" for m in rule.finditer(js)]
    return found
