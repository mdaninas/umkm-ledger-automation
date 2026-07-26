from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import seed_demo


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        healthcheck_externals=False,
        jwt_secret="test-only-secret-with-enough-entropy",
    )


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        with app.state.database.session_factory() as session:
            seed_demo(session, settings)
        yield test_client
