import hashlib
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.database import get_db_session
from app.document_service import (
    get_document_or_404,
    post_document,
    review_document,
    serialize_document_detail,
)
from app.finance_schemas import (
    DocumentDetail,
    DocumentListResponse,
    DocumentReviewRequest,
    DocumentSummary,
    PostDocumentRequest,
)
from app.models import (
    ActorType,
    Document,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    Role,
)
from app.security import AuthContext, get_auth_context
from app.storage import ObjectStorage
from app.workflow import create_document_workflow

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_SIGNATURES = {
    "application/pdf": lambda data: data.startswith(b"%PDF-"),
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
}


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG, PNG, or PDF document")],
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ] = None,
) -> Document:
    if idempotency_key:
        existing = session.scalar(
            select(Document).where(
                Document.business_id == context.business_id,
                Document.upload_idempotency_key == idempotency_key,
            )
        )
        if existing:
            response.status_code = status.HTTP_200_OK
            return existing

    filename = _safe_filename(file.filename)
    content = file.file.read(request.app.state.settings.max_upload_bytes + 1)
    if len(content) > request.app.state.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    mime_type = _verified_mime_type(file.content_type, content)

    document_id = uuid.uuid4()
    storage_key = f"{context.business_id}/{document_id}/{filename}"
    storage: ObjectStorage = request.app.state.storage
    storage.put(storage_key, content, mime_type)

    document = Document(
        id=document_id,
        business_id=context.business_id,
        source=DocumentSource.UPLOAD,
        original_filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        sha256=hashlib.sha256(content).hexdigest(),
        upload_idempotency_key=idempotency_key,
        status=DocumentStatus.QUEUED,
        document_type=DocumentType.UNKNOWN,
        currency=context.business.currency,
        created_by=context.user.id,
    )
    session.add(document)
    run = create_document_workflow(
        session,
        document=document,
        correlation_id=request.state.correlation_id,
    )
    record_audit_event(
        session,
        business_id=context.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        correlation_id=request.state.correlation_id,
        metadata={
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": document.sha256,
            "workflow_run_id": str(run.id),
        },
    )
    try:
        session.commit()
    except Exception:
        storage.delete(storage_key)
        raise

    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import process_document_task

        process_document_task.delay(str(document.id), str(run.id))
    return document


@router.get("", response_model=DocumentListResponse)
def list_documents(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    document_type: Annotated[DocumentType | None, Query(alias="type")] = None,
    source: DocumentSource | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    filters = [Document.business_id == context.business_id]
    if document_status:
        filters.append(Document.status == document_status)
    if document_type:
        filters.append(Document.document_type == document_type)
    if source:
        filters.append(Document.source == source)
    if date_from:
        filters.append(Document.transaction_date >= date_from)
    if date_to:
        filters.append(Document.transaction_date <= date_to)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Document.original_filename.ilike(term),
                Document.vendor_name.ilike(term),
                Document.document_number.ilike(term),
            )
        )
    total = session.scalar(
        select(func.count()).select_from(Document).where(*filters)
    ) or 0
    items = list(
        session.scalars(
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return DocumentListResponse(
        items=[DocumentSummary.model_validate(item) for item in items],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentDetail:
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=document_id,
    )
    return serialize_document_detail(session, document)


@router.get("/{document_id}/content")
def get_document_content(
    document_id: uuid.UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> StreamingResponse:
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=document_id,
    )
    storage: ObjectStorage = request.app.state.storage
    content = storage.get(document.storage_key)
    return StreamingResponse(
        iter([content]),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.post("/{document_id}/review", response_model=DocumentDetail)
def submit_document_review(
    document_id: uuid.UUID,
    payload: DocumentReviewRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentDetail:
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=document_id,
        for_update=True,
    )
    document = review_document(
        session,
        document=document,
        payload=payload,
        context=context,
        settings=request.app.state.settings,
        correlation_id=request.state.correlation_id,
    )
    return serialize_document_detail(session, document)


@router.post("/{document_id}/post", response_model=DocumentDetail)
def post_reviewed_document(
    document_id: uuid.UUID,
    payload: PostDocumentRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> DocumentDetail:
    if context.membership.role != Role.OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can post journals.")
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=document_id,
        for_update=True,
    )
    post_document(
        session,
        document=document,
        context=context,
        idempotency_key=idempotency_key,
        correlation_id=request.state.correlation_id,
        comment=payload.comment,
    )
    return serialize_document_detail(session, document)


@router.post(
    "/{document_id}/retry",
    response_model=DocumentSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_document(
    document_id: uuid.UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> Document:
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=document_id,
        for_update=True,
    )
    if document.status != DocumentStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed documents can be retried.")
    document.status = DocumentStatus.QUEUED
    document.error_code = None
    run = create_document_workflow(
        session,
        document=document,
        correlation_id=request.state.correlation_id,
    )
    record_audit_event(
        session,
        business_id=context.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="document.retry.requested",
        entity_type="document",
        entity_id=document.id,
        correlation_id=request.state.correlation_id,
        metadata={"workflow_run_id": str(run.id)},
    )
    session.commit()
    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import process_document_task

        process_document_task.delay(str(document.id), str(run.id))
    return document


def _safe_filename(filename: str | None) -> str:
    original = Path(filename or "document").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", original).strip(".-")
    return (cleaned or "document")[:255]


def _verified_mime_type(declared: str | None, content: bytes) -> str:
    for mime_type, signature_check in ALLOWED_SIGNATURES.items():
        if signature_check(content):
            if declared and declared not in {
                mime_type,
                "application/octet-stream",
                "image/jpg",
            }:
                raise HTTPException(
                    status_code=415,
                    detail="Declared content type does not match the file.",
                )
            return mime_type
    raise HTTPException(
        status_code=415,
        detail="Only valid JPEG, PNG, and PDF files are accepted.",
    )
