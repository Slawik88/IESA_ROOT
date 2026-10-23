"""Safe text cells for spreadsheet-compatible CSV downloads."""


def safe_csv_text(value):
    """Keep user text from becoming a formula when opened in a spreadsheet."""
    value = str(value)
    if value.lstrip(' ').startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value
