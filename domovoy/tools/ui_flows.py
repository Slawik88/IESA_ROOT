"""Сквозные сценарии сайта в настоящем браузере на демо-данных (tools/demo_server.py). Запускает tools/ui_check.py.

Сценарии идут по порядку на одной базе: расходы → уборка и возврат → правки → история → «Дом» → файлы; затем независимые
проверки запуска, файлов на компьютере, языка, жильца без прав, интеграции с Telegram и устойчивости (нет сети, истёкший вход).
"""
import base64
import os
import traceback
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

MASS_ENTRIES = 25
PAGE_SIZE = 20
RECEIPT_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")


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


def open_app(playwright, base, user=1001, size=(390, 844), language=None, platform=None):
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1, is_mobile=size[0] < 700,
                                  has_touch=size[0] < 700, locale="ru-RU", accept_downloads=True)
    if language:
        context.add_init_script(f"try{{localStorage.setItem('domovoy.locale','{language}')}}catch(e){{}}")
    page = context.new_page()
    page.errors = []
    page.traffic = []  # порядок запросов и ответов API — по нему проверяется параллельный запуск
    page.on("console", lambda message: page.errors.append(message.text) if message.type == "error" and "status of 422" not in message.text else None)
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on("request", lambda request: page.traffic.append(("request", request.url.split("/api/", 1)[1])) if "/api/" in request.url else None)
    page.on("response", lambda response: page.traffic.append(("response", response.url.split("/api/", 1)[1])) if "/api/" in response.url else None)
    page.goto(f"{base}?u={user}" + (f"&platform={platform}" if platform else ""))
    page.wait_for_selector(".hero, .welcome, .gate", timeout=10000)
    page.wait_for_timeout(400)
    return browser, context, page


def sheet(page):
    return page.locator("dialog.sheet[open]").last


def toast(page):
    page.wait_for_selector(".toast", timeout=4000)
    return page.locator(".toast").last.inner_text()


def hero(page):
    return page.locator(".hero-amount").inner_text().replace(" ", " ")


def go(page, view):
    page.evaluate(f"document.querySelector('.tabbar .tab[data-view={view}], .topnav .tab[data-view={view}]').click()")
    page.wait_for_timeout(350)


def sheets_closed(page):
    page.locator("dialog.sheet[open]").wait_for(state="detached", timeout=4000)
    page.wait_for_timeout(250)


def back_to_hub(page):
    page.click("#view-house .icon-btn")
    page.wait_for_timeout(300)


def hub(page, title):
    """Строка раздела на экране «Дом» по её названию."""
    return page.locator("#view-house .group-row").filter(has_text=title).first


def history_chip(page, index):
    return page.locator("#view-history .chips[role=group] .chip").nth(index)


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
    sheet(page).get_by_role("button", name="Удалить расход", exact=True).click()
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


def corrections(page, report):
    """Правки уже записанного: возврат, взносы, плашка «Дом должен жильцам»."""
    check = report.check
    for _ in range(3):  # остальные ожидающие взносы принимаются: дальше нужен подтверждённый взнос жильца
        if not page.locator(".pending-row").count():
            break
        page.locator(".pending-row").first.get_by_role("button", name="Принять").click()
        page.wait_for_timeout(800)
    check("взносы: владелец подтвердил все ожидающие", page.locator(".pending-row").count() == 0)
    card = page.locator(".home-top .group-row").filter(has_text="Дом должен жильцам")
    check("долги: на главной плашка «Дом должен жильцам»", card.count() == 1)
    card.click()
    page.wait_for_timeout(700)
    check("долги: нажатие открывает историю с фильтром «Ждут возврата»",
          page.locator("#view-history .chip[aria-pressed=true]").filter(has_text="Ждут возврата").count() == 1
          and page.locator("#view-history .row.entry").count() >= 1)
    page.locator("#view-history .chip").filter(has_text="Ждут возврата").first.click()
    page.wait_for_timeout(500)
    page.click(".month-btn")
    sheet(page).get_by_role("button", name="За всё время").click()
    sheets_closed(page)
    page.fill(".search-input", "стёкол")
    page.wait_for_timeout(900)

    page.locator("#view-history .row.entry").first.click()
    entry = sheet(page)
    check("правки: у возвращённого расхода объяснено, почему он закрыт", "закрыт для правок" in entry.inner_text())
    check("правки: у возвращённого расхода нет «Изменить», есть «Отменить возврат»",
          entry.get_by_role("button", name="Изменить", exact=True).count() == 0
          and entry.get_by_role("button", name="Отменить возврат").count() == 1)
    entry.get_by_role("button", name="Отменить возврат").click()
    sheet(page).locator(".btn-primary").click()
    page.wait_for_timeout(900)
    check("возврат: отмена показывает уведомление", "Возврат отменён" in toast(page))
    page.locator("#view-history .row.entry").first.click()
    entry = sheet(page)
    check("правки: после отмены возврата запись снова можно изменить и удалить",
          entry.get_by_role("button", name="Изменить", exact=True).count() == 1
          and entry.get_by_role("button", name="Удалить расход").count() == 1)
    entry.get_by_role("button", name="Изменить", exact=True).click()
    page.fill(".amount-input", "50")
    sheet(page).locator(".btn-primary").click()
    sheets_closed(page)
    check("правки: сумма бывшей возвращённой траты изменилась", "−50,00" in page.locator("#view-history .row.entry").first.inner_text())

    page.fill(".search-input", "")
    page.wait_for_timeout(900)
    history_chip(page, 2).click()
    page.wait_for_timeout(700)
    page.locator("#view-history .row.entry").last.click()
    entry = sheet(page)
    check("взнос: владелец видит «Изменить» и «Удалить взнос»",
          entry.get_by_role("button", name="Изменить", exact=True).count() == 1 and entry.get_by_role("button", name="Удалить взнос").count() == 1)
    entry.get_by_role("button", name="Изменить", exact=True).click()
    form = sheet(page).inner_text()
    check("взнос: форма правки с пояснением про остаток", "Изменить взнос" in form and "остаток пересчитается" in form, form[:80])
    page.fill(".amount-input", "123")
    sheet(page).locator(".btn-primary").click()
    sheets_closed(page)
    check("взнос: сумма изменилась в истории", "+123,00" in page.locator("#view-history .row.entry").last.inner_text())
    page.locator("#view-history .row.entry").last.click()
    sheet(page).get_by_role("button", name="Удалить взнос").click()
    sheet(page).locator(".btn-danger").click()
    page.wait_for_timeout(900)
    check("взнос: удаление после подтверждения", "Взнос удалён" in toast(page))
    go(page, "home")


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
    loaded = page.locator("#view-history .row.entry").count()
    check("постраничность: «Показать ещё» добавляет записи", loaded > PAGE_SIZE)
    go(page, "house")
    page.get_by_role("button", name="Обновить данные").click()
    page.wait_for_timeout(900)
    go(page, "history")
    check("обновление одним запросом сохраняет длину раскрытого списка", page.locator("#view-history .row.entry").count() == loaded,
          f"{loaded} -> {page.locator('#view-history .row.entry').count()}")


# ── Дом ───────────────────────────────────────────────────────────────────────────────────────────

def house(page, report):
    check = report.check
    go(page, "house")
    check("дом: у владельца есть раздел «Передача и удаление дома»", hub(page, "Передача и удаление дома").count() == 1)
    hub(page, "Жильцы").click()
    page.wait_for_selector(".invite-code", timeout=4000)
    check("жильцы: владельцу виден код приглашения", page.locator(".invite-code").inner_text().strip() != "")
    page.locator("#view-house button.row").first.click()
    switches = sheet(page).locator(".switch")
    check("жильцы: права — восемь настоящих переключателей", switches.count() == 8, str(switches.count()))
    check("жильцы: в листе прав есть «Убрать из дома»", sheet(page).get_by_role("button", name="Убрать из дома").count() == 1)
    switches.nth(2).click()
    page.wait_for_timeout(500)
    check("жильцы: переключатель сохраняется сразу", switches.nth(2).get_attribute("aria-checked") == "true" and "Права обновлены" in toast(page))
    page.keyboard.press("Escape")
    sheets_closed(page)
    back_to_hub(page)

    hub(page, "График уборки").click()
    page.wait_for_selector(".days", timeout=4000)
    save = page.get_by_role("button", name="Сохранить график")
    check("график: «Сохранить» недоступна без изменений", save.is_disabled())
    page.locator(".schedule-member").nth(1).locator(".day-pick").nth(4).click()
    check("график: после выбора дня кнопка доступна", save.is_enabled())
    save.click()
    page.wait_for_timeout(900)
    check("график: сохранение с уведомлением", "График обновлён" in toast(page))
    reopen = page.get_by_role("button", name="Вернуть в ожидание")
    check("график: у отмеченного дня есть «Вернуть в ожидание»", reopen.count() >= 1, str(reopen.count()))
    reopen.first.click()
    page.wait_for_timeout(900)
    check("график: день вернулся в ожидание", "День снова ждёт отметки" in toast(page))
    back_to_hub(page)

    hub(page, "Деньги и категории").click()
    page.wait_for_selector("#categories-title", timeout=4000)
    page.fill("#view-house input[maxlength='24']", "Тестовая")
    page.get_by_role("button", name="Добавить категорию").click()
    page.wait_for_timeout(900)
    check("категории: добавление", "Тестовая" in page.locator("#view-house").inner_text())
    page.get_by_role("button", name="Переименовать категорию «Тестовая»").click()
    sheet(page).locator("input").fill("Тестовая Б")
    sheet(page).get_by_role("button", name="Сохранить", exact=True).click()
    page.wait_for_timeout(900)
    check("категории: переименование", "Тестовая Б" in page.locator("#view-house").inner_text())
    page.get_by_role("button", name="Убрать категорию «Тестовая Б»").click()
    sheet(page).locator(".btn-danger").click()
    page.wait_for_timeout(900)
    check("категории: удаление после подтверждения", "Тестовая" not in page.locator("#view-house").inner_text())
    back_to_hub(page)

    hub(page, "Мои уведомления").click()
    page.wait_for_selector(".seg", timeout=4000)
    page.locator(".setting-block").first.get_by_role("radio", name="Не присылать").click()
    page.wait_for_timeout(500)
    check("уведомления: выбор сохраняется сразу", "Сохранено" in toast(page))
    back_to_hub(page)

    hub(page, "Настройки дома").click()
    page.wait_for_selector("#rules-title", timeout=4000)
    switch = page.locator("#view-house .switch").nth(1)  # «Напоминать каждый вечер»; первый переключатель — подтверждение взносов
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
    check("настройки: «Выйти из дома» и удаление живут в «Управлении домом»", page.get_by_role("button", name="Выйти из дома").count() == 0)
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

    delete_house(page, report)


def delete_house(page, report):
    """Удаление дома: название набирается вручную, после удаления открывается другой дом."""
    check = report.check
    page.locator(".topbar-actions .pill").nth(1).click()
    sheet(page).locator(".group-row").filter(has_text="Гараж").click()
    page.wait_for_timeout(900)
    go(page, "house")
    hub(page, "Передача и удаление дома").click()
    page.wait_for_selector("#view-house .card-danger", timeout=4000)
    check("управление: одинокому владельцу предлагают пригласить соседа", "Пока вы живёте в доме один" in page.locator("#view-house").inner_text())
    page.get_by_role("button", name="Удалить дом…").click()
    dialog = sheet(page)
    remove = dialog.get_by_role("button", name="Удалить дом навсегда")
    check("удаление дома: без названия кнопка недоступна", remove.is_disabled())
    dialog.locator("input").fill("Не то название")
    check("удаление дома: с чужим названием кнопка недоступна", remove.is_disabled())
    dialog.locator("input").fill("Гараж")
    check("удаление дома: с точным названием кнопка доступна", remove.is_enabled())
    remove.click()
    page.wait_for_selector("#home-title", timeout=6000)
    page.wait_for_timeout(900)
    check("удаление дома: открылся другой дом", page.locator("#home-title").inner_text() == "Квартира на Садовой", page.locator("#home-title").inner_text())
    page.locator(".topbar-actions .pill").nth(1).click()
    check("удаление дома: в списке домов осталось три", sheet(page).locator(".group-row").count() == 3, str(sheet(page).locator(".group-row").count()))
    check("удаление дома: «Гаража» в списке нет", "Гараж" not in sheet(page).inner_text())
    page.keyboard.press("Escape")
    sheets_closed(page)


def files(page, report, shots):
    """Телефон Telegram (ios): файлы уходят в чат с ботом, скачивания на устройство нет."""
    check = report.check
    go(page, "history")
    opener = page.locator("#view-history .head-actions").get_by_role("button", name="Файлы")
    check("файлы: в истории есть кнопка «Файлы» с подписью", opener.count() == 1)
    opener.click()
    panel = sheet(page)
    check("файлы: на телефоне нет скачивания, отправка в чат — главный путь",
          panel.get_by_role("button", name="Скачать на устройство").count() == 0
          and panel.get_by_role("button", name="Отправить в чат с ботом").count() == 1)
    check("файлы: формат по умолчанию — Excel", panel.get_by_role("button", name="Excel").first.get_attribute("aria-pressed") == "true")
    check("файлы: загрузка разбита на три шага", panel.locator(".steps .step").count() == 3)
    panel.get_by_role("button", name="Отправить в чат с ботом").click()
    panel.locator(".sent-card").first.wait_for(timeout=5000)
    check("файлы: после отправки видно, что файл ушёл, и есть «Открыть чат»", panel.get_by_role("button", name="Открыть чат").count() == 1)
    panel.get_by_role("button", name="Открыть чат").click()
    opened = [call for call in page.evaluate("window.__tgcalls") if call[0] == "openTelegramLink"]
    check("файлы: «Открыть чат» ведёт к боту", bool(opened) and "t.me/domovoy_demo_bot" in opened[-1][1][0], str(opened[-1:]))
    panel.get_by_role("button", name="Отправить шаблон в чат").click()
    page.wait_for_timeout(900)
    check("файлы: шаблон тоже уходит в чат", panel.locator(".sent-card").count() == 2, str(panel.locator(".sent-card").count()))
    page.keyboard.press("Escape")
    sheets_closed(page)
    go(page, "house")
    hub(page, "Скачать и загрузить записи").click()
    check("файлы: из раздела «Дом» тоже открываются", "Записи и файлы" in sheet(page).inner_text())
    page.keyboard.press("Escape")
    sheets_closed(page)
    receipts(page, report, shots)


def receipts(page, report, shots):
    """Фото чека: добавить, увидеть в сетке, удалить после подтверждения."""
    check = report.check
    go(page, "history")
    page.locator("#view-history .row.entry").first.click()
    sheet(page).get_by_role("button", name="Чеки", exact=True).click()
    page.wait_for_timeout(700)
    panel = sheet(page)
    check("чеки: пока нет — сказано об этом, фото добавить можно",
          "Чеков пока нет" in panel.inner_text() and panel.locator("input[type=file]").count() == 1)
    photo = Path(shots) / "receipt.png"
    photo.write_bytes(RECEIPT_PNG)
    panel.locator("input[type=file]").set_input_files(str(photo))
    page.wait_for_timeout(400)
    panel.get_by_role("button", name="Прикрепить чек").click()
    page.wait_for_selector(".receipt-grid img", timeout=6000)
    panel = sheet(page)
    check("чеки: загруженное фото видно в сетке", panel.locator(".receipt-grid img").count() == 1)
    remove = panel.get_by_role("button", name="Удалить чек 1")
    check("чеки: у фото есть кнопка «Удалить чек»", remove.count() == 1)
    remove.click()
    sheet(page).locator(".btn-danger").click()
    page.wait_for_timeout(1200)
    check("чеки: после удаления фото пропало", "Чеков пока нет" in sheet(page).inner_text() and sheet(page).locator(".receipt-grid img").count() == 0)
    page.keyboard.press("Escape")
    sheets_closed(page)


# ── Независимые проверки ──────────────────────────────────────────────────────────────────────────

def files_desktop(playwright, base, report, shots):
    """Компьютер (tdesktop): и отправка в чат, и скачивание файла; собственный экспорт загружается как одни дубли."""
    check = report.check
    browser, _, page = open_app(playwright, base, size=(1280, 800), platform="tdesktop")
    go(page, "history")
    page.locator("#view-history .head-actions").get_by_role("button", name="Файлы").click()
    panel = sheet(page)
    check("файлы (компьютер): есть и отправка в чат, и скачивание",
          panel.get_by_role("button", name="Отправить в чат с ботом").count() == 1
          and panel.get_by_role("button", name="Скачать на устройство").count() == 1)
    with page.expect_download(timeout=8000) as download:
        panel.get_by_role("button", name="Скачать на устройство").click()
    check("файлы: Excel скачивается и не пустой", os.path.getsize(download.value.path()) > 2000, download.value.suggested_filename)
    panel.get_by_role("button", name="CSV", exact=True).click()
    with page.expect_download(timeout=8000) as download:
        panel.get_by_role("button", name="Скачать на устройство").click()
    csv_path = Path(shots) / "export.csv"
    download.value.save_as(str(csv_path))
    check("файлы: CSV скачивается", csv_path.stat().st_size > 100, download.value.suggested_filename)
    with page.expect_download(timeout=8000) as download:
        panel.get_by_role("button", name="Скачать шаблон").click()
    check("файлы: шаблон скачивается в выбранном формате", download.value.suggested_filename.endswith(".csv"), download.value.suggested_filename)
    panel.locator("input[type=file]").set_input_files(str(csv_path))
    page.wait_for_selector(".import-preview:not([hidden])", timeout=5000)
    summary = panel.locator(".import-preview .sheet-text").inner_text()
    check("файлы: собственный экспорт — только дубли", "Новых: 0" in summary, summary)
    check("файлы: в проверке указано имя файла", "export.csv" in panel.locator(".import-preview").inner_text())
    check("файлы: без новых записей подтвердить нельзя", panel.get_by_role("button", name="Добавить записи").is_disabled())
    check("файлы: без ошибок в консоли", not page.errors, "; ".join(page.errors[:3]))
    browser.close()


def boot(playwright, base, report):
    """Запуск: список домов и обзор запомненного дома запрашиваются одновременно, обзор — ровно один."""
    browser, _, page = open_app(playwright, base)
    first = [kind for kind, path in page.traffic if path.startswith("houses/")]
    report.check("запуск: при первом входе обзор дома запрашивается один раз", first.count("request") == 1, str(page.traffic[:4]))
    page.traffic.clear()
    page.reload()
    page.wait_for_selector(".hero", timeout=10000)
    page.wait_for_timeout(400)
    events = page.traffic
    houses_list = next(index for index, (kind, path) in enumerate(events) if kind == "request" and path == "houses")
    overview = next(index for index, (kind, path) in enumerate(events) if kind == "request" and path.startswith("houses/"))
    first_response = next(index for index, (kind, _) in enumerate(events) if kind == "response")
    report.check("запуск: обзор дома идёт параллельно со списком домов", houses_list < overview < first_response, str(events[:5]))
    report.check("запуск: обзор дома запрошен один раз", sum(1 for kind, path in events if kind == "request" and path.startswith("houses/")) == 1,
                 str(events))
    browser.close()


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
    go(page, "history")
    page.click(".month-btn")
    sheet(page).get_by_role("button", name="За всё время").click()
    sheets_closed(page)
    history_chip(page, 2).click()
    page.wait_for_timeout(700)
    page.locator("#view-history .row.entry").filter(has_text="Борис").first.click()
    own = sheet(page)
    report.check("жилец: подтверждённый взнос закрыт для правок, и сказано почему",
                 own.get_by_role("button", name="Изменить", exact=True).count() == 0 and "пока он не подтверждён" in own.inner_text())
    page.keyboard.press("Escape")
    sheets_closed(page)
    go(page, "house")
    hub(page, "Жильцы").click()
    page.wait_for_timeout(700)
    report.check("жилец: нет приглашения без права", page.locator(".invite-code").count() == 0)
    report.check("жилец: права других недоступны для правки", page.locator("#view-house button.row").count() == 0)
    back_to_hub(page)
    report.check("жилец: нет раздела «Передача и удаление дома»", hub(page, "Передача и удаление дома").count() == 0)
    hub(page, "Настройки дома").click()
    page.wait_for_timeout(700)
    report.check("жилец: настройки только для чтения", page.locator("#view-house .switch").count() == 0)
    report.check("жилец: «Выйти из дома» не в настройках", page.get_by_role("button", name="Выйти из дома").count() == 0)
    back_to_hub(page)
    hub(page, "Выйти из дома").click()
    page.wait_for_selector(".card-danger", timeout=4000)
    report.check("жилец: выйти из дома можно в «Управлении домом»", page.locator(".card-danger .btn").count() == 1)
    page.locator(".card-danger .btn").click()
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
    report.guard("правки записанного", corrections, page, report)
    report.guard("история", history, page, report)
    report.guard("дом", house, page, report)
    report.guard("файлы", files, page, report, shots)
    report.check("основной прогон: без ошибок в консоли", not page.errors, "; ".join(page.errors[:3]))
    browser.close()
    report.guard("файлы на компьютере", files_desktop, playwright, base, report, shots)
    for name, scenario in (("запуск", boot), ("язык", language), ("жилец", resident), ("telegram", telegram), ("устойчивость", resilience)):
        report.guard(name, scenario, playwright, base, report)
