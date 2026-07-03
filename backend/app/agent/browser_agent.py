import asyncio
import time
import traceback

from playwright.async_api import async_playwright

from app.agent.actions import execute_action
from app.agent.audits import run_page_audits
from app.agent.dom_extract import (
    draw_marks_on_screenshot,
    elements_to_text,
    extract_interactive_elements,
    resize_for_model,
)
from app.agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    build_report_user_context,
    build_user_context,
)
from app.ai_client import ask_text, ask_vision
from app.config import SCREENSHOTS_DIR, is_configured
from app.models import Issue, IssueCategory, IssueSeverity, RunStatus, Step, Summary, TestRun
from app.reports.generator import generate_html_report
from app.storage import store

MAX_CONSECUTIVE_FAILURES = 5
MAX_CONSECUTIVE_DECISION_ERRORS = 4

# Smaller/local models don't always follow the exact action vocabulary given
# in the prompt (observed e.g. qwen2.5vl:7b via Ollama returning "clique"
# instead of "click", following the language of the rest of the prompt
# instead of the literal enum). Normalize common variants defensively so a
# weaker model's response doesn't get treated as an unknown action.
_ACTION_ALIASES = {
    "clique": "click",
    "clicar": "click",
    "click": "click",
    "preencher": "fill",
    "digitar": "fill",
    "escrever": "fill",
    "fill": "fill",
    "pressionar": "press_key",
    "tecla": "press_key",
    "apertar": "press_key",
    "press_key": "press_key",
    "rolar": "scroll",
    "rolagem": "scroll",
    "scroll": "scroll",
    "voltar": "go_back",
    "go_back": "go_back",
    "esperar": "wait",
    "aguardar": "wait",
    "wait": "wait",
    "reportar": "report_issue",
    "reportar_problema": "report_issue",
    "report_issue": "report_issue",
    "finalizar": "finish",
    "concluir": "finish",
    "terminar": "finish",
    "finish": "finish",
}


def _normalize_action(action: str) -> str:
    return _ACTION_ALIASES.get((action or "").strip().lower(), action)


def _safe_severity(value) -> IssueSeverity:
    try:
        return IssueSeverity(value)
    except ValueError:
        return IssueSeverity.MINOR


def _safe_category(value) -> IssueCategory:
    try:
        return IssueCategory(value)
    except ValueError:
        return IssueCategory.FUNCTIONAL


def _save_screenshot(run_id: str, index: int, image_bytes: bytes) -> str:
    filename = f"{run_id}_{index}.png"
    (SCREENSHOTS_DIR / filename).write_bytes(image_bytes)
    return filename


async def _publish(run: TestRun, event: dict) -> None:
    await store.publish(run.id, event)


async def _maybe_audit_page(page, run: TestRun, audited_urls: set) -> None:
    """Runs the SEO/accessibility/performance/security audits the first time
    the agent lands on a given URL. Cheap no-op on repeat visits."""
    url = page.url
    if url in audited_urls:
        return
    audited_urls.add(url)

    try:
        issues, metrics = await run_page_audits(page)
    except Exception:
        return

    if metrics:
        run.performance_metrics[url] = metrics
    for issue in issues:
        run.issues.append(issue)
        await _publish(run, {"type": "issue", "issue": issue.model_dump()})
    if issues or metrics:
        store.update(run)


def _history_text(steps: list[Step]) -> str:
    lines = []
    for s in steps[-8:]:
        marker = "OK" if s.ok else f"ERRO: {s.error}"
        lines.append(f"#{s.index} [{s.action}] {s.thought or ''} -> {marker}")
    return "\n".join(lines)


def _issues_text(issues: list[Issue]) -> str:
    lines = []
    for i in issues:
        lines.append(f"- ({i.severity}/{i.category}) {i.title}: {i.description}")
    return "\n".join(lines)


def _steps_text(steps: list[Step]) -> str:
    lines = []
    for s in steps:
        status = "ok" if s.ok else f"falhou: {s.error}"
        lines.append(f"{s.index}. {s.action} target={s.target} value={s.value} -> {status}")
    return "\n".join(lines)


async def run_test(run: TestRun, username: str | None, password: str | None) -> None:
    if not is_configured():
        run.status = RunStatus.FAILED
        run.error = "Nenhum provedor de IA configurado. Adicione um em Configurações antes de iniciar um teste."
        run.finished_at = time.time()
        store.update(run)
        await _publish(run, {"type": "finished", "status": run.status})
        return

    run.status = RunStatus.RUNNING
    store.update(run)
    await _publish(run, {"type": "status", "status": "running"})

    consecutive_failures = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=run.headless)
            context = await browser.new_context(viewport={"width": 1366, "height": 900})
            page = await context.new_page()

            def on_console(msg):
                if msg.type == "error":
                    issue = Issue(
                        severity=IssueSeverity.MINOR,
                        category=IssueCategory.FUNCTIONAL,
                        title="Erro no console do navegador",
                        description=msg.text[:500],
                        source="console",
                        step_index=len(run.steps),
                    )
                    run.issues.append(issue)
                    asyncio.create_task(_publish(run, {"type": "issue", "issue": issue.model_dump()}))

            def on_page_error(exc):
                issue = Issue(
                    severity=IssueSeverity.MAJOR,
                    category=IssueCategory.FUNCTIONAL,
                    title="Exceção JavaScript não tratada",
                    description=str(exc)[:500],
                    source="console",
                    step_index=len(run.steps),
                )
                run.issues.append(issue)
                asyncio.create_task(_publish(run, {"type": "issue", "issue": issue.model_dump()}))

            def on_response(response):
                if response.status >= 400:
                    issue = Issue(
                        severity=IssueSeverity.MAJOR if response.status >= 500 else IssueSeverity.MINOR,
                        category=IssueCategory.FUNCTIONAL,
                        title=f"Requisição HTTP {response.status}",
                        description=f"{response.request.method} {response.url} retornou {response.status}",
                        source="network",
                        step_index=len(run.steps),
                    )
                    run.issues.append(issue)
                    asyncio.create_task(_publish(run, {"type": "issue", "issue": issue.model_dump()}))

            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("response", on_response)

            await page.goto(run.url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(800)

            audited_urls: set = set()
            await _maybe_audit_page(page, run, audited_urls)

            step_index = 0
            consecutive_decision_errors = 0
            while step_index < run.max_steps:
                await _maybe_audit_page(page, run, audited_urls)
                elements = await extract_interactive_elements(page)
                raw_screenshot = await page.screenshot(full_page=False)
                marked_screenshot = draw_marks_on_screenshot(raw_screenshot, elements)
                filename = _save_screenshot(run.id, step_index, marked_screenshot)
                model_screenshot = resize_for_model(marked_screenshot)

                user_text = build_user_context(
                    goal=run.goal,
                    url=page.url,
                    has_credentials=bool(username and password),
                    history_text=_history_text(run.steps),
                    elements_text=elements_to_text(elements),
                )
                if username and password:
                    user_text += f"\n\nCredenciais de teste: usuário='{username}' senha='{password}'"

                try:
                    decision, provider_used = await asyncio.to_thread(
                        ask_vision, AGENT_SYSTEM_PROMPT, user_text, model_screenshot
                    )
                    consecutive_decision_errors = 0
                except Exception as exc:  # noqa: BLE001
                    consecutive_decision_errors += 1
                    step = Step(index=step_index, action="decision_error", ok=False, error=str(exc), screenshot=filename)
                    run.steps.append(step)
                    store.update(run)
                    await _publish(run, {"type": "step", "step": step.model_dump()})
                    if consecutive_decision_errors >= MAX_CONSECUTIVE_DECISION_ERRORS:
                        run.error = "Interrompido após várias falhas consecutivas ao consultar a IA."
                        break
                    step_index += 1
                    await page.wait_for_timeout(1500)
                    continue

                action = _normalize_action(decision.get("action", "wait"))
                mark_id = decision.get("mark_id")
                value = decision.get("value")
                thought = decision.get("thought")

                if action == "report_issue" and decision.get("issue"):
                    issue_data = decision["issue"]
                    issue = Issue(
                        severity=_safe_severity(issue_data.get("severity", "minor")),
                        category=_safe_category(issue_data.get("category", "functional")),
                        title=issue_data.get("title", "Problema identificado"),
                        description=issue_data.get("description", ""),
                        recommendation=issue_data.get("recommendation"),
                        screenshot=filename,
                        step_index=step_index,
                        source="agent",
                    )
                    run.issues.append(issue)
                    step = Step(
                        index=step_index,
                        action="report_issue",
                        thought=thought,
                        screenshot=filename,
                        ok=True,
                        provider=provider_used,
                    )
                    run.steps.append(step)
                    store.update(run)
                    await _publish(run, {"type": "issue", "issue": issue.model_dump()})
                    await _publish(run, {"type": "step", "step": step.model_dump()})
                    step_index += 1
                    continue

                if action == "finish":
                    step = Step(
                        index=step_index, action="finish", thought=thought, screenshot=filename, ok=True, provider=provider_used
                    )
                    run.steps.append(step)
                    store.update(run)
                    await _publish(run, {"type": "step", "step": step.model_dump()})
                    break

                result = await execute_action(page, action, mark_id, value, elements)
                step = Step(
                    index=step_index,
                    action=action,
                    target=str(mark_id) if mark_id is not None else None,
                    value=value,
                    thought=thought,
                    screenshot=filename,
                    ok=result.ok,
                    error=result.error,
                    provider=provider_used,
                )
                run.steps.append(step)
                store.update(run)
                await _publish(run, {"type": "step", "step": step.model_dump()})

                consecutive_failures = 0 if result.ok else consecutive_failures + 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    run.error = "Interrompido após várias falhas consecutivas de ação."
                    break

                await page.wait_for_timeout(600)
                step_index += 1

            await context.close()
            await browser.close()

        await _build_final_report(run)
        run.status = RunStatus.FAILED if run.error else RunStatus.COMPLETED

    except Exception as exc:  # noqa: BLE001
        run.status = RunStatus.FAILED
        run.error = f"{exc}\n{traceback.format_exc(limit=3)}"

    run.finished_at = time.time()
    store.update(run)
    await _publish(run, {"type": "finished", "status": run.status})


def _performance_text(performance_metrics: dict) -> str:
    lines = []
    for url, metrics in performance_metrics.items():
        load_time = metrics.get("loadTime")
        load_s = f"{load_time / 1000:.1f}s" if load_time else "n/d"
        lines.append(
            f"- {url}: carregamento={load_s}, requisições={metrics.get('resourceCount', 'n/d')}, "
            f"transferido={(metrics.get('transferSize', 0) or 0) / (1024*1024):.1f}MB"
        )
    return "\n".join(lines)


async def _build_final_report(run: TestRun) -> None:
    try:
        report_data, _provider = await asyncio.to_thread(
            ask_text,
            REPORT_SYSTEM_PROMPT,
            build_report_user_context(
                run.url,
                run.goal,
                _steps_text(run.steps),
                _issues_text(run.issues),
                _performance_text(run.performance_metrics),
            ),
        )
        run.summary = Summary(
            overall_assessment=report_data.get("overall_assessment", ""),
            score=report_data.get("score"),
            functional_suggestions=report_data.get("functional_suggestions", []),
            ui_ux_suggestions=report_data.get("ui_ux_suggestions", []),
            seo_suggestions=report_data.get("seo_suggestions", []),
            security_suggestions=report_data.get("security_suggestions", []),
        )
    except Exception as exc:  # noqa: BLE001
        run.summary = Summary(overall_assessment=f"Não foi possível gerar o resumo automático: {exc}")

    run.report_html_path = generate_html_report(run)
