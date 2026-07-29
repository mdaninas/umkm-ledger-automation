import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.bank_schemas import (
    BankColumnMapping,
    BankImportListResponse,
    BankImportResponse,
    BankTransactionCounts,
    BankTransactionListResponse,
    BankTransactionResponse,
    ReconciliationDecisionRequest,
    ReconciliationListResponse,
    ReconciliationRejectRequest,
    ReconciliationResponse,
)
from app.bank_service import (
    BankImportValidationError,
    confirm_reconciliation,
    get_reconciliation_or_404,
    import_bank_csv,
    reject_reconciliation,
    safe_csv_filename,
    serialize_reconciliations,
)
from app.database import get_db_session
from app.models import (
    BankImport,
    BankTransaction,
    BankTransactionStatus,
    Reconciliation,
    ReconciliationStatus,
)
from app.security import AuthContext, get_auth_context

router = APIRouter(tags=["banking"])
ALLOWED_CSV_CONTENT_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


@router.post(
    "/bank-imports",
    response_model=BankImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_import(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="UTF-8 CSV bank statement")],
    mapping_json: Annotated[str, Form(alias="mapping")],
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    filename = safe_csv_filename(file.filename)
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only CSV bank statements are accepted.")
    if file.content_type and file.content_type.lower() not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="The uploaded file does not have a supported CSV content type.",
        )
    try:
        mapping = BankColumnMapping.model_validate_json(mapping_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Complete the date, description, and amount column mapping.",
        ) from exc

    content = file.file.read(request.app.state.settings.max_upload_bytes + 1)
    try:
        bank_import, duplicate_file = import_bank_csv(
            session,
            context=context,
            filename=filename,
            content=content,
            mapping=mapping,
            settings=request.app.state.settings,
            correlation_id=request.state.correlation_id,
        )
    except BankImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if duplicate_file:
        response.status_code = status.HTTP_200_OK
    return _bank_import_payload(bank_import, duplicate_file=duplicate_file)


@router.get("/bank-imports", response_model=BankImportListResponse)
def list_bank_imports(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BankImportListResponse:
    filters = [BankImport.business_id == context.business_id]
    total = session.scalar(
        select(func.count()).select_from(BankImport).where(*filters)
    ) or 0
    items = list(
        session.scalars(
            select(BankImport)
            .where(*filters)
            .order_by(BankImport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return BankImportListResponse(
        items=[
            BankImportResponse.model_validate(_bank_import_payload(item))
            for item in items
        ],
        total=total,
    )


@router.get("/bank-imports/{bank_import_id}", response_model=BankImportResponse)
def get_bank_import(
    bank_import_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> BankImportResponse:
    bank_import = session.scalar(
        select(BankImport).where(
            BankImport.business_id == context.business_id,
            BankImport.id == bank_import_id,
        )
    )
    if bank_import is None:
        raise HTTPException(status_code=404, detail="Bank import not found.")
    return BankImportResponse.model_validate(_bank_import_payload(bank_import))


@router.get("/bank-transactions", response_model=BankTransactionListResponse)
def list_bank_transactions(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    transaction_status: Annotated[
        BankTransactionStatus | None,
        Query(alias="status"),
    ] = None,
    bank_import_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BankTransactionListResponse:
    filters = [BankTransaction.business_id == context.business_id]
    if transaction_status:
        filters.append(BankTransaction.status == transaction_status)
    if bank_import_id:
        filters.append(BankTransaction.bank_import_id == bank_import_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                BankTransaction.description.ilike(term),
                BankTransaction.reference.ilike(term),
            )
        )
    total = session.scalar(
        select(func.count()).select_from(BankTransaction).where(*filters)
    ) or 0
    transactions = list(
        session.scalars(
            select(BankTransaction)
            .options(selectinload(BankTransaction.reconciliations))
            .where(*filters)
            .order_by(
                BankTransaction.transaction_date.desc(),
                BankTransaction.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    candidates = [
        candidate
        for transaction in transactions
        for candidate in transaction.reconciliations
    ]
    candidate_payloads = serialize_reconciliations(session, candidates)
    candidates_by_transaction: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for payload in candidate_payloads:
        candidates_by_transaction.setdefault(
            payload["bank_transaction_id"],
            [],
        ).append(payload)

    counts = _transaction_counts(session, context.business_id)
    return BankTransactionListResponse(
        items=[
            BankTransactionResponse.model_validate(
                {
                "id": transaction.id,
                "bank_import_id": transaction.bank_import_id,
                "row_number": transaction.row_number,
                "transaction_date": transaction.transaction_date,
                "description": transaction.description,
                "amount": transaction.amount,
                "direction": transaction.direction,
                "reference": transaction.reference,
                "status": transaction.status,
                "created_at": transaction.created_at,
                "candidates": candidates_by_transaction.get(transaction.id, []),
                }
            )
            for transaction in transactions
        ],
        total=total,
        counts=counts,
    )


@router.get("/reconciliations", response_model=ReconciliationListResponse)
def list_reconciliations(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    reconciliation_status: Annotated[
        ReconciliationStatus | None,
        Query(alias="status"),
    ] = None,
    bank_transaction_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReconciliationListResponse:
    filters = [Reconciliation.business_id == context.business_id]
    if reconciliation_status:
        filters.append(Reconciliation.status == reconciliation_status)
    if bank_transaction_id:
        filters.append(Reconciliation.bank_transaction_id == bank_transaction_id)
    total = session.scalar(
        select(func.count()).select_from(Reconciliation).where(*filters)
    ) or 0
    reconciliations = list(
        session.scalars(
            select(Reconciliation)
            .where(*filters)
            .order_by(Reconciliation.score.desc(), Reconciliation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return ReconciliationListResponse(
        items=[
            ReconciliationResponse.model_validate(item)
            for item in serialize_reconciliations(session, reconciliations)
        ],
        total=total,
    )


@router.post(
    "/reconciliations/{reconciliation_id}/confirm",
    response_model=ReconciliationResponse,
)
def confirm_reconciliation_candidate(
    reconciliation_id: uuid.UUID,
    payload: ReconciliationDecisionRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    reconciliation = get_reconciliation_or_404(
        session,
        business_id=context.business_id,
        reconciliation_id=reconciliation_id,
        for_update=True,
    )
    confirmed = confirm_reconciliation(
        session,
        reconciliation=reconciliation,
        context=context,
        correlation_id=request.state.correlation_id,
        comment=payload.comment,
    )
    return serialize_reconciliations(session, [confirmed])[0]


@router.post(
    "/reconciliations/{reconciliation_id}/reject",
    response_model=ReconciliationResponse,
)
def reject_reconciliation_candidate(
    reconciliation_id: uuid.UUID,
    payload: ReconciliationRejectRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    reconciliation = get_reconciliation_or_404(
        session,
        business_id=context.business_id,
        reconciliation_id=reconciliation_id,
        for_update=True,
    )
    rejected = reject_reconciliation(
        session,
        reconciliation=reconciliation,
        context=context,
        correlation_id=request.state.correlation_id,
        comment=payload.comment,
    )
    return serialize_reconciliations(session, [rejected])[0]


def _bank_import_payload(
    bank_import: BankImport,
    *,
    duplicate_file: bool = False,
) -> dict[str, Any]:
    return {
        "id": bank_import.id,
        "filename": bank_import.filename,
        "sha256": bank_import.sha256,
        "column_mapping": bank_import.column_mapping,
        "status": bank_import.status,
        "row_count": bank_import.row_count,
        "imported_count": bank_import.imported_count,
        "duplicate_count": bank_import.duplicate_count,
        "error_count": bank_import.error_count,
        "row_errors": bank_import.row_errors,
        "created_at": bank_import.created_at,
        "duplicate_file": duplicate_file,
    }


def _transaction_counts(
    session: Session,
    business_id: uuid.UUID,
) -> BankTransactionCounts:
    rows = session.execute(
        select(BankTransaction.status, func.count())
        .where(BankTransaction.business_id == business_id)
        .group_by(BankTransaction.status)
    )
    by_status = {transaction_status: count for transaction_status, count in rows}
    unmatched = by_status.get(BankTransactionStatus.UNMATCHED, 0)
    suggested = by_status.get(BankTransactionStatus.SUGGESTED, 0)
    matched = by_status.get(BankTransactionStatus.AUTO_MATCHED, 0) + by_status.get(
        BankTransactionStatus.CONFIRMED,
        0,
    )
    return BankTransactionCounts(
        total=sum(by_status.values()),
        unmatched=unmatched,
        suggested=suggested,
        matched=matched,
    )
