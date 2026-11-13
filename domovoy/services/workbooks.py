"""Ограниченный XLSX-адаптер общего контракта переноса денежных записей."""
import io
import posixpath
from datetime import date, datetime
from decimal import Decimal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.exceptions import IllegalCharacterError, InvalidFileException
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

from core.constants import (
    TRANSFER_MAX_ROWS, WORKBOOK_MAX_COLUMNS, WORKBOOK_MAX_PARTS, WORKBOOK_MAX_UNPACKED_BYTES,
)
from services.households import DomainError

SHEET_NAME = "Операции"


def write_workbook(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET_NAME
    sheet.append(fields)
    for row in rows:
        try:
            sheet.append([str(row[field]) for field in fields])
        except IllegalCharacterError as exc:
            raise DomainError("В записи есть непечатаемые символы. Для неё используйте экспорт JSON.") from exc
        for cell in sheet[sheet.max_row]:
            # Explicit strings preserve long IDs, exact decimals and literal '=…' text.
            cell.data_type = "s"
            cell.number_format = "@"
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="302348")
        cell.font = Font(color="FFFFFF", bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, field in enumerate(fields, 1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = 36 if field == "description" else 23
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def _validate_archive(content: bytes) -> None:
    with ZipFile(io.BytesIO(content)) as archive:
        parts = archive.infolist()
        if (len(parts) > WORKBOOK_MAX_PARTS or
                sum(part.file_size for part in parts) > WORKBOOK_MAX_UNPACKED_BYTES):
            raise DomainError("Книга Excel слишком большая после распаковки. Сохраните только лист с операциями.")
        if len({part.filename for part in parts}) != len(parts):
            raise DomainError("Книга Excel повреждена: повторяющиеся части.")
        types = fromstring(archive.read("[Content_Types].xml"))
        main_parts = [item.attrib.get("PartName") for item in types
                      if item.attrib.get("ContentType", "").endswith("spreadsheetml.sheet.main+xml")]
        if main_parts != ["/xl/workbook.xml"]:
            raise DomainError("Нужна стандартная книга XLSX. Сохраните операции в нашем шаблоне.")
        checked_sheets = {part.filename for part in parts
                          if part.filename.startswith("xl/worksheets/") and part.filename.endswith(".xml")}
        relationships = fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for relation in relationships:
            if relation.attrib.get("Type", "").endswith("/worksheet"):
                target = relation.attrib.get("Target", "")
                resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                             else posixpath.join("xl", target))
                if relation.attrib.get("TargetMode") == "External" or resolved not in checked_sheets:
                    raise DomainError("Нестандартный лист Excel. Перенесите значения в наш шаблон.")
        for part in parts:
            if part.flag_bits & 1 or "vbaproject" in part.filename.lower():
                raise DomainError("Нужен обычный XLSX без пароля и макросов.")
            if part.filename.startswith("xl/worksheets/") and part.filename.endswith(".xml"):
                root = fromstring(archive.read(part))
                row_count = 0
                for element in root.iter():
                    local = element.tag.rsplit("}", 1)[-1]
                    if local == "row":
                        row_count += 1
                        if (row_count > TRANSFER_MAX_ROWS + 1 or
                                not 1 <= int(element.attrib.get("r", 0)) <= TRANSFER_MAX_ROWS + 1):
                            raise DomainError(f"В Excel максимум {TRANSFER_MAX_ROWS} строк. Удалите лишние строки.")
                        if len(element) > WORKBOOK_MAX_COLUMNS:
                            raise DomainError("Слишком много ячеек в строке Excel. Используйте шаблон.")
                    if local == "c":
                        column, row_number = coordinate_from_string(element.attrib["r"])
                        if (column_index_from_string(column) > WORKBOOK_MAX_COLUMNS or
                                row_number > TRANSFER_MAX_ROWS + 1):
                            raise DomainError("Лист Excel выходит за допустимые размеры. Используйте шаблон.")


def _bounded_archive(content: bytes) -> bytes:
    """Never give a library the original ZIP: its size declarations are untrusted."""
    output = io.BytesIO()
    with ZipFile(io.BytesIO(content)) as source, ZipFile(output, "w") as target:
        parts = source.infolist()
        if len(parts) > WORKBOOK_MAX_PARTS or len({part.filename for part in parts}) != len(parts):
            raise DomainError("В книге Excel слишком много частей или есть повторяющиеся части.")
        remaining = WORKBOOK_MAX_UNPACKED_BYTES
        for part in parts:
            if part.flag_bits & 1:
                raise DomainError("Нужен XLSX без пароля.")
            if part.file_size > remaining:
                raise DomainError("Книга Excel слишком большая после распаковки. Используйте шаблон.")
            with source.open(part) as stream:
                data = stream.read(remaining + 1)
            if len(data) > remaining:
                raise DomainError("Книга Excel слишком большая после распаковки. Используйте шаблон.")
            remaining -= len(data)
            target.writestr(part.filename, data)
    return output.getvalue()


def _value(cell, field: str) -> str:
    if cell.data_type in ("f", "e"):
        raise DomainError("В Excel есть формулы или ошибки ячеек. Вставьте значения вместо формул.")
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m" if field == "month" else "%Y-%m-%d")
    if field == "amount" and isinstance(value, (float, int)) and not isinstance(value, bool):
        return format(Decimal(str(value)), "f")
    if field == "member_tg_id" and isinstance(value, (int, float)):
        if isinstance(value, bool) or value != int(value) or abs(value) >= 10**15:
            raise DomainError("Длинный member_tg_id сохраните как текст: Excel может округлить ID.")
        return str(int(value))
    if field == "reimbursed" and isinstance(value, bool):
        return str(int(value))
    return str(value)


def read_workbook(content: bytes) -> list[dict]:
    book = None
    try:
        content = _bounded_archive(content)
        _validate_archive(content)
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
        if book.sheetnames != [SHEET_NAME] or len(book.worksheets) != 1:
            raise DomainError(f"В книге нужен один лист «{SHEET_NAME}». Скачайте шаблон Excel.")
        sheet = book[SHEET_NAME]
        sheet.reset_dimensions()
        source = sheet.iter_rows(max_col=WORKBOOK_MAX_COLUMNS)
        header_cells = next(source, ())
        fields = [_value(cell, "header").strip() for cell in header_cells]
        while fields and not fields[-1]:
            fields.pop()
        if (not {"kind", "date", "member_tg_id", "amount"}.issubset(fields) or
                len(fields) != len(set(fields)) or "" in fields):
            raise DomainError("Проверьте заголовки колонок Excel. Скачайте шаблон.")
        rows = []
        for row_number, cells in enumerate(source, 2):
            if row_number > TRANSFER_MAX_ROWS + 1:
                raise DomainError(f"В Excel максимум {TRANSFER_MAX_ROWS} строк. Удалите лишние строки.")
            if not any(cell.value is not None for cell in cells):
                continue
            if any(cell.value is not None for cell in cells[len(fields):]):
                raise DomainError("В Excel есть данные без заголовка колонки.")
            row = {field: _value(cell, field) for field, cell in zip(fields, cells)}
            row["_xlsx_row"] = row_number
            rows.append(row)
            if len(rows) > TRANSFER_MAX_ROWS:
                raise DomainError(f"В Excel максимум {TRANSFER_MAX_ROWS} операций.")
        return rows
    except (BadZipFile, ParseError, DefusedXmlException, InvalidFileException,
            KeyError, ValueError, TypeError, OSError, IndexError, OverflowError, NotImplementedError) as exc:
        raise DomainError("Не удалось прочитать Excel. Нужен неповреждённый XLSX без пароля.") from exc
    finally:
        if book is not None:
            book.close()
