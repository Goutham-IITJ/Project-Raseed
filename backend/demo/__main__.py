import argparse
import json
from datetime import date

from backend.app.config import Settings
from backend.app.database import make_engine
from backend.demo.seed import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the explicit development-only local demo database."
    )
    parser.add_argument("command", choices=["seed"])
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="First-seed date (YYYY-MM-DD); defaults to today in Asia/Kolkata.",
    )
    args = parser.parse_args()
    settings = Settings()
    if not settings.local_demo:
        parser.error("Set LOCAL_DEMO=true and APP_ENV=development with a local *_demo database.")
    engine = make_engine(settings.database_url)
    try:
        print(json.dumps(seed_demo(engine, settings, as_of=args.as_of)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
