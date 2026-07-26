from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.config import Settings
from app.database import Database
from app.health import probe_components
from app.schemas import HealthComponent, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "healthy", "service": "api"}


@router.get("", response_model=HealthResponse)
def ready(request: Request, response: Response) -> HealthResponse:
    settings: Settings = request.app.state.settings
    database: Database = request.app.state.database
    components = probe_components(settings, database)
    is_healthy = all(
        component.status in {"healthy", "skipped"} for component in components.values()
    )
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="healthy" if is_healthy else "degraded",
        service="api",
        environment=settings.environment,
        timestamp=datetime.now(UTC),
        components=components,
    )


def liveness_components() -> dict[str, HealthComponent]:
    return {"api": HealthComponent(status="healthy", latency_ms=0)}
