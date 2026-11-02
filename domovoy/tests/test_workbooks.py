"""Excel-native values, exact money and bounded malformed workbook handling."""
import io
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from openpyxl import Workbook, load_workbook

from core.constants import TRANSFER_MAX_ROWS, WORKBOOK_MAX_UNPACKED_BYTES
from services import transfers, workbooks
from services.households import DomainError


def workbook_content(values, *, extra_sheet=False, far_row=None):
    book = Workbook()
    sheet = book.active
    sheet.title = "Операции"
    sheet.append(["kind", "date", "member_tg_id", "amount", "month", "description"])
    sheet.append(values)
    if extra_sheet:
        book.create_sheet("Другой лист")
    if far_row:
        sheet.cell(far_row, 1, "expense")
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_native_excel_date_numeric_amount_and_long_text_id():
    content = workbook_content(["expense", datetime(2026, 10, 12), "1234567890123456789", .29,
                                datetime(2026, 10, 1), "Чек"])
    row = workbooks.read_workbook(content)[0]
    assert row["date"] == "2026-10-12" and row["month"] == "2026-10"
    normalized = transfers.normalize_row(row, "2026-11-02", "CHF", {1234567890123456789})
    assert normalized["amount_kop"] == 29


def test_export_literal_formula_and_long_ids_are_text_not_executable():
    row = dict.fromkeys(transfers.FIELDS, "")
    row.update(member_tg_id="1234567890123456789", amount="0.29", description="=HYPERLINK(\"https://bad\")")
    content = workbooks.write_workbook(transfers.FIELDS, [row])
    book = load_workbook(io.BytesIO(content), data_only=False)
    for field in ("member_tg_id", "amount", "description"):
        cell = book.active.cell(2, transfers.FIELDS.index(field) + 1)
        assert cell.data_type == "s" and cell.value == row[field]
    assert workbooks.read_workbook(content)[0]["description"] == row["description"]
    book.close()


@pytest.mark.parametrize("values", [
    ["expense", "2026-10-12", "100", "=1+2", "", ""],
    ["expense", "2026-10-12", 12345678901234567, 10, "", ""],
])
def test_import_rejects_formula_and_rounded_numeric_ids(values):
    with pytest.raises(DomainError):
        workbooks.read_workbook(workbook_content(values))


@pytest.mark.parametrize("options", [{"extra_sheet": True}, {"far_row": TRANSFER_MAX_ROWS + 2}])
def test_sheet_scope_and_row_bounds_cannot_silently_drop_data(options):
    with pytest.raises(DomainError):
        workbooks.read_workbook(workbook_content(["expense", "2026-10-12", "100", "10"], **options))


def test_compressed_bomb_and_corrupt_file_are_domain_errors():
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"A" * (WORKBOOK_MAX_UNPACKED_BYTES + 1))
    for content in (output.getvalue(), b"broken xlsx"):
        with pytest.raises(DomainError):
            workbooks.read_workbook(content)


def test_nonstandard_worksheet_target_cannot_bypass_row_limits():
    content = workbook_content(["expense", "2026-10-12", "100", "10"], far_row=TRANSFER_MAX_ROWS + 2)
    output = io.BytesIO()
    with ZipFile(io.BytesIO(content)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for part in source.infolist():
            data = source.read(part)
            name = part.filename
            if name == "xl/worksheets/sheet1.xml":
                name = "xl/custom-sheet.xml"
            elif name in ("xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
                data = data.replace(b"/xl/worksheets/sheet1.xml", b"/xl/custom-sheet.xml")
            target.writestr(name, data)
    with pytest.raises(DomainError, match="Нестандартный лист"):
        workbooks.read_workbook(output.getvalue())


def test_empty_template_has_clear_error_and_one_thousand_rows_fit():
    with pytest.raises(DomainError, match="нет операций"):
        transfers._read_file(transfers.template_file("xlsx"), "xlsx")
    row = dict.fromkeys(transfers.FIELDS, "")
    row.update(kind="expense", date="2026-10-12", member_tg_id="100", amount="10.00")
    assert len(transfers._read_file(workbooks.write_workbook(transfers.FIELDS,
                                                           [row] * TRANSFER_MAX_ROWS), "xlsx")) == TRANSFER_MAX_ROWS
