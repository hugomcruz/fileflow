"""
FileFlow Worker
===============
Runs as a separate container.  Responsibilities:
  1. Owns the APScheduler – fires cron jobs for enabled rules.
  2. Periodically re-syncs the schedule from the DB so that rule changes
     made through the API (create / update / toggle / delete) are applied.
  3. Polls the `processing_jobs` table for pending jobs created by the API's
     "Run Now" endpoint and executes them.
"""

import asyncio
import logging

from sqlalchemy import select, text

from app.database import async_session_factory
from app.models import ProcessingJob
from app.services.processor import processor_service
from app.services.scheduler import scheduler_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
# Keep noisy third-party libraries at WARNING so debug output stays readable
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logging.getLogger("sqlalchemy").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# IDs of jobs currently being executed – prevents double-dispatch when the
# poll loop fires before the processor has had a chance to mark the job as
# "running" in the DB.
_in_flight: set[str] = set()


async def _execute_job(job_id: str) -> None:
    try:
        await processor_service.run_job(job_id)
    finally:
        _in_flight.discard(job_id)


async def poll_pending_jobs() -> None:
    """Pick up jobs with status='pending' (created by the API's /run endpoint)."""
    while True:
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(ProcessingJob).where(ProcessingJob.status == "pending")
                )
                jobs = result.scalars().all()

            for job in jobs:
                if job.id not in _in_flight:
                    _in_flight.add(job.id)
                    asyncio.create_task(_execute_job(job.id))

        except Exception as exc:
            logger.warning("poll_pending_jobs error: %s", exc)

        await asyncio.sleep(5)


async def resync_scheduler() -> None:
    """Reload rule schedules from DB every 30 s to apply API-side changes."""
    while True:
        await asyncio.sleep(30)
        try:
            await scheduler_service.sync()
        except Exception as exc:
            logger.warning("resync_scheduler error: %s", exc)


async def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    """Wait until the DB is reachable and migrations have been applied."""
    for attempt in range(1, retries + 1):
        try:
            async with async_session_factory() as db:
                await db.execute(text("SELECT 1 FROM rules LIMIT 1"))
            logger.info("Database ready.")
            return
        except Exception as exc:
            logger.info("Waiting for database... (attempt %d/%d): %s", attempt, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("Database not ready after %d attempts — giving up." % retries)


async def main() -> None:
    await wait_for_db()
    scheduler_service.start()
    await scheduler_service.init()
    logger.info("FileFlow worker started")

    await asyncio.gather(
        poll_pending_jobs(),
        resync_scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
