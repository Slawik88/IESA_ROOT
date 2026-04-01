"""
utils/bot_logging.py — централизованная конфигурация логирования.

Call setup_logging() once at bot startup (before anything else).
After that every module can simply do:
    import logging
    log = logging.getLogger(__name__)
and get richly-formatted, timestamped, leveled output.

Log levels:
  DEBUG   — every DB query, every middleware step, every scheduler tick detail
  INFO    — normal lifecycle events (bot started, task ran, user registered)
  WARNING — recoverable problems (failed send, skipped task)
  ERROR   — unhandled exceptions inside tasks / handlers
  CRITICAL— fatal startup failures

Format on Linux/server:
  2026-04-01 18:27:32.123 [ERROR   ] aiogram.event            — message here
  (includes exception traceback on ERROR+)
"""

import logging
import sys
from logging import Formatter, StreamHandler

# ─── Colour codes (stripped automatically when not a TTY) ────────────────────
_GREY    = "\033[37m"
_CYAN    = "\033[36m"
_YELLOW  = "\033[33m"
_RED     = "\033[31m"
_BRED    = "\033[31;1m"
_RESET   = "\033[0m"

_LEVEL_COLOURS = {
    logging.DEBUG:    _GREY,
    logging.INFO:     _CYAN,
    logging.WARNING:  _YELLOW,
    logging.ERROR:    _RED,
    logging.CRITICAL: _BRED,
}


class _ColourFormatter(Formatter):
    """Human-readable coloured formatter for TTY output."""

    FMT = "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)-32s — %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, use_colour: bool = True):
        super().__init__(self.FMT, datefmt=self.DATEFMT)
        self._use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if self._use_colour:
            colour = _LEVEL_COLOURS.get(record.levelno, "")
            msg = f"{colour}{msg}{_RESET}"
        return msg


def setup_logging(level: int = logging.DEBUG) -> None:
    """Configure root logger + opinionated per-library levels.

    Call this once at the very top of main.py before any imports that log.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (e.g. from basicConfig)
    for h in root.handlers[:]:
        root.removeHandler(h)

    use_colour = sys.stderr.isatty()
    handler = StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(_ColourFormatter(use_colour=use_colour))
    root.addHandler(handler)

    # ── Third-party library noise reduction ────────────────────────────────
    # Keep aiogram at DEBUG so we see every update, but silence its
    # hyper-verbose sub-loggers that add no value.
    logging.getLogger("aiogram").setLevel(logging.DEBUG)
    logging.getLogger("aiogram.dispatcher").setLevel(logging.DEBUG)
    logging.getLogger("aiogram.event").setLevel(logging.DEBUG)

    # asyncpg connection pool lifecycle — INFO is enough
    logging.getLogger("asyncpg").setLevel(logging.INFO)

    # aiohttp internal machinery — WARNING is enough
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    # Django / Daphne ASGI (runs in same process on the server)
    logging.getLogger("django").setLevel(logging.INFO)
    logging.getLogger("daphne").setLevel(logging.INFO)

    logging.getLogger(__name__).debug("Logging initialised — level %s", logging.getLevelName(level))
