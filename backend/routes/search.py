from fastapi import APIRouter, Query
from services.search_service import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/fulltext")
def fulltext(q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_body_fulltext(q, limit)


@router.get("/sender")
def sender(q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_sender(q, limit)


@router.get("/subject")
def subject(q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_subject_keyword(q, limit)


@router.get("/date-range")
def date_range(
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    limit: int = Query(20, le=100),
):
    return search_service.search_date_range(date_from, date_to, limit)


@router.get("/label")
def label(label: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_by_label(label, limit)


@router.get("/attachments")
def attachments(
    filename: str = Query(None),
    has_attachments: bool = Query(True),
    limit: int = Query(20, le=100),
):
    return search_service.search_attachments(filename, has_attachments, limit)


@router.get("/thread/{thread_id}")
def thread(thread_id: str):
    return search_service.search_thread(thread_id)


@router.get("/sender-summary")
def sender_summary(email: str = Query(...)):
    return search_service.get_sender_summary(email)


@router.get("/combined")
def combined(
    sender: str = Query(None),
    subject: str = Query(None),
    body_keyword: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    label: str = Query(None),
    has_attachments: bool = Query(None),
    limit: int = Query(20, le=100),
):
    return search_service.search_combined(
        sender=sender,
        subject=subject,
        body_keyword=body_keyword,
        date_from=date_from,
        date_to=date_to,
        label=label,
        has_attachments=has_attachments,
        limit=limit,
    )
