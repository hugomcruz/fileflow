from datetime import datetime

from pydantic import AliasGenerator, BaseModel, ConfigDict, EmailStr, field_validator
from pydantic.alias_generators import to_camel


# ─── Base for all response schemas (serializes as camelCase) ──────────────────

class CamelOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        populate_by_name=True,
    )


# ─── User ─────────────────────────────────────────────────────────────────────

class ConnectionSummary(CamelOut):
    provider: str
    expires_at: datetime | None
    updated_at: datetime


class UserOut(CamelOut):
    id: str
    email: str
    name: str | None
    avatar: str | None
    provider: str
    created_at: datetime
    connections: list[ConnectionSummary] = []


# ─── Email auth ───────────────────────────────────────────────────────────────

class EmailRegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class EmailLoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str


# ─── Rule ─────────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(validation_alias=to_camel),
        populate_by_name=True,
    )

    name: str
    source_provider: str
    source_connection_id: str | None = None
    source_path: str
    file_types: list[str]
    file_pattern: str | None = None
    target_provider: str
    target_connection_id: str | None = None
    target_path: str
    schedule: str = "0 * * * *"
    delete_source: bool = False
    recursive: bool = False


class RuleUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(validation_alias=to_camel),
        populate_by_name=True,
    )

    name: str | None = None
    source_provider: str | None = None
    source_connection_id: str | None = None
    source_path: str | None = None
    file_types: list[str] | None = None
    file_pattern: str | None = None
    target_provider: str | None = None
    target_connection_id: str | None = None
    target_path: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    delete_source: bool | None = None
    recursive: bool | None = None


class JobSummary(CamelOut):
    status: str
    started_at: datetime
    files_processed: int


class RuleOut(CamelOut):
    id: str
    user_id: str
    name: str
    source_provider: str
    source_connection_id: str | None
    source_path: str
    file_types: list[str]
    file_pattern: str | None
    target_provider: str
    target_connection_id: str | None
    target_path: str
    schedule: str
    enabled: bool
    delete_source: bool
    recursive: bool
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    jobs: list[JobSummary] = []


# ─── Job ──────────────────────────────────────────────────────────────────────

class RuleSummary(CamelOut):
    name: str
    source_provider: str
    target_provider: str


class ProcessingLogOut(CamelOut):
    id: str
    original_name: str
    new_name: str | None
    source_path: str | None
    target_path: str | None
    source_connection: str | None
    target_connection: str | None
    status: str
    message: str | None
    processed_at: datetime


class JobListOut(CamelOut):
    """Used in list responses – does not include per-file logs."""
    id: str
    rule_id: str
    user_id: str
    status: str
    files_processed: int
    files_skipped: int
    files_errored: int
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    rule: RuleSummary | None = None


class JobOut(CamelOut):
    id: str
    rule_id: str
    user_id: str
    status: str
    files_processed: int
    files_skipped: int
    files_errored: int
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    rule: RuleSummary | None = None
    logs: list[ProcessingLogOut] = []


class JobsPage(BaseModel):
    jobs: list[JobListOut]
    total: int
    page: int
    limit: int
    pages: int


# ─── Connection ───────────────────────────────────────────────────────────────

class ConnectionOut(CamelOut):
    id: str
    provider: str
    display_name: str | None
    scope: str | None
    expires_at: datetime | None
    updated_at: datetime


class ConnectionRename(BaseModel):
    display_name: str
