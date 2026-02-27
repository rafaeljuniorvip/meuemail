import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, desc, asc, or_, text, literal_column
from sqlalchemy.orm import Session

from config.database import get_db, SessionLocal
from models.email import Email
from services.gmail_service import gmail_service


def get_current_user(request: Request) -> dict:
    return getattr(request.state, "user", {})

router = APIRouter(prefix="/api")

sync_state = {"running": False, "total": 0, "synced": 0, "status": "idle"}


class DeleteRequest(BaseModel):
    gmail_ids: list[str]


class DeleteByFilterRequest(BaseModel):
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    label: Optional[str] = None
    has_attachments: Optional[bool] = None
    is_read: Optional[bool] = None
    min_size: Optional[int] = None


@router.get("/auth/status")
def auth_status():
    return {
        "authenticated": gmail_service.is_authenticated(),
        "email": gmail_service.user_email,
    }


@router.post("/auth/connect")
def auth_connect():
    result = gmail_service.authenticate()
    return result


@router.get("/emails")
def list_emails(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    label: Optional[str] = None,
    has_attachments: Optional[bool] = None,
    is_read: Optional[bool] = None,
    min_size: Optional[int] = None,
    account_id: Optional[int] = None,
    sort_by: str = Query("date", regex="^(date|sender|subject|size_estimate)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    user = get_current_user(request)
    query = db.query(Email)
    if user.get("id"):
        query = query.filter(Email.user_id == user["id"])

    if account_id is not None:
        query = query.filter(Email.account_id == account_id)

    if sender:
        query = query.filter(
            or_(
                Email.sender.ilike(f"%{sender}%"),
                Email.sender_email.ilike(f"%{sender}%"),
            )
        )
    if subject:
        query = query.filter(Email.subject.ilike(f"%{subject}%"))
    if date_from:
        query = query.filter(Email.date >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(Email.date <= datetime.fromisoformat(date_to + "T23:59:59"))
    if label:
        query = query.filter(Email.labels.any(label))
    if has_attachments is not None:
        query = query.filter(Email.has_attachments == has_attachments)
    if is_read is not None:
        query = query.filter(Email.is_read == is_read)
    if min_size is not None:
        query = query.filter(Email.size_estimate >= min_size)

    total = query.count()

    sort_column = getattr(Email, sort_by)
    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(sort_column))

    offset = (page - 1) * per_page
    emails = query.offset(offset).limit(per_page).all()

    return {
        "emails": [_email_to_dict(e) for e in emails],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/emails/stats")
def email_stats(request: Request, account_id: Optional[int] = None, db: Session = Depends(get_db)):
    user = get_current_user(request)
    base_query = db.query(Email)
    if user.get("id"):
        base_query = base_query.filter(Email.user_id == user["id"])
    if account_id is not None:
        base_query = base_query.filter(Email.account_id == account_id)

    total = base_query.with_entities(func.count(Email.id)).scalar()
    total_size = base_query.with_entities(func.sum(Email.size_estimate)).scalar() or 0
    unread = base_query.filter(Email.is_read == False).with_entities(func.count(Email.id)).scalar()

    senders_query = db.query(Email.sender_email, func.count(Email.id).label("count"))
    if user.get("id"):
        senders_query = senders_query.filter(Email.user_id == user["id"])
    if account_id is not None:
        senders_query = senders_query.filter(Email.account_id == account_id)
    top_senders = (
        senders_query
        .group_by(Email.sender_email)
        .order_by(desc("count"))
        .limit(30)
        .all()
    )

    labels_base = db.query(func.unnest(Email.labels).label("label"))
    if user.get("id"):
        labels_base = labels_base.filter(Email.user_id == user["id"])
    if account_id is not None:
        labels_base = labels_base.filter(Email.account_id == account_id)
    labels_query = labels_base.subquery()
    label_counts = (
        db.query(labels_query.c.label, func.count().label("count"))
        .group_by(labels_query.c.label)
        .order_by(desc("count"))
        .all()
    )

    # Top domains
    domain_expr = func.split_part(Email.sender_email, "@", 2)
    domains_query = db.query(domain_expr.label("domain"), func.count(Email.id).label("count")).filter(Email.sender_email.ilike("%@%"))
    if user.get("id"):
        domains_query = domains_query.filter(Email.user_id == user["id"])
    if account_id is not None:
        domains_query = domains_query.filter(Email.account_id == account_id)
    top_domains = (
        domains_query
        .group_by(domain_expr)
        .order_by(desc("count"))
        .limit(20)
        .all()
    )

    return {
        "total_emails": total,
        "total_size_bytes": total_size,
        "unread": unread,
        "top_senders": [
            {"email": s[0], "count": s[1]} for s in top_senders
        ],
        "labels": [
            {"label": l[0], "count": l[1]} for l in label_counts
        ],
        "top_domains": [
            {"domain": d[0], "count": d[1]} for d in top_domains
        ],
    }


@router.get("/emails/analysis/fuzzy-senders")
def fuzzy_senders(db: Session = Depends(get_db)):
    """Group similar sender emails using trigram similarity."""
    results = db.execute(text("""
        WITH sender_counts AS (
            SELECT sender_email, COUNT(*) as cnt
            FROM emails
            WHERE sender_email IS NOT NULL AND sender_email != ''
            GROUP BY sender_email
            HAVING COUNT(*) >= 2
        ),
        pairs AS (
            SELECT
                a.sender_email AS email_a,
                b.sender_email AS email_b,
                a.cnt AS count_a,
                b.cnt AS count_b,
                similarity(a.sender_email, b.sender_email) AS sim
            FROM sender_counts a
            JOIN sender_counts b ON a.sender_email < b.sender_email
            WHERE similarity(a.sender_email, b.sender_email) > 0.4
              AND split_part(a.sender_email, '@', 2) = split_part(b.sender_email, '@', 2)
        )
        SELECT email_a, email_b, count_a, count_b, sim
        FROM pairs
        ORDER BY sim DESC, count_a + count_b DESC
        LIMIT 50
    """)).fetchall()

    return [
        {
            "email_a": r[0], "email_b": r[1],
            "count_a": r[2], "count_b": r[3],
            "similarity": round(float(r[4]), 2),
        }
        for r in results
    ]


@router.get("/emails/analysis/noreply")
def noreply_analysis(db: Session = Depends(get_db)):
    """Find automated/noreply senders."""
    results = (
        db.query(Email.sender_email, Email.sender, func.count(Email.id).label("count"))
        .filter(
            or_(
                Email.sender_email.ilike("%noreply%"),
                Email.sender_email.ilike("%no-reply%"),
                Email.sender_email.ilike("%notification%"),
                Email.sender_email.ilike("%mailer-daemon%"),
                Email.sender_email.ilike("%bounce%"),
                Email.sender_email.ilike("%alert%"),
                Email.sender_email.ilike("%automated%"),
                Email.sender_email.ilike("%donotreply%"),
            )
        )
        .group_by(Email.sender_email, Email.sender)
        .order_by(desc("count"))
        .limit(30)
        .all()
    )
    total = sum(r[2] for r in results)
    return {
        "total_automated": total,
        "senders": [
            {"email": r[0], "name": r[1], "count": r[2]} for r in results
        ],
    }


@router.get("/emails/analysis/domain-groups")
def domain_groups(db: Session = Depends(get_db)):
    """Group senders by domain with fuzzy domain similarity."""
    results = db.execute(text("""
        WITH domain_stats AS (
            SELECT
                split_part(sender_email, '@', 2) AS domain,
                COUNT(*) AS total_emails,
                COUNT(DISTINCT sender_email) AS unique_senders,
                SUM(size_estimate) AS total_size,
                array_agg(DISTINCT sender_email ORDER BY sender_email) AS senders
            FROM emails
            WHERE sender_email LIKE '%%@%%'
            GROUP BY split_part(sender_email, '@', 2)
            HAVING COUNT(*) >= 3
        )
        SELECT domain, total_emails, unique_senders, total_size,
               senders[1:5] AS top_senders
        FROM domain_stats
        ORDER BY total_emails DESC
        LIMIT 30
    """)).fetchall()

    return [
        {
            "domain": r[0],
            "total_emails": r[1],
            "unique_senders": r[2],
            "total_size": r[3],
            "top_senders": r[4] or [],
        }
        for r in results
    ]


def _get_gmail_account(db) -> tuple:
    """Get the account_id and user_id for the Gmail account."""
    from models.account import Account
    account = db.query(Account).filter(Account.provider == "gmail").first()
    if account:
        return account.id, account.user_id
    return None, None


def _sync_worker():
    global sync_state
    db = SessionLocal()

    try:
        gmail_account_id, gmail_user_id = _get_gmail_account(db)

        all_ids = []
        page_token = None

        while True:
            result = gmail_service.fetch_email_ids(page_token=page_token)
            messages = result["messages"]
            all_ids.extend([m["id"] for m in messages])
            sync_state["total"] = len(all_ids)

            page_token = result["nextPageToken"]
            if not page_token:
                break

        existing_with_body = set(
            row[0]
            for row in db.query(Email.gmail_id)
            .filter(Email.gmail_id.in_(all_ids), Email.body.isnot(None), Email.body != "")
            .all()
        )
        ids_to_fetch = [mid for mid in all_ids if mid not in existing_with_body]
        sync_state["total"] = len(ids_to_fetch)
        sync_state["status"] = "fetching_details"

        batch_size = 100
        new_count = 0
        updated_count = 0
        for i in range(0, len(ids_to_fetch), batch_size):
            chunk = ids_to_fetch[i : i + batch_size]
            emails_data = gmail_service.fetch_emails_batch(chunk)

            for data in emails_data:
                existing = db.query(Email).filter(Email.gmail_id == data["gmail_id"]).first()
                if existing:
                    existing.body = data.get("body", "")
                    existing.attachments = data.get("attachments", [])
                    updated_count += 1
                else:
                    email = Email(
                        gmail_id=data["gmail_id"],
                        thread_id=data["thread_id"],
                        subject=data["subject"],
                        sender=data["sender"],
                        sender_email=data["sender_email"],
                        recipients=data["recipients"],
                        date=data["date"],
                        snippet=data["snippet"],
                        labels=data["labels"],
                        size_estimate=data["size_estimate"],
                        has_attachments=data["has_attachments"],
                        gmail_link=data["gmail_link"],
                        is_read=data["is_read"],
                        body=data.get("body", ""),
                        attachments=data.get("attachments", []),
                        account_id=gmail_account_id,
                        user_id=gmail_user_id,
                    )
                    db.add(email)
                    new_count += 1

            db.commit()
            sync_state["synced"] += len(emails_data)

        sync_state["status"] = "done"
        sync_state["running"] = False

    except Exception as e:
        sync_state["running"] = False
        sync_state["status"] = "error"
        sync_state["error"] = str(e)
        db.rollback()
    finally:
        db.close()


@router.post("/sync")
def sync_emails():
    global sync_state

    if sync_state["running"]:
        return {"status": "already_running", "progress": sync_state}

    if not gmail_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Gmail não conectado")

    sync_state = {"running": True, "total": 0, "synced": 0, "status": "fetching_ids"}

    thread = threading.Thread(target=_sync_worker, daemon=True)
    thread.start()

    return {"status": "started"}


@router.get("/sync/status")
def sync_status():
    return sync_state


@router.post("/emails/delete")
def delete_emails(request: DeleteRequest, http_request: Request = None, db: Session = Depends(get_db)):
    if not request.gmail_ids:
        raise HTTPException(status_code=400, detail="Nenhum email selecionado")

    # Try to delete from Gmail API if authenticated (only affects Gmail emails)
    gmail_deleted = 0
    gmail_errors = []
    if gmail_service.is_authenticated():
        # Only send actual Gmail IDs (not imap_ prefixed)
        gmail_ids = [gid for gid in request.gmail_ids if not gid.startswith("imap_")]
        if gmail_ids:
            result = gmail_service.delete_emails(gmail_ids)
            gmail_deleted = result["deleted"]
            gmail_errors = result["errors"]

    # Always delete from local database
    deleted_local = db.query(Email).filter(Email.gmail_id.in_(request.gmail_ids)).delete(
        synchronize_session=False
    )
    db.commit()

    return {
        "status": "ok",
        "deleted_gmail": gmail_deleted,
        "deleted_local": deleted_local,
        "errors": gmail_errors,
    }


@router.post("/emails/delete-by-filter")
def delete_by_filter(request: DeleteByFilterRequest, db: Session = Depends(get_db)):
    query = db.query(Email)

    if request.sender_email:
        query = query.filter(
            or_(
                Email.sender.ilike(f"%{request.sender_email}%"),
                Email.sender_email.ilike(f"%{request.sender_email}%"),
            )
        )
    if request.subject:
        query = query.filter(Email.subject.ilike(f"%{request.subject}%"))
    if request.date_from:
        query = query.filter(Email.date >= datetime.fromisoformat(request.date_from))
    if request.date_to:
        query = query.filter(
            Email.date <= datetime.fromisoformat(request.date_to + "T23:59:59")
        )
    if request.label:
        query = query.filter(Email.labels.any(request.label))
    if request.has_attachments is not None:
        query = query.filter(Email.has_attachments == request.has_attachments)
    if request.is_read is not None:
        query = query.filter(Email.is_read == request.is_read)
    if request.min_size is not None:
        query = query.filter(Email.size_estimate >= request.min_size)

    emails = query.all()
    all_ids = [e.gmail_id for e in emails]

    if not all_ids:
        return {"status": "ok", "deleted": 0}

    # Only try Gmail API for non-IMAP emails
    gmail_deleted = 0
    gmail_errors = []
    if gmail_service.is_authenticated():
        gmail_ids = [gid for gid in all_ids if not gid.startswith("imap_")]
        if gmail_ids:
            result = gmail_service.delete_emails(gmail_ids)
            gmail_deleted = result["deleted"]
            gmail_errors = result["errors"]

    query.delete(synchronize_session=False)
    db.commit()

    return {
        "status": "ok",
        "deleted_gmail": gmail_deleted,
        "deleted_local": len(all_ids),
        "errors": gmail_errors,
    }


@router.get("/emails/{gmail_id}")
def get_email(gmail_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    q = db.query(Email).filter(Email.gmail_id == gmail_id)
    if user.get("id"):
        q = q.filter(Email.user_id == user["id"])
    email = q.first()
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    # Re-fetch from Gmail if body has cid: images or attachments metadata missing
    needs_refetch = (
        (email.body and "cid:" in email.body)
        or (email.has_attachments and (not email.attachments or len(email.attachments) == 0))
        or not email.body
    )
    if needs_refetch and gmail_service.is_authenticated():
        try:
            detail = gmail_service.fetch_email_detail(gmail_id)
            if detail.get("body"):
                email.body = detail["body"]
            if detail.get("attachments"):
                email.attachments = detail["attachments"]
            db.commit()
        except Exception as e:
            print(f"[get_email] refetch error: {e}")
            db.rollback()

    return _email_to_dict(email)


@router.get("/emails/{gmail_id}/attachments/{attachment_id}")
def download_attachment(gmail_id: str, attachment_id: str, db: Session = Depends(get_db)):
    if not gmail_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Gmail não conectado")

    email = db.query(Email).filter(Email.gmail_id == gmail_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    att_meta = None
    for att in (email.attachments or []):
        if att["attachmentId"] == attachment_id:
            att_meta = att
            break

    if not att_meta:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    data = gmail_service.download_attachment(gmail_id, attachment_id)

    return Response(
        content=data,
        media_type=att_meta.get("mimeType", "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{att_meta["filename"]}"'
        },
    )


@router.get("/labels")
def list_labels(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    base = db.query(Email)
    if user.get("id"):
        base = base.filter(Email.user_id == user["id"])
    labels_query = base.with_entities(func.unnest(Email.labels).label("label")).subquery()
    labels = (
        db.query(labels_query.c.label, func.count().label("count"))
        .group_by(labels_query.c.label)
        .order_by(desc("count"))
        .all()
    )
    return [{"label": l[0], "count": l[1]} for l in labels]


def _email_to_dict(email: Email) -> dict:
    return {
        "id": email.id,
        "gmail_id": email.gmail_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "sender_email": email.sender_email,
        "recipients": email.recipients,
        "date": email.date.isoformat() if email.date else None,
        "snippet": email.snippet,
        "labels": email.labels or [],
        "size_estimate": email.size_estimate,
        "has_attachments": email.has_attachments,
        "gmail_link": email.gmail_link,
        "body": email.body,
        "attachments": email.attachments or [],
        "is_read": email.is_read,
        "synced_at": email.synced_at.isoformat() if email.synced_at else None,
        "account_id": email.account_id,
    }
