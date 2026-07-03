"""Deterministic, non-AI page audits: SEO, accessibility, performance and
passive security hygiene checks, plus a simple SSO/social-login detector.

These run once per distinct URL the agent visits (see browser_agent.py),
independently of the vision-driven decision loop — they don't cost AI tokens
and are far more reliable for checklist-style facts than asking a model to
"notice" a missing meta tag.

Security checks here are intentionally passive and read-only (HTTP headers,
cookie flags, well-known exposed-file paths on the site being tested). No
active exploitation (XSS/SQLi payloads, auth bypass attempts, etc.) is
performed — this tool points at arbitrary user-supplied URLs, so anything
beyond passive hygiene checks would need explicit, scoped authorization.
"""

from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page

from app.models import Issue, IssueCategory, IssueSeverity

_AXE_JS_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
_axe_js_cache: str | None = None

_SENSITIVE_PATHS = [
    ".env",
    ".git/config",
    ".git/HEAD",
    "wp-config.php.bak",
    "config.php.bak",
    ".DS_Store",
    "backup.zip",
    "phpinfo.php",
]

_SSO_SIGNATURES = {
    "Google": ["accounts.google.com", "entrar com google", "sign in with google", "continuar com google", "continue with google"],
    "Microsoft": ["login.microsoftonline.com", "entrar com microsoft", "sign in with microsoft"],
    "Apple": ["appleid.apple.com", "sign in with apple", "entrar com apple"],
    "Facebook": ["facebook.com/dialog/oauth", "entrar com facebook", "login with facebook", "continuar com facebook"],
    "GitHub": ["github.com/login/oauth", "sign in with github"],
}

_AXE_IMPACT_TO_SEVERITY = {
    "critical": IssueSeverity.CRITICAL,
    "serious": IssueSeverity.MAJOR,
    "moderate": IssueSeverity.MINOR,
    "minor": IssueSeverity.SUGGESTION,
}


def _issue(severity: IssueSeverity, category: IssueCategory, title: str, description: str, recommendation: str | None, source: str) -> Issue:
    return Issue(
        severity=severity,
        category=category,
        title=title,
        description=description,
        recommendation=recommendation,
        source=source,
    )


async def seo_audit(page: Page) -> list[Issue]:
    issues: list[Issue] = []
    try:
        data = await page.evaluate(
            """() => ({
                title: document.title || '',
                metaDescription: document.querySelector('meta[name="description"]')?.content || '',
                viewport: document.querySelector('meta[name="viewport"]')?.content || '',
                h1Count: document.querySelectorAll('h1').length,
            })"""
        )
    except Exception:
        return issues

    if not data["title"] or len(data["title"]) < 10:
        issues.append(_issue(
            IssueSeverity.MINOR, IssueCategory.SEO, "Título da página ausente ou muito curto",
            f"Título atual: '{data['title']}'. Títulos ideais têm entre 10 e 60 caracteres.",
            "Defina um <title> descritivo e único para cada página (10-60 caracteres).", "seo",
        ))
    if not data["metaDescription"]:
        issues.append(_issue(
            IssueSeverity.MINOR, IssueCategory.SEO, "Meta description ausente",
            "Nenhuma tag <meta name=\"description\"> foi encontrada nesta página.",
            "Adicione uma meta description de 120-160 caracteres resumindo o conteúdo da página.", "seo",
        ))
    if not data["viewport"]:
        issues.append(_issue(
            IssueSeverity.MINOR, IssueCategory.SEO, "Meta viewport ausente",
            "Sem <meta name=\"viewport\">, a página pode não se adaptar corretamente a telas de celular.",
            "Adicione <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.", "seo",
        ))
    if data["h1Count"] == 0:
        issues.append(_issue(
            IssueSeverity.MINOR, IssueCategory.SEO, "Nenhum <h1> encontrado na página",
            "A página não tem um heading principal (h1), importante para SEO e estrutura de conteúdo.",
            "Adicione um único <h1> descrevendo o conteúdo principal da página.", "seo",
        ))
    elif data["h1Count"] > 1:
        issues.append(_issue(
            IssueSeverity.SUGGESTION, IssueCategory.SEO, f"Múltiplos elementos <h1> encontrados ({data['h1Count']})",
            "Ter mais de um h1 pode confundir buscadores sobre o tópico principal da página.",
            "Use apenas um <h1> por página; use h2/h3 para os subtítulos.", "seo",
        ))
    return issues


async def seo_network_audit(page: Page) -> list[Issue]:
    issues: list[Issue] = []
    parsed = urlparse(page.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for path, label in (("robots.txt", "robots.txt"), ("sitemap.xml", "sitemap.xml")):
        try:
            response = await page.context.request.get(f"{origin}/{path}", timeout=5000)
            if response.status >= 400:
                issues.append(_issue(
                    IssueSeverity.SUGGESTION, IssueCategory.SEO, f"{label} não encontrado",
                    f"Uma requisição a /{path} retornou HTTP {response.status}.",
                    f"Considere adicionar um {label} para orientar os buscadores.", "seo",
                ))
        except Exception:
            continue

    return issues


async def security_audit(page: Page) -> list[Issue]:
    issues: list[Issue] = []
    parsed = urlparse(page.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    is_https = parsed.scheme == "https"
    if not is_https:
        issues.append(_issue(
            IssueSeverity.MAJOR, IssueCategory.SECURITY, "Site não está usando HTTPS",
            f"A página atual é servida via {parsed.scheme}, o que expõe os dados trafegados a interceptação.",
            "Configure um certificado TLS válido e force o redirecionamento de HTTP para HTTPS.", "security",
        ))
        # Header/cookie/exposed-path checks below are still meaningful over
        # plain HTTP (e.g. a leaked .env file is just as bad either way), so
        # we don't bail out here — only the HSTS check is skipped further
        # down since it's meaningless without HTTPS.

    try:
        response = await page.context.request.get(page.url, timeout=10000)
        headers = {k.lower(): v for k, v in response.headers.items()}
    except Exception:
        headers = None

    if headers is not None:
        header_checks = [
            ("content-security-policy", "Content-Security-Policy ausente",
             "Ajuda a mitigar ataques XSS restringindo de onde scripts e recursos podem ser carregados.", IssueSeverity.MINOR),
            ("strict-transport-security", "Strict-Transport-Security (HSTS) ausente",
             "Sem HSTS, o navegador pode ser induzido a acessar o site via HTTP em vez de HTTPS.", IssueSeverity.MINOR),
            ("x-content-type-options", "X-Content-Type-Options ausente",
             "Sem 'nosniff', navegadores podem interpretar erroneamente o tipo de um arquivo, facilitando certos ataques.", IssueSeverity.MINOR),
            ("x-frame-options", "X-Frame-Options ausente",
             "Sem essa proteção (ou 'frame-ancestors' na CSP), o site pode ficar vulnerável a clickjacking.", IssueSeverity.MINOR),
            ("referrer-policy", "Referrer-Policy ausente",
             "Sem essa política, a URL completa da página pode vazar para sites de terceiros via cabeçalho Referer.", IssueSeverity.SUGGESTION),
        ]
        for header, title, description, severity in header_checks:
            if header == "strict-transport-security" and not is_https:
                continue
            if header == "x-frame-options" and "frame-ancestors" in headers.get("content-security-policy", ""):
                continue
            if header not in headers:
                issues.append(_issue(
                    severity, IssueCategory.SECURITY, title, description,
                    f"Adicione o cabeçalho HTTP '{header}' nas respostas do servidor.", "security",
                ))

    try:
        cookies = await page.context.cookies()
    except Exception:
        cookies = []
    for cookie in cookies:
        problems = []
        if not cookie.get("secure"):
            problems.append("sem flag Secure")
        if not cookie.get("httpOnly"):
            problems.append("sem flag HttpOnly")
        if cookie.get("sameSite") in (None, "None"):
            problems.append("SameSite ausente ou 'None'")
        if problems:
            issues.append(_issue(
                IssueSeverity.MINOR, IssueCategory.SECURITY,
                f"Cookie '{cookie.get('name')}' com configuração fraca",
                f"Problemas encontrados: {', '.join(problems)}.",
                "Marque cookies de sessão como Secure e HttpOnly, e defina SameSite=Lax/Strict quando possível.", "security",
            ))

    for path in _SENSITIVE_PATHS:
        try:
            response = await page.context.request.get(f"{origin}/{path}", timeout=5000)
            if response.status == 200:
                issues.append(_issue(
                    IssueSeverity.CRITICAL, IssueCategory.SECURITY,
                    f"Possível arquivo sensível exposto: /{path}",
                    f"Uma requisição de leitura a /{path} retornou HTTP 200, o que pode expor credenciais ou configuração interna.",
                    "Bloqueie o acesso a esse caminho no servidor/CDN e remova o arquivo do diretório público.", "security",
                ))
        except Exception:
            continue

    return issues


async def performance_audit(page: Page) -> tuple[list[Issue], dict]:
    try:
        metrics = await page.evaluate(
            """() => {
                const nav = performance.getEntriesByType('navigation')[0];
                const paints = performance.getEntriesByType('paint');
                const fcp = paints.find(p => p.name === 'first-contentful-paint');
                const resources = performance.getEntriesByType('resource');
                return {
                    loadTime: nav ? nav.loadEventEnd - nav.startTime : null,
                    domContentLoaded: nav ? nav.domContentLoadedEventEnd - nav.startTime : null,
                    ttfb: nav ? nav.responseStart - nav.startTime : null,
                    fcp: fcp ? fcp.startTime : null,
                    resourceCount: resources.length,
                    transferSize: resources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
                };
            }"""
        )
    except Exception:
        return [], {}

    issues: list[Issue] = []
    load_time = metrics.get("loadTime")
    if load_time:
        load_s = load_time / 1000
        if load_s > 6:
            issues.append(_issue(
                IssueSeverity.MAJOR, IssueCategory.PERFORMANCE, f"Carregamento muito lento ({load_s:.1f}s)",
                f"O evento de carregamento completo da página {page.url} levou {load_s:.1f} segundos.",
                "Otimize imagens, ative compressão/cache no servidor e reduza scripts que bloqueiam o carregamento.", "performance",
            ))
        elif load_s > 3:
            issues.append(_issue(
                IssueSeverity.MINOR, IssueCategory.PERFORMANCE, f"Carregamento lento ({load_s:.1f}s)",
                f"O carregamento completo da página levou {load_s:.1f}s (ideal: abaixo de 3s).",
                "Considere otimizar recursos pesados e revisar scripts de terceiros.", "performance",
            ))

    resource_count = metrics.get("resourceCount", 0)
    if resource_count > 120:
        issues.append(_issue(
            IssueSeverity.SUGGESTION, IssueCategory.PERFORMANCE, f"Número alto de requisições na página ({resource_count})",
            "Muitas requisições podem atrasar o carregamento, especialmente em conexões lentas.",
            "Combine/otimize arquivos CSS e JS e utilize lazy-loading para imagens fora da tela inicial.", "performance",
        ))

    transfer_mb = metrics.get("transferSize", 0) / (1024 * 1024)
    if transfer_mb > 5:
        issues.append(_issue(
            IssueSeverity.MINOR, IssueCategory.PERFORMANCE, f"Página pesada ({transfer_mb:.1f} MB transferidos)",
            "O total de dados baixados para carregar a página está acima do recomendado (referência: ~2-3MB).",
            "Comprima imagens, ative gzip/brotli no servidor, e remova dependências não utilizadas.", "performance",
        ))

    return issues, metrics


def _load_axe_js() -> str:
    global _axe_js_cache
    if _axe_js_cache is None:
        _axe_js_cache = _AXE_JS_PATH.read_text(encoding="utf-8")
    return _axe_js_cache


async def accessibility_audit(page: Page) -> list[Issue]:
    issues: list[Issue] = []
    try:
        await page.evaluate(_load_axe_js())
        violations = await page.evaluate(
            """async () => {
                const results = await axe.run(document, { resultTypes: ['violations'] });
                return results.violations.map(v => ({
                    id: v.id,
                    impact: v.impact,
                    help: v.help,
                    description: v.description,
                    nodeCount: v.nodes.length,
                    target: (v.nodes[0] && v.nodes[0].target && v.nodes[0].target[0]) || '',
                }));
            }"""
        )
    except Exception:
        return issues

    order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
    violations.sort(key=lambda v: order.get(v.get("impact"), 4))

    for v in violations[:15]:
        severity = _AXE_IMPACT_TO_SEVERITY.get(v.get("impact"), IssueSeverity.MINOR)
        issues.append(_issue(
            severity, IssueCategory.ACCESSIBILITY, v.get("help") or "Problema de acessibilidade",
            f"{v.get('description', '')} (afeta {v.get('nodeCount', 0)} elemento(s); ex.: {v.get('target', '')})",
            f"Regra axe-core: '{v.get('id')}'. Consulte https://dequeuniversity.com/rules/axe/4.12/{v.get('id')} para detalhes de correção.",
            "accessibility",
        ))

    return issues


async def detect_sso_providers(page: Page) -> list[Issue]:
    try:
        content = (await page.content()).lower()
    except Exception:
        return []

    found = [provider for provider, signatures in _SSO_SIGNATURES.items() if any(sig in content for sig in signatures)]
    if not found:
        return []

    providers_text = ", ".join(found)
    return [_issue(
        IssueSeverity.SUGGESTION, IssueCategory.FUNCTIONAL, f"Login social/SSO detectado: {providers_text}",
        f"A página oferece login via {providers_text}. Provedores OAuth de terceiros costumam exigir uma conta "
        "real e uma tela de consentimento fora do site, então o agente pode não conseguir concluir esse fluxo "
        "sozinho com segurança.",
        "Teste manualmente o fluxo de SSO e garanta que erros de autenticação (conta cancelada, popup bloqueado, "
        "permissão negada) tenham uma mensagem clara para o usuário.", "sso",
    )]


async def run_page_audits(page: Page) -> tuple[list[Issue], dict]:
    """Runs every audit against the currently loaded page. Returns the
    combined issue list plus the raw performance metrics dict (so the caller
    can store them per-URL without re-computing)."""
    issues: list[Issue] = []
    issues += await seo_audit(page)
    issues += await seo_network_audit(page)
    issues += await security_audit(page)
    issues += await detect_sso_providers(page)
    perf_issues, metrics = await performance_audit(page)
    issues += perf_issues
    issues += await accessibility_audit(page)
    return issues, metrics
