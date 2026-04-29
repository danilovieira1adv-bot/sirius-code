#!/usr/bin/env python3
"""Sirius Code CLI — Agente de programação autônomo"""
import sys, os, json, asyncio, threading, time, shutil
from pathlib import Path

CONFIG_DIR = Path.home() / ".sirius"
CONFIG_FILE = CONFIG_DIR / "config.json"

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg):
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def get_config(key, default=None):
    return load_config().get(key, default)

# ── Cores e UI ──
ORANGE = '\033[38;5;208m'
CYAN   = '\033[36m'
DIM    = '\033[2m'
BOLD   = '\033[1m'
RED    = '\033[31m'
GREEN  = '\033[32m'
RESET  = '\033[0m'

SPINNER_FRAMES = ('⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏')

class Spinner:
    def __init__(self):
        self._running = False
        self._thread = None
        self._msg = ''
    def _spin(self):
        i = 0
        while self._running:
            sys.stdout.write(f'\r{ORANGE}{SPINNER_FRAMES[i%len(SPINNER_FRAMES)]}{RESET} {self._msg}')
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)
    def start(self, msg='thinking...'):
        self._msg = msg
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=0.3)
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()

spinner = Spinner()

def print_header():
    cols = shutil.get_terminal_size().columns
    print(f"\n{ORANGE}{'─'*cols}{RESET}")
    print(f"  {BOLD}{ORANGE}◈ Sirius Code{RESET} {DIM}v1.0.0{RESET}  {DIM}siriusopen.ai{RESET}")
    print(f"  {DIM}Agente autônomo de programação{RESET}")
    print(f"{ORANGE}{'─'*cols}{RESET}\n")

def print_tool(name, args):
    tool_map = {
        'run_shell': 'Bash', 'write_file': 'Write',
        'read_file': 'Read', 'web_search': 'Search'
    }
    display = tool_map.get(name, name)
    arg_str = str(args)[:100] if args else ''
    print(f"{ORANGE}●{RESET} {BOLD}{display}{RESET}({DIM}{arg_str}{DIM})")

def print_result(result):
    lines = str(result).split('\n')[:6]
    for line in lines:
        print(f"  {DIM}⎿ {line}{RESET}")

async def chat(message, session_id=None):
    import httpx
    api_url = get_config('api_url', 'http://localhost:5002')
    api_key = get_config('api_key', '')

    if not api_key:
        print(f"\n{RED}✗ API key não configurada.{RESET}")
        print(f"  Configure com: {BOLD}sirius config --key SUA_CHAVE{RESET}")
        print(f"  Obtenha sua chave em: {CYAN}siriusopen.ai{RESET}\n")
        sys.exit(1)

    headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}
    payload = {
        'message': message,
        'session_id': session_id or '',
        'context_dir': str(Path.cwd()),
        'channel': 'cli'
    }

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream('POST', f'{api_url}/api/cli/chat',
                                  json=payload, headers=headers) as resp:
            if resp.status_code == 401:
                print(f"\n{RED}✗ API key inválida.{RESET}")
                sys.exit(1)
            if resp.status_code == 402:
                print(f"\n{RED}✗ Créditos insuficientes. Recarregue em siriusopen.ai{RESET}")
                sys.exit(1)
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"\n{RED}✗ Erro {resp.status_code}: {body.decode()}{RESET}")
                sys.exit(1)

            result_text = ''
            new_session = session_id
            async for line in resp.aiter_lines():
                if not line.startswith('data: '): continue
                data = json.loads(line[6:])
                event = data.get('event')
                if event == 'session':
                    new_session = data.get('session_id')
                elif event == 'tool_start':
                    spinner.stop()
                    print_tool(data.get('name'), data.get('args'))
                    spinner.start(data.get('name','')+'...')
                elif event == 'tool_result':
                    spinner.stop()
                    print_result(data.get('result',''))
                elif event == 'done':
                    result_text = data.get('text', '')
                    break
                elif event == 'error':
                    raise Exception(data.get('message','Erro'))
            return result_text, new_session

def cmd_config(args):
    cfg = load_config()
    if '--key' in args:
        idx = args.index('--key')
        cfg['api_key'] = args[idx+1]
        save_config(cfg)
        print(f"{GREEN}✓ API key configurada.{RESET}")
    elif '--url' in args:
        idx = args.index('--url')
        cfg['api_url'] = args[idx+1]
        save_config(cfg)
        print(f"{GREEN}✓ URL configurada: {args[idx+1]}{RESET}")
    elif '--show' in args:
        key = cfg.get('api_key','não configurada')
        url = cfg.get('api_url','http://localhost:5002')
        print(f"  API Key: {key[:20]}..." if len(key)>20 else f"  API Key: {key}")
        print(f"  API URL: {url}")
    else:
        print("Uso: sirius config --key CHAVE | --url URL | --show")

def cmd_repl():
    print_header()
    print(f"  {DIM}Digite sua tarefa. /help para comandos. Ctrl+C para sair.{RESET}\n")
    session_id = None
    while True:
        try:
            user_input = input(f"{ORANGE}❯{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Até logo.{RESET}\n")
            break
        if not user_input: continue
        if user_input in ('/exit','/quit'): break
        if user_input == '/help':
            print(f"\n  {BOLD}Comandos:{RESET}")
            print(f"  /exit     Sair")
            print(f"  /clear    Limpar tela")
            print(f"  /session  Ver sessão atual\n")
            continue
        if user_input == '/clear':
            os.system('clear')
            print_header()
            continue
        if user_input == '/session':
            print(f"  Sessão: {session_id or 'nova'}\n")
            continue

        spinner.start()
        try:
            result, session_id = asyncio.run(chat(user_input, session_id))
            spinner.stop()
            print(f"\n{result}\n")
        except Exception as e:
            spinner.stop()
            print(f"\n{RED}✗ {e}{RESET}\n")

def main():
    args = sys.argv[1:]

    if not args:
        cmd_repl()
        return

    if args[0] == 'config':
        cmd_config(args[1:])
        return

    if args[0] == 'version':
        print("Sirius Code v1.0.0")
        return

    if args[0] == 'status':
        import httpx
        async def check():
            api_url = get_config('api_url','http://localhost:5002')
            api_key = get_config('api_key','')
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f'{api_url}/status', headers={'X-API-Key': api_key})
                return r.json()
        try:
            result = asyncio.run(check())
            print(f"{GREEN}✓ Sirius Code online{RESET}")
        except Exception as e:
            print(f"{RED}✗ Offline: {e}{RESET}")
        return

    # Executar tarefa direta: sirius "crie um CRUD"
    message = ' '.join(args)
    spinner.start()
    try:
        result, _ = asyncio.run(chat(message))
        spinner.stop()
        print(f"\n{result}\n")
    except Exception as e:
        spinner.stop()
        print(f"\n{RED}✗ {e}{RESET}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
