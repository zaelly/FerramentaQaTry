import re
import smtplib
import uuid
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from app.config import SCREENSHOTS_DIR, get_smtp_settings
from app.models import STATUS_LABELS_PT, TestRun

MAX_RECIPIENTS = 10
MAX_EMBEDDED_SCREENSHOTS = 12
_EMAIL_IMAGE_MAX_WIDTH = 800

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailNotConfiguredError(Exception):
    pass


class InvalidRecipientsError(Exception):
    pass


def validate_recipients(recipients: list[str]) -> list[str]:
    cleaned = [r.strip() for r in recipients if r.strip()]
    if not cleaned:
        raise InvalidRecipientsError("Informe pelo menos um destinatário.")
    if len(cleaned) > MAX_RECIPIENTS:
        raise InvalidRecipientsError(f"No máximo {MAX_RECIPIENTS} destinatários por envio (recebido: {len(cleaned)}).")
    invalid = [r for r in cleaned if not _EMAIL_RE.match(r)]
    if invalid:
        raise InvalidRecipientsError(f"E-mail(s) inválido(s): {', '.join(invalid)}")
    return cleaned


def _score_color(score: int | None) -> str:
    if score is None:
        return "#6b7280"
    if score >= 8:
        return "#16a34a"
    if score >= 5:
        return "#d97706"
    return "#dc2626"


def _compress_for_email(image_path: Path) -> bytes:
    image = Image.open(image_path).convert("RGB")
    if image.width > _EMAIL_IMAGE_MAX_WIDTH:
        ratio = _EMAIL_IMAGE_MAX_WIDTH / image.width
        image = image.resize((_EMAIL_IMAGE_MAX_WIDTH, round(image.height * ratio)), Image.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=72)
    return buffer.getvalue()


def build_email_content(run: TestRun, custom_message: str | None) -> tuple[str, list[tuple[str, bytes]]]:
    """Renders the email-safe HTML report and collects the (at most
    MAX_EMBEDDED_SCREENSHOTS) unique screenshots referenced by issues,
    downscaled/recompressed for a reasonable email size. Returns
    (html, [(content_id, jpeg_bytes), ...])."""
    screenshot_cids: dict[str, str] = {}
    inline_images: list[tuple[str, bytes]] = []

    for issue in run.issues:
        if not issue.screenshot or issue.screenshot in screenshot_cids:
            continue
        if len(inline_images) >= MAX_EMBEDDED_SCREENSHOTS:
            continue
        path = SCREENSHOTS_DIR / issue.screenshot
        if not path.exists():
            continue
        cid = f"shot-{uuid.uuid4().hex[:10]}"
        try:
            inline_images.append((cid, _compress_for_email(path)))
            screenshot_cids[issue.screenshot] = cid
        except Exception:
            continue

    template = _env.get_template("report_email_template.html")
    html = template.render(
        run=run,
        started_at_str=datetime.fromtimestamp(run.started_at).strftime("%d/%m/%Y %H:%M"),
        status_label=STATUS_LABELS_PT.get(run.status, run.status),
        score_color=_score_color(run.summary.score),
        custom_message=custom_message,
        screenshot_cids=screenshot_cids,
        suggestion_groups=[
            ("Sugestões funcionais", run.summary.functional_suggestions),
            ("Sugestões de UI/UX", run.summary.ui_ux_suggestions),
            ("Sugestões de SEO", run.summary.seo_suggestions),
            ("Sugestões de segurança", run.summary.security_suggestions),
        ],
    )
    return html, inline_images


def send_report_email(run: TestRun, recipients: list[str], custom_message: str | None = None) -> None:
    recipients = validate_recipients(recipients)
    smtp = get_smtp_settings()
    if not smtp.get("host") or not smtp.get("from_email"):
        raise EmailNotConfiguredError("Configure o SMTP em Configurações antes de enviar relatórios por e-mail.")

    html, inline_images = build_email_content(run, custom_message)

    msg = MIMEMultipart("related")
    msg["Subject"] = f"Relatório de QA — {run.url}" + (
        f" (nota {run.summary.score}/10)" if run.summary.score is not None else ""
    )
    from_name = smtp.get("from_name") or "QA Agent"
    msg["From"] = f"{from_name} <{smtp['from_email']}>"
    msg["To"] = ", ".join(recipients)

    alternative = MIMEMultipart("alternative")
    plain_text = (
        f"Relatório de QA para {run.url}\n"
        f"Nota geral: {run.summary.score if run.summary.score is not None else '-'}/10\n\n"
        f"{run.summary.overall_assessment}\n\n"
        "Abra este e-mail em um cliente com suporte a HTML para ver o relatório completo."
    )
    alternative.attach(MIMEText(plain_text, "plain", "utf-8"))
    alternative.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alternative)

    for cid, image_bytes in inline_images:
        image_part = MIMEImage(image_bytes, _subtype="jpeg")
        image_part.add_header("Content-ID", f"<{cid}>")
        image_part.add_header("Content-Disposition", "inline", filename=f"{cid}.jpg")
        msg.attach(image_part)

    port = int(smtp.get("port") or 587)
    encryption = smtp.get("encryption", "starttls")

    if encryption == "ssl":
        server = smtplib.SMTP_SSL(smtp["host"], port, timeout=20)
    else:
        server = smtplib.SMTP(smtp["host"], port, timeout=20)
        if encryption == "starttls":
            server.starttls()

    try:
        if smtp.get("username"):
            server.login(smtp["username"], smtp.get("password", ""))
        server.sendmail(smtp["from_email"], recipients, msg.as_string())
    finally:
        server.quit()
