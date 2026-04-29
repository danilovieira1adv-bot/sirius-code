"""
browser.py — Browser control via Playwright (Chromium headless) com modo stealth
"""
import os
import re
import json
import asyncio
import time
import random

TIMEOUT = 30_000  # 30 segundos
SCREENSHOT_PATH = "/app/data/files/screenshot.png"
SESSION_DIR = "/app/data/browser_sessions"

# User agents reais e modernos para parecer humano
_REAL_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

def _get_random_user_agent():
    """Retorna um user-agent aleatório da lista de agentes reais"""
    return random.choice(_REAL_USER_AGENTS)

# ---------------------------------------------------------------------------
# Fluxos de login por plataforma
# ---------------------------------------------------------------------------

PLATFORM_FLOWS = {
    'mercadolivre': {
        'name': 'Mercado Livre',
        'login_url': 'https://www.mercadolivre.com.br/login',
        'check_url': 'https://www.mercadolivre.com.br/',
        'logged_selector': '.nav-user-menu, [data-testid="header-user-info"], a[href*="/perfil"]',
        'steps': [
            {'type': 'fill',   'selectors': ['#user_email', 'input[name="user_email"]', 'input[type="email"]'], 'field': 'username'},
            {'type': 'submit', 'selectors': ['#login_action', 'button[type="submit"]']},
            {'type': 'wait',   'ms': 2000},
            {'type': 'fill',   'selectors': ['#user_password', 'input[name="user_password"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['button[type="submit"]', '#login_action']},
            {'type': 'wait',   'ms': 3000},
        ],
    },
    'google': {
        'name': 'Google',
        'login_url': 'https://accounts.google.com/signin',
        'check_url': 'https://myaccount.google.com/',
        'logged_selector': '[data-email], .gb_d, img.gbii',
        'steps': [
            {'type': 'fill',   'selectors': ['input[type="email"]', '#identifierId'], 'field': 'username'},
            {'type': 'submit', 'selectors': ['#identifierNext button', 'button[jsname="LgbsSe"]']},
            {'type': 'wait',   'ms': 2500},
            {'type': 'fill',   'selectors': ['input[type="password"]', 'input[name="Passwd"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['#passwordNext button', 'button[jsname="LgbsSe"]']},
            {'type': 'wait',   'ms': 3500},
        ],
    },
    'instagram': {
        'name': 'Instagram',
        'login_url': 'https://www.instagram.com/accounts/login/',
        'check_url': 'https://www.instagram.com/',
        'logged_selector': 'svg[aria-label="Home"], a[href="/direct/inbox/"]',
        'steps': [
            {'type': 'wait',   'ms': 2500},
            {'type': 'fill',   'selectors': ['input[name="username"]'], 'field': 'username'},
            {'type': 'fill',   'selectors': ['input[name="password"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['button[type="submit"]']},
            {'type': 'wait',   'ms': 4000},
        ],
    },
    'facebook': {
        'name': 'Facebook',
        'login_url': 'https://www.facebook.com/',
        'check_url': 'https://www.facebook.com/',
        'logged_selector': '[aria-label="Facebook"], a[href*="/profile.php"], [data-pagelet="LeftRail"]',
        'steps': [
            {'type': 'fill',   'selectors': ['#email', 'input[name="email"]'], 'field': 'username'},
            {'type': 'fill',   'selectors': ['#pass', 'input[name="pass"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['button[name="login"]', 'button[type="submit"]', 'input[name="login"]']},
            {'type': 'wait',   'ms': 4000},
        ],
    },
    'twitter': {
        'name': 'X / Twitter',
        'login_url': 'https://x.com/i/flow/login',
        'check_url': 'https://x.com/home',
        'logged_selector': 'a[data-testid="SideNav_NewTweet_Button"], a[aria-label="Profile"]',
        'steps': [
            {'type': 'wait',   'ms': 2500},
            {'type': 'fill',   'selectors': ['input[autocomplete="username"]', 'input[name="text"]'], 'field': 'username'},
            {'type': 'submit', 'selectors': ['[data-testid="LoginForm_Login_Button"]', 'div[role="button"][tabindex="0"]']},
            {'type': 'wait',   'ms': 2500},
            {'type': 'fill',   'selectors': ['input[type="password"]', 'input[name="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['[data-testid="LoginForm_Login_Button"]']},
            {'type': 'wait',   'ms': 4000},
        ],
    },
    'linkedin': {
        'name': 'LinkedIn',
        'login_url': 'https://www.linkedin.com/login',
        'check_url': 'https://www.linkedin.com/feed/',
        'logged_selector': '.feed-identity-module, a[href*="/in/"], [data-control-name="nav.homepage"]',
        'steps': [
            {'type': 'fill',   'selectors': ['#username', 'input[name="session_key"]'], 'field': 'username'},
            {'type': 'fill',   'selectors': ['#password', 'input[name="session_password"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['button[type="submit"]', '.btn__primary--large']},
            {'type': 'wait',   'ms': 4000},
        ],
    },
    'booking': {
        'name': 'Booking.com',
        'login_url': 'https://account.booking.com/sign-in',
        'check_url': 'https://www.booking.com/',
        'logged_selector': '[data-testid="header-user-profile"], .bui-avatar',
        'steps': [
            {'type': 'fill',   'selectors': ['#username', 'input[name="username"]', 'input[type="email"]'], 'field': 'username'},
            {'type': 'submit', 'selectors': ['button[type="submit"]', '#login-button']},
            {'type': 'wait',   'ms': 2000},
            {'type': 'fill',   'selectors': ['#password', 'input[name="password"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['button[type="submit"]']},
            {'type': 'wait',   'ms': 3500},
        ],
    },
    'amazon': {
        'name': 'Amazon',
        'login_url': 'https://www.amazon.com.br/ap/signin?openid.pape.max_auth_age=0&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=brflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.return_to=https%3A%2F%2Fwww.amazon.com.br',
        'check_url': 'https://www.amazon.com.br/',
        'logged_selector': '#nav-link-accountList[data-nav-role="signin"] .nav-line-2:not(:empty)',
        'steps': [
            {'type': 'fill',   'selectors': ['#ap_email', 'input[name="email"]', 'input[type="email"]'], 'field': 'username'},
            {'type': 'submit', 'selectors': ['#continue', 'input[id="continue"]']},
            {'type': 'wait',   'ms': 2000},
            {'type': 'fill',   'selectors': ['#ap_password', 'input[name="password"]', 'input[type="password"]'], 'field': 'password'},
            {'type': 'submit', 'selectors': ['#signInSubmit', 'input[type="submit"]']},
            {'type': 'wait',   'ms': 3500},
        ],
    },
}


def _clean_text(raw: str) -> str:
    """Remove whitespace excessivo e retorna texto limpo."""
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r'[ \t]{2,}', ' ', raw)
    return raw.strip()


async def _human_like_delay(min_ms=500, max_ms=3000):
    """Delay aleatório para simular comportamento humano"""
    delay = random.randint(min_ms, max_ms)
    await asyncio.sleep(delay / 1000)


async def _human_like_scroll(page):
    """Rola a página de forma humana com variações de velocidade"""
    scroll_height = await page.evaluate("document.body.scrollHeight")
    viewport_height = await page.evaluate("window.innerHeight")

    # Rola em segmentos com delays aleatórios
    current_pos = 0
    while current_pos < scroll_height:
        # Tamanho do scroll aleatório (entre 100-500px)
        scroll_amount = random.randint(100, 500)
        current_pos = min(current_pos + scroll_amount, scroll_height)

        # Scroll suave
        await page.evaluate(f"window.scrollTo({{top: {current_pos}, behavior: 'smooth'}})")

        # Delay aleatório entre scrolls
        await _human_like_delay(200, 1500)

        # Pequena chance de rolar para cima (como humano faria)
        if random.random() < 0.1:
            back_scroll = random.randint(50, 200)
            current_pos = max(0, current_pos - back_scroll)
            await page.evaluate(f"window.scrollTo({{top: {current_pos}, behavior: 'smooth'}})")
            await _human_like_delay(300, 1000)


async def _new_page(playwright, use_stealth=True):
    """Cria um novo contexto de navegador com opção de modo stealth"""
    from playwright_stealth import stealth

    # Configurações do navegador
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-web-security",
        "--disable-site-isolation-trials",
    ]

    # Adiciona argumentos adicionais para stealth
    if use_stealth:
        launch_args.extend([
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-blink-features=AutomationControlled",
        ])

    browser = await playwright.chromium.launch(
        headless=True,
        args=launch_args,
    )

    # Cria contexto com user-agent aleatório
    user_agent = _get_random_user_agent()
    ctx = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1280 + random.randint(-100, 100), "height": 800 + random.randint(-100, 100)},
        ignore_https_errors=True,
        # Configurações para parecer mais humano
        has_touch=random.choice([True, False]),
        is_mobile=random.choice([True, False]),
        device_scale_factor=random.choice([1, 2]),
        # Desabilita recursos de automação
        bypass_csp=True,
        java_script_enabled=True,
    )

    page = await ctx.new_page()

    # Aplica técnicas de stealth se habilitado
    if use_stealth:
        stealth_obj = stealth.Stealth(
            navigator_languages_override=('pt-BR', 'pt', 'en-US', 'en'),
            navigator_platform_override='Win32',
        )
        await stealth_obj.apply_stealth_async(page)

        # Injetar scripts adicionais para bypass de detecção
        await page.add_init_script("""
            // Remove propriedades de automação
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Sobrescreve languages para parecer humano
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en']
            });

            // Sobrescreve platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });

            // Chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)

    return browser, page


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_path(platform: str) -> str:
    os.makedirs(SESSION_DIR, exist_ok=True)
    return os.path.join(SESSION_DIR, f"{platform}.json")


def _session_meta_path(platform: str) -> str:
    return os.path.join(SESSION_DIR, f"{platform}.meta.json")


def _load_meta(platform: str) -> dict:
    p = _session_meta_path(platform)
    try:
        return json.load(open(p))
    except Exception:
        return {}


def _save_meta(platform: str, data: dict):
    with open(_session_meta_path(platform), 'w') as f:
        json.dump(data, f)


async def _try_fill(page, selectors: list, value: str, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout, state='visible')
            await page.fill(sel, value)
            return True
        except Exception:
            pass
    return False


async def _try_click(page, selectors: list, timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout, state='visible')
            await page.click(sel)
            return True
        except Exception:
            pass
    return False


async def login(platform: str, username: str, password: str) -> str:
    """Faz login na plataforma e salva cookies em SESSION_DIR/{platform}.json.

    Retorna mensagem de sucesso ou erro.
    """
    flow = PLATFORM_FLOWS.get(platform.lower())
    if not flow:
        supported = ', '.join(PLATFORM_FLOWS.keys())
        return f"Plataforma '{platform}' não suportada. Use: {supported}"

    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth
        os.makedirs(SESSION_DIR, exist_ok=True)

        async with async_playwright() as pw:
            # Usa _new_page com stealth para login também
            browser, page = await _new_page(pw, use_stealth=True)

            try:
                # Delay humano antes de começar
                await _human_like_delay(1000, 3000)

                await page.goto(flow['login_url'], timeout=TIMEOUT, wait_until="domcontentloaded")

                # Delay após carregar página de login
                await _human_like_delay(1500, 2500)

                for step in flow['steps']:
                    stype = step['type']
                    if stype == 'wait':
                        await page.wait_for_timeout(step['ms'])
                    elif stype == 'fill':
                        val = username if step['field'] == 'username' else password
                        # Delay antes de preencher cada campo
                        await _human_like_delay(300, 1200)
                        ok = await _try_fill(page, step['selectors'], val)
                        if not ok:
                            return f"Não encontrei campo '{step['field']}' em {flow['name']}. Página pode ter mudado."
                    elif stype == 'submit':
                        # Delay antes de clicar
                        await _human_like_delay(500, 1800)
                        await _try_click(page, step['selectors'])

                # Salva estado da sessão (cookies + localStorage)
                # Obtém o contexto da página
                ctx = page.context
                await ctx.storage_state(path=_session_path(platform))
                _save_meta(platform, {
                    'platform': platform,
                    'username': username,
                    'logged_at': time.time(),
                    'login_url': flow['login_url'],
                })

                # Verifica se realmente logou
                current_url = page.url
                is_logged = await page.query_selector(flow['logged_selector']) is not None
                if not is_logged and 'login' in current_url.lower():
                    return f"Login em {flow['name']} falhou — verifique usuário/senha. URL atual: {current_url}"

                return f"Login em {flow['name']} realizado com sucesso. Sessão salva para {username}."
            finally:
                await browser.close()

    except Exception as e:
        return f"Erro no login em {platform}: {e}"


async def browse_authenticated(url: str, platform: str) -> str:
    """Abre URL usando cookies salvos da plataforma. Retorna texto limpo."""
    session_file = _session_path(platform)
    if not os.path.exists(session_file):
        return f"Nenhuma sessão salva para '{platform}'. Use platform_login primeiro."

    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth

        async with async_playwright() as pw:
            # Configurações similares ao _new_page mas com storage_state
            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-site-isolation-trials",
            ]

            browser = await pw.chromium.launch(
                headless=True,
                args=launch_args,
            )

            user_agent = _get_random_user_agent()
            ctx = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280 + random.randint(-100, 100), "height": 800 + random.randint(-100, 100)},
                ignore_https_errors=True,
                storage_state=session_file,
                has_touch=random.choice([True, False]),
                is_mobile=random.choice([True, False]),
                device_scale_factor=random.choice([1, 2]),
                bypass_csp=True,
                java_script_enabled=True,
            )

            page = await ctx.new_page()
            stealth_obj = stealth.Stealth(
                navigator_languages_override=('pt-BR', 'pt', 'en-US', 'en'),
                navigator_platform_override='Win32',
            )
            await stealth_obj.apply_stealth_async(page)

            # Injetar scripts de stealth
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-BR', 'pt', 'en-US', 'en']
                });
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            """)

            try:
                # Comportamento humano
                await _human_like_delay(1000, 3000)
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(1500, 4000)
                await _human_like_scroll(page)
                await _human_like_delay(1000, 2500)

                text = await page.evaluate(_EXTRACT_JS)
                result = _clean_text(text)

                if len(result) < 100:
                    await _human_like_delay(3000, 6000)
                    await _human_like_scroll(page)
                    text = await page.evaluate(_EXTRACT_JS)
                    result = _clean_text(text)

                return result[:8000] if result else "Página sem conteúdo textual."
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao acessar {url} autenticado em {platform}: {e}"


async def check_session(platform: str) -> str:
    """Verifica se a sessão da plataforma ainda está válida."""
    flow = PLATFORM_FLOWS.get(platform.lower())
    if not flow:
        return f"Plataforma '{platform}' não reconhecida."

    session_file = _session_path(platform)
    if not os.path.exists(session_file):
        return f"Nenhuma sessão salva para '{platform}'."

    meta = _load_meta(platform)
    age_h = (time.time() - meta.get('logged_at', 0)) / 3600

    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth

        async with async_playwright() as pw:
            # Configurações similares
            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-site-isolation-trials",
            ]

            browser = await pw.chromium.launch(
                headless=True,
                args=launch_args,
            )

            user_agent = _get_random_user_agent()
            ctx = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280 + random.randint(-100, 100), "height": 800 + random.randint(-100, 100)},
                ignore_https_errors=True,
                storage_state=session_file,
                has_touch=random.choice([True, False]),
                is_mobile=random.choice([True, False]),
                device_scale_factor=random.choice([1, 2]),
                bypass_csp=True,
                java_script_enabled=True,
            )

            page = await ctx.new_page()
            stealth_obj = stealth.Stealth(
                navigator_languages_override=('pt-BR', 'pt', 'en-US', 'en'),
                navigator_platform_override='Win32',
            )
            await stealth_obj.apply_stealth_async(page)

            # Scripts de stealth
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-BR', 'pt', 'en-US', 'en']
                });
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            """)

            try:
                await _human_like_delay(1000, 3000)
                await page.goto(flow['check_url'], timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(2000, 4000)
                found = await page.query_selector(flow['logged_selector']) is not None
                current_url = page.url
                if found:
                    return (f"Sessão '{platform}' ATIVA — usuário: {meta.get('username','?')}, "
                            f"login há {age_h:.1f}h.")
                else:
                    return (f"Sessão '{platform}' EXPIRADA ou inválida. "
                            f"URL: {current_url}. Faça login novamente.")
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao verificar sessão de {platform}: {e}"


# ---------------------------------------------------------------------------
# browse
# ---------------------------------------------------------------------------

_EXTRACT_JS = """() => {
    ['script','style','noscript','nav','footer','header','aside',
     '[aria-hidden="true"]'].forEach(
        sel => document.querySelectorAll(sel).forEach(el => el.remove())
    );
    return document.body ? document.body.innerText : '';
}"""


async def browse(url: str, use_stealth=True) -> str:
    """Abre URL e retorna o texto limpo da página (sem HTML) com comportamento humano.

    Estratégia de três estágios:
    1. Navegação com delays humanos
    2. Scroll humano para carregar conteúdo lazy
    3. Extração com limpeza inteligente
    """
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, use_stealth=use_stealth)
            try:
                # Delay inicial aleatório antes de navegar
                await _human_like_delay(1000, 3000)

                # Navega com wait_until networkidle para carregar tudo
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")

                # Delay após carregamento (como humano esperaria)
                await _human_like_delay(1500, 4000)

                # Scroll humano para carregar conteúdo lazy
                await _human_like_scroll(page)

                # Delay final antes de extrair
                await _human_like_delay(1000, 2500)

                # Extrai conteúdo
                text = await page.evaluate(_EXTRACT_JS)
                result = _clean_text(text)

                # Se conteúdo muito curto, tenta estratégia alternativa
                if len(result) < 100:
                    # Tenta com mais tempo de espera
                    await _human_like_delay(3000, 6000)
                    await _human_like_scroll(page)
                    text = await page.evaluate(_EXTRACT_JS)
                    result = _clean_text(text)

                return result[:8000] if result else "Página sem conteúdo textual."
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao acessar {url}: {e}"


# ---------------------------------------------------------------------------
# click
# ---------------------------------------------------------------------------

async def click(url: str, selector: str) -> str:
    """Navega até URL, clica no seletor CSS e retorna o texto resultante."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, use_stealth=True)
            try:
                await _human_like_delay(1000, 3000)
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(1500, 3500)

                # Delay antes de clicar
                await _human_like_delay(500, 2000)
                await page.click(selector, timeout=TIMEOUT)

                # Delay após clicar
                await _human_like_delay(1000, 2500)
                await _human_like_scroll(page)

                text = await page.evaluate(_EXTRACT_JS)
                return _clean_text(text)[:4000]
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao clicar em '{selector}' em {url}: {e}"


# ---------------------------------------------------------------------------
# fill_form
# ---------------------------------------------------------------------------

async def fill_form(url: str, fields_dict: dict) -> str:
    """Preenche campos de formulário e submete com comportamento humano.

    fields_dict: {seletor_css: valor, ...}
    """
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, use_stealth=True)
            try:
                await _human_like_delay(1000, 3000)
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(1500, 3500)

                items = list(fields_dict.items())
                for i, (selector, value) in enumerate(items):
                    # Delay antes de preencher cada campo
                    await _human_like_delay(300, 1200)
                    await page.fill(selector, str(value), timeout=TIMEOUT)

                    if i == len(items) - 1:
                        # Delay antes de submeter
                        await _human_like_delay(500, 1800)
                        await page.press(selector, "Enter")

                # Delay após submeter
                await _human_like_delay(2000, 4000)
                await _human_like_scroll(page)

                text = await page.evaluate(_EXTRACT_JS)
                return _clean_text(text)[:4000]
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao preencher formulário em {url}: {e}"


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------

async def screenshot(url: str) -> str:
    """Tira screenshot de URL, salva em /app/data/files/screenshot.png."""
    try:
        from playwright.async_api import async_playwright
        os.makedirs("/app/data/files", exist_ok=True)
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, use_stealth=True)
            try:
                await _human_like_delay(1000, 3000)
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(1500, 3500)
                await _human_like_scroll(page)
                await page.wait_for_timeout(1000)
                await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
                size = os.path.getsize(SCREENSHOT_PATH)
                return f"Screenshot salvo em {SCREENSHOT_PATH} ({size} bytes)"
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao tirar screenshot de {url}: {e}"


# ---------------------------------------------------------------------------
# search_and_extract
# ---------------------------------------------------------------------------

async def _serper_urls(query: str) -> list:
    """Obtém URLs via Serper API (SERPER_API_KEY). Retorna lista de {title, url, snippet}."""
    import httpx
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "gl": "br", "hl": "pt", "num": 5},
            )
            data = r.json()
            return [
                {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")}
                for i in data.get("organic", [])[:5]
                if i.get("link")
            ]
    except Exception:
        return []


async def search_and_extract(query: str, site: str = None) -> str:
    """Pesquisa e extrai conteúdo real dos top 3 resultados.

    Estratégia: Serper API (sem bloqueio) → URLs reais → Playwright para extrair conteúdo.
    Fallback para Bing se Serper não estiver configurado.
    Se `site` for fornecido, restringe a busca ao domínio.
    """
    try:
        from playwright.async_api import async_playwright
        import urllib.parse

        search_query = f"site:{site} {query}" if site else query

        # Tenta Serper API primeiro (mais confiável, sem anti-bot)
        results = await _serper_urls(search_query)

        if not results:
            # Fallback: Bing (menos agressivo que Google contra VPS)
            bing_url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(search_query) + "&cc=BR"
            async with async_playwright() as pw:
                browser, page = await _new_page(pw, use_stealth=True)
                try:
                    await _human_like_delay(1000, 3000)
                    await page.goto(bing_url, timeout=TIMEOUT, wait_until="networkidle")
                    await _human_like_delay(1500, 3500)
                    results = await page.evaluate("""() => {
                        const items = [];
                        document.querySelectorAll('li.b_algo').forEach(el => {
                            const a = el.querySelector('h2 a');
                            const snip = el.querySelector('.b_caption p');
                            if (a) items.push({
                                title: a.innerText.trim(),
                                url: a.href,
                                snippet: snip ? snip.innerText.trim() : ''
                            });
                        });
                        return items.slice(0, 5);
                    }""")
                    if not results:
                        text = await page.evaluate(_EXTRACT_JS)
                        await browser.close()
                        return _clean_text(text)[:4000]
                    await browser.close()
                except Exception:
                    await browser.close()
                    raise

        if not results:
            return "Sem resultados encontrados para: " + query

        # Abre os top 3 links com Playwright e extrai conteúdo real com stealth
        async with async_playwright() as pw:
            browser, _ = await _new_page(pw, use_stealth=True)
            output = []
            for item in results[:3]:
                title   = item.get('title', '')
                url     = item.get('url', '')
                snippet = item.get('snippet', '')
                if not url:
                    continue
                try:
                    p2 = await browser.new_page()
                    # Aplica stealth na nova página também
                    from playwright_stealth import stealth
                    await stealth_async(p2)

                    await _human_like_delay(1000, 2500)
                    await p2.goto(url, timeout=20_000, wait_until="networkidle")
                    await _human_like_delay(1500, 3500)
                    await _human_like_scroll(p2)
                    await _human_like_delay(1000, 2500)

                    content = await p2.evaluate(_EXTRACT_JS)
                    await p2.close()
                    content = _clean_text(content)[:2000]
                    if not content:
                        content = snippet
                except Exception:
                    content = snippet
                output.append(f"### {title}\n{url}\n{content}")
            await browser.close()
            return "\n\n---\n\n".join(output) if output else "Sem resultados encontrados."

    except Exception as e:
        return f"Erro na busca '{query}': {e}"


# ---------------------------------------------------------------------------
# run_script
# ---------------------------------------------------------------------------

async def run_script(url: str, js_code: str) -> str:
    """Navega até URL e executa código JavaScript na página."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, use_stealth=True)
            try:
                await _human_like_delay(1000, 3000)
                await page.goto(url, timeout=TIMEOUT, wait_until="networkidle")
                await _human_like_delay(1500, 3500)
                result = await page.evaluate(js_code)
                return str(result)[:4000] if result is not None else "Script executado (sem retorno)"
            finally:
                await browser.close()
    except Exception as e:
        return f"Erro ao executar script em {url}: {e}"
