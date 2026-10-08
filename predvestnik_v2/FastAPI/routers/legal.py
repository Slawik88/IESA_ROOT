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
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600&display=swap">
<style>
  :root {{ color-scheme: dark; --ink:#f3f4f7; --dim:#8a90a2; --acc:#d8cffd; --faint:rgba(255,255,255,.09); }}
  html {{ overflow-x: clip; }}
  body {{ margin:0 auto; background:#08090c; color:var(--ink);
    font:15px/1.65 'Onest',system-ui,-apple-system,"Segoe UI",sans-serif;
    padding:max(20px,env(safe-area-inset-top)) 20px calc(56px + env(safe-area-inset-bottom)); max-width:720px; overflow-wrap:anywhere; }}
  h1 {{ font-size:11px; font-weight:500; letter-spacing:.16em; text-transform:uppercase; color:var(--dim); margin:0 0 22px; }}
  h2 {{ font-size:24px; font-weight:600; letter-spacing:-.02em; line-height:1.2; margin:0 0 18px; }}
  h3 {{ font-size:16px; font-weight:600; margin:28px 0 8px; padding-top:20px; box-shadow:0 -1px 0 var(--faint); }}
  p {{ margin:8px 0; color:#c4c9d6; }}
  a {{ color:var(--acc); }}
  .ver {{ margin-top:36px; font-size:12px; color:var(--dim); padding-top:16px; box-shadow:0 -1px 0 var(--faint); }}
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
