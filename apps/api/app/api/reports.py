import csv
import io
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models import Business, Role, WeeklyDigest
from app.report_schemas import (
    DashboardReport,
    WeeklyDigestResponse,
    WeeklyDigestRunRequest,
)
from app.report_service import (
    build_dashboard_report,
    generate_weekly_digest,
    ledger_export_rows,
    resolve_report_period,
    serialize_weekly_digest,
)
from app.security import AuthContext, get_auth_context

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard", response_model=DashboardReport)
def dashboard_report(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> DashboardReport:
    business = _business_or_404(session, context.business_id)
    try:
        return build_dashboard_report(
            session,
            business=business,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/export.csv")
def export_report_csv(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> Response:
    business = _business_or_404(session, context.business_id)
    try:
        period = resolve_report_period(
            business,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = ledger_export_rows(
        session,
        business_id=context.business_id,
        start_date=period.start_date,
        end_date=period.end_date,
    )
    output = io.StringIO(newline="")
    fieldnames = [
        "tanggal",
        "journal_id",
        "deskripsi",
        "kode_akun",
        "nama_akun",
        "debit",
        "kredit",
        "dokumen_id",
        "nomor_dokumen",
        "vendor",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    filename = f"laporan-{period.start_date}-{period.end_date}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/weekly-digests", response_model=list[WeeklyDigestResponse])
def list_weekly_digests(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[WeeklyDigestResponse]:
    digests = session.scalars(
        select(WeeklyDigest)
        .where(WeeklyDigest.business_id == context.business_id)
        .order_by(WeeklyDigest.period_end.desc())
        .limit(12)
    )
    return [serialize_weekly_digest(digest) for digest in digests]


@router.post("/weekly-digests/run", response_model=WeeklyDigestResponse)
def run_weekly_digest(
    payload: WeeklyDigestRunRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> WeeklyDigestResponse:
    if context.membership.role != Role.OWNER:
        raise HTTPException(
            status_code=403,
            detail="Hanya owner yang dapat membuat weekly digest.",
        )
    digest = generate_weekly_digest(
        session,
        business=_business_or_404(session, context.business_id),
        correlation_id=request.state.correlation_id,
        period_end=payload.period_end,
    )
    return serialize_weekly_digest(digest)


def _business_or_404(session: Session, business_id: uuid.UUID) -> Business:
    business = session.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="Bisnis tidak ditemukan.")
    return business
