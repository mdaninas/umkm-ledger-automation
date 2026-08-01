import argparse
import json
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.database import Database
from app.eval_service import create_evaluation_run, execute_evaluation_run
from app.models import Business


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persisted golden finance evaluation.")
    parser.add_argument("--business-id", type=uuid.UUID)
    parser.add_argument("--model")
    parser.add_argument("--prompt-version")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            business_id = args.business_id or session.scalar(
                select(Business.id).order_by(Business.created_at)
            )
            if business_id is None:
                raise SystemExit("Seed a business before running evaluations.")
            run = create_evaluation_run(
                session,
                business_id=business_id,
                created_by=None,
                settings=settings,
                correlation_id=f"eval-cli-{uuid.uuid4()}",
                model=args.model,
                prompt_version=args.prompt_version,
            )
            completed = execute_evaluation_run(session, run_id=run.id, settings=settings)
            print(json.dumps({"run_id": str(completed.id), **completed.summary}, indent=2))
            if not completed.summary.get("target_passed"):
                raise SystemExit(1)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
