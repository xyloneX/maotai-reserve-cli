"""批量发码 / 批量登录后台任务。"""

from __future__ import annotations

import csv
import io
import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.entities import Account, Job
from .imaotai_service import (
    _encrypt_token,
    _to_credentials,
    get_app_config,
    login_with_vcode,
    mask_mobile_api,
    send_vcode,
    sync_account_to_credentials_file,
)
from src.exceptions import AuthError, RateLimitError

logger = logging.getLogger(__name__)

_running: set[int] = set()
_lock = threading.Lock()
_cancelled: set[int] = set()


def _parse_ids(raw: str) -> list[int]:
    try:
        return [int(x) for x in json.loads(raw or "[]")]
    except Exception:
        return []


def _parse_meta(job: Job) -> dict:
    try:
        return json.loads(job.cron or "{}")
    except Exception:
        return {}


def _vcode_interval() -> float:
    cfg = get_app_config()
    return float(cfg.antidetect.login_vcode_interval or 90)


def cancel_batch_job(job_id: int) -> None:
    _cancelled.add(job_id)


def is_batch_running() -> bool:
    return bool(_running)


def run_batch_vcode_async(job_id: int) -> None:
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)
    threading.Thread(target=_run_batch_vcode, args=(job_id,), daemon=True).start()


def run_batch_login_async(job_id: int) -> None:
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)
    threading.Thread(target=_run_batch_login, args=(job_id,), daemon=True).start()


def _finish_job(db: Session, job: Job, lines: list[str], ok: int, fail: int) -> None:
    job.progress = 100
    job.finished_at = datetime.now(timezone.utc)
    if fail == 0 and ok > 0:
        job.status = "success"
    elif ok > 0:
        job.status = "partial"
    elif ok == 0 and fail > 0:
        job.status = "failed"
    else:
        job.status = "failed"
    job.log_text = "\n".join(lines[-500:])
    db.commit()


def _run_batch_vcode(job_id: int) -> None:
    db = SessionLocal()
    lines: list[str] = []
    ok = fail = 0
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        meta = _parse_meta(job)
        interval = float(meta.get("interval_seconds") or _vcode_interval())
        account_ids = _parse_ids(job.account_ids_json)
        if account_ids:
            accounts = db.query(Account).filter(Account.id.in_(account_ids)).order_by(Account.id).all()
        else:
            accounts = (
                db.query(Account)
                .filter(Account.enabled == True, Account.token_enc == "")  # noqa: E712
                .order_by(Account.id)
                .all()
            )
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.total = len(accounts)
        job.progress = 0
        job.log_text = f"批量发码开始，共 {len(accounts)} 个，间隔 {interval:.0f}s\n"
        db.commit()

        for idx, acc in enumerate(accounts):
            if job_id in _cancelled:
                lines.append("⏹ 任务已取消")
                job.status = "cancelled"
                break
            label = mask_mobile_api(acc.mobile)
            try:
                ok_flag, msg = send_vcode(acc)
                if ok_flag:
                    acc.vcode_sent_at = datetime.now(timezone.utc)
                    acc.last_error = ""
                    ok += 1
                    lines.append(f"✅ {label}: {msg}")
                else:
                    fail += 1
                    acc.last_error = msg[:500]
                    lines.append(f"❌ {label}: {msg}")
            except RateLimitError as e:
                wait = _extract_wait_seconds(str(e), interval)
                lines.append(f"⏳ {label}: 限流，等待 {wait:.0f}s 后重试…")
                job.log_text = "\n".join(lines[-300:])
                db.commit()
                time.sleep(wait)
                try:
                    ok_flag, msg = send_vcode(acc)
                    if ok_flag:
                        acc.vcode_sent_at = datetime.now(timezone.utc)
                        acc.last_error = ""
                        ok += 1
                        lines.append(f"✅ {label}: {msg}（重试成功）")
                    else:
                        fail += 1
                        acc.last_error = msg[:500]
                        lines.append(f"❌ {label}: {msg}")
                except Exception as e2:
                    fail += 1
                    err = str(e2)[:500]
                    acc.last_error = err
                    lines.append(f"❌ {label}: {err}")
            except Exception as e:
                fail += 1
                err = str(e)[:500]
                acc.last_error = err
                lines.append(f"❌ {label}: {err}")
            job.progress = int((idx + 1) / max(1, len(accounts)) * 100)
            job.log_text = "\n".join(lines[-300:])
            db.commit()
            if idx < len(accounts) - 1 and job_id not in _cancelled:
                time.sleep(interval)

        if job.status != "cancelled":
            _finish_job(db, job, lines, ok, fail)
        else:
            job.finished_at = datetime.now(timezone.utc)
            job.log_text = "\n".join(lines[-500:])
            db.commit()
        logger.info("批量发码任务 %s 完成 ok=%s fail=%s", job_id, ok, fail)
    except Exception as e:
        logger.exception("批量发码 %s 失败: %s", job_id, e)
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.log_text = (job.log_text or "") + f"\n❌ {e}"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _cancelled.discard(job_id)
        with _lock:
            _running.discard(job_id)


def _run_batch_login(job_id: int) -> None:
    """meta.pairs: [{mobile, vcode}] 或 [{account_id, vcode}]"""
    db = SessionLocal()
    lines: list[str] = []
    ok = fail = 0
    cfg = get_app_config()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        meta = _parse_meta(job)
        pairs = meta.get("pairs") or []
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.total = len(pairs)
        job.progress = 0
        job.log_text = f"批量登录开始，共 {len(pairs)} 条\n"
        db.commit()

        for idx, pair in enumerate(pairs):
            if job_id in _cancelled:
                lines.append("⏹ 任务已取消")
                job.status = "cancelled"
                break
            acc = _resolve_account(db, pair)
            if not acc:
                fail += 1
                mobile = pair.get("mobile") or pair.get("account_id")
                lines.append(f"❌ {mobile}: 账号不存在")
                continue
            label = mask_mobile_api(acc.mobile)
            vcode = str(pair.get("vcode") or "").strip()
            if len(vcode) < 4:
                fail += 1
                lines.append(f"❌ {label}: 验证码无效")
                continue
            try:
                token, user_id = login_with_vcode(acc, vcode)
                acc.token_enc = _encrypt_token(token, cfg.secret_key)
                acc.user_id = user_id
                acc.logged_at = datetime.now(timezone.utc)
                acc.last_error = ""
                cred = _to_credentials(acc, cfg)
                acc.device_ua = cred.device_ua
                acc.device_mt_info = cred.device_mt_info
                acc.device_network = cred.device_network
                db.commit()
                sync_account_to_credentials_file(acc)
                ok += 1
                lines.append(f"✅ {label}: 登录成功")
            except (AuthError, RateLimitError) as e:
                fail += 1
                acc.last_error = str(e)[:500]
                lines.append(f"❌ {label}: {e}")
                db.commit()
            except Exception as e:
                fail += 1
                acc.last_error = str(e)[:500]
                lines.append(f"❌ {label}: {e}")
                db.commit()
            job.progress = int((idx + 1) / max(1, len(pairs)) * 100)
            job.log_text = "\n".join(lines[-300:])
            db.commit()
            time.sleep(0.3)

        if job.status != "cancelled":
            _finish_job(db, job, lines, ok, fail)
            from .credential_sync import sync_db_to_credentials_file

            sync_db_to_credentials_file(db)
        else:
            job.finished_at = datetime.now(timezone.utc)
            job.log_text = "\n".join(lines[-500:])
            db.commit()
    except Exception as e:
        logger.exception("批量登录 %s 失败: %s", job_id, e)
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.log_text = (job.log_text or "") + f"\n❌ {e}"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _cancelled.discard(job_id)
        with _lock:
            _running.discard(job_id)


def _resolve_account(db: Session, pair: dict) -> Account | None:
    aid = pair.get("account_id")
    if aid:
        return db.get(Account, int(aid))
    mobile = str(pair.get("mobile") or "").strip()
    if len(mobile) == 11:
        return db.query(Account).filter(Account.mobile == mobile).first()
    return None


def _extract_wait_seconds(msg: str, default: float) -> float:
    import re

    m = re.search(r"(\d+)\s*秒", msg)
    if m:
        return float(m.group(1)) + 1
    return default


def parse_login_csv(text: str) -> list[dict]:
    """解析 mobile,vcode CSV。"""
    reader = csv.DictReader(io.StringIO(text))
    pairs: list[dict] = []
    for row in reader:
        mobile = (row.get("mobile") or row.get("手机号") or "").strip()
        vcode = (row.get("vcode") or row.get("验证码") or "").strip()
        if mobile and vcode:
            pairs.append({"mobile": mobile, "vcode": vcode})
    return pairs


def login_stats(db: Session) -> dict:
    total = db.query(Account).count()
    enabled = db.query(Account).filter(Account.enabled == True).count()  # noqa: E712
    logged = db.query(Account).filter(Account.token_enc != "").count()
    unlogged = total - logged
    recent_vcode = (
        db.query(Account)
        .filter(Account.vcode_sent_at.isnot(None), Account.token_enc == "")
        .count()
    )
    return {
        "total": total,
        "enabled": enabled,
        "logged_in": logged,
        "unlogged": unlogged,
        "vcode_sent_pending_login": recent_vcode,
        "batch_running": is_batch_running(),
    }
