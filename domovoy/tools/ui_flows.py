"""Сквозные сценарии сайта в настоящем браузере на демо-данных (tools/demo_server.py). Запускает tools/ui_check.py.

Сценарии идут по порядку на одной базе: расходы → уборка и возврат → история → «Дом» → файлы; затем независимые проверки
языка, жильца без прав, интеграции с Telegram и устойчивости (нет сети, истёкший вход).
"""
import os
import traceback
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

MASS_ENTRIES = 25
PAGE_SIZE = 20


class Report:
    def __init__(self):
        self.results = []

    def check(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)

    def guard(self, name, scenario, *arguments):
        try:
            scenario(*arguments)
        except Exception as error:  # один упавший сценарий не должен скрывать остальные
            self.check(name, False, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}")
            traceback.print_exc(limit=2)

    @property
    def failed(self):
        return [result for result in self.results if not result[1]]


def open_app(playwright, base, user=1001, size=(390, 844), language=None):
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1, is_mobile=size[0] < 700,
                                  has_touch=size[0] < 700, locale="ru-RU", accept_downloads=True)
    if language:
        context.add_init_script(f"try{{localStorage.setItem('domovoy.locale','{language}')}}catch(e){{}}")
    page = context.new_page()
    page.errors = []
    page.on("console", lambda message: page.errors.append(message.text) if message.type == "error" and "status of 422" not in message.text else None)
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.goto(f"{base}?u={user}")
    page.wait_for_selector(".hero, .welcome, .gate", timeout=10000)
    page.wait_for_timeout(400)
    return browser, context, page


def sheet(page):
    return page.locator("dialog.sheet[open]").last


def toast(page):
    page.wait_for_selector(".toast", timeout=4000)
    return page.locator(".toast").last.inner_text()


def hero(page):
    return page.locator(".hero-amount").inner_text().replace(" ", " ")


def go(page, view):
    page.evaluate(f"document.querySelector('.tabbar .tab[data-view={view}], .topnav .tab[data-view={view}]').click()")
    page.wait_for_timeout(350)


def sheets_closed(page):
    page.locator("dialog.sheet[open]").wait_for(state="detached", timeout=4000)
    page.wait_for_timeout(250)


def back_to_hub(page):
    page.click("#view-house .icon-btn")
    page.wait_for_timeout(300)


def api(page, method, path, body=None):
    return page.evaluate("""async ([method, path, body]) => {
        const response = await fetch('./api/' + path, {method, headers: {Authorization: 'tma ' + window.Telegram.WebApp.initData,
          'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
        return {status: response.status, data: await response.json().catch(() => null)};
    }""", [method, path, body])


# ── Деньги ────────────────────────────────────────────────────────────────────────────────────────

def money(page, report):
    check = report.check
    before = hero(page)
    page.click(".quick-item.is-primary")
    sheet(page).wait_for(state="visible")
    check("форма: сумма в фокусе", page.evaluate("document.activeElement?.classList.contains('amount-input')"))
    page.fill(".amount-input", "12,50")
    page.locator(".tx-fields .chip", has_text="Продукты").last.click()
    page.fill(".tx-fields textarea", "Тест: хлеб")
    sheet(page).locator(".btn-primary").click()
    sheets_closed(page)
    check("расход: уведомление после записи", "Запись сохранена" in toast(page))
    first = page.locator(".home-feed .row.entry").first.inner_text()
    check("расход: первым в ленте, со знаком минус", "Тест: хлеб" in first and "−12,50" in first, first.replace("\n", " | "))
    check("расход: остаток уменьшился", hero(page) != before, f"{before} -> {hero(page)}")

    page.locator(".home-feed .row.entry").first.click()
    sheet(page).get_by_role("button", name="Изменить", exact=True).click()
    page.fill(".amount-input", "20")
    sheet(page).locator(".btn-primary").click()
    sheets_closed(page)
    check("правка: сумма изменилась в ленте", "−20,00" in page.locator(".home-feed .row.entry").first.inner_text())

    page.locator(".home-feed .row.entry").first.click()
    sheet(page).get_by_role("button", name="Повторить", exact=True).click()
    check("повтор: форма заполнена", page.input_value(".amount-input") == "20.00", page.input_value(".amount-input"))
    page.keyboard.press("Escape")
    sheets_closed(page)
    check("повтор: закрытие без правок не оставляет черновик", page.locator(".card-draft").count() == 0)

    page.locator(".home-feed .row.entry").first.click()
    sheet(page).get_by_role("button", name="Удалить", exact=True).click()
    confirm = sheet(page)
    check("удаление: собственный лист подтверждения", confirm.locator(".btn-danger").count() == 1)
    confirm.locator(".btn-danger").click()
    page.wait_for_timeout(800)
    sheets_closed(page)
    check("удаление: запись исчезла", "Тест: хлеб" not in page.locator(".home-feed").inner_text())
    check("удаление: остаток вернулся", hero(page) == before, f"{before} vs {hero(page)}")

    page.click(".quick-item.is-primary")
    page.fill(".amount-input", "5")
    page.locator("input[type=date]").locator("xpath=preceding-sibling::div[1]//button").last.click()
    check("дата: «Другая дата» показывает поле", page.locator("input[type=date]").is_visible())
    page.keyboard.press("Escape")
    sheets_closed(page)
    page.locator(".card-draft .icon-btn").click()

    page.click(".quick-item.is-primary")
    page.fill(".amount-input", "abc")
    check("сумма: буквы не вводятся", page.input_value(".amount-input") == "")
    sheet(page).locator(".btn-primary").click()
    page.wait_for_timeout(200)
    check("сумма: пустая — ошибка у поля и фокус", "Введите сумму" in sheet(page).inner_text()
          and page.evaluate("document.activeElement?.classList.contains('amount-input')"))
    page.fill(".amount-input", "7")
    page.locator(".tx-fields .chip", has_text="Прочее").last.click()
    page.keyboard.press("Escape")
    sheets_closed(page)
    check("черновик: закрытая заполненная форма даёт карточку", page.locator(".card-draft").count() == 1)
    page.locator(".card-draft .btn").click()
    check("черновик: продолжение восстанавливает сумму", page.input_value(".amount-input") == "7")
    page.keyboard.press("Escape")
    sheets_closed(page)
    page.locator(".card-draft .icon-btn").click()
    page.wait_for_timeout(200)
    check("черновик: удаление убирает карточку", page.locator(".card-draft").count() == 0)

    page.click(".quick-item >> nth=1")
    page.fill(".amount-input", "100")
    sheet(page).get_by_role("button", name="Октябрь").first.click()
    sheet(page).locator(".btn-primary").click()
    sheets_closed(page)
    check("взнос: ждёт подтверждения", "Взнос ждёт подтверждения" in toast(page))
    check("взнос: у владельца два запроса", page.locator(".pending-row").count() == 2, str(page.locator(".pending-row").count()))
    balance = hero(page)
    page.locator(".pending-row").first.get_by_role("button", name="Принять").click()
    page.wait_for_timeout(700)
    check("взнос: принятие меняет остаток", hero(page) != balance, f"{balance} -> {hero(page)}")


def cleaning_and_reimbursement(page, report):
    check = report.check
    check("уборка: сегодняшний день первым, с кнопкой «Готово»", "Сегодня ваша очередь" in page.locator(".home-tasks").inner_text())
    page.locator(".chore-row .btn").first.click()
    page.wait_for_timeout(700)
    check("уборка: отметка даёт уведомление", "Уборка отмечена" in toast(page))
    check("уборка: просрочка свёрнута со счётчиком", "Пропущено: 2" in page.locator(".chore-overdue").inner_text())
    page.click(".chore-overdue")
    check("уборка: просроченные дни раскрываются", page.locator(".chore-row").count() >= 2)

    page.click("text=Вся история")
    page.wait_for_timeout(400)
    page.click(".chip >> text=Ждут возврата")
    page.wait_for_timeout(600)
    rows = page.locator("#view-history .row.entry")
    check("история: быстрый фильтр «Ждут возврата» находит траты за свои", rows.count() >= 1, str(rows.count()))
    before = page.evaluate("document.querySelector('.hero-amount')?.firstChild?.textContent") or ""
    rows.first.click()
    sheet(page).get_by_role("button", name="Вернуть из котла").click()
    sheet(page).locator(".btn-primary").click()
    page.wait_for_timeout(900)
    check("возврат: лист подтверждения и уведомление", "Возврат отмечен" in toast(page))
    go(page, "home")
    after = page.evaluate("document.querySelector('.hero-amount')?.firstChild?.textContent") or ""
    check("возврат: остаток изменился", after != before, f"{before} -> {after}")


def history(page, report):
    check = report.check
    page.reload()
    page.wait_for_selector(".hero")
    go(page, "history")
    check("история: первая запись видна без прокрутки", page.locator("#view-history .row.entry").first.bounding_box()["y"] < 800)
    page.fill(".search-input", "Migros")
    page.wait_for_timeout(900)
    check("история: поиск сужает список", page.locator("#view-history .row.entry").count() == 1, str(page.locator("#view-history .row.entry").count()))
    page.fill(".search-input", "")
    page.wait_for_timeout(900)
    page.get_by_role("button", name="Расходы", exact=True).first.click()
    page.wait_for_timeout(600)
    check("история: чип «Расходы» оставляет только расходы",
          all("Взнос" not in text for text in page.locator("#view-history .row.entry .row-title").all_inner_texts()))
    page.get_by_role("button", name="Все записи").click()
    page.wait_for_timeout(500)
    page.click(".chip-filter")
    sheet(page).get_by_role("button", name="Бытовая химия").click()
    sheet(page).get_by_role("button", name="Показать записи").click()
    sheets_closed(page)
    page.wait_for_timeout(500)
    check("история: фильтр по категории и счётчик на кнопке",
          "· 1" in page.locator(".chip-filter").inner_text() and page.locator("#view-history .row.entry").count() == 1)
    page.click(".chip-filter")
    sheet(page).get_by_role("button", name="Сбросить").click()
    sheets_closed(page)
    page.wait_for_timeout(500)
    page.click(".month-btn")
    sheet(page).get_by_role("button", name="Окт", exact=True).click()
    sheets_closed(page)
    page.wait_for_timeout(500)
    check("история: выбор месяца", "Октябрь" in page.locator(".month-btn").inner_text() and page.locator("#view-history .row.entry").count() >= 3)
    page.click(".month-btn")
    sheet(page).get_by_role("button", name="За всё время").click()
    sheets_closed(page)
    page.wait_for_timeout(500)
    check("история: режим «За всё время»", "За всё время" in page.locator(".month-btn").inner_text())
    page.click(".summary-line .link-btn")
    check("история: итоги с разбором по категориям", "На что потратили" in sheet(page).inner_text() and sheet(page).locator("meter").count() >= 1)
    page.keyboard.press("Escape")
    sheets_closed(page)

    for index in range(MASS_ENTRIES):
        api(page, "POST", "houses/1/transactions", {"request_id": f"00000000-0000-4000-8000-{index:012d}", "kind": "expense", "amount": str(index + 1),
                                                    "date": page.evaluate("new Date().toISOString().slice(0, 10)"), "month": "", "category_id": None,
                                                    "mode": "house", "description": f"Массовая {index}"})
    page.reload()
    page.wait_for_selector(".hero")
    go(page, "history")
    page.click(".month-btn")
    sheet(page).get_by_role("button", name="За всё время").click()
    sheets_closed(page)
    page.wait_for_timeout(600)
    rows = page.locator("#view-history .row.entry").count()
    check("постраничность: 20 записей и кнопка «Показать ещё»", rows == PAGE_SIZE and page.get_by_role("button", name="Показать ещё").count() == 1, str(rows))
    page.get_by_role("button", name="Показать ещё").click()
    page.wait_for_timeout(700)
    check("постраничность: «Показать ещё» добавляет записи", page.locator("#view-history .row.entry").count() > PAGE_SIZE)


# ── Дом ───────────────────────────────────────────────────────────────────────────────────────────

def house(page, report):
    check = report.check
    go(page, "house")
    rows = page.locator("#view-house .group-row")
    rows.nth(0).click()
    page.wait_for_selector(".invite-code", timeout=4000)
    check("жильцы: владельцу виден код приглашения", page.locator(".invite-code").inner_text().strip() != "")
    page.locator("#view-house button.row").first.click()
    switches = sheet(page).locator(".switch")
    check("жильцы: права — восемь настоящих переключателей", switches.count() == 8, str(switches.count()))
    switches.nth(2).click()
    page.wait_for_timeout(500)
    check("жильцы: переключатель сохраняется сразу", switches.nth(2).get_attribute("aria-checked") == "true" and "Права обновлены" in toast(page))
    page.keyboard.press("Escape")
    sheets_closed(page)
    back_to_hub(page)

    rows.nth(1).click()
    page.wait_for_selector(".days", timeout=4000)
    save = page.get_by_role("button", name="Сохранить график")
    check("график: «Сохранить» недоступна без изменений", save.is_disabled())
    page.locator(".schedule-member").nth(1).locator(".day-pick").nth(4).click()
    check("график: после выбора дня кнопка доступна", save.is_enabled())
    save.click()
    page.wait_for_timeout(900)
    check("график: сохранение с уведомлением", "График обновлён" in toast(page))
    back_to_hub(page)

    rows.nth(2).click()
    page.wait_for_selector("#categories-title", timeout=4000)
    page.fill("#view-house input[maxlength='24']", "Тестовая")
    page.get_by_role("button", name="Добавить категорию").click()
    page.wait_for_timeout(900)
    check("категории: добавление", "Тестовая" in page.locator("#view-house").inner_text())
    page.get_by_role("button", name="Убрать категорию «Тестовая»").click()
    sheet(page).locator(".btn-danger").click()
    page.wait_for_timeout(900)
    check("категории: удаление после подтверждения", "Тестовая" not in page.locator("#view-house").inner_text())
    back_to_hub(page)

    rows.nth(3).click()
    page.wait_for_selector(".seg", timeout=4000)
    page.locator(".setting-block").first.get_by_role("radio", name="Не присылать").click()
    page.wait_for_timeout(500)
    check("уведомления: выбор сохраняется сразу", "Сохранено" in toast(page))
    back_to_hub(page)

    rows.nth(4).click()
    page.wait_for_selector("#rules-title", timeout=4000)
    switch = page.locator("#view-house .switch").first
    was = switch.get_attribute("aria-checked")
    switch.click()
    page.wait_for_timeout(600)
    check("настройки: переключатель сохраняется сразу", switch.get_attribute("aria-checked") != was and "Сохранено" in toast(page))
    page.locator("#view-house select").first.select_option("10")
    page.wait_for_timeout(600)
    check("настройки: выбор сохраняется сразу", "Сохранено" in toast(page))
    page.fill("#view-house input[maxlength='32'] >> nth=1", "Слава Т")
    page.get_by_role("button", name="Сохранить имя").click()
    page.wait_for_timeout(700)
    check("настройки: имя обновлено", "Имя обновлено" in toast(page))
    check("настройки: у владельца нет «Выйти из дома»", page.get_by_role("button", name="Выйти из дома").count() == 0)
    back_to_hub(page)

    page.get_by_role("button", name="Другой дом").click()
    page.wait_for_selector(".seg", timeout=3000)
    page.fill("#view-house input >> nth=0", "Гараж")
    page.get_by_role("button", name="Создать дом").click()
    page.wait_for_timeout(1200)
    check("другой дом: создан и открыт", page.locator("#home-title").inner_text() == "Гараж", page.locator("#home-title").inner_text())
    check("другой дом: новый дом показывает первые шаги", page.locator("#setup-title").count() == 1)
    page.locator(".topbar-actions .pill").nth(1).click()
    check("список домов: четыре дома", sheet(page).locator(".group-row").count() == 4, str(sheet(page).locator(".group-row").count()))
    sheet(page).locator(".group-row").first.click()
    page.wait_for_timeout(900)
    check("список домов: возврат в прежний дом", page.locator("#home-title").inner_text() == "Квартира на Садовой")


def files(page, report, shots):
    check = report.check
    go(page, "history")
    page.locator("#view-history .head-actions .icon-btn").first.click()
    with page.expect_download(timeout=8000) as download:
        sheet(page).get_by_role("button", name="Excel").first.click()
    check("файлы: Excel скачивается и не пустой", os.path.getsize(download.value.path()) > 2000, download.value.suggested_filename)
    with page.expect_download(timeout=8000) as download:
        sheet(page).get_by_role("button", name="CSV").click()
    csv_path = Path(shots) / "export.csv"
    download.value.save_as(str(csv_path))
    check("файлы: CSV скачивается", csv_path.stat().st_size > 100, download.value.suggested_filename)
    sheet(page).locator("input[type=file]").set_input_files(str(csv_path))
    page.wait_for_selector(".import-preview:not([hidden])", timeout=5000)
    summary = sheet(page).locator(".import-preview .sheet-text").inner_text()
    check("файлы: собственный экспорт — только дубли", "Новых: 0" in summary, summary)
    check("файлы: без новых записей подтвердить нельзя", sheet(page).get_by_role("button", name="Добавить записи").is_disabled())
    page.keyboard.press("Escape")
    sheets_closed(page)
    go(page, "history")
    page.locator("#view-history .row.entry").first.click()
    sheet(page).get_by_role("button", name="Чеки", exact=True).click()
    page.wait_for_timeout(700)
    check("чеки: без хранилища — понятное сообщение", "Хранилище чеков временно недоступно" in sheet(page).inner_text())
    page.keyboard.press("Escape")
    sheets_closed(page)


# ── Независимые проверки ──────────────────────────────────────────────────────────────────────────

def language(playwright, base, report):
    browser, _, page = open_app(playwright, base)
    page.locator(".topbar-actions .pill").first.click()
    sheet(page).get_by_role("radio", name="Deutsch").click()
    page.wait_for_load_state("load")
    page.wait_for_selector(".hero", timeout=8000)
    page.wait_for_timeout(500)
    report.check("язык: немецкий применён после перезагрузки", page.evaluate("document.documentElement.lang") == "de" and "Gemeinsame Kasse" in page.locator(".hero").inner_text())
    report.check("язык: русский текст не просочился", "Общий" not in page.locator("#view-home").inner_text())
    report.check("язык: суммы с швейцарскими разделителями", any(mark in page.locator(".hero-split").inner_text() for mark in ("’", "'")))
    go(page, "history")
    page.locator(".topbar-actions .pill").first.click()
    sheet(page).get_by_role("radio", name="Русский").click()
    page.wait_for_selector(".tabbar", timeout=8000)
    report.check("язык: возврат на русский", page.evaluate("document.documentElement.lang") == "ru")
    try:  # оболочка строится сразу, а раздел возвращается после загрузки данных
        page.locator("#view-history").wait_for(state="visible", timeout=8000)
        restored = True
    except PlaywrightTimeout:
        restored = False
    report.check("язык: раздел восстановлен после перезагрузки", restored)
    report.check("язык: без ошибок в консоли", not page.errors, "; ".join(page.errors[:3]))
    browser.close()


def resident(playwright, base, report):
    browser, _, page = open_app(playwright, base, user=1003)
    report.check("жилец: нет карточки подтверждения взносов", page.locator(".card-attention").count() == 0)
    go(page, "house")
    page.locator("#view-house .group-row").nth(0).click()
    page.wait_for_timeout(700)
    report.check("жилец: нет приглашения без права", page.locator(".invite-code").count() == 0)
    report.check("жилец: права других недоступны для правки", page.locator("#view-house button.row").count() == 0)
    back_to_hub(page)
    page.locator("#view-house .group-row").nth(4).click()
    page.wait_for_timeout(700)
    report.check("жилец: настройки только для чтения", page.locator("#view-house .switch").count() == 0)
    report.check("жилец: может выйти из дома", page.get_by_role("button", name="Выйти из дома").count() == 1)
    page.get_by_role("button", name="Выйти из дома").click()
    sheet(page).locator(".btn-danger").click()
    page.wait_for_timeout(1200)
    report.check("жилец: после выхода — экран первого входа", page.locator(".welcome").count() == 1)
    browser.close()


def telegram(playwright, base, report):
    browser, _, page = open_app(playwright, base)
    calls = lambda: [call[0] for call in page.evaluate("window.__tgcalls")]  # noqa: E731
    report.check("telegram: ready и expand вызваны", "ready" in calls() and "expand" in calls())
    report.check("telegram: цвета шапки, фона и нижней панели заданы", all(name in calls() for name in ("setHeaderColor", "setBackgroundColor", "setBottomBarColor")))
    page.click(".quick-item.is-primary")
    report.check("telegram: «Назад» показана, свайп закрытия выключен при открытом листе", "BackButton.show" in calls() and "disableVerticalSwipes" in calls())
    page.fill(".amount-input", "9")
    report.check("telegram: подтверждение закрытия при несохранённом вводе", "enableClosingConfirmation" in calls())
    page.keyboard.press("Escape")
    sheets_closed(page)
    page.locator(".card-draft .icon-btn").click()
    report.check("telegram: без ошибок в консоли", not page.errors, "; ".join(page.errors[:3]))
    browser.close()


def resilience(playwright, base, report):
    browser, context, page = open_app(playwright, base)
    context.set_offline(True)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    report.check("нет сети: баннер показан", page.locator(".banner").is_visible())
    page.click(".quick-item.is-primary")
    page.fill(".amount-input", "3")
    sheet(page).locator(".btn-primary").click()
    page.wait_for_timeout(900)
    report.check("нет сети: ошибка в форме, ввод сохранён", "Нет соединения" in sheet(page).inner_text() and page.input_value(".amount-input") == "3")
    context.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    report.check("сеть вернулась: баннер скрыт", not page.locator(".banner").is_visible())
    page.keyboard.press("Escape")
    sheets_closed(page)
    page.route("**/api/**", lambda route: route.fulfill(status=404, body='{"detail":"Not Found"}', content_type="application/json"))
    page.click(".quick-item >> nth=1")
    page.fill(".amount-input", "1")
    sheet(page).locator(".btn-primary").click()
    page.wait_for_timeout(800)
    report.check("вход устарел: отдельный экран «Сеанс закончился»", page.get_by_text("Сеанс закончился").count() == 1)
    browser.close()


def run_all(playwright, base, report, shots):
    browser, _, page = open_app(playwright, base)
    report.guard("деньги", money, page, report)
    report.guard("уборка и возврат", cleaning_and_reimbursement, page, report)
    report.guard("история", history, page, report)
    report.guard("дом", house, page, report)
    report.guard("файлы", files, page, report, shots)
    report.check("основной прогон: без ошибок в консоли", not page.errors, "; ".join(page.errors[:3]))
    browser.close()
    for name, scenario in (("язык", language), ("жилец", resident), ("telegram", telegram), ("устойчивость", resilience)):
        report.guard(name, scenario, playwright, base, report)
