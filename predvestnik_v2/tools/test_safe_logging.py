"""Regression contract: Telegram credentials never reach standard logs."""

import io
import logging
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.__main__ import _configure_safe_logging  # noqa: E402


token = "123456789:TEST_SECRET_VALUE"
url = f"https://api.telegram.org/bot{token}/getMe"
stream = io.StringIO()
root_logger = logging.getLogger()
old_handlers = list(root_logger.handlers)
old_level = root_logger.level
handler = logging.StreamHandler(stream)

try:
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    _configure_safe_logging()
    logging.getLogger("probe").warning("request failed: %s", url)
    try:
        raise RuntimeError(url)
    except RuntimeError:
        logging.getLogger("probe").exception("request raised")

    rendered = stream.getvalue()
    assert token not in rendered
    assert rendered.count("<redacted>") >= 2
finally:
    root_logger.handlers = old_handlers
    root_logger.setLevel(old_level)

print("OK: Telegram bot token redacted from messages and tracebacks")
