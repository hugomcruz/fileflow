import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DB
from app.models import ProcessingJob, Rule
from app.schemas import RuleCreate, RuleOut, RuleUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[RuleOut])
async def list_rules(current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule)
        .where(Rule.user_id == current_user["sub"])
        .options(
            selectinload(Rule.jobs)
        )
        .order_by(Rule.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=RuleOut, status_code=201)
async def create_rule(body: RuleCreate, current_user: CurrentUser, db: DB):
    rule = Rule(
        user_id=current_user["sub"],
        name=body.name,
        source_provider=body.source_provider,
        source_connection_id=body.source_connection_id,
        source_path=body.source_path,
        file_types=body.file_types,
        file_pattern=body.file_pattern,
        target_provider=body.target_provider,
        target_connection_id=body.target_connection_id,
        target_path=body.target_path,
        schedule=body.schedule,
        enabled=True,
        delete_source=body.delete_source,
        recursive=body.recursive,
    )
    db.add(rule)
    await db.commit()

    result = await db.execute(
        select(Rule).where(Rule.id == rule.id).options(selectinload(Rule.jobs))
    )
    rule = result.scalar_one()

    return rule


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(rule_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule)
        .where(Rule.id == rule_id, Rule.user_id == current_user["sub"])
        .options(selectinload(Rule.jobs))
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: str, body: RuleUpdate, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.user_id == current_user["sub"])
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    await db.commit()

    result = await db.execute(
        select(Rule).where(Rule.id == rule_id).options(selectinload(Rule.jobs))
    )
    rule = result.scalar_one()

    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.user_id == current_user["sub"])
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()


@router.post("/{rule_id}/toggle", response_model=RuleOut)
async def toggle_rule(rule_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.user_id == current_user["sub"])
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.enabled = not rule.enabled
    await db.commit()

    result = await db.execute(
        select(Rule).where(Rule.id == rule_id).options(selectinload(Rule.jobs))
    )
    rule = result.scalar_one()

    return rule


@router.post("/{rule_id}/run")
async def run_rule_now(rule_id: str, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.user_id == current_user["sub"])
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    job = ProcessingJob(rule_id=rule.id, user_id=rule.user_id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # The worker container polls for pending jobs and will pick this up.
    return {"jobId": job.id}
