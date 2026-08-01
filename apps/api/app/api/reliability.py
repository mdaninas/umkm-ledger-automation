import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.database import get_db_session
from app.eval_service import (
    create_evaluation_run,
    execute_evaluation_run,
    get_evaluation_run,
    serialize_evaluation_run,
)
from app.models import (
    ActorType,
    AuditEvent,
    Document,
    EvaluationRun,
    Role,
    WorkflowRun,
    WorkflowStatus,
)
from app.reliability import (
    list_chaos_scenarios,
    prepare_safe_recovery,
    serialize_workflow,
    set_chaos_scenario,
)
from app.security import AuthContext, get_auth_context

router = APIRouter(tags=["reliability"])


class EvaluationRunRequest(BaseModel):
    model: str | None = Field(default=None, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=40)


@router.get("/demo/chaos-scenarios")
def chaos_scenarios(
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    return {
        "environment": request.app.state.settings.environment,
        "demo_only": True,
        "items": list_chaos_scenarios(
            session,
            business_id=context.business_id,
            settings=request.app.state.settings,
        ),
    }


@router.post("/demo/chaos-scenarios/{scenario_key}/enable")
def enable_chaos_scenario(
    scenario_key: str,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    _set_chaos(session, request, context, scenario_key, True)
    return chaos_scenarios(request, context, session)


@router.post("/demo/chaos-scenarios/{scenario_key}/disable")
def disable_chaos_scenario(
    scenario_key: str,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    _set_chaos(session, request, context, scenario_key, False)
    return chaos_scenarios(request, context, session)


@router.get("/workflows")
def list_workflows(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    workflow_status: Annotated[WorkflowStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    query = (
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.steps), selectinload(WorkflowRun.attempts))
        .where(WorkflowRun.business_id == context.business_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    if workflow_status:
        query = query.where(WorkflowRun.status == workflow_status)
    runs = list(session.scalars(query))
    return {
        "items": [_workflow_payload(session, run) for run in runs],
        "dead_letter_count": sum(run.status == WorkflowStatus.DEAD_LETTER for run in runs),
    }


@router.get("/workflows/{workflow_run_id}")
def get_workflow(
    workflow_run_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    run = _workflow_or_404(session, context.business_id, workflow_run_id)
    return _workflow_payload(session, run)


@router.post("/workflows/{workflow_run_id}/recover", status_code=status.HTTP_202_ACCEPTED)
def recover_workflow(
    workflow_run_id: uuid.UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    run = _workflow_or_404(session, context.business_id, workflow_run_id, for_update=True)
    previous_run_status = run.status
    previous_error_code = run.error_code
    previous_finished_at = run.finished_at
    previous_steps = {
        step.id: (
            step.status,
            step.error_code,
            step.started_at,
            step.finished_at,
            dict(step.output_summary),
        )
        for step in run.steps
    }
    document = session.get(Document, run.entity_id)
    previous_document_state = (
        (document.status, document.error_code) if document is not None else None
    )
    try:
        resume_sequence = prepare_safe_recovery(
            session,
            run=run,
            actor_id=context.user.id,
            actor_role=context.membership.role,
            correlation_id=request.state.correlation_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail="Hanya owner yang dapat memulihkan workflow."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import process_document_task

        try:
            process_document_task.delay(str(run.entity_id), str(run.id))
        except Exception as exc:
            run.status = previous_run_status
            run.error_code = previous_error_code
            run.finished_at = previous_finished_at
            for step in run.steps:
                (
                    step.status,
                    step.error_code,
                    step.started_at,
                    step.finished_at,
                    step.output_summary,
                ) = previous_steps[step.id]
            if document is not None and previous_document_state is not None:
                document.status, document.error_code = previous_document_state
            record_audit_event(
                session,
                business_id=run.business_id,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                action="workflow.recovery.enqueue_failed",
                entity_type="workflow_run",
                entity_id=run.id,
                correlation_id=request.state.correlation_id,
                metadata={"restored_status": previous_run_status.value},
            )
            session.commit()
            raise HTTPException(
                status_code=503,
                detail="Recovery belum dapat dijadwalkan. Workflow tetap aman untuk dicoba lagi.",
            ) from exc
    return {
        "workflow_run_id": str(run.id),
        "status": run.status.value,
        "resume_sequence": resume_sequence,
    }


@router.get("/evals/runs")
def list_evaluation_runs(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    runs = list(
        session.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.business_id == context.business_id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(limit)
        )
    )
    return {"items": [serialize_evaluation_run(run) for run in runs]}


@router.get("/evals/runs/{run_id}")
def evaluation_run_detail(
    run_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    run = get_evaluation_run(session, run_id)
    if run is None or run.business_id != context.business_id:
        raise HTTPException(status_code=404, detail="Evaluation run tidak ditemukan.")
    return serialize_evaluation_run(run, include_results=True)


@router.post("/evals/runs", status_code=status.HTTP_202_ACCEPTED)
def start_evaluation_run(
    payload: EvaluationRunRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    if context.membership.role != Role.OWNER:
        raise HTTPException(status_code=403, detail="Hanya owner yang dapat menjalankan evaluasi.")
    try:
        run = create_evaluation_run(
            session,
            business_id=context.business_id,
            created_by=context.user.id,
            settings=request.app.state.settings,
            correlation_id=request.state.correlation_id,
            model=payload.model,
            prompt_version=payload.prompt_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import run_evaluation_task

        run_evaluation_task.delay(str(run.id))
    else:
        run = execute_evaluation_run(session, run_id=run.id, settings=request.app.state.settings)
    return serialize_evaluation_run(run)


def _set_chaos(
    session: Session,
    request: Request,
    context: AuthContext,
    scenario_key: str,
    enabled: bool,
) -> None:
    try:
        set_chaos_scenario(
            session,
            business_id=context.business_id,
            scenario_key=scenario_key,
            enabled=enabled,
            actor_id=context.user.id,
            actor_role=context.membership.role,
            correlation_id=request.state.correlation_id,
            settings=request.app.state.settings,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail="Hanya owner yang dapat mengubah Chaos Mode."
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skenario Chaos Mode tidak ditemukan.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _workflow_or_404(
    session: Session,
    business_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> WorkflowRun:
    query = (
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.steps), selectinload(WorkflowRun.attempts))
        .where(WorkflowRun.business_id == business_id, WorkflowRun.id == run_id)
    )
    if for_update:
        query = query.with_for_update()
    run = session.scalar(query)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow tidak ditemukan.")
    return run


def _workflow_payload(session: Session, run: WorkflowRun) -> dict[str, Any]:
    audit_events = list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.business_id == run.business_id,
                AuditEvent.correlation_id == run.correlation_id,
            )
            .order_by(AuditEvent.created_at)
        )
    )
    return serialize_workflow(run, audit_events)
