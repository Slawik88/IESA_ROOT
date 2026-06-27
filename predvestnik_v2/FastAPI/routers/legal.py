"""FastAPI/routers/legal.py — юридические документы (БЛОК22).

  GET  /legal/{slug}        — самостоятельная HTML-страница (ПРЯМАЯ публичная
                              ссылка: открывается из инлайн-кнопки бота и в браузере).
  GET  /legal/{slug}/text   — JSON {title, html} для рендера в модалке Web App
                              (чтобы не уходить из мини-аппа).
  POST /legal/accept        — зафиксировать принятие документов текущим веб-юзером.

slug ∈ {"tos", "privacy"}. Источник текста — core/legal.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from core.legal import get_doc, doc_to_html, LEGAL_VERSION
from infrastructure.repositories import users as users_repo
from FastAPI.deps import get_db, require_tg_user

router = APIRouter(prefix="/legal", tags=["legal"])

_PAGE = """<!doctype html><html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} — PREDVESTNIK</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0a0b12; color:#e7ecf4;
    font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    padding:20px 16px 56px; max-width:760px; margin:0 auto; }}
  h1 {{ font-size:13px; letter-spacing:2px; text-transform:uppercase;
    color:#c9a84c; margin:0 0 18px; }}
  h2 {{ font-size:19px; color:#f0d27a; margin:26px 0 14px; }}
  h3 {{ font-size:15px; color:#dbe2ee; margin:20px 0 8px; }}
  p {{ margin:6px 0; color:#c0c8d6; }}
  a {{ color:#8ab4ff; }}
  .ver {{ margin-top:34px; font-size:12px; color:#6b7585; border-top:1px solid #1c2030; padding-top:14px; }}
</style></head><body>
<h1>PREDVESTNIK · Юридические документы</h1>
{body}
<div class="ver">Версия документов: {ver}</div>
</body></html>"""


def _resolve(slug: str) -> dict:
    doc = get_doc(slug)
    if not doc:
        raise HTTPException(404, "Документ не найден.")
    return doc


@router.get("/{slug}", response_class=HTMLResponse)
async def legal_page(slug: str):
    """Самостоятельная HTML-страница документа (прямая публичная ссылка)."""
    doc = _resolve(slug)
    html = _PAGE.format(title=doc["title"], body=doc_to_html(doc["md"]), ver=LEGAL_VERSION)
    return HTMLResponse(html)


@router.get("/{slug}/text")
async def legal_text(slug: str):
    """JSON для рендера документа в модалке Web App."""
    doc = _resolve(slug)
    return {"title": doc["title"], "emoji": doc["emoji"],
            "html": doc_to_html(doc["md"]), "version": LEGAL_VERSION}


@router.post("/accept")
async def legal_accept(db=Depends(get_db), user=Depends(require_tg_user)):
    """Зафиксировать принятие ToS/Privacy текущим веб-пользователем."""
    await users_repo.accept_tos(db, int(user["id"]), user.get("username"))
    return JSONResponse({"ok": True, "version": LEGAL_VERSION})
