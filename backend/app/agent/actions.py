from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page

from app.agent.dom_extract import InteractiveElement


@dataclass
class ActionResult:
    ok: bool
    description: str
    error: Optional[str] = None


def _find_element(elements: list[InteractiveElement], mark_id: Optional[int]) -> Optional[InteractiveElement]:
    if mark_id is None:
        return None
    for el in elements:
        if el.mark_id == mark_id:
            return el
    return None


async def execute_action(
    page: Page,
    action: str,
    mark_id: Optional[int],
    value: Optional[str],
    elements: list[InteractiveElement],
) -> ActionResult:
    try:
        if action == "click":
            el = _find_element(elements, mark_id)
            if not el:
                return ActionResult(False, "click", error=f"Elemento mark_id={mark_id} não encontrado")
            locator = page.locator(f'[data-qa-agent-id="{el.qa_id}"]')
            await locator.scroll_into_view_if_needed(timeout=5000)
            try:
                await locator.click(timeout=6000)
            except Exception:
                # A common cause here is a styled widget overlapping its own
                # trigger element (e.g. custom dropdowns) — force bypasses
                # Playwright's actionability checks and clicks at the
                # element's coordinates directly.
                await locator.click(timeout=4000, force=True)
            return ActionResult(True, f"Clicou em [{mark_id}] {el.label or el.tag}")

        if action == "fill":
            el = _find_element(elements, mark_id)
            if not el:
                return ActionResult(False, "fill", error=f"Elemento mark_id={mark_id} não encontrado")
            locator = page.locator(f'[data-qa-agent-id="{el.qa_id}"]')
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.fill(value or "", timeout=8000)
            return ActionResult(True, f"Preencheu [{mark_id}] {el.label or el.tag} com '{value}'")

        if action == "press_key":
            key = value or "Enter"
            await page.keyboard.press(key)
            return ActionResult(True, f"Pressionou a tecla '{key}'")

        if action == "scroll":
            direction = (value or "down").lower()
            delta = 600 if direction == "down" else -600
            await page.mouse.wheel(0, delta)
            return ActionResult(True, f"Rolou a página para {direction}")

        if action == "go_back":
            await page.go_back(timeout=8000)
            return ActionResult(True, "Voltou para a página anterior")

        if action == "wait":
            seconds = float(value) if value else 1.0
            await page.wait_for_timeout(min(seconds, 10) * 1000)
            return ActionResult(True, f"Aguardou {seconds}s")

        if action in ("report_issue", "finish"):
            return ActionResult(True, action)

        return ActionResult(False, action, error=f"Ação desconhecida: {action}")
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, action, error=str(exc))
