"""Release identity and delivery of the text assets served by the Mini App.

Every file is prepared once when the process starts: JS loses comments and indentation (`minify_js`), JSON its spaces, and the result is gzipped
once instead of on every request. Each file carries its own content hash (`StaticAsset.version`): a page links `/static/<name>?v=<version>`,
so a deploy that changes one file makes clients download only that file again.
"""
import gzip
import json
import os
from hashlib import sha256
from pathlib import Path
from collections.abc import Iterable
from typing import NamedTuple

from fastapi import Request, Response

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


def asset_version(directory: str | Path, names: Iterable[str]) -> str:
    """Hash delivered contents in order, independent of buildpack file times."""
    digest = sha256()
    for name in dict.fromkeys(names):
        # Match _read_static's newline handling on Windows and Linux.
        content = (Path(directory) / name).read_text(encoding="utf-8").encode("utf-8")
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()[:20]


class StaticAsset(NamedTuple):
    body: bytes
    gzipped: bytes | None     # None when gzip would not make it smaller
    etag: str
    version: str
    media_type: str


def prepare(text: str, media_type: str) -> StaticAsset:
    body = text.encode("utf-8")
    version = sha256(body).hexdigest()[:16]
    packed = gzip.compress(body, compresslevel=9, mtime=0)
    return StaticAsset(body, packed if len(packed) < len(body) else None, f'"{version}"', version, media_type)


def _accepts_gzip(request: Request) -> bool:
    for part in request.headers.get("accept-encoding", "").lower().split(","):
        coding, _, params = part.strip().partition(";")
        if coding.strip() in ("gzip", "*"):
            quality = params.strip().removeprefix("q=").strip()
            return quality not in ("0", "0.0", "0.00", "0.000")
    return False


def _etag_matches(request: Request, etag: str) -> bool:
    # a proxy that re-compresses the body may hand the browser a weak validator (W/"…"); it still names the same bytes
    header = request.headers.get("if-none-match", "")
    return any(tag.strip().removeprefix("W/") == etag or tag.strip() == "*" for tag in header.split(",")) if header else False


def respond(asset: StaticAsset, request: Request) -> Response:
    """The asset with its validator: cached for a year under a versioned address (`?v=`, pages always link the current one), revalidated otherwise (304 while unchanged)."""
    headers = {"ETag": asset.etag, "Vary": "Accept-Encoding", "Cache-Control": IMMUTABLE if request.query_params.get("v") else REVALIDATE}
    if _etag_matches(request, asset.etag):
        return Response(status_code=304, headers=headers)
    if asset.gzipped is not None and _accepts_gzip(request):
        return Response(asset.gzipped, media_type=asset.media_type, headers={**headers, "Content-Encoding": "gzip"})
    return Response(asset.body, media_type=asset.media_type, headers=headers)


def compact_json(text: str) -> str:
    return json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))


# Words after which a slash starts a regular expression, not a division.
_REGEX_AFTER_WORDS = frozenset("return typeof instanceof in of new delete void throw case do else yield await".split())


class _Unsure(Exception):
    """The source has a construct the minifier will not guess about: the file is served as it is."""


def minify_js(source: str) -> str:
    """Drop comments, indentation and runs of spaces; strings, template literals and regular expressions are copied byte for byte.

    Every line break stays where it was, so automatic semicolon insertion sees the same code and an error reports the same line number
    as in the unminified bundle (only columns move). Names are never touched: inline handlers and `_GV_GO` keep reaching the globals.
    PV_MINIFY_JS=0 serves the sources as they are (an emergency switch); anything the scanner is not sure about does the same.
    """
    if os.getenv("PV_MINIFY_JS", "1").strip() == "0":
        return source
    try:
        return _minify(source)
    except _Unsure:
        return source


def _minify(src: str) -> str:
    out: list[str] = []
    n, i = len(src), 0
    last = ""            # last significant character written (decides regex or division)
    last_word = ""       # last identifier written, when `last` ends one
    braces: list[str] = []   # "{" for a code block, "${" for a placeholder inside a template literal
    pending_space = False
    at_line_start = True

    def emit(text: str) -> None:
        nonlocal pending_space, at_line_start, last
        if pending_space and not at_line_start:
            out.append(" ")
        pending_space = False
        at_line_start = False
        out.append(text)
        last = text[-1]

    def template(j: int) -> int:
        """Copy template text from its opening backtick (or the `}` closing a placeholder) up to its end or to the next `${`, which returns into code."""
        start = j
        j += 1
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                emit(src[start:j + 1])
                return j + 1
            if c == "$" and j + 1 < n and src[j + 1] == "{":
                emit(src[start:j + 2])
                braces.append("${")
                return j + 2
            j += 1
        raise _Unsure("unterminated template literal")

    while i < n:
        c = src[i]
        if c == "\n":
            out.append("\n")
            pending_space, at_line_start = False, True
            i += 1
        elif c in " \t\r\f\v ﻿":
            pending_space = True
            i += 1
        elif c == "/" and src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
        elif c == "/" and src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                raise _Unsure("unterminated comment")
            out.append("\n" * src.count("\n", i, end))
            if "\n" in src[i:end]:
                pending_space, at_line_start = False, True
            else:
                pending_space = True
            i = end + 2
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                elif src[j] == "\n":
                    raise _Unsure("line break in a string")
                j += 1
            if j >= n:
                raise _Unsure("unterminated string")
            emit(src[i:j + 1])
            last_word = ""
            i = j + 1
        elif c == "`":
            i = template(i)
            last_word = ""
        elif c == "/" and (not last or last in "(,=:[!&|?{};+-*%<>~^" or last_word in _REGEX_AFTER_WORDS):
            j, in_class = i + 1, False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "\n":
                    raise _Unsure("line break in a regular expression")
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                j += 1
            j += 1
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            emit(src[i:j])
            last_word = ""
            i = j
        elif c.isalnum() or c in "_$" or ord(c) > 127:
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in "_$" or ord(src[j]) > 127) and src[j] not in " ﻿":
                j += 1
            word = src[i:j]
            emit(word)
            last_word = word
            i = j
        elif c == "{":
            braces.append("{")
            emit(c)
            last_word = ""
            i += 1
        elif c == "}":
            if not braces:
                raise _Unsure("unbalanced braces")
            if braces.pop() == "${":
                # back inside the template literal: copy from this brace on as its text
                pending_space = False
                i = template(i)
            else:
                emit(c)
                last_word = ""
                i += 1
        else:
            emit(c)
            last_word = ""
            i += 1
    if braces:
        raise _Unsure("unbalanced braces")
    return "".join(out)
