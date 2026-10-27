"""Developer-only report triage, including export and audited state changes."""
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from infrastructure.repositories import support_reports as repo
from services import support_reports

router = APIRouter(prefix="/bot-admin/api/diagnostics",tags=["bot-admin"],route_class=AdminRoute)
staff = section("diagnostics")


@router.get("")
async def listing(status: str = "", category: str = "", page: int = 0, user=Depends(staff), db=Depends(get_db)):
    return await support_reports.listing(db,status=status,category=category,page=page)


@router.get("/{report_id}")
async def detail(report_id: UUID, user=Depends(staff), db=Depends(get_db)):
    await support_reports.storage.prepare(db)
    result = await repo.get(db,str(report_id))
    if result is None:
        raise HTTPException(404,"Отчёт не найден.")
    return result


@router.get("/{report_id}/download")
async def download(report_id: UUID, user=Depends(staff), db=Depends(get_db)):
    result = await detail(report_id,user,db)
    return JSONResponse(result,headers={"Content-Disposition":f'attachment; filename="{result["code"]}.json"',"Cache-Control":"no-store"})


@router.post("/{report_id}/status")
async def change_status(report_id: UUID, data: dict = Body(...), user=Depends(staff), db=Depends(get_db)):
    if not await support_reports.set_status(db,str(report_id),data.get("status",""),int(user["id"])):
        raise HTTPException(404,"Отчёт не найден.")
    return {"ok":True}
