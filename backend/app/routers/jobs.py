import math

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DB
from app.models import ProcessingJob, Rule
from app.schemas import JobListOut, JobOut, JobsPage

router = APIRouter()


@router.get("/", response_model=JobsPage)
async def list_jobs(
    current_user: CurrentUser,
    db: DB,
    page: int = 1,
    limit: int = 20,
):
    limit = min(limit, 100)
    skip = (page - 1) * limit

    total_result = await db.execute(
        select(func.count()).where(ProcessingJob.user_id == current_user["sub"])
        .select_from(ProcessingJob)
    )
    total = total_result.scalar_one()

    jobs_result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.user_id == current_user["sub"])
        .options(selectinload(ProcessingJob.rule))
        .order_by(ProcessingJob.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    jobs = jobs_result.scalars().all()

    return JobsPage(
        jobs=jobs,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total else 1,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id, ProcessingJob.user_id == current_user["sub"])
        .options(selectinload(ProcessingJob.rule), selectinload(ProcessingJob.logs))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
