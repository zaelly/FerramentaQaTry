import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class IssueCategory(str, Enum):
    FUNCTIONAL = "functional"
    UI_UX = "ui_ux"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    SEO = "seo"
    SECURITY = "security"


class TestRequest(BaseModel):
    url: str
    goal: str = Field(default="Explore o site como um usuário real e identifique problemas de funcionamento ou de usabilidade.")
    username: Optional[str] = None
    password: Optional[str] = None
    max_steps: int = 25
    headless: bool = True


class Step(BaseModel):
    index: int
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    thought: Optional[str] = None
    screenshot: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    ok: bool = True
    error: Optional[str] = None
    provider: Optional[str] = None


class Issue(BaseModel):
    id: str = Field(default_factory=lambda: new_id("issue"))
    severity: IssueSeverity
    category: IssueCategory
    title: str
    description: str
    recommendation: Optional[str] = None
    screenshot: Optional[str] = None
    step_index: Optional[int] = None
    source: str = "agent"  # agent | console | network | seo | security | accessibility | performance | sso
    timestamp: float = Field(default_factory=time.time)


class Summary(BaseModel):
    overall_assessment: str = ""
    score: Optional[int] = None
    functional_suggestions: list[str] = Field(default_factory=list)
    ui_ux_suggestions: list[str] = Field(default_factory=list)
    seo_suggestions: list[str] = Field(default_factory=list)
    security_suggestions: list[str] = Field(default_factory=list)


class TestRun(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    url: str
    goal: str
    max_steps: int = 25
    headless: bool = True
    status: RunStatus = RunStatus.QUEUED
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None
    steps: list[Step] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    performance_metrics: dict = Field(default_factory=dict)  # url -> {loadTime, ttfb, fcp, resourceCount, transferSize}
    error: Optional[str] = None
    report_html_path: Optional[str] = None
