"""Автоаудит интерфейса в браузере: размеры текста и целей касания, контраст, переполнение, имена, вес загрузки.

Пункты стандарта с меткой [A] из docs/UI_REQUIREMENTS.md. Запускает tools/ui_check.py.
"""
from collections import Counter

MIN_FONT_PX = 13
MIN_TAP_PX = 44
GOOD_SHIFT = 0.1  # порог «хорошо» для сдвигов после действий пользователя (результат поиска меняет высоту списка)
DEFAULT_SIZES = ("320x568", "360x740", "390x844", "430x932", "768x1024", "844x390", "1280x800", "1920x1080")

# Скрипт читает видимое состояние страницы (или верхнего открытого листа) и возвращает найденные проблемы.
PROBE = r"""
() => {
  const out = {tap: [], font: [], contrast: [], overflow: [], names: [], clipped: [], ids: [], lang: document.documentElement.lang};
  const toRgb = value => { const m = value.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  // Наложение полупрозрачных слоёв (стекло поверх стекла): итог полупрозрачен, пока снизу не окажется сплошной фон.
  const over = (top, bottom) => { const a = top.a + bottom.a * (1 - top.a); if (!a) return {r: 0, g: 0, b: 0, a: 0}; const mix = key => (top[key] * top.a + bottom[key] * bottom.a * (1 - top.a)) / a; return {r: mix('r'), g: mix('g'), b: mix('b'), a}; };
  const luminance = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = luminance(a), l2 = luminance(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const gradientMean = image => { const colors = [...image.matchAll(/rgba?\([^)]+\)/g)].map(m => toRgb(m[0])).filter(Boolean); const weight = colors.reduce((sum, c) => sum + c.a, 0); if (!weight) return null; const mean = key => colors.reduce((sum, c) => sum + c[key] * c.a, 0) / weight; return {r: mean('r'), g: mean('g'), b: mean('b'), a: Math.max(...colors.map(c => c.a))}; };
  const backgroundOf = element => {
    const layers = [];
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      let color = toRgb(style.backgroundColor);
      if (style.backgroundImage && style.backgroundImage !== 'none') { const mean = gradientMean(style.backgroundImage); if (mean) color = color && color.a > 0 ? over(mean, color) : mean; }
      if (color && color.a > 0) layers.push(color);
      if (color && color.a >= 1) break;
    }
    return layers.reduceRight((base, layer) => over(layer, base), toRgb(getComputedStyle(document.body).backgroundColor));
  };
  const visible = element => {
    const box = element.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return false;
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      if (node.tagName === 'DIALOG' && !node.open) return false;
    }
    return true;
  };
  const dialog = [...document.querySelectorAll('dialog[open]')].pop();
  const hiddenDetails = element => { for (let d = element.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) if (!d.open && !(element.closest('summary')?.parentElement === d)) return true; return false; };
  const inScope = element => (!dialog || dialog.contains(element)) && !hiddenDetails(element);
  const label = element => (element.getAttribute('aria-label') || element.innerText || element.value || element.title || element.id || element.className || element.tagName).toString().trim().replace(/\s+/g, ' ').slice(0, 40);
  const selector = element => element.tagName.toLowerCase() + (element.id ? '#' + element.id : '') + (typeof element.className === 'string' && element.className ? '.' + element.className.trim().split(/\s+/).join('.') : '');

  for (const element of document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button]')) {
    if (!visible(element) || !inScope(element) || element.closest('.sr-only, .skip')) continue;
    let box = element.getBoundingClientRect();
    if (element.type === 'checkbox' || element.type === 'radio') { const wrapper = element.closest('label'); if (wrapper) box = wrapper.getBoundingClientRect(); }
    if (box.width < MIN_TAP - 0.5 || box.height < MIN_TAP - 0.5) out.tap.push({el: selector(element), text: label(element), w: Math.round(box.width), h: Math.round(box.height)});
    const name = (element.getAttribute('aria-label') || element.getAttribute('aria-labelledby') || element.title || (element.labels && element.labels.length && element.labels[0].innerText) || element.innerText || element.value || '').toString().trim();
    if (!name && element.tagName !== 'SUMMARY') out.names.push({el: selector(element)});
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const text = walker.currentNode.nodeValue.trim();
    const element = walker.currentNode.parentElement;
    if (!text || !element || seen.has(element) || !visible(element) || !inScope(element) || element.closest('.sr-only, .skip, script, style, option, svg')) continue;
    seen.add(element);
    const style = getComputedStyle(element), size = parseFloat(style.fontSize);
    out.font.push({size, text: text.slice(0, 30), el: selector(element)});
    const color = toRgb(style.color), background = backgroundOf(element);
    if (color) {
      const solid = color.a < 1 ? over(color, background) : color, value = ratio(solid, background);
      const large = size >= 24 || (size >= 18.66 && parseInt(style.fontWeight) >= 700);
      if (value < (large ? 3 : 4.5)) out.contrast.push({ratio: +value.toFixed(2), size, text: text.slice(0, 30), el: selector(element)});
    }
  }
  const width = document.documentElement.clientWidth;
  out.scrollW = document.documentElement.scrollWidth; out.clientW = width;
  for (const element of document.querySelectorAll('body *')) {
    if (!visible(element) || !inScope(element) || element.closest('.sr-only, .skip, svg, .chips')) continue;
    const box = element.getBoundingClientRect();
    if (box.right > width + 1 || box.left < -1) out.overflow.push({el: selector(element), left: Math.round(box.left), right: Math.round(box.right)});
    if (getComputedStyle(element).textOverflow === 'ellipsis' && element.scrollWidth > element.clientWidth + 1) out.clipped.push({el: selector(element), text: label(element)});
  }
  // Контейнер с overflow, чьё содержимое не помещается, молча обрезает его (так группа переключателей в листе теряла последнюю строку).
  for (const element of document.querySelectorAll('.group, .facts, .sheet-section, .card')) {
    if (!visible(element) || !inScope(element) || getComputedStyle(element).overflowY === 'visible') continue;
    if (element.scrollHeight > element.clientHeight + 1) out.clipped.push({el: selector(element), text: 'контейнер обрезает содержимое'});
  }
  const ids = [...document.querySelectorAll('[id]')].map(element => element.id);
  out.ids = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
  return out;
}
""".replace("MIN_TAP", str(MIN_TAP_PX))

PERFORMANCE = r"""
() => new Promise(resolve => {
  const resources = performance.getEntriesByType('resource').map(e => ({name: e.name.replace(location.origin, ''), size: e.transferSize}));
  let lcp = 0, shift = 0;
  try { new PerformanceObserver(list => list.getEntries().forEach(e => { lcp = e.startTime; })).observe({type: 'largest-contentful-paint', buffered: true}); } catch (e) {}
  try { new PerformanceObserver(list => list.getEntries().forEach(e => { if (!e.hadRecentInput) shift += e.value; })).observe({type: 'layout-shift', buffered: true}); } catch (e) {}
  setTimeout(() => resolve({resources, lcp: Math.round(lcp), shift: +shift.toFixed(3)}), 300);
})
"""


def visit_states(page, probe):
    """Обходит экраны и листы владельца дома; probe(метка) снимает состояние."""
    def close_sheets():
        page.evaluate("document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close())")
        page.wait_for_timeout(150)

    def tab(view):
        close_sheets()
        page.evaluate(f"document.querySelector('.tabbar .tab[data-view={view}], .topnav .tab[data-view={view}]').click()")
        page.wait_for_timeout(450)

    probe("home")
    page.click(".quick-item.is-primary")
    probe("form-expense")
    page.click(".seg-item >> nth=1")
    page.locator("input[type=date]").locator("xpath=preceding-sibling::div[1]//button").last.click()
    probe("form-expense-personal-date")
    close_sheets()
    page.click(".quick-item >> nth=1")
    probe("form-contribution")
    close_sheets()
    page.locator(".home-feed .row.entry").first.click()
    probe("entry-sheet")
    close_sheets()
    tab("history")
    probe("history")
    page.click(".chip-filter")
    probe("history-filters")
    close_sheets()
    page.click(".month-btn")
    probe("history-months")
    page.locator("dialog.sheet[open] .sheet-foot .btn").click()  # «За всё время»: видны и прошлые записи
    page.wait_for_timeout(700)
    page.click(".summary-line .link-btn")
    probe("history-totals")
    close_sheets()
    page.locator(".search-input").press_sequentially("стёкол", delay=20)  # настоящий ввод: сдвиг сразу после него не считается
    page.wait_for_timeout(700)
    page.wait_for_load_state("networkidle")  # под нагрузкой ответ поиска приходит позже: иначе строки исчезают между подсчётом и кликом
    if page.locator("#view-history .row.entry").count():  # возвращённая трата закрыта для правок: показана причина
        page.locator("#view-history .row.entry").first.click()
        probe("entry-locked")
        close_sheets()
    page.fill(".search-input", "")
    page.wait_for_timeout(600)
    page.locator("#view-history .chips[role=group] .chip").nth(2).click()  # «Взносы»
    page.wait_for_timeout(600)
    if page.locator("#view-history .row.entry").count():
        page.locator("#view-history .row.entry").first.click()
        probe("entry-contribution")
        page.locator(".entry-actions > .btn-secondary").first.click()  # «Изменить» (кнопки решения лежат в .button-row)
        probe("form-contribution-edit")
        close_sheets()
    page.locator("#view-history .chips[role=group] .chip").nth(0).click()
    page.locator("#view-history .head-actions .btn-secondary").first.click()
    probe("files-sheet")
    page.locator("dialog.sheet[open] .delivery .btn-primary").first.click()  # отправка в чат: карточка результата
    page.wait_for_selector("dialog.sheet[open] .sent-card", timeout=5000)
    probe("files-sent")
    close_sheets()
    tab("house")
    probe("house-hub")
    # Порядок строк на экране «Дом»: жильцы, график, деньги, файлы (лист), уведомления, настройки, управление домом.
    for name, index in (("people", 0), ("schedule", 1), ("money", 2), ("notifications", 4), ("settings", 5), ("manage", 6)):
        tab("house")
        page.locator("#view-house .group-row").nth(index).click()
        page.wait_for_timeout(700)
        probe(f"house-{name}")
        if name == "people" and page.locator("#view-house button.row").count():
            page.locator("#view-house button.row").first.click()
            probe("rights-sheet")
            close_sheets()
        if name == "money" and page.locator("#view-house .row .icon-btn").count():
            page.locator("#view-house .row .icon-btn").first.click()  # переименование категории
            probe("rename-category-sheet")
            close_sheets()
        if name == "manage":
            page.locator("#view-house .card-danger .btn-danger-soft").last.click()  # «Удалить дом…»
            probe("delete-house-sheet")
            close_sheets()


def audit(playwright, base, sizes=DEFAULT_SIZES, house=1, language=None, user=1001, theme="dark"):
    """Возвращает (нарушения, строки отчёта). Нарушение — кортеж (размер, состояние, вид, подробности)."""
    violations, report = [], []
    for size in sizes:
        width, height = map(int, size.split("x"))
        where = f"{size} {theme}"
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1,
                                      is_mobile=width < 700, has_touch=width < 700, locale="ru-RU")
        storage = f"localStorage.setItem('domovoy.house','{house}');" + (f"localStorage.setItem('domovoy.locale','{language}');" if language else "")
        context.add_init_script(f"try{{{storage}}}catch(e){{}}")
        page = context.new_page()
        console = []
        page.on("console", lambda message, log=console: log.append(message.text) if message.type in ("error", "warning") else None)
        page.on("pageerror", lambda error, log=console: log.append(str(error)))
        page.goto(f"{base}?u={user}&theme={theme}")
        page.wait_for_selector(".hero", timeout=10000)
        page.wait_for_timeout(400)
        loading = page.evaluate(PERFORMANCE)  # сдвиги самой загрузки: после неё экран не должен прыгать
        states = {}

        def probe(label, shots=states):
            page.wait_for_timeout(250)
            shots[label] = page.evaluate(PROBE)

        visit_states(page, probe)
        performance = page.evaluate(PERFORMANCE)
        found = 0
        for label, data in states.items():
            problems = {"tap": data["tap"], "font": [f for f in data["font"] if f["size"] < MIN_FONT_PX - 0.01], "contrast": data["contrast"],
                        "overflow": data["overflow"], "name": data["names"], "clipped": data["clipped"], "duplicate-id": data["ids"]}
            if data["scrollW"] > data["clientW"] + 1:
                problems["horizontal-scroll"] = [{"scrollWidth": data["scrollW"], "clientWidth": data["clientW"]}]
            for kind, items in problems.items():
                violations.extend((where, label, kind, item) for item in items)
                found += len(items)
        for message in console:
            violations.append((where, "page", "console", message))
        sizes_seen = Counter(round(f["size"], 1) for data in states.values() for f in data["font"])
        transferred = sum(r["size"] for r in performance["resources"] if r["size"])
        report.append(f"{size} {language or 'ru'} {theme} дом {house}: состояний {len(states)}, нарушений {found + len(console)}, запросов "
                      f"{len(performance['resources'])}, {transferred / 1024:.0f} КБ, LCP {performance['lcp']} мс, CLS загрузки {loading['shift']} "
                      f"(после действий {performance['shift']}), "
                      f"шрифты {dict(sorted(sizes_seen.items()))}")
        if loading["shift"] > 0:
            violations.append((where, "page", "layout-shift-on-load", loading["shift"]))
        if performance["shift"] > GOOD_SHIFT:
            violations.append((where, "page", "layout-shift", performance["shift"]))
        browser.close()
    return violations, report
