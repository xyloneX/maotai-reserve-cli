"""批量发码、批量登录、待登录看板。"""

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.response import fail, ok
from ...models.entities import Account, Job
from ...services.batch_login_service import (
    cancel_batch_job,
    login_stats,
    parse_login_csv,
    run_batch_login_async,
    run_batch_vcode_async,
)
from ...services.imaotai_service import mask_mobile_api
from ..deps import get_current_user

router = APIRouter(prefix="/accounts/batch", tags=["批量登录"])


class BatchVcodeBody(BaseModel):
    account_ids: list[int] = Field(default_factory=list)
    all_unlogged: bool = True
    interval_seconds: float | None = None


class LoginPair(BaseModel):
    account_id: int | None = None
    mobile: str | None = None
    vcode: str = Field(min_length=4, max_length=8)


class BatchLoginBody(BaseModel):
    pairs: list[LoginPair]


def _unlogged_out(a: Account) -> dict:
    return {
        "id": a.id,
        "mobile": mask_mobile_api(a.mobile),
        "mobile_raw": a.mobile,
        "city": a.city,
        "egress_group": a.egress_group,
        "enabled": a.enabled,
        "vcode_sent_at": a.vcode_sent_at.isoformat() if a.vcode_sent_at else None,
        "last_error": a.last_error,
        "remark": a.remark,
    }


@router.get("/stats")
def batch_stats(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return ok(login_stats(db))


@router.get("/unlogged")
def list_unlogged(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    vcode_sent_only: bool = Query(False, description="仅显示已发码待登录"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(Account).filter(Account.token_enc == "").order_by(Account.id)
    if vcode_sent_only:
        q = q.filter(Account.vcode_sent_at.isnot(None))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return ok({"total": total, "items": [_unlogged_out(a) for a in items]})


@router.get("/unlogged/export")
def export_unlogged(
    vcode_sent_only: bool = False,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    q = db.query(Account).filter(Account.token_enc == "").order_by(Account.id)
    if vcode_sent_only:
        q = q.filter(Account.vcode_sent_at.isnot(None))
    rows = q.all()

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["mobile", "city", "egress_group", "vcode_sent_at", "last_error", "remark", "vcode"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for a in rows:
            w.writerow(
                [
                    a.mobile,
                    a.city,
                    a.egress_group,
                    a.vcode_sent_at.isoformat() if a.vcode_sent_at else "",
                    a.last_error,
                    a.remark,
                    "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"unlogged_accounts_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/send-vcode")
def start_batch_vcode(
    body: BatchVcodeBody,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    if body.account_ids:
        ids = body.account_ids
    elif body.all_unlogged:
        ids = [a.id for a in db.query(Account).filter(Account.token_enc == "").all()]
    else:
        raise HTTPException(status_code=400, detail=fail(40001, "请指定 account_ids 或 all_unlogged=true"))
    if not ids:
        raise HTTPException(status_code=400, detail=fail(40001, "没有待发码的账号"))
    meta = {}
    if body.interval_seconds is not None:
        meta["interval_seconds"] = body.interval_seconds
    job = Job(
        name="批量发码",
        job_type="batch_vcode",
        cron=json.dumps(meta),
        dry_run=False,
        account_ids_json=json.dumps(ids),
        product_ids_json="[]",
        status="pending",
        total=len(ids),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_batch_vcode_async(job.id)
    return ok({"job_id": job.id, "total": len(ids), "message": "批量发码已启动"})


@router.post("/login")
def start_batch_login(
    body: BatchLoginBody,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    if not body.pairs:
        raise HTTPException(status_code=400, detail=fail(40001, "登录列表为空"))
    pairs = [p.model_dump(exclude_none=True) for p in body.pairs]
    job = Job(
        name="批量登录",
        job_type="batch_login",
        cron=json.dumps({"pairs": pairs}),
        dry_run=False,
        account_ids_json="[]",
        product_ids_json="[]",
        status="pending",
        total=len(pairs),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_batch_login_async(job.id)
    return ok({"job_id": job.id, "total": len(pairs), "message": "批量登录已启动"})


@router.post("/login-csv")
async def batch_login_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    pairs = parse_login_csv(text)
    if not pairs:
        raise HTTPException(status_code=400, detail=fail(40001, "CSV 需包含 mobile, vcode 列"))
    job = Job(
        name="CSV批量登录",
        job_type="batch_login",
        cron=json.dumps({"pairs": pairs}),
        dry_run=False,
        account_ids_json="[]",
        product_ids_json="[]",
        status="pending",
        total=len(pairs),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_batch_login_async(job.id)
    return ok({"job_id": job.id, "total": len(pairs), "message": "批量登录已启动"})


@router.post("/cancel/{job_id}")
def cancel_batch(job_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=fail(40001, "任务不存在"))
    if job.job_type not in ("batch_vcode", "batch_login"):
        raise HTTPException(status_code=400, detail=fail(40001, "非批量登录任务"))
    cancel_batch_job(job_id)
    if job.status in ("pending", "running"):
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    return ok(None, "已请求取消")
