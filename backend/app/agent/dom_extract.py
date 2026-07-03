from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page

INTERACTIVE_SELECTOR = (
    "a, button, input, select, textarea, [role=button], [role=link], "
    "[role=checkbox], [role=radio], [role=tab], [role=option], [onclick], summary, "
    "li[role=option], .select2-results__option, .chosen-results li"
)

# Widget libraries like select2/Chosen hide the native <select> (aria-hidden or
# a zero-size accessibility-only box) and render a custom clickable widget as a
# sibling. Clicking the hidden select directly fails ("intercepts pointer
# events") because the fake widget sits visually on top of it — so when we
# detect this pattern we swap the click target to that visible sibling.
_EXTRACTOR_JS = """
(selector) => {
  function isVisuallyHidden(rect, style) {
    if (rect.width <= 2 && rect.height <= 2) return true;
    if (style.clipPath === 'inset(50%)') return true;
    if (style.clip && style.clip.replace(/\\s/g, '') === 'rect(0px,0px,0px,0px)') return true;
    return false;
  }

  const els = Array.from(document.querySelectorAll(selector));
  const results = [];
  const seen = new Set();

  for (const el of els) {
    let target = el;
    let rect = target.getBoundingClientRect();
    let style = window.getComputedStyle(target);

    const isHiddenSelect = el.tagName.toLowerCase() === 'select' &&
      (el.getAttribute('aria-hidden') === 'true' || isVisuallyHidden(rect, style));

    if (isHiddenSelect) {
      const companion = el.nextElementSibling;
      if (!companion) continue;
      const cRect = companion.getBoundingClientRect();
      const cStyle = window.getComputedStyle(companion);
      if (cRect.width <= 2 || cRect.height <= 2 || cStyle.visibility === 'hidden' || cStyle.display === 'none') {
        continue;
      }
      target = companion;
      rect = cRect;
      style = cStyle;
    }

    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
    if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;

    const key = Math.round(rect.left) + ',' + Math.round(rect.top) + ',' + Math.round(rect.width);
    if (seen.has(key)) continue;
    seen.add(key);

    let label = (target.innerText || target.value || target.placeholder || target.getAttribute('aria-label') || target.getAttribute('title') || '').trim();
    label = label.replace(/\\s+/g, ' ').slice(0, 60);

    if (!target.dataset.qaAgentId) {
      target.dataset.qaAgentId = 'qa-' + results.length + '-' + Math.random().toString(36).slice(2, 7);
    }

    results.push({
      qa_id: target.dataset.qaAgentId,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      label: label,
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    });
  }
  return results;
}
"""


@dataclass
class InteractiveElement:
    qa_id: str
    tag: str
    type: str
    label: str
    x: float
    y: float
    width: float
    height: float
    mark_id: int = 0


async def extract_interactive_elements(page: Page) -> list[InteractiveElement]:
    raw = await page.evaluate(_EXTRACTOR_JS, INTERACTIVE_SELECTOR)
    elements = [InteractiveElement(**item) for item in raw[:60]]
    for i, el in enumerate(elements):
        el.mark_id = i
    return elements


def draw_marks_on_screenshot(screenshot_bytes: bytes, elements: list[InteractiveElement]) -> bytes:
    """Overlays numbered boxes on top of interactive elements (set-of-marks
    prompting) so the vision model can reliably point at what to click."""
    image = Image.open(BytesIO(screenshot_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    for el in elements:
        box = (el.x, el.y, el.x + el.width, el.y + el.height)
        draw.rectangle(box, outline=(255, 0, 60), width=2)
        tag_text = str(el.mark_id)
        text_w = draw.textlength(tag_text, font=font)
        label_box = (el.x, max(0, el.y - 15), el.x + text_w + 6, max(0, el.y - 15) + 15)
        draw.rectangle(label_box, fill=(255, 0, 60))
        draw.text((label_box[0] + 3, label_box[1] + 1), tag_text, fill=(255, 255, 255), font=font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def resize_for_model(image_bytes: bytes, max_width: int = 900) -> bytes:
    """Downscales and re-encodes the screenshot as JPEG before sending it to
    the vision model, since image tokens scale with resolution/size and some
    Groq tiers cap tokens/minute well below what a full 1366px-wide PNG
    screenshot costs. The full-resolution PNG is still saved to disk for the
    report/UI — only the API payload shrinks."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, round(image.height * ratio)), Image.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=78)
    return buffer.getvalue()


def elements_to_text(elements: list[InteractiveElement]) -> str:
    lines = []
    for el in elements:
        descriptor = el.label or f"({el.tag} sem texto)"
        extra = f" type={el.type}" if el.type else ""
        lines.append(f"[{el.mark_id}] <{el.tag}{extra}> {descriptor}")
    return "\n".join(lines) if lines else "(nenhum elemento interativo visível)"
