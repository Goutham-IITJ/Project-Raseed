import argparse
import logging
import time
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import Settings
from backend.app.database import make_engine, make_session_factory
from backend.app.ingestion.factory import make_extractor, make_storage
from backend.app.ingestion.service import LocalTaskQueue, OutboxDispatcher, ReceiptProcessor
from backend.app.insights.worker import InsightDispatcher, InsightProcessor, LocalInsightTaskQueue
from backend.app.inventory.worker import (
    InventoryDispatcher,
    InventoryProcessor,
    LocalInventoryTaskQueue,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dispatch receipt, inventory, and scheduled insight jobs."
    )
    parser.add_argument("--once", action="store_true", help="Process one ready batch and exit.")
    parser.add_argument(
        "--retry", type=UUID, help="Explicitly requeue a FAILED/NEEDS_REVIEW receipt."
    )
    parser.add_argument(
        "--retry-inventory", type=UUID, help="Requeue exhausted inventory delivery by purchase ID."
    )
    parser.add_argument(
        "--retry-insight", type=UUID, help="Requeue exhausted insight delivery by event ID."
    )
    args = parser.parse_args()
    # All three dispatchers run outside the API process.
    settings = Settings()
    engine = make_engine(settings.database_url)
    processor = ReceiptProcessor(
        make_session_factory(engine),
        make_storage(settings),
        make_extractor(settings),
        settings,
    )
    dispatcher = OutboxDispatcher(processor.factory, LocalTaskQueue(processor))
    inventory = InventoryProcessor(processor.factory)
    inventory_dispatcher = InventoryDispatcher(
        processor.factory, LocalInventoryTaskQueue(inventory)
    )
    insights = InsightProcessor(processor.factory)
    insight_dispatcher = InsightDispatcher(processor.factory, LocalInsightTaskQueue(insights))
    try:
        if args.retry:
            processor.retry(args.retry)
        if args.retry_inventory:
            inventory.retry(args.retry_inventory)
        if args.retry_insight:
            insights.retry(args.retry_insight)
        while True:
            try:
                dispatcher.dispatch_once()
                inventory_dispatcher.dispatch_once()
                insight_dispatcher.schedule_once()
                insight_dispatcher.dispatch_once()
            except SQLAlchemyError:
                logging.error("Worker database unavailable; durable jobs remain pending.")
                if args.once:
                    raise
            if args.once:
                break
            time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
