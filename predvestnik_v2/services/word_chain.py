"""A shared, persistent word game. Activity uses ordinary chat tracking only."""
import secrets

from core import word_chain as rules
from infrastructure.repositories import word_chain as repo


class WordChainError(ValueError):
    pass


def _scope(chat_id: int, topic_id: int) -> None:
    if chat_id >= 0 or topic_id < 0:
        raise WordChainError("Игра работает в группе. В каждой теме своя партия.")


def _choose(letter: str, used: set[str]) -> str | None:
    available = [w for w in rules.BY_LETTER.get(letter, ()) if w not in used]
    if not available:
        return None
    common = [w for w in rules.COMMON_WORDS if w.startswith(letter) and w not in used]
    # Prefer a familiar noun that leaves the player at least one legal answer.
    playable = [w for w in common if any(n not in used and n != w for n in rules.BY_LETTER.get(rules.next_letter(w), ()))]
    candidates = playable or [w for w in available if any(n not in used and n != w for n in rules.BY_LETTER.get(rules.next_letter(w), ()))]
    return secrets.choice(candidates) if candidates else None


async def _current(db, chat_id: int, topic_id: int) -> dict | None:
    row = await repo.active(db,chat_id,topic_id)
    if row and row["expired"]:
        await repo.finish(db,int(row["id"]),"expired")
        return None
    return row


async def _view(db, row: dict | None) -> dict:
    if not row:
        return {"active": False}
    return {"active": row["status"]=="active","round_id":int(row["id"]),"last_word":row["last_word"],
            "letter":rules.next_letter(row["last_word"]),"turns":int(row["turns"]),
            "leaders":await repo.leaders(db,int(row["id"]))}


async def start(db, *, chat_id: int, topic_id: int, actor: int) -> dict:
    _scope(chat_id,topic_id)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock(db,chat_id,topic_id)
        if await repo.paused(db,chat_id,topic_id):
            raise WordChainError("Чат закрыт или идёт Мафия. Продолжи игру, когда участники снова смогут писать.")
        row = await _current(db,chat_id,topic_id)
        if row:
            return {**await _view(db,row),"created":False}
        word = secrets.choice(rules.COMMON_WORDS)
        row = await repo.create(db,chat_id,topic_id,actor,word)
        return {**await _view(db,row),"created":True}


async def status(db, *, chat_id: int, topic_id: int, hint: bool = False) -> dict:
    _scope(chat_id,topic_id)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock(db,chat_id,topic_id)
        row = await _current(db,chat_id,topic_id)
        if not row:
            previous = await repo.latest(db,chat_id,topic_id)
            return {**await _view(db,previous),"last_round":bool(previous)}
        result = await _view(db,row)
        if hint and row:
            used = await repo.used(db,int(row["id"]))
            result["hints"] = [w for w in rules.COMMON_WORDS if w.startswith(result["letter"]) and w not in used][:3]
            if not result["hints"]:
                result["hints"] = [w for w in rules.BY_LETTER.get(result["letter"],()) if w not in used][:3]
        return result


async def play(db, *, chat_id: int, topic_id: int, actor: int, message_id: int, value: str) -> dict:
    _scope(chat_id,topic_id)
    word = rules.normalize(value)
    if not rules.WORD_RE.fullmatch(word):
        raise WordChainError("Пришли одно русское существительное: 2–32 буквы, без пробелов, цифр и дефисов.")
    if word not in rules.WORDS:
        raise WordChainError("Такого слова нет в словаре игры. Проверь написание или напиши «бот слова, подсказка».")
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock(db,chat_id,topic_id)
        previous = await repo.receipt(db,chat_id,topic_id,message_id)
        if previous:
            if previous["word"] != word or previous["actor"] != actor:
                raise WordChainError("Этот ход уже записан с другим словом или игроком.")
            return {**previous,"replayed":True}
        row = await _current(db,chat_id,topic_id)
        if not row:
            raise WordChainError("Партии нет или сутки никто не играл. Начни новую: «бот слова».")
        if await repo.paused(db,chat_id,topic_id):
            raise WordChainError("Игра ждёт: чат закрыт или идёт Мафия. Слова и счёт сохранятся.")
        letter = rules.next_letter(row["last_word"])
        if not word.startswith(letter):
            raise WordChainError(f"Сейчас нужно слово на «{letter.upper()}»: последнее слово — {row['last_word']}.")
        used = await repo.used(db,int(row["id"]))
        if word in used:
            raise WordChainError("Это слово уже было в этой партии. Выбери другое или попроси подсказку.")
        if await repo.cooling_down(db,int(row["id"]),actor,rules.TURN_COOLDOWN_SECONDS):
            raise WordChainError(f"Подожди {rules.TURN_COOLDOWN_SECONDS} секунды между своими ходами. Другие игроки могут ходить сейчас.")
        used.add(word)
        bot_word = _choose(rules.next_letter(word),used) if int(row["turns"])+1 < rules.MAX_TURNS else None
        result = {"active":bool(bot_word),"round_id":int(row["id"]),"word":word,"bot_word":bot_word,
                  "letter":rules.next_letter(bot_word) if bot_word else None,"turns":int(row["turns"])+1,
                  "finished":not bool(bot_word),"replayed":False,"actor":actor}
        await repo.save_move(db,int(row["id"]),message_id,actor,word,result)
        if result["finished"]:
            result["leaders"] = await repo.leaders(db,int(row["id"]))
            await repo.save_reply(db,int(row["id"]),message_id,result)
        return result


async def stop(db, *, chat_id: int, topic_id: int, actor: int, can_moderate: bool) -> dict:
    _scope(chat_id,topic_id)
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock(db,chat_id,topic_id)
        row = await _current(db,chat_id,topic_id)
        if not row:
            raise WordChainError("Игра сейчас не идёт. Начать: «бот слова».")
        if actor != int(row["initiator_id"]) and not can_moderate:
            raise WordChainError("Завершить партию может тот, кто её начал, или администратор чата.")
        result = await _view(db,row)
        await repo.finish(db,int(row["id"]))
        return {**result,"active":False}
