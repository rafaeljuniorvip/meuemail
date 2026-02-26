from fastapi import APIRouter, Query, Request
from services.search_service import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


def _get_user_id(request: Request) -> int | None:
    user = getattr(request.state, "user", None)
    return user["id"] if user else None


@router.get("/fulltext")
def fulltext(request: Request, q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_body_fulltext(q, limit, user_id=_get_user_id(request))


@router.get("/sender")
def sender(request: Request, q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_sender(q, limit, user_id=_get_user_id(request))


@router.get("/subject")
def subject(request: Request, q: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_subject_keyword(q, limit, user_id=_get_user_id(request))


@router.get("/date-range")
def date_range(
    request: Request,
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    limit: int = Query(20, le=100),
):
    return search_service.search_date_range(date_from, date_to, limit, user_id=_get_user_id(request))


@router.get("/label")
def label(request: Request, label: str = Query(...), limit: int = Query(20, le=100)):
    return search_service.search_by_label(label, limit, user_id=_get_user_id(request))


@router.get("/attachments")
def attachments(
    request: Request,
    filename: str = Query(None),
    has_attachments: bool = Query(True),
    limit: int = Query(20, le=100),
):
    return search_service.search_attachments(filename, has_attachments, limit, user_id=_get_user_id(request))


@router.get("/thread/{thread_id}")
def thread(request: Request, thread_id: str):
    return search_service.search_thread(thread_id, user_id=_get_user_id(request))


@router.get("/sender-summary")
def sender_summary(request: Request, email: str = Query(...)):
    return search_service.get_sender_summary(email, user_id=_get_user_id(request))


@router.get("/combined")
def combined(
    request: Request,
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
        user_id=_get_user_id(request),
    )
