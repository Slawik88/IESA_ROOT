"""Authorized routing for callbacks, typed settings and legacy commands."""

from html import escape

from .models import SOURCES, safe_url
from .preferences import updated_search
from .telegram import TelegramError
from .ui import Screens
from .views import buttons


class Interaction(Screens):
    async def handle(self, update):
        callback = update.get("callback_query")
        message = (callback or {}).get("message") or update.get("message") or {}
        user_id = (callback or message).get("from", {}).get("id")
        private = (
            message.get("chat", {}).get("type") == "private"
            and message.get("chat", {}).get("id") == user_id
        )
        if user_id not in self.allowed_ids or not private:
            if callback:
                await self.telegram.call(
                    "answerCallbackQuery",
                    callback_query_id=callback["id"],
                    text="Этот бот доступен только приглашённым пользователям.",
                    show_alert=True,
                )
            return
        self.store.ensure_user(user_id)
        self.store.set_user(user_id, active=True)
        if callback:
            self.panels[user_id] = message.get("message_id")
            try:
                await self.telegram.call(
                    "answerCallbackQuery", callback_query_id=callback["id"]
                )
            except TelegramError as exc:
                if exc.code != 400:
                    raise
            action = callback.get("data", "")
            if action.startswith("edit:"):
                return await self.prompt(user_id, action.split(":", 1)[1])
            if action.startswith("set:"):
                parts = action.split(":", 2)
                if len(parts) == 3:
                    return await self.save(user_id, parts[1], parts[2])
                return
            self.store.set_user(user_id, pending="")
            if action.startswith("toggle:") or action in {
                "sources:all",
                "sources:none",
            }:
                search = self.store.search(user_id)
                if action == "sources:all":
                    search.sources = list(SOURCES)
                elif action == "sources:none":
                    search.sources = []
                else:
                    source = action.split(":", 1)[1]
                    if source not in SOURCES:
                        return
                    search.sources = (
                        [s for s in search.sources if s != source]
                        if source in search.sources
                        else search.sources + [source]
                    )
                self.store.save_search(user_id, search)
                return await self.sources(user_id)
            if action.startswith("source:"):
                return await self.status(user_id, action.split(":", 1)[1])
            if action.startswith("browse:"):
                parts = action.split(":")
                if len(parts) == 3 and parts[2].isdigit():
                    return await self.browse(user_id, parts[1], int(parts[2]))
                return
            if action.startswith("fav:"):
                return await self.favorite_action(user_id, action)
            if action.startswith("sort:"):
                parts = action.split(":")
                if (
                    len(parts) == 3
                    and parts[1] in {"current", "favorites"}
                    and parts[2] in {"price", "recent"}
                ):
                    self.store.put("sort:" + str(user_id), parts[2])
                    return await self.current(user_id, parts[1], parts[2])
                return
            return await self.action(user_id, action)
        text = message.get("text", "").strip()
        if not text:
            return
        self.panels[user_id] = self.store.get("panel:" + str(user_id))
        if text.startswith("/"):
            self.panels[user_id] = None  # Typed commands start a fresh visible panel.
            command, _, args = text.partition(" ")
            command = command.split("@")[0][1:].lower()
            if command in {"price", "rooms", "cities", "area", "interval", "exclude"}:
                return (
                    await self.save(user_id, command, args)
                    if args
                    else await self.prompt(user_id, command)
                )
            if command == "url":
                return await self.custom_url(user_id, args)
            self.store.set_user(user_id, pending="")
            return await self.action(user_id, command)
        if pending := self.store.user(user_id)["pending"]:
            return await self.save(user_id, pending, text)
        self.panels[user_id] = None
        await self.menu(user_id, "Выберите действие ниже.\n\n")

    async def save(self, user_id, field, value):
        try:
            search = updated_search(self.store.search(user_id), field, value)
        except (ValueError, OverflowError) as exc:
            explanation = (
                str(exc)
                if "invalid literal" not in str(exc)
                else "Нужно целое число, например 1500."
            )
            await self.prompt(user_id, field, explanation)
            return
        self.store.save_search(user_id, search)
        self.store.set_user(user_id, pending="")
        await self.settings(
            user_id, "<b>Сохранено.</b> Новые уведомления учитывают ваш фильтр.\n\n"
        )

    async def custom_url(self, user_id, args):
        self.store.set_user(user_id, pending="")
        source, _, value = args.partition(" ")
        if source not in SOURCES or not value or source == "flatfox":
            await self.show(
                user_id,
                "Своя ссылка поиска: /url huusbro https://huusbro.ch/de/mieten/wetzikon\nСброс: /url huusbro reset\nКарта Flatfox строится по выбранным городам.",
                buttons([[("К настройкам", "settings")]]),
            )
            return
        search = self.store.search(user_id)
        try:
            if value == "reset":
                search.urls.pop(source, None)
            else:
                search.urls[source] = safe_url(value.strip(), source)
            self.store.save_search(user_id, search)
        except ValueError as exc:
            await self.show(
                user_id, escape(str(exc)), buttons([[("К настройкам", "settings")]])
            )
            return
        await self.settings(
            user_id,
            "Ссылка сохранена. Ваши фильтры проверяются дополнительно по объявлению.\n\n",
        )

    async def action(self, user_id, action):
        if action in {"start", "menu", "home"}:
            return await self.menu(
                user_id,
                "Помогу найти жильё и сообщу о новых совпадениях. Начните с настройки поиска.\n\n"
                if action == "start"
                else "",
            )
        if action in {"settings", "cancel"}:
            return await self.settings(user_id)
        if action in {"pause", "resume"}:
            search = self.store.search(user_id)
            search.paused = action == "pause"
            self.store.save_search(user_id, search)
            return await self.menu(
                user_id,
                "Поиск приостановлен.\n\n"
                if search.paused
                else "Поиск возобновлён.\n\n",
            )
        if action == "sources":
            return await self.sources(user_id)
        if action in {"current", "favorites"}:
            return await self.current(user_id, action)
        if action == "status":
            return await self.status(user_id)
        await self.show(
            user_id,
            "<b>Как пользоваться</b>\n\n1. Откройте «Настроить поиск»: город, бюджет и комнаты.\n2. Посмотрите «Объявления» — варианты листаются по одному.\n3. Сохраните понравившиеся в избранное. Новые совпадения я пришлю сам.\n\nПервая проверка запоминает выдачу без массовой рассылки. Старые варианты доступны в подборке. Пауза останавливает только ваш поиск.\n\nУ некоторых сайтов бывают блокировки или неполная выдача. Это видно в состоянии сайтов. Цены и доступность уточняйте у автора.\n\nМожно писать команды:\n/price 1500 · /rooms 1.5 2.5\n/cities Wetzikon ZH, Uster\n/area 40 · /interval 3\n/exclude befristet, möbliert\n/cancel — отменить ввод\n/menu — вернуться на главную",
            buttons([[("Настроить поиск", "settings"), ("На главную", "home")]]),
        )
