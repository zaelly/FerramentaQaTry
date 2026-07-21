from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import REPORTS_DIR
from app.models import STATUS_LABELS_PT, TestRun

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _score_class(score: int | None) -> str:
    if score is None:
        return "mid"
    if score >= 8:
        return "good"
    if score >= 5:
        return "mid"
    return "bad"


def group_issues_by_url(issues: list) -> list[dict]:
    """Groups issues by the URL they were found on, so the report shows a
    single screenshot per page with every issue found there listed under it,
    instead of repeating the same screenshot once per issue."""
    groups: dict[str, dict] = {}
    order: list[str] = []
    for issue in issues:
        key = issue.url or ""
        if key not in groups:
            groups[key] = {"url": issue.url, "screenshot": issue.screenshot, "issues": []}
            order.append(key)
        group = groups[key]
        if not group["screenshot"] and issue.screenshot:
            group["screenshot"] = issue.screenshot
        group["issues"].append(issue)
    return [groups[key] for key in order]


def generate_html_report(run: TestRun) -> str:
    template = _env.get_template("report_template.html")
    started_at_str = datetime.fromtimestamp(run.started_at).strftime("%d/%m/%Y %H:%M")
    html = template.render(
        run=run,
        started_at_str=started_at_str,
        status_label=STATUS_LABELS_PT.get(run.status, run.status),
        score_class=_score_class(run.summary.score),
        issue_groups=group_issues_by_url(run.issues),
    )
    path = REPORTS_DIR / f"{run.id}.html"
    path.write_text(html, encoding="utf-8")
    return f"{run.id}.html"
