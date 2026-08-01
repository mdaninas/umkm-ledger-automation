import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.config import CHAOS_ALLOWED_ENVIRONMENTS, Settings
from app.models import (
    ActorType,
    AuditEvent,
    ChaosScenarioState,
    Document,
    DocumentStatus,
    Role,
    StepStatus,
    WorkflowAttempt,
    WorkflowRun,
    WorkflowStatus,
)

CHAOS_SCENARIOS: dict[str, dict[str, str]] = {
    "AI_TIMEOUT": {
        "name": "AI timeout",
        "description": "Simulasi timeout provider ekstraksi untuk memeriksa kebijakan retry.",
        "recovery": "Worker mencoba ulang dengan backoff, lalu memindahkan run ke dead-letter.",
    },
    "INVALID_JSON": {
        "name": "Respons AI tidak valid",
        "description": "Mengembalikan respons terstruktur yang tidak valid sebelum ledger ditulis.",
        "recovery": "Dokumen tetap dalam review dan dapat dicoba ulang setelah diperiksa.",
    },
    "STORAGE_OUTAGE": {
        "name": "Gangguan storage",
        "description": "Simulasi gangguan sementara saat membaca file dokumen asli.",
        "recovery": "Workflow melanjutkan ekstraksi tanpa menggandakan file upload.",
    },
    "CSV_ROW_CORRUPTION": {
        "name": "Baris CSV rusak",
        "description": "Menyisipkan satu baris bank rusak; baris valid tetap dapat diimpor.",
        "recovery": "Import mencatat error per baris yang aman untuk dikoreksi manual.",
    },
    "WORKER_AFTER_EXTRACTION": {
        "name": "Worker terhenti",
        "description": "Menghentikan worker setelah hasil ekstraksi berhasil disimpan.",
        "recovery": "Replay berlanjut dari validasi dan memakai ekstraksi yang tersimpan.",
    },
    "PROMPT_INJECTION_PROBE": {
        "name": "Uji prompt injection",
        "description": (
            "Menambahkan teks adversarial untuk memastikan isi dokumen tetap dianggap data."
        ),
        "recovery": "Instruksi diabaikan; tool dan perubahan kebijakan tetap tidak diizinkan.",
    },
}


def chaos_is_available(settings: Settings) -> bool:
    return (
        settings.chaos_mode_enabled
        and settings.environment.lower() in CHAOS_ALLOWED_ENVIRONMENTS
    )


class ReliabilityFault(RuntimeError):
    def __init__(self, error_code: str, *, retryable: bool = True) -> None:
        self.error_code = error_code
        self.retryable = retryable
        super().__init__(error_code)


def list_chaos_scenarios(
    session: Session, *, business_id: uuid.UUID, settings: Settings
) -> list[dict[str, Any]]:
    stored = {
        item.scenario_key: item
        for item in session.scalars(
            select(ChaosScenarioState).where(ChaosScenarioState.business_id == business_id)
        )
    }
    return [
        {
            "key": key,
            **definition,
            "available": chaos_is_available(settings),
            "enabled": bool(stored.get(key) and stored[key].enabled),
            "trigger_count": stored[key].trigger_count if key in stored else 0,
            "last_triggered_at": stored[key].last_triggered_at if key in stored else None,
        }
        for key, definition in CHAOS_SCENARIOS.items()
    ]


def set_chaos_scenario(
    session: Session,
    *,
    business_id: uuid.UUID,
    scenario_key: str,
    enabled: bool,
    actor_id: uuid.UUID,
    actor_role: Role,
    correlation_id: str,
    settings: Settings,
) -> ChaosScenarioState:
    if actor_role != Role.OWNER:
        raise PermissionError("Only owners can change Chaos Mode.")
    if scenario_key not in CHAOS_SCENARIOS:
        raise KeyError(scenario_key)
    if not chaos_is_available(settings):
        raise RuntimeError("Chaos Mode is not available in this environment.")

    if enabled:
        for active in session.scalars(
            select(ChaosScenarioState).where(
                ChaosScenarioState.business_id == business_id,
                ChaosScenarioState.enabled.is_(True),
            )
        ):
            active.enabled = False

    state = session.scalar(
        select(ChaosScenarioState).where(
            ChaosScenarioState.business_id == business_id,
            ChaosScenarioState.scenario_key == scenario_key,
        )
    )
    if state is None:
        state = ChaosScenarioState(business_id=business_id, scenario_key=scenario_key)
        session.add(state)
    state.enabled = enabled
    state.enabled_by = actor_id if enabled else None
    state.enabled_at = datetime.now(UTC) if enabled else None
    session.flush()
    record_audit_event(
        session,
        business_id=business_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="chaos.scenario.enabled" if enabled else "chaos.scenario.disabled",
        entity_type="chaos_scenario",
        entity_id=state.id,
        correlation_id=correlation_id,
        metadata={"scenario_key": scenario_key},
    )
    session.commit()
    return state


def trigger_chaos(
    session: Session, *, business_id: uuid.UUID, scenario_key: str, settings: Settings
) -> bool:
    if not chaos_is_available(settings):
        return False
    state = session.scalar(
        select(ChaosScenarioState).where(
            ChaosScenarioState.business_id == business_id,
            ChaosScenarioState.scenario_key == scenario_key,
            ChaosScenarioState.enabled.is_(True),
        )
    )
    if state is None:
        return False
    state.trigger_count += 1
    state.last_triggered_at = datetime.now(UTC)
    session.commit()
    return True


def begin_attempt(session: Session, run: WorkflowRun) -> WorkflowAttempt:
    number = (
        session.scalar(
            select(func.max(WorkflowAttempt.attempt_number)).where(
                WorkflowAttempt.workflow_run_id == run.id
            )
        )
        or 0
    ) + 1
    first_incomplete = min(
        (step.sequence for step in run.steps if step.status != StepStatus.SUCCEEDED),
        default=len(run.steps),
    )
    attempt = WorkflowAttempt(
        workflow_run_id=run.id,
        attempt_number=number,
        status=WorkflowStatus.RUNNING,
        safe_resume_sequence=first_incomplete,
    )
    session.add(attempt)
    session.flush()
    return attempt


def finish_attempt(
    attempt: WorkflowAttempt, *, status: WorkflowStatus, error_code: str | None = None
) -> None:
    attempt.status = status
    attempt.error_code = error_code
    attempt.finished_at = datetime.now(UTC)


def retry_delay_seconds(run_id: uuid.UUID, retry_number: int) -> int:
    """Exponential backoff with stable bounded jitter for observable tests."""
    base = min(60, 2 ** max(1, retry_number))
    jitter = (run_id.int + retry_number) % 4
    return min(60, base + jitter)


def schedule_retry(
    session: Session,
    *,
    run_id: uuid.UUID,
    retry_number: int,
    max_retries: int,
) -> tuple[WorkflowRun | None, int, bool]:
    run = session.scalar(
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.attempts))
        .where(WorkflowRun.id == run_id)
    )
    delay = retry_delay_seconds(run_id, retry_number)
    dead_letter = retry_number > max_retries
    if run is None:
        return None, delay, dead_letter
    run.retry_count = retry_number
    run.status = WorkflowStatus.DEAD_LETTER if dead_letter else WorkflowStatus.RETRY_SCHEDULED
    if run.attempts:
        run.attempts[-1].status = run.status
        run.attempts[-1].retry_delay_seconds = None if dead_letter else delay
    record_audit_event(
        session,
        business_id=run.business_id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="workflow.dead_lettered" if dead_letter else "workflow.retry.scheduled",
        entity_type="workflow_run",
        entity_id=run.id,
        correlation_id=run.correlation_id,
        metadata={"retry_number": retry_number, "delay_seconds": delay},
    )
    session.commit()
    return run, delay, dead_letter


def prepare_safe_recovery(
    session: Session,
    *,
    run: WorkflowRun,
    actor_id: uuid.UUID,
    actor_role: Role,
    correlation_id: str,
) -> int:
    if actor_role != Role.OWNER:
        raise PermissionError("Only owners can recover a workflow.")
    if run.status not in {WorkflowStatus.FAILED, WorkflowStatus.DEAD_LETTER}:
        raise ValueError("Only failed or dead-letter workflows can be recovered.")
    first_failed = min(
        (
            step.sequence
            for step in run.steps
            if step.status in {StepStatus.FAILED, StepStatus.RUNNING, StepStatus.PENDING}
        ),
        default=1,
    )
    for step in run.steps:
        if step.sequence >= first_failed and step.status != StepStatus.SUCCEEDED:
            step.status = StepStatus.PENDING
            step.error_code = None
            step.started_at = None
            step.finished_at = None
            step.output_summary = {}
    run.status = WorkflowStatus.PENDING
    run.error_code = None
    run.finished_at = None
    document = session.get(Document, run.entity_id)
    if document:
        document.status = DocumentStatus.QUEUED
        document.error_code = None
    record_audit_event(
        session,
        business_id=run.business_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="workflow.recovery.requested",
        entity_type="workflow_run",
        entity_id=run.id,
        correlation_id=correlation_id,
        metadata={"resume_sequence": first_failed, "retry_count": run.retry_count},
    )
    session.commit()
    return first_failed


def serialize_workflow(run: WorkflowRun, audit_events: list[AuditEvent]) -> dict[str, Any]:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def duration(started: datetime | None, finished: datetime | None) -> int | None:
        if not started or not finished:
            return None
        return max(0, round((finished - started).total_seconds() * 1000))

    return {
        "id": str(run.id),
        "workflow_type": run.workflow_type,
        "entity_type": run.entity_type,
        "entity_id": str(run.entity_id),
        "status": run.status.value,
        "correlation_id": run.correlation_id,
        "retry_count": run.retry_count,
        "error_code": run.error_code,
        "safe_error": safe_error_message(run.error_code),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "duration_ms": duration(run.started_at, run.finished_at),
        "steps": [
            {
                "id": str(step.id),
                "sequence": step.sequence,
                "name": step.step_name,
                "status": step.status.value,
                "output": step.output_summary,
                "error_code": step.error_code,
                "started_at": iso(step.started_at),
                "finished_at": iso(step.finished_at),
                "duration_ms": duration(step.started_at, step.finished_at),
            }
            for step in run.steps
        ],
        "attempts": [
            {
                "id": str(attempt.id),
                "number": attempt.attempt_number,
                "status": attempt.status.value,
                "safe_resume_sequence": attempt.safe_resume_sequence,
                "error_code": attempt.error_code,
                "retry_delay_seconds": attempt.retry_delay_seconds,
                "started_at": iso(attempt.started_at),
                "finished_at": iso(attempt.finished_at),
                "duration_ms": duration(attempt.started_at, attempt.finished_at),
            }
            for attempt in run.attempts
        ],
        "decisions": [
            {
                "id": str(event.id),
                "action": event.action,
                "metadata": event.event_metadata,
                "created_at": event.created_at.isoformat(),
            }
            for event in audit_events
        ],
    }


def safe_error_message(error_code: str | None) -> str | None:
    messages = {
        "AI_PROVIDER_TIMEOUT": "AI extraction timed out. It is safe to retry.",
        "AI_SCHEMA_INVALID": "The extraction response was invalid and did not reach the ledger.",
        "STORAGE_TEMPORARILY_UNAVAILABLE": "The original file is temporarily unavailable.",
        "WORKER_INTERRUPTED": "The worker stopped after a saved step. Recovery will resume safely.",
        "DOCUMENT_PROCESSING_FAILED": "Document processing could not be completed.",
    }
    return (
        messages.get(error_code, "The workflow needs review before recovery.")
        if error_code
        else None
    )
