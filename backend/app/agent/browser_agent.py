import asyncio
import time
import traceback
import uuid

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
from app.models import Issue, IssueCategory, IssueSeverity, RunStatus, Step, Summary, SuggestionItem, TestRun
from app.reports.generator import generate_html_report
from app.storage import store

MAX_CONSECUTIVE_FAILURES = 5
MAX_CONSECUTIVE_DECISION_ERRORS = 4

# Don't take more than one "event" screenshot (console/network errors) within
# this window — a single broken page load can fire a dozen failed requests at
# once, and we don't need a near-identical screenshot for each of them.
EVENT_SCREENSHOT_MIN_INTERVAL = 1.5

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

_ACTION_VERBS_PT = {
    "click": "Clicou em",
    "fill": "Preencheu um campo",
    "press_key": "Pressionou a tecla",
    "scroll": "Rolou a página",
    "go_back": "Voltou para a página anterior",
    "wait": "Aguardou",
    "report_issue": "Registrou um problema",
    "finish": "Finalizou o teste",
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


def _save_screenshot(run_id: str, suffix: str, image_bytes: bytes) -> str:
    filename = f"{run_id}_{suffix}.png"
    (SCREENSHOTS_DIR / filename).write_bytes(image_bytes)
    return filename


async def _publish(run: TestRun, event: dict) -> None:
    await store.publish(run.id, event)


def _describe_step(s: Step) -> str:
    verb = _ACTION_VERBS_PT.get(s.action, s.action)
    target = f" (elemento #{s.target})" if s.target else ""
    detail = f": \"{s.value}\"" if s.value and s.action in ("fill", "press_key") else ""
    return f"{verb}{target}{detail}"


def _path_summary(steps: list[Step], current_url: str) -> str:
    """Numbered breadcrumb of the real actions taken before an issue was
    found — grounded entirely in recorded steps, not invented by an LLM."""
    relevant = [s for s in steps if s.action not in ("report_issue", "decision_error")][-8:]
    lines = [f"{i + 1}. {_describe_step(s)}" for i, s in enumerate(relevant)]
    if not lines:
        lines = ["1. Acessou a página diretamente (nenhuma ação anterior)"]
    lines.append(f"→ Problema identificado em: {current_url}")
    return "\n".join(lines)


def _history_text(steps: list[Step]) -> str:
    lines = []
    for s in steps[-8:]:
        marker = "OK" if s.ok else f"ERRO: {s.error}"
        lines.append(f"#{s.index} [{s.action}] {s.thought or ''} -> {marker}")
    return "\n".join(lines)


def _issues_text(issues: list[Issue]) -> str:
    lines = []
    for idx, i in enumerate(issues):
        lines.append(f"[{idx}] ({i.severity}/{i.category}) {i.title}: {i.description} — URL: {i.url or '(desconhecida)'}")
    return "\n".join(lines)


def _steps_text(steps: list[Step]) -> str:
    lines = []
    for s in steps:
        status = "ok" if s.ok else f"falhou: {s.error}"
        lines.append(f"{s.index}. {s.action} target={s.target} value={s.value} -> {status}")
    return "\n".join(lines)


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


def _safe_score(value) -> int | None:
    """LLMs (especially weaker/local ones) sometimes return a score like 7.5
    instead of an int despite the prompt asking for 0-10 — round it instead
    of letting the whole Summary fail Pydantic validation over one field."""
    if value is None:
        return None
    try:
        return max(0, min(10, round(float(value))))
    except (TypeError, ValueError):
        return None


def _to_suggestion_items(raw_list, issues: list[Issue]) -> list[SuggestionItem]:
    """Converts the LLM's suggestion entries into SuggestionItem objects,
    pulling the real url/screenshot from the issue they reference (when the
    model gave us a valid issue_index) instead of letting the LLM invent
    those details itself."""
    items: list[SuggestionItem] = []
    if not isinstance(raw_list, list):
        return items
    for entry in raw_list:
        if isinstance(entry, str):
            items.append(SuggestionItem(text=entry))
            continue
        if not isinstance(entry, dict):
            continue
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        idx = entry.get("issue_index")
        url = None
        screenshot = None
        severity = None
        if isinstance(idx, int) and 0 <= idx < len(issues):
            ref = issues[idx]
            url = ref.url
            screenshot = ref.screenshot
            severity = ref.severity
        items.append(SuggestionItem(text=text, url=url, screenshot=screenshot, severity=severity))
    return items


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

    if issues:
        try:
            raw_screenshot = await page.screenshot(full_page=False)
            filename = _save_screenshot(run.id, f"audit-{uuid.uuid4().hex[:8]}", raw_screenshot)
        except Exception:
            filename = None
        path = _path_summary(run.steps, url)
        for issue in issues:
            issue.screenshot = filename
            issue.url = url
            issue.path_summary = path
            run.issues.append(issue)
            await _publish(run, {"type": "issue", "issue": issue.model_dump()})

    if issues or metrics:
        store.update(run)


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
    event_screenshot_state = {"filename": None, "time": 0.0}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=run.headless)
            context = await browser.new_context(viewport={"width": 1366, "height": 900})
            page = await context.new_page()

            async def event_screenshot() -> str | None:
                now = time.time()
                if event_screenshot_state["filename"] and now - event_screenshot_state["time"] < EVENT_SCREENSHOT_MIN_INTERVAL:
                    return event_screenshot_state["filename"]
                try:
                    raw = await page.screenshot(full_page=False)
                except Exception:
                    return event_screenshot_state["filename"]
                filename = _save_screenshot(run.id, f"evt-{uuid.uuid4().hex[:8]}", raw)
                event_screenshot_state["filename"] = filename
                event_screenshot_state["time"] = now
                return filename

            async def record_runtime_issue(severity, category, title, description, source):
                filename = await event_screenshot()
                issue = Issue(
                    severity=severity,
                    category=category,
                    title=title,
                    description=description,
                    source=source,
                    step_index=len(run.steps),
                    screenshot=filename,
                    url=page.url,
                    path_summary=_path_summary(run.steps, page.url),
                )
                run.issues.append(issue)
                store.update(run)
                await _publish(run, {"type": "issue", "issue": issue.model_dump()})

            def on_console(msg):
                if msg.type == "error":
                    asyncio.create_task(
                        record_runtime_issue(
                            IssueSeverity.MINOR,
                            IssueCategory.FUNCTIONAL,
                            "Erro no console do navegador",
                            msg.text[:500],
                            "console",
                        )
                    )

            def on_page_error(exc):
                asyncio.create_task(
                    record_runtime_issue(
                        IssueSeverity.MAJOR,
                        IssueCategory.FUNCTIONAL,
                        "Exceção JavaScript não tratada",
                        str(exc)[:500],
                        "console",
                    )
                )

            def on_response(response):
                if response.status >= 400:
                    asyncio.create_task(
                        record_runtime_issue(
                            IssueSeverity.MAJOR if response.status >= 500 else IssueSeverity.MINOR,
                            IssueCategory.FUNCTIONAL,
                            f"Requisição HTTP {response.status}",
                            f"{response.request.method} {response.url} retornou {response.status}",
                            "network",
                        )
                    )

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
                filename = _save_screenshot(run.id, str(step_index), marked_screenshot)
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
                        url=page.url,
                        path_summary=_path_summary(run.steps, page.url),
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
            score=_safe_score(report_data.get("score")),
            functional_suggestions=_to_suggestion_items(report_data.get("functional_suggestions", []), run.issues),
            ui_ux_suggestions=_to_suggestion_items(report_data.get("ui_ux_suggestions", []), run.issues),
            seo_suggestions=_to_suggestion_items(report_data.get("seo_suggestions", []), run.issues),
            security_suggestions=_to_suggestion_items(report_data.get("security_suggestions", []), run.issues),
        )
    except Exception as exc:  # noqa: BLE001
        run.summary = Summary(overall_assessment=f"Não foi possível gerar o resumo automático: {exc}")

    run.report_html_path = generate_html_report(run)
