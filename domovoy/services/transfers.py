"""Перенос денег XLSX/CSV/TSV/JSON: единый контракт, предпросмотр и дедупликация."""
import asyncio
import csv
import hashlib
import io
import json
from dataclasses import dataclass

from core.constants import (
    MAX_CATEGORY_NAME_LEN, MAX_DESCRIPTION_LEN, TRANSFER_MAX_BYTES, TRANSFER_MAX_ROWS,
)
from core.money import AmountError, parse_amount
from infrastructure.repositories import transactions as repo
from services import households, settings, workbooks
from services.households import DomainError
from services.transaction_dates import parse_date, parse_month
from services.journal import JournalQuery, filter_rows

FORMATS = {"csv": ";", "tsv": "\t", "json": None, "xlsx": None}
FIELDS = (
    "source_key", "kind", "date", "month", "member_tg_id", "member_name",
    "amount", "category", "mode", "status", "reimbursed", "description", "currency",
)


@dataclass
class Preview:
    rows: list[dict]
    duplicates: int
    errors: list[str]
    balance_delta: int


def _fingerprint(row: dict) -> str:
    content = {key: value for key, value in row.items() if key not in ("source_key", "fingerprint", "member_name")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _protect_cell(value) -> str:
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _unprotect_cell(text: str) -> str:
    return text[1:] if text.startswith("'") and text[1:].lstrip().startswith(("=", "+", "-", "@")) else text


def template_file(extension: str) -> bytes:
    if extension not in FORMATS:
        raise DomainError("Выберите Excel, CSV, TSV или JSON")
    if extension == "xlsx":
        return workbooks.write_workbook(FIELDS, [])
    if extension == "json":
        return json.dumps({"format": "domovoy-money", "version": 1, "transactions": []}).encode()
    output = io.StringIO(newline="")
    csv.writer(output, delimiter=FORMATS[extension]).writerow(FIELDS)
    return output.getvalue().encode("utf-8-sig")


async def export_file(
    house_id: int, actor: int, extension: str, month: str | None = None, *, query: JournalQuery | None = None,
) -> bytes:
    await households.require_member(house_id, actor)
    if extension not in FORMATS:
        raise DomainError("Выберите Excel, CSV, TSV или JSON")
    if month:
        month = parse_month(month)
    currency = await settings.house_setting(house_id, "currency")
    rows = []
    source = await repo.all_rows(house_id)
    if query is not None:
        source = filter_rows(source, query)
    for item in source:
        if month and item["month"] != month:
            continue
        kop = int(item["amount_kop"])
        rows.append(dict(zip(FIELDS, (
            item["source_key"] or f"domovoy:{house_id}:{item['kind']}:{item['id']}",
            item["kind"], item["date"], item["month"], item["tg_id"], item["display_name"] or "",
            f"{kop // 100}.{kop % 100:02d}", item["category"] or "", item["mode"], item["status"],
            int(item["reimbursed"]), item["description"], currency,
        ))))
    if len(rows) > TRANSFER_MAX_ROWS:
        raise DomainError(f"Больше {TRANSFER_MAX_ROWS} операций. Выберите отдельный месяц.")
    if extension == "xlsx":
        result = await asyncio.to_thread(workbooks.write_workbook, FIELDS, rows)
    elif extension == "json":
        result = json.dumps({"format": "domovoy-money", "version": 1, "transactions": rows},
                            ensure_ascii=False, indent=2).encode("utf-8")
    else:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter=FORMATS[extension])
        writer.writeheader()
        writer.writerows({key: _protect_cell(value) for key, value in row.items()} for row in rows)
        result = output.getvalue().encode("utf-8-sig")
    if len(result) > TRANSFER_MAX_BYTES:
        raise DomainError("Экспорт слишком большой. Выберите отдельный месяц.")
    return result


def _read_file(content: bytes, extension: str) -> list[dict]:
    if len(content) > TRANSFER_MAX_BYTES:
        raise DomainError("Файл слишком большой. Максимум 2 МБ.")
    if extension not in FORMATS:
        raise DomainError("Пришлите файл .xlsx, .csv, .tsv или .json")
    if extension == "xlsx":
        rows = workbooks.read_workbook(content)
        if not rows:
            raise DomainError("В Excel нет операций. Заполните строки под заголовками.")
        return rows
    try:
        text = content.decode("utf-8-sig")
        if extension == "json":
            document = json.loads(text)
            if (not isinstance(document, dict) or document.get("format") != "domovoy-money"
                    or document.get("version") != 1):
                raise DomainError("Нужен JSON Домового версии 1. Скачайте шаблон в формате JSON.")
            rows = document.get("transactions")
            if not isinstance(rows, list):
                raise DomainError("В JSON отсутствует список transactions")
        else:
            separator = "\t" if extension == "tsv" else ";"
            if extension == "csv" and ";" not in text.splitlines()[0]:
                separator = ","
            reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=separator)
            if not {"kind", "date", "member_tg_id", "amount"}.issubset(reader.fieldnames or []):
                raise DomainError("Не хватает колонок kind, date, member_tg_id, amount. Скачайте шаблон.")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise DomainError("В строках разное число колонок. Проверьте разделитель и кавычки.")
                rows.append({key: _unprotect_cell(value) for key, value in row.items()})
                if len(rows) > TRANSFER_MAX_ROWS:
                    break
        if not rows or len(rows) > TRANSFER_MAX_ROWS:
            raise DomainError(f"В файле должно быть от 1 до {TRANSFER_MAX_ROWS} операций")
        return rows
    except (UnicodeError, json.JSONDecodeError, csv.Error, IndexError, RecursionError) as exc:
        raise DomainError("Не удалось прочитать файл. Нужен UTF-8 CSV/TSV или JSON Домового.") from exc


def normalize_row(raw: dict, today: str, currency: str, members: set[int]) -> dict:
    if not isinstance(raw, dict):
        raise DomainError("Операция должна содержать поля, а не строку или число")
    kind = str(raw.get("kind", "")).strip()
    if kind not in ("expense", "contribution"):
        raise DomainError("kind: expense — трата, contribution — взнос")
    member_raw = str(raw.get("member_tg_id", "")).strip()
    if not member_raw.isascii() or not member_raw.isdigit() or len(member_raw) > 19:
        raise DomainError("member_tg_id должен быть Telegram ID участника")
    member_id = int(member_raw)
    if member_id not in members:
        raise DomainError(f"Участник {member_id} отсутствует в доме. Сначала пригласите его.")
    if raw.get("currency") and raw["currency"] != currency:
        raise DomainError("Валюта файла отличается от валюты дома; конвертация не выполняется")
    amount_raw = raw.get("amount", "")
    if not isinstance(amount_raw, (str, int)) or isinstance(amount_raw, bool):
        raise DomainError("Сумма amount должна быть строкой, например 150.50")
    day = parse_date(str(raw.get("date", "")), today)
    category = str(raw.get("category") or "").strip()
    description = str(raw.get("description") or "").strip()
    if len(category) > MAX_CATEGORY_NAME_LEN or len(description) > MAX_DESCRIPTION_LEN:
        raise DomainError("Категория — до 24 символов, описание — до 200")
    mode = str(raw.get("mode", "house") or "house") if kind == "expense" else ""
    status = str(raw.get("status", "confirmed") or "confirmed")
    reimbursed_raw = raw.get("reimbursed", "0")
    if str(reimbursed_raw) not in ("0", "1"):
        raise DomainError("reimbursed: 0 — нет возврата, 1 — возвращено")
    reimbursed = int(reimbursed_raw)
    if mode not in ("", "house", "personal") or status not in ("confirmed", "declared", "rejected"):
        raise DomainError("Недопустимый режим или статус операции")
    if kind == "expense" and status != "confirmed":
        raise DomainError("У траты status должен быть confirmed")
    if reimbursed and (kind != "expense" or mode != "personal"):
        raise DomainError("Возврат допустим только для личной траты")
    row = {
        "kind": kind, "date": day, "month": parse_month(str(raw.get("month") or day[:7])),
        "member_tg_id": member_id, "amount_kop": parse_amount(str(amount_raw)),
        "category": category if kind == "expense" else "", "mode": mode, "status": status,
        "reimbursed": reimbursed, "description": description if kind == "expense" else "", "currency": currency,
    }
    if kind == "expense" and row["month"] != day[:7]:
        raise DomainError("Месяц траты должен совпадать с её датой")
    fingerprint = _fingerprint(row)
    source_key = str(raw.get("source_key", "")).strip() or f"manual:{fingerprint}"
    if len(source_key) > 160:
        raise DomainError("source_key слишком длинный (до 160 символов)")
    return {**row, "source_key": source_key, "fingerprint": fingerprint}


async def preview_import(house_id: int, actor: int, content: bytes, extension: str) -> Preview:
    await households.require(house_id, actor, "import_transactions")
    raw_rows = await asyncio.to_thread(_read_file, content, extension)
    current = await settings.house_settings(house_id)
    members = {member["tg_id"] for member in await households.members(house_id)}
    known = await repo.imported_keys(house_id)
    # Экспорт своих уже существующих операций тоже не должен создавать копии.
    for row in await repo.all_rows(house_id):
        key = row["source_key"] or f"domovoy:{house_id}:{row['kind']}:{row['id']}"
        # Журнал запросов хранит исходное намерение для безопасного повтора POST.
        # Экспорт же сравнивается с текущим состоянием, в том числе после возврата/правки.
        kop = int(row["amount_kop"])
        canonical = normalize_row({
            **dict(row), "member_tg_id": row["tg_id"], "amount": f"{kop // 100}.{kop % 100:02d}",
            "currency": current["currency"], "source_key": key,
        }, settings.house_today(current), current["currency"], members | {row["tg_id"]})
        known[key] = canonical["fingerprint"]
    rows, errors = [], []
    duplicates = delta = 0
    for index, raw in enumerate(raw_rows, 2 if extension != "json" else 1):
        if extension == "xlsx":
            index = raw["_xlsx_row"]
        try:
            row = normalize_row(raw, settings.house_today(current), current["currency"], members)
            previous = known.get(row["source_key"])
            if previous is not None:
                if previous != row["fingerprint"]:
                    raise DomainError("source_key уже существует с другими данными; измените ключ новой операции")
                duplicates += 1
                continue
            known[row["source_key"]] = row["fingerprint"]
            rows.append(row)
            if row["kind"] == "contribution" and row["status"] == "confirmed":
                delta += row["amount_kop"]
            elif row["kind"] == "expense" and (row["mode"] == "house" or row["reimbursed"]):
                delta -= row["amount_kop"]
        except (DomainError, AmountError) as exc:
            errors.append(f"Строка {index}: {exc}")
    return Preview(rows, duplicates, errors, delta)


async def import_file(house_id: int, actor: int, content: bytes, extension: str) -> tuple[int, int]:
    preview = await preview_import(house_id, actor, content, extension)
    if preview.errors:
        raise DomainError("Файл не записан. " + "\n".join(preview.errors[:5]))
    try:
        added, skipped = await repo.apply_import(house_id, actor, preview.rows)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    return added, skipped + preview.duplicates
