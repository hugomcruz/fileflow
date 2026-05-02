import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session_factory
from app.models import ProcessingJob, Rule

logger = logging.getLogger(__name__)


async def _run_rule(rule_id: str) -> None:
    """Called by the scheduler for each triggered rule."""
    from app.services.processor import processor_service

    async with async_session_factory() as db:
        result = await db.execute(select(Rule).where(Rule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule or not rule.enabled:
            return

        logger.info("Scheduler: triggering rule '%s' (%s)", rule.name, rule.id)
        job = ProcessingJob(rule_id=rule.id, user_id=rule.user_id, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)

    await processor_service.run_job(job.id)


class SchedulerService:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def init(self) -> None:
        """Load all enabled rules from DB and register cron jobs."""
        async with async_session_factory() as db:
            result = await db.execute(select(Rule).where(Rule.enabled == True))  # noqa: E712
            rules = result.scalars().all()

        for rule in rules:
            self._register(rule)
        logger.info("Scheduler initialised with %d rule(s)", len(rules))

    async def sync(self) -> None:
        """Re-read all enabled rules from DB and reconcile scheduled jobs.
        Called periodically by the worker so API-side rule changes are applied."""
        async with async_session_factory() as db:
            result = await db.execute(select(Rule).where(Rule.enabled == True))  # noqa: E712
            rules = result.scalars().all()

        live_ids = {r.id for r in rules}

        # Remove jobs whose rules were deleted or disabled
        for job in self._scheduler.get_jobs():
            if job.id not in live_ids:
                self._scheduler.remove_job(job.id)
                logger.debug("Sync: removed stale job for rule %s", job.id)

        # Add / update jobs for all enabled rules (replace_existing handles updates)
        for rule in rules:
            self._register(rule)

        logger.debug("Scheduler synced – %d active rule(s)", len(rules))

    def add_rule(self, rule: Rule) -> None:
        if not rule.enabled:
            return
        self._register(rule)

    def update_rule(self, rule: Rule) -> None:
        self.remove_rule(rule.id)
        if rule.enabled:
            self._register(rule)

    def remove_rule(self, rule_id: str) -> None:
        try:
            self._scheduler.remove_job(rule_id)
            logger.debug("Removed scheduled job for rule %s", rule_id)
        except Exception:
            pass  # job may not exist

    def _register(self, rule: Rule) -> None:
        try:
            trigger = CronTrigger.from_crontab(rule.schedule)
            self._scheduler.add_job(
                _run_rule,
                trigger=trigger,
                id=rule.id,
                args=[rule.id],
                replace_existing=True,
            )
            logger.debug("Scheduled rule '%s' – cron: %s", rule.name, rule.schedule)
        except Exception as exc:
            logger.warning("Invalid cron for rule %s ('%s'): %s", rule.id, rule.schedule, exc)


scheduler_service = SchedulerService()
