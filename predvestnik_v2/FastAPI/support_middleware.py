"""Safe HTTP breadcrumbs with server-generated correlation IDs and auth binding."""
import time
import traceback
from pathlib import Path
from uuid import uuid4
from loguru import logger

from core.support_reports import safe_route
from services.support_diagnostics import recent


async def record_request(request, call_next):
    path = request.url.path
    excluded = path.startswith(("/static/","/bot-admin/","/support/")) or path in {"/api/health","/api/ready"}
    if excluded:
        response = await call_next(request)
        if path.startswith(("/support/","/bot-admin/api/diagnostics")):
            response.headers["Cache-Control"] = "no-store"
        return response
    request_id = str(uuid4())
    request.state.support_request_id = request_id
    started = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Diagnostic-Route"] = safe_route(getattr(request.scope.get("route"),"path",path))
        if getattr(request.state,"support_user_id",0):
            response.headers["X-Support-Owner"] = str(request.state.support_user_id)
        return response
    except Exception as error:
        frames = [f"{Path(frame.filename).name}:{frame.lineno}:0" for frame in traceback.extract_tb(error.__traceback__)[-8:]]
        recent.record(getattr(request.state,"support_user_id",0),"runtime",
                      {"error_kind":type(error).__name__,"request_id":request_id,"frames":frames})
        logger.error("Support trace request={} route={} exception={}",request_id,safe_route(path),type(error).__name__)
        raise
    finally:
        recent.record(getattr(request.state,"support_user_id",0),"request",
                      {"route":safe_route(getattr(request.scope.get("route"),"path",path)),
                       "method":request.method,"status":status,"duration_ms":int((time.monotonic()-started)*1000),"request_id":request_id})
