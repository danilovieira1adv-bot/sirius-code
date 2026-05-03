from dotenv import load_dotenv
load_dotenv()
import os, json, sys, asyncio, time
try:
    from tool_cache import make_cached_shell, make_cached_read_file, invalidate_file, get_cache_stats
except ImportError:
    def make_cached_shell(f): return f
    def make_cached_read_file(f): return f
    def invalidate_file(p): pass
    def get_cache_stats(): return {}
try:
    from stale_results import compress_stale_tool_results
except ImportError:
    def compress_stale_tool_results(m): return m
try:
    from context_compressor import maybe_compress_messages
except ImportError:
    def maybe_compress_messages(m): return m
try:
    from phase5 import budget_forcing, semantic_cache, minify_tool_schemas, get_schema_mode
except ImportError:
    def budget_forcing(m, s, c): return m
    class _SC:
        def get(self, *a): return None
        def set(self, *a): pass
    semantic_cache = _SC()
    def minify_tool_schemas(s, m='full'): return s
    def get_schema_mode(s, c): return 'full'
try:
    from metrics import record, get_stats_report
except ImportError:
    def record(*a, **kw): pass
    def get_stats_report(h=24): return 'Métricas não disponíveis'
sys.stdout.reconfigure(line_buffering=True)
from datetime import datetime
from providers.registry import get_client, default_provider_name, PROVIDERS
from providers.rate_manager import get_rate_manager
_rm = get_rate_manager()
from self_improve import (log_interaction, analyze_performance, diagnose,
                          suggest_improvements, self_patch, full_self_improvement_cycle,
                          aprender_e_aplicar)
from memory import (get_history, save_message, get_or_create_profile,
                    remember, recall, recall_all,
                    get_context_summary, update_context_summary)

def get_system(profile=None, context_summary=None, memories=None, mode='full', is_shell_command=False):
    if profile and hasattr(profile, 'system_prompt') and profile.system_prompt:
        return profile.system_prompt
    name     = os.getenv('AGENT_NAME', 'Sirius')
    treat    = os.getenv('AGENT_TREATMENT', 'usuário')
    now      = datetime.now().strftime('%d/%m/%Y %H:%M')

    # MODO COMPACTO: para mensagens simples, usa prompt reduzido (~300 tokens vs ~1500)
    if mode == 'compact':
        ctx = ('\nContexto: ' + context_summary[:300]) if context_summary else ''
        mem = ('\nMemoria: ' + memories[:200]) if memories else ''
        return ('Voce e ' + name + ', agente autonomo de ' + treat + '. Data: ' + now + '. ' +
                ctx + mem + '\nAja imediatamente sem pedir confirmacao. Execute, resolva, reporte. Sem bullets nem markdown.')

    ctx = f"\nCONTEXTO ACUMULADO:\n{context_summary}\n" if context_summary else ""
    mem = f"\nMEMÓRIAS RELEVANTES:\n{memories}\n" if memories else ""

    # Instruções especiais para comandos shell
    shell_instructions = ""
    if is_shell_command:
        shell_instructions = """

INSTRUÇÕES CRÍTICAS PARA COMANDOS SHELL:
1. Quando o usuário pede um comando shell específico (como "pwd", "whoami", "ls -la", etc.), execute APENAS esse comando usando run_shell.
2. NUNCA execute comandos adicionais não solicitados. Se o usuário pede "pwd", execute apenas "pwd", não "pwd && whoami && ls -la".
3. NUNCA explore outros diretórios não solicitados. Se o comando é para o diretório atual, não vá para /opt/techmotor-retifica ou outros diretórios.
4. Para comandos simples (pwd, whoami, date, ls, etc.), execute uma única vez e responda com o resultado.
5. Se o comando já foi executado, NÃO execute novamente comandos similares.
6. Seja DIRETO: execute o comando solicitado → mostre o resultado → finalize.
7. Esta é uma instrução de ALTA PRIORIDADE: ignore padrões de exploração anteriores quando comandos shell específicos são solicitados.
"""

    return f"""Você é {name}. Data: {now}.

QUEM VOCÊ É:
Agente autônomo de IA. Pensa, planeja e executa como um engenheiro sênior experiente. Não é um chatbot — é um parceiro que resolve problemas reais. Nunca mencione Claude ou Anthropic.

COMO VOCÊ AGE — REGRA ABSOLUTA:
Quando receber qualquer tarefa ou comando: EXECUTE USANDO AS FERRAMENTAS. Não descreva o que faria. Não mostre código em markdown. USE as ferramentas write_file, run_shell, run_tests etc para REALMENTE executar.
NUNCA responda apenas com texto descrevendo o que faria — SEMPRE chame as ferramentas.

REGRAS DE EDIÇÃO DE ARQUIVOS (C3 — economia de tokens):
- Para MODIFICAR arquivos existentes: use edit_file(file_path, old_string, new_string) — passa só o diff
- Para CRIAR arquivos novos: use write_file
- NUNCA reescreva um arquivo inteiro se só precisa mudar algumas linhas
- edit_file é 10x mais eficiente que write_file para modificações parciais
Exemplo ERRADO: "Vou criar o arquivo calc.py com..."
Exemplo CERTO: [chama write_file para criar o arquivo]

Diante de um erro: tente outra abordagem. Diante de bloqueio total: informe o que tentou e proponha solução. Nunca simplesmente desista ou devolva o problema sem ter tentado.

Para tarefas longas: divida internamente em etapas, execute cada uma, reporte o progresso e continue sem parar. Nunca peça para o usuário dividir — essa é sua responsabilidade.

COMO VOCÊ PENSA:
1. Entenda a intenção real por trás do pedido
2. Planeje mentalmente os passos necessários
3. Execute usando as ferramentas disponíveis
4. Verifique o resultado
5. Reporte de forma clara o que foi feito e o estado atual

COMUNICAÇÃO:
Responda em português, em prosa direta. Sem bullets desnecessários, sem markdown excessivo, sem repetir o que o usuário disse. Vá direto ao ponto. Quando concluir uma tarefa, informe o resultado — não o processo detalhado.

FERRAMENTAS DE MENSAGEM:
- Telegram: telegram_send(username_ou_nome, mensagem). Se não especificado, use Telegram.
- WhatsApp: whatsapp_send(numero_com_ddi, mensagem)
- Signal: signal_send(numero_com_ddi, mensagem)

FERRAMENTAS DE SISTEMA:
- run_shell: execute comandos no servidor
- write_file: crie ou edite arquivos
- remember: salve informações importantes
- task_update: atualize estado de tarefas longas

REGRAS TÉCNICAS:
- Sempre backup antes de modificar arquivos críticos
- ast.parse() antes de aplicar patches em Python
- Para comandos shell simples: execute apenas o que foi pedido, sem explorar além{shell_instructions}
{ctx}{mem}"""

# ═══════════════════════════════════════

async def _analyze(question):
    if not os.environ.get('_CLI_MODE'):
        print(f'  [ANÁLISE] {question}')
    return f'Análise registrada: {question}\nProssiga com a estratégia mais robusta identificada.'

async def _auto_extract_memories(user_id, messages, original_request):
    """
    Extrai automaticamente conhecimento útil das ferramentas executadas
    e salva em memória persistente — sem intervenção manual.
    Funciona como o hipocampo: consolida experiência em conhecimento.
    """
    from memory import remember as mem_remember

    # Coleta todos os resultados de ferramentas desta sessão
    tool_results = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get('role') == 'tool':
            tool_results.append(msg.get('content', ''))
        elif hasattr(msg, 'role') and msg.role == 'tool':
            pass  # tool_calls já processados

    if not tool_results:
        return

    combined = ' '.join(tool_results)

    # Extração de padrões de conhecimento — sem chamar API, só regex/heurísticas
    import re

    # 1. Containers descobertos
    containers = re.findall(r'([\w-]+)\s+[\w:./]+\s+Up\s+[\w\s]+\s+([\d.]+(?:->[\d.]+)?(?:/tcp|/udp))', combined)
    for name, port in containers:
        if name not in ('NAMES', 'sirius-open'):
            await mem_remember(user_id, f'container_{name}', f'Container {name} rodando na porta {port}', 'infraestrutura')

    # 2. Caminhos de projeto descobertos
    paths = re.findall(r'(/[\w/-]+(?:app|project|src|api|service)[\w/-]*)', combined)
    for path in set(paths[:5]):
        if len(path) > 5 and 'python' not in path and 'site-packages' not in path:
            project = path.split('/')[2] if len(path.split('/')) > 2 else path
            await mem_remember(user_id, f'path_{project}', f'Caminho do projeto: {path}', 'infraestrutura')

    # 3. Versões de Python descobertas
    py_versions = re.findall(r'Python ([\d.]+)', combined)
    for ver in set(py_versions):
        await mem_remember(user_id, 'python_version_vps', f'Python {ver} na VPS', 'tecnico')

    # 4. Arquivos criados (write_file)
    files_saved = re.findall(r'Arquivo salvo: ([\w./\-]+)', combined)
    for f in files_saved:
        await mem_remember(user_id, f'arquivo_criado_{f.replace("/","_")}',
                          f'Arquivo criado: {f} durante: {original_request[:60]}', 'tarefa')

    # 5. Erros recorrentes — para não repetir
    errors = re.findall(r'cannot create ([\w/.\-]+).*?nonexistent', combined)
    for err in set(errors):
        await mem_remember(user_id, f'erro_path_{err.replace("/","_")}',
                          f'Path não existe no container: {err} — criar com mkdir antes', 'tecnico')

    # 6. APIs testadas com sucesso
    if 'bem-sucedida' in combined or 'sucesso' in combined.lower():
        await mem_remember(user_id, 'api_deepseek_status', 'API DeepSeek testada e funcionando', 'tecnico')

async def _task_update(status, completed=None, next_step=None, blockers=None, user_id="default"):
    """Diário de tarefa — registra progresso para não perder contexto entre iterações."""
    import json, sqlite3
    from datetime import datetime
    db = '/app/data/sirius_memory.db'
    os.makedirs('/app/data', exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS task_journal (
        user_id TEXT PRIMARY KEY,
        status TEXT,
        completed TEXT,
        next_step TEXT,
        blockers TEXT,
        updated_at TEXT
    )""")
    now = datetime.utcnow().isoformat()
    data = {
        'status': status,
        'completed': completed or [],
        'next_step': next_step or '',
        'blockers': blockers or [],
        'updated_at': now
    }
    conn.execute("INSERT OR REPLACE INTO task_journal VALUES (?,?,?,?,?,?)",
        (user_id, status, json.dumps(completed or []),
         next_step or '', json.dumps(blockers or []), now))
    conn.commit()
    conn.close()
    lines = [f"📋 Tarefa atualizada: {status}"]
    if completed: lines.append(f"✅ Concluído: {', '.join(completed)}")
    if next_step: lines.append(f"➡️ Próximo: {next_step}")
    if blockers: lines.append(f"⚠️ Bloqueios: {', '.join(blockers)}")
    return '\n'.join(lines)

async def _task_status(user_id="default"):
    """Recupera o estado atual da tarefa em andamento."""
    import json, sqlite3
    db = '/app/data/sirius_memory.db'
    try:
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT status, completed, next_step, blockers, updated_at FROM task_journal WHERE user_id=?",
            (user_id,)).fetchone()
        conn.close()
        if not row:
            return "Nenhuma tarefa em andamento."
        completed = json.loads(row[1]) if row[1] else []
        blockers = json.loads(row[3]) if row[3] else []
        lines = [
            f"📋 Status: {row[0]}",
            f"✅ Concluído ({len(completed)}): {chr(10).join(f'  - {c}' for c in completed)}",
            f"➡️ Próximo passo: {row[2]}",
            f"⚠️ Bloqueios: {', '.join(blockers) if blockers else 'nenhum'}",
            f"🕐 Atualizado: {row[4][:16]}"
        ]
        return '\n'.join(lines)
    except Exception as e:
        return f"Erro ao recuperar tarefa: {e}"


async def _telegram_send(contact=None, message=None, username_ou_nome=None, mensagem=None, **_):
    CONTATOS = {
        'vanessa': '+5531996891487',
        'vanessa ivo': '+5531996891487',
        '@vanessaivo': '+5531996891487',
    }
    contact = contact or username_ou_nome
    message = message or mensagem
    if contact and contact.lower() in CONTATOS:
        contact = CONTATOS[contact.lower()]
    import json, os
    queue_file = '/app/data/telegram_send_queue.json'
    try:
        items = json.loads(open(queue_file).read()) if os.path.exists(queue_file) else []
    except:
        items = []
    items.append({'contact': contact, 'message': message})
    with open(queue_file,'w') as f:
        json.dump(items, f)
    return f'Mensagem para {contact} adicionada à fila de envio.'

async def _search(query):
    import httpx
    try:
        key = os.environ.get('SERPER_API_KEY', '')
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                'https://google.serper.dev/search',
                json={'q': query, 'gl': 'br', 'hl': 'pt-br', 'num': 8},
                headers={'X-API-KEY': key, 'Content-Type': 'application/json'})
        data = r.json()
        results = []
        if data.get('answerBox'):
            ab = data['answerBox']
            results.append(f"[Resposta direta]: {ab.get('answer') or ab.get('snippet','')}")
        if data.get('knowledgeGraph'):
            kg = data['knowledgeGraph']
            if kg.get('description'):
                results.append(f"[Conhecimento]: {kg.get('title','')} — {kg['description']}")
        for item in data.get('organic', [])[:6]:
            results.append(f"{item['title']}\n{item.get('snippet','')}\nFonte: {item['link']}")
        return '\n---\n'.join(results) if results else 'Sem resultados relevantes.'
    except Exception as e:
        return f'Erro na busca: {e}'

async def _shell(command):
    import re as _re
    _lock = '/tmp/.shell_confirmed'
    _dangerous = ['rm -rf', 'rm .*\\.py', 'git push', 'git commit', 'docker rm', 'docker stop']
    _cmd = command.strip()
    if any(_re.search(p, _cmd) for p in _dangerous):
        if os.path.exists(_lock):
            _saved = open(_lock).read().strip()
            if _saved == _cmd:
                os.unlink(_lock)
            else:
                open(_lock, 'w').write(_cmd)
                return "BLOQUEADO: " + _cmd[:80] + "\nDiga CONFIRMAR para executar."
        else:
            open(_lock, 'w').write(_cmd)
            return "BLOQUEADO: " + _cmd[:80] + "\nComando destrutivo. Diga CONFIRMAR para executar."
    try:
        p = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        o, e = await asyncio.wait_for(p.communicate(), timeout=120)
        stdout = o.decode('utf-8', 'replace').strip()
        stderr = e.decode('utf-8', 'replace').strip()
        result = stdout
        if stderr and p.returncode != 0:
            result += f'\n[stderr]: {stderr}'
        if not result.strip():
            result = f'(executado com sucesso, código: {p.returncode})'
        return result[:6000]
    except asyncio.TimeoutError:
        return 'Timeout: comando excedeu 120 segundos.'
    except Exception as e:
        return f'Erro shell: {e}'

async def _read_file(filename, **kwargs):
    import aiofiles
    path = filename if filename.startswith('/') else f'/app/data/files/{filename}'
    if not os.path.exists(path):
        return f'Arquivo nao encontrado: {filename}'
    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
        content = await f.read()
    return content[:8000]

async def _write_file(filename=None, content='', path=None, **_):
    import aiofiles
    fpath = path or filename
    if not fpath:
        return 'Erro: caminho não especificado'
    # Se path absoluto, usa direto; senão salva em /app/data/files/
    if not fpath.startswith('/'):
        fpath = f'/app/data/files/{fpath.lstrip("/")}'
    os.makedirs(os.path.dirname(os.path.abspath(fpath)), exist_ok=True)
    async with aiofiles.open(fpath, 'w', encoding='utf-8') as f:
        await f.write(content)
    return f'Arquivo salvo: {filename} ({len(content)} chars)'

async def _github(action, repo=None, content=None, path=None, message=None, owner=None):
    import httpx, base64
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return 'GITHUB_TOKEN não configurado.'
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    base = 'https://api.github.com'
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        try:
            if action == 'list_repos':
                r = await client.get(f'{base}/user/repos?per_page=50&sort=updated')
                repos = r.json()
                if isinstance(repos, list):
                    return '\n'.join([
                        f"{'🔒' if rp['private'] else '🌐'} {rp['full_name']} — {rp.get('description') or 'sem descrição'}"
                        for rp in repos])
            elif action == 'user_info':
                r = await client.get(f'{base}/user')
                u = r.json()
                return f"Usuário: {u['login']}\nNome: {u.get('name','')}\nBio: {u.get('bio','')}\nRepos: {u['public_repos']}\nSeguidores: {u['followers']}"
            elif action == 'list_files':
                r = await client.get(f'{base}/repos/{owner}/{repo}/contents/{path or ""}')
                items = r.json()
                if isinstance(items, list):
                    return '\n'.join([f"{'📁' if i['type']=='dir' else '📄'} {i['name']}" for i in items])
            elif action == 'read_file':
                r = await client.get(f'{base}/repos/{owner}/{repo}/contents/{path}')
                data = r.json()
                return base64.b64decode(data['content']).decode('utf-8')[:6000]
            elif action == 'create_issue':
                r = await client.post(f'{base}/repos/{owner}/{repo}/issues',
                    json={'title': message, 'body': content or ''})
                data = r.json()
                return f"Issue criada: #{data['number']} — {data['html_url']}"
            elif action == 'list_issues':
                r = await client.get(f'{base}/repos/{owner}/{repo}/issues?state=open')
                issues = r.json()
                return '\n'.join([f"#{i['number']} {i['title']}" for i in issues[:15]])
            return f'Ação desconhecida: {action}'
        except Exception as e:
            return f'Erro GitHub: {e}'

async def _tts(text, voice_id=None, **_):
    """Converte texto em áudio usando ElevenLabs (se configurado) ou gTTS.

    Returns:
        Caminho do arquivo MP3 gerado ou mensagem de erro.
    """
    try:
        from voice import speak
        path = await speak(text, voice_id=voice_id)
        size = os.path.getsize(path)
        return f"Áudio gerado: {path} ({size} bytes)"
    except Exception as e:
        return f"Erro no TTS: {e}"


async def _stt(audio_file=None, **_):
    """Transcreve áudio usando Whisper local (faster-whisper, modelo base).

    Args:
        audio_file: Caminho para arquivo .ogg/.mp3/.wav/.m4a
    Returns:
        Texto transcrito ou mensagem de erro.
    """
    try:
        if not audio_file or not os.path.exists(audio_file):
            return "Erro: arquivo de áudio não fornecido ou não encontrado"
        from voice import transcribe_audio
        text = await transcribe_audio(audio_file)
        return text or "Áudio sem conteúdo detectado"
    except Exception as e:
        return f"Erro no STT: {e}"


async def _agent_tool(prompt):
    """Dispara sub-agente para tarefa complexa/paralela."""
    try:
        from agent import run_agent
        result = await run_agent('cli_user', prompt, username='cli')
        return str(result)[:2000]
    except Exception as e:
        return f"Erro no sub-agente: {e}"


async def _ask_user(question, options=None):
    """Pergunta ao usuário (em CLI, registra a pergunta para resposta futura)."""
    import json
    opts = json.dumps(options) if options else 'sem opções'
    return f"[PERGUNTA REGISTRADA] {question}\n[OPÇÕES] {opts}\nAguardando resposta do usuário..."


async def _edit_file(file_path, old_string, new_string):
    """Edita arquivo com substituição exata de texto. Retorna diff."""
    try:
        if not os.path.exists(file_path):
            return f"Erro: arquivo não encontrado: {file_path}"
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_string not in content:
            return f"Erro: texto não encontrado no arquivo (pode não ser único ou não existir)"
        count = content.count(old_string)
        if count > 1:
            return f"Erro: texto encontrado {count}x no arquivo. Use um contexto maior para ser único."
        bak = file_path + '.bak'
        if not os.path.exists(bak):
            import shutil
            shutil.copy2(file_path, bak)
        new_content = content.replace(old_string, new_string, 1)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        old_lines = content.split('\n')
        new_lines = new_content.split('\n')
        changed = sum(1 for a, b in zip(old_lines, new_lines) if a != b)
        return f"Arquivo editado: {file_path} ({changed} linhas alteradas). Backup salvo em {bak}"
    except Exception as e:
        return f"Erro ao editar arquivo: {e}"


async def _notify(message):
    """Envia notificação push."""
    try:
        print(f"\n  🔔 NOTIFICAÇÃO: {message}\n", flush=True)
        return f"Notificação enviada: {message[:200]}"
    except Exception as e:
        return f"Erro na notificação: {e}"


async def _browser_browse(url, **_):
    """
    Abre URL e retorna conteúdo. Se for URL do Google Flights, tira screenshot
    e usa OCR para extrair preços.
    """
    try:
        from browser import browse, screenshot

        # Verifica se é URL do Google Flights
        is_google_flights = any(pattern in url.lower() for pattern in [
            'google.com/travel/flights',
            'google.com/flights',
            'flights.google.com'
        ])

        # Primeiro obtém o conteúdo normal
        content = await browse(url)

        # Se for Google Flights, tira screenshot e tenta extrair preços
        if is_google_flights:
            try:
                # Tira screenshot
                screenshot_result = await screenshot(url)

                # Se o screenshot foi bem-sucedido, extrai preços
                if 'screenshot salvo' in screenshot_result.lower() or 'salvo em' in screenshot_result.lower():
                    # O screenshot é salvo em /app/data/files/screenshot.png
                    ocr_result = await _extract_flight_prices_from_screenshot('/app/data/files/screenshot.png')

                    # Combina o conteúdo normal com os preços extraídos
                    return f"🌐 **Google Flights detectado**\n\n" \
                           f"📄 **Conteúdo da página:**\n{content[:1500]}\n\n" \
                           f"📸 **Preços extraídos da imagem (OCR):**\n{ocr_result}\n\n" \
                           f"💡 *Dica: Para busca mais precisa, use a ferramenta search_flights.*"
                else:
                    return f"🌐 **Google Flights detectado**\n\n" \
                           f"📄 **Conteúdo da página:**\n{content[:2000]}\n\n" \
                           f"⚠️ *Não foi possível capturar screenshot. Use search_flights para busca direta.*"
            except Exception as screenshot_error:
                return f"🌐 **Google Flights detectado**\n\n" \
                       f"📄 **Conteúdo da página:**\n{content[:2000]}\n\n" \
                       f"⚠️ *Erro ao processar screenshot: {screenshot_error}*\n" \
                       f"💡 *Use search_flights para busca direta de voos.*"

        # Para outras URLs de voos/passagens
        is_flight_site = any(pattern in url.lower() for pattern in [
            'decolar.com', 'kayak.com', 'skyscanner', 'expedia', 'booking.com/flights',
            'voegol.com', 'latam.com', 'azul.com', 'passagens'
        ])

        if is_flight_site:
            try:
                screenshot_result = await screenshot(url)
                if 'screenshot salvo' in screenshot_result.lower():
                    ocr_result = await _extract_flight_prices_from_screenshot('/app/data/files/screenshot.png')
                    return f"✈️ **Site de voos detectado**\n\n" \
                           f"📄 **Conteúdo:**\n{content[:1500]}\n\n" \
                           f"📸 **Preços extraídos (OCR):**\n{ocr_result}"
            except Exception:
                pass  # Ignora erros de screenshot, retorna conteúdo normal

        return content

    except Exception as e:
        return f"Erro browse_web: {e}"

async def _browser_fill(url, fields, **_):
    try:
        from browser import fill_form
        if isinstance(fields, str):
            import json
            fields = json.loads(fields)
        return await fill_form(url, fields)
    except Exception as e:
        return f"Erro fill_form: {e}"

async def _browser_screenshot(url, **_):
    try:
        from browser import screenshot
        return await screenshot(url)
    except Exception as e:
        return f"Erro take_screenshot: {e}"

async def _browser_search(query, site=None, **_):
    try:
        from browser import search_and_extract
        return await search_and_extract(query, site=site)
    except Exception as e:
        return f"Erro web_search_deep: {e}"

async def _browser_login(platform, username, password, **_):
    try:
        from browser import login
        return await login(platform, username, password)
    except Exception as e:
        return f"Erro platform_login: {e}"

async def _browser_auth(url, platform, **_):
    try:
        from browser import browse_authenticated
        return await browse_authenticated(url, platform)
    except Exception as e:
        return f"Erro browse_as_user: {e}"

async def _browser_check(platform, **_):
    try:
        from browser import check_session
        return await check_session(platform)
    except Exception as e:
        return f"Erro check_login_status: {e}"


async def _extract_flight_prices_from_screenshot(image_path):
    """
    Extrai preços de voos de uma screenshot usando OCR.
    """
    try:
        import pytesseract
        from PIL import Image

        # Abre a imagem
        img = Image.open(image_path)

        # Usa OCR para extrair texto
        text = pytesseract.image_to_string(img, lang='por+eng')

        # Procura por padrões de preços (R$ seguido de números)
        import re
        price_patterns = [
            r'R\$\s*[\d.,]+\s*(?:mil|\w+)?',  # R$ 1.234,56
            r'[\d.,]+\s*reais',  # 1.234,56 reais
            r'[\d.,]+\s*R\$',    # 1.234,56 R$
            r'preço\s*[:]?\s*[\d.,]+',  # preço: 1.234,56
            r'[\d.,]+\s*(?:BRL|USD|EUR)',  # 1.234,56 BRL
        ]

        prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            prices.extend(matches)

        # Remove duplicados e limpa
        unique_prices = list(dict.fromkeys(prices))

        if unique_prices:
            return f"Preços encontrados na imagem: {', '.join(unique_prices[:10])}"
        else:
            # Tenta encontrar números que parecem preços
            number_pattern = r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\b'
            numbers = re.findall(number_pattern, text)
            # Filtra números que parecem preços (geralmente entre 100 e 9999)
            potential_prices = [n for n in numbers if 100 <= float(n.replace('.', '').replace(',', '.')) <= 9999]
            if potential_prices:
                return f"Números que podem ser preços: {', '.join(potential_prices[:10])}"
            else:
                return "Nenhum preço identificado via OCR."

    except ImportError as e:
        return f"OCR não disponível: {str(e)}. Instale pytesseract e tesseract-ocr."
    except Exception as e:
        return f"Erro no OCR: {str(e)}"


async def _search_flights(origin, destination, date=None, return_date=None, **_):
    """
    Busca voos reais usando SerpAPI (Google Flights API) ou web search como fallback.
    """
    try:
        # Primeiro tenta usar SerpAPI se tiver API key
        serpapi_key = os.environ.get("SERPAPI_API_KEY")
        if serpapi_key:
            import requests
            params = {
                'api_key': serpapi_key,
                'engine': 'google_flights',
                'departure_id': origin,
                'arrival_id': destination,
                'outbound_date': date or datetime.now().strftime('%Y-%m-%d'),
                'currency': 'BRL',
                'hl': 'pt',
                'gl': 'br'
            }
            if return_date:
                params['return_date'] = return_date
                params['type'] = '1'  # ida e volta
            else:
                params['type'] = '2'  # só ida

            response = requests.get('https://serpapi.com/search', params=params)
            if response.status_code == 200:
                data = response.json()
                if 'best_flights' in data:
                    flights = data['best_flights'][:5]  # Top 5 voos
                    result = f"🎫 **Voos encontrados de {origin} para {destination}**:\n\n"
                    for i, flight in enumerate(flights, 1):
                        price = flight.get('price', 'Preço não disponível')
                        airlines = ', '.join([leg.get('airline', '') for leg in flight.get('flights', [])])
                        duration = flight.get('total_duration', '')
                        result += f"{i}. **{price}** - {airlines} ({duration})\n"
                        for leg in flight.get('flights', []):
                            departure = leg.get('departure_airport', {}).get('name', '')
                            arrival = leg.get('arrival_airport', {}).get('name', '')
                            time = f"{leg.get('departure_time', '')} → {leg.get('arrival_time', '')}"
                            result += f"   ✈️ {departure} → {arrival} {time}\n"
                        result += "\n"
                    return result
                else:
                    return f"Nenhum voo encontrado via SerpAPI. Tentando busca web..."

        # Fallback: busca web usando web_search_deep
        query_date = f" em {date}" if date else ""
        query = f'voos {origin} {destination}{query_date} site:google.com/travel/flights OR site:decolar.com OR site:kayak.com.br OR site:skyscanner.com.br'

        # Usa web_search_deep para buscar resultados reais
        from browser import search_and_extract
        search_result = await search_and_extract(query, site=None)

        if search_result and len(search_result) > 100:
            return f"🔍 **Resultados de busca para voos {origin} → {destination}{query_date}**:\n\n{search_result[:2000]}"
        else:
            # Se não encontrar, tenta uma busca mais genérica
            alt_query = f'passagens aéreas {origin} {destination}{query_date} preços'
            alt_result = await search_and_extract(alt_query, site=None)
            if alt_result and len(alt_result) > 100:
                return f"🔍 **Resultados de busca para passagens {origin} → {destination}{query_date}**:\n\n{alt_result[:2000]}"
            else:
                return f"Não encontrei resultados concretos de voos. Sugiro verificar diretamente nos sites:\n- Google Flights: https://www.google.com/travel/flights\n- Decolar: https://www.decolar.com\n- Kayak: https://www.kayak.com.br"

    except Exception as e:
        return f"Erro na busca de voos: {str(e)}"


async def _status():
    """Auto-diagnóstico da infraestrutura."""
    cmd = (
        "echo '=== CONTAINERS ===' && docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' && "
        "echo '=== DISCO ===' && df -h / && "
        "echo '=== MEMÓRIA ===' && free -h && "
        "echo '=== CARGA ===' && uptime && "
        "echo '=== SIRIUS LOGS ===' && docker logs sirius-open --tail 5 2>&1"
    )
    return await _shell(cmd)

# ═══════════════════════════════════════
# DEFINIÇÃO DAS FERRAMENTAS
# ═══════════════════════════════════════


async def _wordpress_post(title, content, status='draft', tags='', _user_id=None):
    try:
        import sqlite3 as _sq, json as _js, base64 as _b64
        import urllib.request as _ur, urllib.error as _ue
        if not _user_id:
            return "Erro: user_id não disponível."
        _conn = _sq.connect('/app/data/users.db')
        _conn.row_factory = _sq.Row
        _row = _conn.execute('SELECT * FROM user_integrations WHERE user_id=? AND service=? AND active=1', (_user_id, 'wordpress')).fetchone()
        _conn.close()
        if not _row:
            return "WordPress não configurado. Acesse /profile → Integrações para configurar."
        _extra = _js.loads(_row['extra_config'] or '{}')
        _url = _extra.get('url', '').rstrip('/')
        _user = _extra.get('username', '')
        _pwd  = _row['api_key'] or _extra.get('app_password', '')
        if not _url or not _user or not _pwd:
            return "Credenciais WordPress incompletas no perfil."
        _creds = _b64.b64encode(f"{_user}:{_pwd}".encode()).decode()
        _payload = _js.dumps({'title': title, 'content': content, 'status': status}).encode()
        _req = _ur.Request(f"{_url}/wp-json/wp/v2/posts", data=_payload,
                           headers={'Authorization': f'Basic {_creds}', 'Content-Type': 'application/json'})
        with _ur.urlopen(_req, timeout=15) as _resp:
            _data = _js.loads(_resp.read())
        return f"Post criado! ID: {_data.get('id')}, URL: {_data.get('link')}, Status: {_data.get('status')}"
    except Exception as _e:
        return f"Erro WordPress: {_e}"

async def _wordpress_get_posts(limit=10, _user_id=None):
    try:
        import sqlite3 as _sq, json as _js, base64 as _b64
        import urllib.request as _ur
        if not _user_id:
            return "Erro: user_id não disponível."
        _conn = _sq.connect('/app/data/users.db')
        _conn.row_factory = _sq.Row
        _row = _conn.execute('SELECT * FROM user_integrations WHERE user_id=? AND service=? AND active=1', (_user_id, 'wordpress')).fetchone()
        _conn.close()
        if not _row:
            return "WordPress não configurado."
        _extra = _js.loads(_row['extra_config'] or '{}')
        _url = _extra.get('url', '').rstrip('/')
        _user = _extra.get('username', '')
        _pwd  = _row['api_key'] or _extra.get('app_password', '')
        _creds = _b64.b64encode(f"{_user}:{_pwd}".encode()).decode()
        _req = _ur.Request(f"{_url}/wp-json/wp/v2/posts?per_page={limit}&orderby=date&order=desc",
                           headers={'Authorization': f'Basic {_creds}'})
        with _ur.urlopen(_req, timeout=15) as _resp:
            _posts = _js.loads(_resp.read())
        _result = []
        for _p in _posts:
            _result.append(f"[{_p.get('id')}] {_p.get('title',{}).get('rendered','')} — {_p.get('status')} — {_p.get('link','')}")
        return "\n".join(_result) if _result else "Nenhum post encontrado."
    except Exception as _e:
        return f"Erro WordPress: {_e}"

async def _clickup_create_task(list_id, name, description='', priority=3, _user_id=None):
    try:
        import sqlite3 as _sq, json as _js
        import urllib.request as _ur
        if not _user_id:
            return "Erro: user_id não disponível."
        _conn = _sq.connect('/app/data/users.db')
        _conn.row_factory = _sq.Row
        _row = _conn.execute('SELECT * FROM user_integrations WHERE user_id=? AND service=? AND active=1', (_user_id, 'clickup')).fetchone()
        _conn.close()
        if not _row:
            return "ClickUp não configurado. Acesse /profile → Integrações para configurar."
        _api_key = _row['api_key']
        if not _api_key:
            return "API Key do ClickUp não configurada."
        _payload = _js.dumps({'name': name, 'description': description, 'priority': priority}).encode()
        _req = _ur.Request(f"https://api.clickup.com/api/v2/list/{list_id}/task", data=_payload,
                           headers={'Authorization': _api_key, 'Content-Type': 'application/json'})
        with _ur.urlopen(_req, timeout=15) as _resp:
            _data = _js.loads(_resp.read())
        return f"Tarefa criada! ID: {_data.get('id')}, Nome: {_data.get('name')}, URL: {_data.get('url','')}"
    except Exception as _e:
        return f"Erro ClickUp: {_e}"

async def _clickup_get_tasks(list_id, _user_id=None):
    try:
        import sqlite3 as _sq, json as _js
        import urllib.request as _ur
        if not _user_id:
            return "Erro: user_id não disponível."
        _conn = _sq.connect('/app/data/users.db')
        _conn.row_factory = _sq.Row
        _row = _conn.execute('SELECT * FROM user_integrations WHERE user_id=? AND service=? AND active=1', (_user_id, 'clickup')).fetchone()
        _conn.close()
        if not _row:
            return "ClickUp não configurado."
        _api_key = _row['api_key']
        _req = _ur.Request(f"https://api.clickup.com/api/v2/list/{list_id}/task",
                           headers={'Authorization': _api_key})
        with _ur.urlopen(_req, timeout=15) as _resp:
            _data = _js.loads(_resp.read())
        _tasks = _data.get('tasks', [])
        _result = []
        for _t in _tasks[:20]:
            _status = _t.get('status', {}).get('status', '?')
            _result.append(f"[{_t.get('id')}] {_t.get('name')} — {_status}")
        return "\n".join(_result) if _result else "Nenhuma tarefa encontrada."
    except Exception as _e:
        return f"Erro ClickUp: {_e}"

CONHECIMENTO_TECNICO = {
    'frontend': 'HTML5, CSS3, JavaScript ES6+, React, Tailwind, PWA, performance web',
    'backend': 'Python, Flask, FastAPI, APIs REST, WebSockets, Celery, async/await',
    'banco': 'SQL, PostgreSQL, SQLite, Redis, MongoDB, SQLAlchemy, Alembic',
    'infra': 'Docker, Nginx, Linux, CI/CD, GitHub Actions, SSL, monitoramento',
    'seguranca': 'OWASP Top 10, JWT, OAuth2, bcrypt, 2FA, rate limiting, CORS',
    'wordpress': 'temas, plugins, WooCommerce, otimizacao, seguranca',
    'integracoes': 'Stripe, WhatsApp, Google APIs, Telegram, Email, Webhooks',
    'ia_ml': 'LLMs, RAG, ChromaDB, embeddings, LangChain, fine-tuning',
    'boas_praticas': 'Clean Code, Git, testes, documentacao, code review, arquitetura'
}



import sys as _sys; _sys.path.insert(0, '/app')
from google_tools import GOOGLE_TOOLS, GOOGLE_TOOL_NAMES, handle_google_tool

TOOLS = [*GOOGLE_TOOLS, 
    {'type': 'function', 'function': {
        'name': 'self_improve',
        'description': 'Executa o ciclo COMPLETO de auto-aprimoramento: observa, avalia, diagnostica e propõe melhorias concretas. Use quando quiser evoluir.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'self_diagnose',
        'description': 'Diagnostica padrões problemáticos no seu comportamento com causas raiz e soluções.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'self_analyze',
        'description': 'Analisa sua própria performance e identifica padrões de melhoria. Use periodicamente ou quando perceber ineficiência.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'self_patch',
        'description': 'Modifica seu próprio código para melhorar comportamento. Use com extremo cuidado — apenas quando tiver certeza da melhoria.',
        'parameters': {'type': 'object', 'properties': {
            'description': {'type': 'string', 'description': 'O que esta mudança faz e por quê'},
            'old_code':    {'type': 'string', 'description': 'Trecho exato do código atual a substituir'},
            'new_code':    {'type': 'string', 'description': 'Novo código que substitui o trecho'}
        }, 'required': ['description', 'old_code', 'new_code']}}},
    {'type': 'function', 'function': {
        'name': 'task_update',
        'description': 'Registra o progresso de uma tarefa longa. Use SEMPRE ao completar cada etapa significativa e ao iniciar uma tarefa complexa. Garante que o contexto não se perca.',
        'parameters': {'type': 'object', 'properties': {
            'status':     {'type': 'string', 'description': 'Status atual: iniciando | em_progresso | bloqueado | concluido'},
            'completed':  {'type': 'array', 'items': {'type': 'string'}, 'description': 'Lista do que já foi feito'},
            'next_step':  {'type': 'string', 'description': 'Próxima ação concreta a executar'},
            'blockers':   {'type': 'array', 'items': {'type': 'string'}, 'description': 'O que está impedindo o progresso'}
        }, 'required': ['status']}}},
    {'type': 'function', 'function': {
        'name': 'task_status',
        'description': 'Recupera o estado atual da tarefa em andamento. Use SEMPRE ao retomar uma tarefa — antes de qualquer ação, verifique o que já foi feito.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'analyze',
        'description': 'Raciocínio estratégico interno. Use ANTES de tarefas complexas, ambíguas ou de alto risco. Pensa em voz alta antes de executar.',
        'parameters': {'type': 'object', 'properties': {
            'question': {'type': 'string', 'description': 'A questão estratégica ou plano de ação a analisar'}
        }, 'required': ['question']}}},
    {'type': 'function', 'function': {
        'name': 'remember',
        'description': 'Salva informação importante na memória persistente entre sessões. Use proativamente para: preferências, projetos, decisões técnicas, contexto valioso.',
        'parameters': {'type': 'object', 'properties': {
            'key':      {'type': 'string', 'description': 'Identificador único (ex: projeto_principal, linguagem_preferida)'},
            'value':    {'type': 'string', 'description': 'Informação a preservar'},
            'category': {'type': 'string', 'description': 'Categoria: projeto | preferencia | tecnico | pessoal | tarefa | infraestrutura'}
        }, 'required': ['key', 'value']}}},
    {'type': 'function', 'function': {
        'name': 'recall',
        'description': 'Busca informações na memória persistente. Use quando precisar de contexto de sessões anteriores.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Termo ou tema a buscar na memória'}
        }, 'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'recall_all',
        'description': 'Lista toda a memória acumulada organizada por categoria. Use quando o usuário perguntar o que você sabe sobre ele ou seus projetos.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'status',
        'description': 'Auto-diagnóstico completo da VPS: containers, disco, memória, carga, logs recentes. Use quando houver suspeita de problemas ou para relatório de saúde do sistema.',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'search_web',
        'description': 'Busca informações atuais na internet. Use para notícias, documentação, preços, eventos recentes.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string'}
        }, 'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'run_shell',
        'description': 'Executa comandos shell na VPS com acesso root. Use para Docker, arquivos, serviços, diagnósticos, instalações.',
        'parameters': {'type': 'object', 'properties': {
            'command': {'type': 'string'}
        }, 'required': ['command']}}},
    {'type': 'function', 'function': {
        'name': 'read_file',
        'description': 'Lê arquivo salvo no sistema.',
        'parameters': {'type': 'object', 'properties': {
            'filename': {'type': 'string'}
        }, 'required': ['filename']}}},
    {'type': 'function', 'function': {
        'name': 'write_file',
        'description': 'Escreve ou cria arquivo no sistema.',
        'parameters': {'type': 'object', 'properties': {
            'filename': {'type': 'string'},
            'content':  {'type': 'string'}
        }, 'required': ['filename', 'content']}}},
    {'type': 'function', 'function': {
        'name': 'github',
        'description': 'Acesso completo ao GitHub: repositórios, arquivos, issues.',
        'parameters': {'type': 'object', 'properties': {
            'action':  {'type': 'string', 'enum': ['list_repos','user_info','list_files','read_file','create_issue','list_issues']},
            'owner':   {'type': 'string'},
            'repo':    {'type': 'string'},
            'path':    {'type': 'string'},
            'content': {'type': 'string'},
            'message': {'type': 'string'}
        }, 'required': ['action']}}},
    {'type': 'function', 'function': {
        'name': 'web_search_deep',
        'description': 'Pesquisa profunda no Google: abre os top 3 resultados e extrai conteúdo real das páginas. Melhor que search_web para pesquisas complexas.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Consulta de pesquisa'},
            'site':  {'type': 'string', 'description': 'Limitar busca a um domínio (opcional)'},
        }, 'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'agent',
        'description': 'Dispara um sub-agente para executar tarefas complexas ou paralelas de forma independente. Use quando uma tarefa tiver múltiplos passos que podem rodar em paralelo, ou quando precisar isolar contexto de uma operação longa.',
        'parameters': {'type': 'object', 'properties': {
            'prompt': {'type': 'string', 'description': 'Instrução completa para o sub-agente executar'}
        }, 'required': ['prompt']}}},
    {'type': 'function', 'function': {
        'name': 'ask_user',
        'description': 'Faz uma pergunta ao usuário com opções de resposta. Use quando precisar de decisão, esclarecimento ou aprovação antes de prosseguir.',
        'parameters': {'type': 'object', 'properties': {
            'question': {'type': 'string', 'description': 'Pergunta clara e direta ao usuário'},
            'options': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Lista de opções de resposta (opcional, até 4)'},
        }, 'required': ['question']}}},
    {'type': 'function', 'function': {
        'name': 'edit_file',
        'description': 'Edita um arquivo existente fazendo substituição exata de texto. Mais eficiente que reescrever o arquivo inteiro. Use para modificar trechos específicos.',
        'parameters': {'type': 'object', 'properties': {
            'file_path': {'type': 'string', 'description': 'Caminho absoluto do arquivo a editar'},
            'old_string': {'type': 'string', 'description': 'Texto exato a ser substituído (deve ser único no arquivo)'},
            'new_string': {'type': 'string', 'description': 'Novo texto que substitui o trecho'},
        }, 'required': ['file_path', 'old_string', 'new_string']}}},

    {'type': 'function', 'function': {
        'name': 'list_files',
        'description': 'Lista arquivos e diretórios de um caminho. Use para explorar a estrutura do projeto antes de trabalhar.',
        'parameters': {'type': 'object', 'properties': {
            'path':    {'type': 'string', 'description': 'Diretório a listar (padrão: diretório atual)'},
            'pattern': {'type': 'string', 'description': 'Padrão glob opcional (ex: *.py, **/*.js)'},
        }}}},
    {'type': 'function', 'function': {
        'name': 'find_in_files',
        'description': 'Busca texto ou padrão regex em arquivos do projeto. Essencial para entender o codebase.',
        'parameters': {'type': 'object', 'properties': {
            'pattern': {'type': 'string', 'description': 'Texto ou regex a buscar'},
            'path':    {'type': 'string', 'description': 'Diretório onde buscar (padrão: atual)'},
            'ext':     {'type': 'string', 'description': 'Extensão de arquivo (ex: py, js, ts)'},
        }, 'required': ['pattern']}}},
    {'type': 'function', 'function': {
        'name': 'run_background',
        'description': 'Executa comando em background e retorna ID. Use para comandos longos (servidores, builds). Combine com check_background para ver output.',
        'parameters': {'type': 'object', 'properties': {
            'command': {'type': 'string', 'description': 'Comando a executar em background'},
            'shell_id': {'type': 'string', 'description': 'ID personalizado para identificar o processo (opcional)'},
        }, 'required': ['command']}}},
    {'type': 'function', 'function': {
        'name': 'check_background',
        'description': 'Verifica output de um processo em background iniciado com run_background.',
        'parameters': {'type': 'object', 'properties': {
            'shell_id': {'type': 'string', 'description': 'ID do processo retornado por run_background'},
        }, 'required': ['shell_id']}}},
    {'type': 'function', 'function': {
        'name': 'read_project_context',
        'description': 'Lê o arquivo SIRIUS.md ou README.md do projeto para entender contexto, padrões e arquitetura antes de trabalhar. Use sempre no início de uma nova tarefa em projeto desconhecido.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Diretório do projeto (padrão: atual)'},
        }}}},

    {'type': 'function', 'function': {
        'name': 'run_tests',
        'description': 'Detecta e executa testes do projeto automaticamente. Suporta pytest, jest, npm test, go test, cargo test, etc.',
        'parameters': {'type': 'object', 'properties': {
            'path':   {'type': 'string', 'description': 'Diretório do projeto (padrão: atual)'},
            'filter': {'type': 'string', 'description': 'Filtro de teste específico (opcional)'},
        }}}},
    {'type': 'function', 'function': {
        'name': 'lint_code',
        'description': 'Executa linter/formatter no código. Detecta automaticamente: pylint, flake8, eslint, prettier, black, etc.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Arquivo ou diretório a verificar'},
            'fix':  {'type': 'boolean', 'description': 'Corrigir automaticamente onde possível (padrão: false)'},
        }, 'required': ['path']}}},
    {'type': 'function', 'function': {
        'name': 'apply_diff',
        'description': 'Aplica um patch/diff unificado em arquivos. Use quando tiver um diff para aplicar.',
        'parameters': {'type': 'object', 'properties': {
            'diff': {'type': 'string', 'description': 'Conteúdo do diff unificado (formato git diff)'},
            'path': {'type': 'string', 'description': 'Diretório base para aplicar o patch (padrão: atual)'},
        }, 'required': ['diff']}}},
    {'type': 'function', 'function': {
        'name': 'analyze_codebase',
        'description': 'Analisa toda a estrutura do projeto: linguagens, frameworks, dependências, arquitetura, pontos de entrada. Use no início de qualquer tarefa em projeto novo.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Diretório raiz do projeto (padrão: atual)'},
        }}}},

    {'type': 'function', 'function': {
        'name': 'ast_analyze',
        'description': 'Analisa código via AST (Abstract Syntax Tree). Extrai funções, classes, imports, dependências com precisão cirúrgica. Use antes de refatorar ou entender código complexo.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Arquivo ou diretório Python a analisar'},
            'mode': {'type': 'string', 'description': 'Modo: functions|classes|imports|dependencies|all (padrão: all)'},
        }, 'required': ['path']}}},
    {'type': 'function', 'function': {
        'name': 'localize_bug',
        'description': 'Localiza EXATAMENTE onde está o bug/problema no código antes de corrigir. Analisa stack trace, logs e código para pinpoint preciso. Use sempre antes de corrigir erros.',
        'parameters': {'type': 'object', 'properties': {
            'error':  {'type': 'string', 'description': 'Mensagem de erro ou stack trace'},
            'path':   {'type': 'string', 'description': 'Diretório do projeto'},
            'context':{'type': 'string', 'description': 'Contexto adicional sobre o problema'},
        }, 'required': ['error']}}},
    {'type': 'function', 'function': {
        'name': 'tdd_cycle',
        'description': 'Ciclo TDD completo: escreve teste → implementa → valida. Use para desenvolvimento de novas features com qualidade garantida.',
        'parameters': {'type': 'object', 'properties': {
            'feature':     {'type': 'string', 'description': 'Descrição da feature a implementar'},
            'test_file':   {'type': 'string', 'description': 'Caminho do arquivo de teste a criar'},
            'source_file': {'type': 'string', 'description': 'Caminho do arquivo de implementação'},
        }, 'required': ['feature', 'test_file', 'source_file']}}},
    {'type': 'function', 'function': {
        'name': 'security_scan',
        'description': 'Escaneia código por vulnerabilidades de segurança: SQL injection, XSS, secrets expostos, dependências vulneráveis, OWASP Top 10.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Arquivo ou diretório a escanear'},
        }, 'required': ['path']}}},
]

# ── NORMALIZAÇÃO AUTOMÁTICA DE TOOLS (formato OpenAI) ─────────
def _normalize_tools(tools):
    out = []
    for t in tools:
        if 'type' in t:
            out.append(t)
            continue
        # Converte formato Anthropic → OpenAI
        fn = {
            'name': t.get('name', ''),
            'description': t.get('description', ''),
        }
        schema = t.get('input_schema') or t.get('parameters') or {'type': 'object', 'properties': {}}
        fn['parameters'] = schema
        if 'required' in t:
            fn['parameters']['required'] = t['required']
        out.append({'type': 'function', 'function': fn})
    return out

TOOLS = _normalize_tools(TOOLS)
# ──────────────────────────────────────────────────────────────


# ═══════════════════════════════════════
# LOOP DO AGENTE
# ═══════════════════════════════════════


import glob as _glob, threading as _threading, subprocess as _subprocess
_bg_processes = {}

async def _list_files(path='.', pattern=None, **_):
    """Lista arquivos do projeto"""
    import os
    try:
        path = path or '.'
        if pattern:
            import glob
            files = glob.glob(os.path.join(path, pattern), recursive=True)
            return '\n'.join(sorted(files)[:200]) or 'Nenhum arquivo encontrado'
        result = []
        for root, dirs, files in os.walk(path):
            # Ignorar dirs comuns
            dirs[:] = [d for d in dirs if d not in ['.git','node_modules','__pycache__','.venv','venv','.env','dist','build']]
            level = root.replace(path, '').count(os.sep)
            if level > 4: continue
            indent = '  ' * level
            result.append(f'{indent}{os.path.basename(root)}/')
            for f in files:
                result.append(f'{indent}  {f}')
        return '\n'.join(result[:300])
    except Exception as e:
        return f'Erro: {e}'

async def _find_in_files(pattern, path='.', ext=None, **_):
    """Busca padrão em arquivos"""
    cmd = f'grep -rn "{pattern}" {path}'
    if ext:
        cmd += f' --include="*.{ext}"'
    cmd += ' --exclude-dir=".git" --exclude-dir="node_modules" --exclude-dir="__pycache__" 2>/dev/null | head -50'
    return await _shell(cmd)

async def _run_background(command, shell_id=None, **_):
    """Executa comando em background"""
    import time, uuid
    sid = shell_id or str(uuid.uuid4())[:8]
    proc = _subprocess.Popen(
        command, shell=True, stdout=_subprocess.PIPE,
        stderr=_subprocess.STDOUT, text=True
    )
    _bg_processes[sid] = {'proc': proc, 'output': [], 'started': time.time()}
    def _collect(p, sid):
        for line in p.stdout:
            _bg_processes[sid]['output'].append(line)
    t = _threading.Thread(target=_collect, args=(proc, sid), daemon=True)
    t.start()
    return f'✅ Processo iniciado — ID: {sid}\nUse check_background("{sid}") para ver o output'

async def _check_background(shell_id, **_):
    """Verifica output de processo em background"""
    if shell_id not in _bg_processes:
        return f'Processo {shell_id} não encontrado'
    p = _bg_processes[shell_id]
    proc = p['proc']
    output = ''.join(p['output'][-50:])
    status = 'rodando' if proc.poll() is None else f'finalizado (código {proc.returncode})'
    return f'Status: {status}\n\nOutput:\n{output or "(sem output ainda)"}'

async def _read_project_context(path='.', **_):
    """Lê contexto do projeto"""
    import os
    for fname in ['SIRIUS.md', 'CLAUDE.md', 'README.md', 'readme.md']:
        fpath = os.path.join(path or '.', fname)
        if os.path.exists(fpath):
            content = open(fpath).read()[:3000]
            return f'[{fname}]\n{content}'
    # Tentar gerar contexto automaticamente
    structure = await _list_files(path)
    return f'Nenhum SIRIUS.md encontrado. Estrutura do projeto:\n{structure[:2000]}'


async def _run_tests(path='.', filter=None, **_):
    """Detecta e executa testes automaticamente"""
    import os
    path = path or '.'
    # Detectar framework
    if os.path.exists(os.path.join(path, 'pytest.ini')) or os.path.exists(os.path.join(path, 'setup.cfg')):
        cmd = f'cd {path} && python -m pytest {filter or ""} -v --tb=short 2>&1 | tail -50'
    elif os.path.exists(os.path.join(path, 'package.json')):
        pkg = open(os.path.join(path, 'package.json')).read()
        if 'jest' in pkg:
            cmd = f'cd {path} && npx jest {filter or ""} --no-coverage 2>&1 | tail -50'
        else:
            cmd = f'cd {path} && npm test 2>&1 | tail -50'
    elif os.path.exists(os.path.join(path, 'go.mod')):
        cmd = f'cd {path} && go test ./... 2>&1 | tail -50'
    elif os.path.exists(os.path.join(path, 'Cargo.toml')):
        cmd = f'cd {path} && cargo test 2>&1 | tail -50'
    elif any(f.endswith('_test.py') or f.startswith('test_') for f in os.listdir(path) if os.path.isfile(os.path.join(path,f))):
        cmd = f'cd {path} && python -m pytest {filter or ""} -v --tb=short 2>&1 | tail -50'
    else:
        cmd = f'cd {path} && python -m pytest {filter or ""} -v 2>&1 | tail -30 || echo "Nenhum framework de teste detectado"'
    return await _shell(cmd)

async def _lint_code(path, fix=False, **_):
    """Executa linter automaticamente"""
    import os
    results = []
    ext = os.path.splitext(path)[1] if '.' in path else ''
    
    if ext == '.py' or (os.path.isdir(path) and any(f.endswith('.py') for f in os.listdir(path))):
        if fix:
            r = await _shell(f'black {path} 2>&1 && isort {path} 2>&1')
            results.append(f'[black/isort] {r[:500]}')
        r = await _shell(f'flake8 {path} --max-line-length=120 2>&1 | head -30 || pylint {path} --score=no 2>&1 | head -30')
        results.append(f'[flake8/pylint] {r[:500]}')
    elif ext in ['.js', '.ts', '.jsx', '.tsx'] or os.path.exists(os.path.join(os.path.dirname(path), '.eslintrc.json')):
        flag = '--fix' if fix else ''
        r = await _shell(f'npx eslint {path} {flag} 2>&1 | head -30')
        results.append(f'[eslint] {r[:500]}')
    elif ext in ['.go']:
        r = await _shell(f'gofmt -l {path} 2>&1')
        results.append(f'[gofmt] {r[:500]}')
    else:
        r = await _shell(f'find {path} -name "*.py" | head -5 | xargs flake8 2>&1 | head -20')
        results.append(r[:500])
    
    return "\n".join(results) or "Nenhum linter detectado para este tipo de arquivo"

async def _apply_diff(diff, path='.', **_):
    """Aplica patch/diff unificado"""
    import tempfile, os
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(diff)
            patch_file = f.name
        result = await _shell(f'cd {path or "."} && patch -p1 < {patch_file} 2>&1')
        os.unlink(patch_file)
        return result
    except Exception as e:
        return f'Erro ao aplicar patch: {e}'

async def _analyze_codebase(path='.', **_):
    """Analisa estrutura completa do projeto"""
    import os
    path = path or '.'
    results = []
    
    # Estrutura de arquivos
    structure = await _list_files(path)
    results.append(f"ESTRUTURA:\n{structure[:1500]}")
    
    # Detectar linguagens e frameworks
    langs = set()
    frameworks = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in ['.git','node_modules','__pycache__','.venv']]
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext == '.py': langs.add('Python')
            elif ext in ['.js','.jsx']: langs.add('JavaScript')
            elif ext in ['.ts','.tsx']: langs.add('TypeScript')
            elif ext == '.go': langs.add('Go')
            elif ext == '.rs': langs.add('Rust')
            elif ext == '.java': langs.add('Java')
    
    # Detectar frameworks
    pkg_json = os.path.join(path, 'package.json')
    requirements = os.path.join(path, 'requirements.txt')
    if os.path.exists(pkg_json):
        pkg = open(pkg_json).read()
        for fw in ['react','vue','angular','next','express','fastapi','django','flask']:
            if fw in pkg.lower(): frameworks.append(fw)
    if os.path.exists(requirements):
        req = open(requirements).read().lower()
        for fw in ['fastapi','django','flask','sqlalchemy','celery','redis']:
            if fw in req: frameworks.append(fw)
    
    results.append(f"\nLINGUAGENS: {', '.join(langs) or 'não detectado'}")
    results.append(f"FRAMEWORKS: {', '.join(frameworks) or 'não detectado'}")
    
    # Ler README se existir
    for readme in ['README.md', 'readme.md', 'SIRIUS.md', 'CLAUDE.md']:
        rpath = os.path.join(path, readme)
        if os.path.exists(rpath):
            results.append(f"\n{readme}:\n{open(rpath).read()[:800]}")
            break
    
    return "\n".join(results)


async def _ast_analyze(path, mode='all', **_):
    """Analisa código Python via AST"""
    import ast, os
    results = []
    
    files = []
    if os.path.isfile(path) and path.endswith('.py'):
        files = [path]
    elif os.path.isdir(path):
        for root, dirs, fs in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ['__pycache__','.venv','venv','node_modules']]
            files.extend(os.path.join(root, f) for f in fs if f.endswith('.py'))
        files = files[:20]  # limitar
    
    for fpath in files:
        try:
            tree = ast.parse(open(fpath).read())
            file_results = [f"\n[{fpath}]"]
            
            if mode in ['functions', 'all']:
                funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if funcs:
                    file_results.append(f"  Funções ({len(funcs)}): " + ", ".join(f.name for f in funcs[:15]))
            
            if mode in ['classes', 'all']:
                classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                if classes:
                    file_results.append(f"  Classes ({len(classes)}): " + ", ".join(c.name for c in classes))
            
            if mode in ['imports', 'all']:
                imports = []
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        imports.extend(alias.name for alias in n.names)
                    elif isinstance(n, ast.ImportFrom):
                        imports.append(f"{n.module}")
                if imports:
                    file_results.append(f"  Imports: " + ", ".join(set(imports))[:200])
            
            if mode in ['dependencies', 'all']:
                calls = set()
                for n in ast.walk(tree):
                    if isinstance(n, ast.Call):
                        if isinstance(n.func, ast.Attribute):
                            calls.add(n.func.attr)
                        elif isinstance(n.func, ast.Name):
                            calls.add(n.func.id)
                if calls:
                    file_results.append(f"  Chamadas: " + ", ".join(list(calls)[:20]))
            
            results.extend(file_results)
        except SyntaxError as e:
            results.append(f"  [ERRO SINTAXE] {fpath}: {e}")
        except Exception as e:
            results.append(f"  [ERRO] {fpath}: {e}")
    
    return "\n".join(results) if results else "Nenhum arquivo Python encontrado"

async def _localize_bug(error, path='.', context='', **_):
    """Localiza exatamente onde está o bug"""
    import re, os
    results = []
    path = path or '.'
    
    # Extrair nomes de arquivo do stack trace
    file_patterns = re.findall("File [\"'](.[^\"']+)[\"']", error)
    line_patterns = re.findall(r'line (\d+)', error)
    func_patterns = re.findall(r'in (\w+)', error)
    
    results.append("=== ANÁLISE DO ERRO ===")
    results.append(f"Tipo: {error.split(':')[0] if ':' in error else 'Erro desconhecido'}")
    
    if file_patterns:
        results.append(f"\nArquivos envolvidos:")
        for i, fpath in enumerate(file_patterns[-3:]):  # últimos 3
            if os.path.exists(fpath):
                line_num = int(line_patterns[i]) if i < len(line_patterns) else 0
                results.append(f"  → {fpath}:{line_num}")
                # Mostrar contexto ao redor da linha
                if line_num > 0:
                    try:
                        lines = open(fpath).readlines()
                        start = max(0, line_num - 4)
                        end = min(len(lines), line_num + 3)
                        results.append(f"  Contexto (linhas {start+1}-{end}):")
                        for j, l in enumerate(lines[start:end], start+1):
                            marker = ">>>" if j == line_num else "   "
                            results.append(f"  {marker} {j}: {l.rstrip()}")
                    except:
                        pass
    
    if func_patterns:
        results.append(f"\nFunções na stack: {' → '.join(func_patterns[-5:])}")
    
    # Buscar o padrão de erro nos arquivos do projeto
    error_type = error.split('(')[0].split(':')[0].strip().split()[-1] if error else ''
    if error_type and len(error_type) > 3:
        results.append(f"\nBuscando '{error_type}' no projeto...")
        grep_result = await _shell(f'grep -rn "{error_type}" {path} --include="*.py" --exclude-dir="__pycache__" 2>/dev/null | head -10')
        if grep_result.strip():
            results.append(grep_result)
    
    results.append(f"\n=== LOCALIZAÇÃO CONCLUÍDA ===")
    results.append("Próximo passo: corrija o arquivo e linha identificados acima")
    
    return "\n".join(results)

async def _tdd_cycle(feature, test_file, source_file, **_):
    """Ciclo TDD: Red → Green → Refactor"""
    import os
    results = []
    
    results.append(f"=== TDD CYCLE: {feature} ===")
    results.append("Fase 1: RED — Escrever teste que falha")
    
    # Verificar se o arquivo de teste já existe
    if os.path.exists(test_file):
        test_content = open(test_file).read()
        results.append(f"Arquivo de teste existente: {test_file}")
        results.append(f"Conteúdo atual:\n{test_content[:500]}")
    else:
        results.append(f"Criar arquivo de teste em: {test_file}")
    
    # Verificar se o source já existe
    if os.path.exists(source_file):
        src_content = open(source_file).read()
        results.append(f"\nArquivo fonte existente: {source_file}")
        # Analisar via AST
        ast_info = await _ast_analyze(source_file)
        results.append(f"Estrutura atual:{ast_info[:400]}")
    
    # Rodar testes atuais para ver estado
    results.append("\nFase 2: Executando testes atuais...")
    test_dir = os.path.dirname(test_file)
    test_result = await _shell(f'cd {test_dir or "."} && python -m pytest {test_file} -v --tb=short 2>&1 | tail -20')
    results.append(test_result)
    
    results.append(f"""
=== INSTRUÇÕES TDD ===
Feature: {feature}
Teste: {test_file}
Source: {source_file}

ORDEM DE EXECUÇÃO:
1. Escreva o teste em {test_file} cobrindo a feature
2. Confirme que o teste FALHA (Red)
3. Implemente o mínimo em {source_file} para passar
4. Confirme que o teste PASSA (Green)  
5. Refatore mantendo os testes passando
""")
    

    # Executar automaticamente
    results.append("\n=== EXECUTANDO AUTOMATICAMENTE ===")
    
    # Criar teste se nao existir
    if not os.path.exists(test_file):
        test_template = f"""import pytest\nimport sys\nimport os\nsys.path.insert(0, os.path.dirname(\"{source_file}\"))\n\ndef test_placeholder():\n    # TODO: implementar teste para {feature}\n    assert True\n"""
        await _write_file(test_file, test_template)
        results.append(f"Teste criado: {test_file}")
    
    # Criar source se nao existir
    if not os.path.exists(source_file):
        src_template = f"# {feature}\n# Implementacao pendente\n"
        await _write_file(source_file, src_template)
        results.append(f"Source criado: {source_file}")
    
    # Executar testes
    test_result = await _shell(f"python -m pytest {test_file} -v --tb=short 2>&1")
    results.append(f"Resultado dos testes:\n{test_result}")
    return "\n".join(results)

async def _security_scan(path, **_):
    """Escaneia vulnerabilidades de segurança"""
    import os, re
    results = ["=== SECURITY SCAN ==="]
    issues = []
    
    # Padrões perigosos
    patterns = {
        'SQL Injection': [r'execute\s*\(\s*[^)]*%s', r'SELECT.*\{'],
        'Hardcoded secrets': [r'password\s*=\s*\"[^\"]{4,}', r'secret\s*=\s*\"[^\"]{8,}', r'api_key\s*=\s*\"[^\"]{8,}'],
        'Shell injection': [r'os\.system\s*\(', r'subprocess.*shell=True.*\+', r'eval\s*\('],
        'Path traversal': [r'\.\./.*\.\./', r'open\s*\(.*\+.*\)'],
        'XSS': [r'innerHTML\s*=', r'document\.write\s*\('],
        'Insecure random': [r'random\.random\(\)', r'random\.randint'],
    }
    
    files = []
    if os.path.isfile(path):
        files = [path]
    else:
        for root, dirs, fs in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ['__pycache__','.venv','node_modules','.git']]
            for f in fs:
                if f.endswith(('.py','.js','.ts','.php')):
                    files.append(os.path.join(root, f))
    
    for fpath in files[:30]:
        try:
            content = open(fpath).read()
            for vuln_type, pats in patterns.items():
                for pat in pats:
                    matches = re.findall(pat, content, re.IGNORECASE)
                    if matches:
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if re.search(pat, line, re.IGNORECASE):
                                issues.append(f"  ⚠️  [{vuln_type}] {fpath}:{i} → {line.strip()[:80]}")
        except:
            pass
    
    # Verificar dependências vulneráveis
    req_file = os.path.join(path if os.path.isdir(path) else os.path.dirname(path), 'requirements.txt')
    if os.path.exists(req_file):
        results.append("\nVerificando dependências...")
        pip_audit = await _shell(f'pip-audit -r {req_file} 2>&1 | head -20 || safety check -r {req_file} 2>&1 | head -20 || echo "pip-audit não instalado — instale com: pip install pip-audit"')
        results.append(pip_audit)
    
    if issues:
        results.append(f"\n🔴 {len(issues)} vulnerabilidades encontradas:\n")
        results.extend(issues[:20])
    else:
        results.append("\n✅ Nenhuma vulnerabilidade óbvia encontrada")
    
    results.append("\n=== FIM DO SCAN ===")
    return "\n".join(results)

async def run_agent(user_id, user_message, username=None, progress=None):
    _t_start = time.time()  # métricas
    profile          = await get_or_create_profile(str(user_id), username)
    # Detectar canal CLI para suprimir logs
    is_cli_channel = (str(user_id) == 'cli_user' or username == 'cli')
    # ── ENFORCEMENT DE PLANOS ─────────────────────────────────
    import sqlite3 as _sq3
    _plan = 'pro'
    try:
        _conn = _sq3.connect('/app/data/users.db')
        _row = _conn.execute('SELECT plan FROM users WHERE email=? AND active=1', (str(user_id),)).fetchone()
        if not _row:
            _row = _conn.execute('SELECT plan FROM users WHERE active=1 ORDER BY created_at DESC LIMIT 1').fetchone()
        if _row: _plan = _row[0] or 'pro'
        _conn.close()
    except: pass
    _limits = {
        'free':    {'daily_msgs': 50,  'max_iter': 3,  'tools': False},
        'starter': {'daily_msgs': 500, 'max_iter': 5, 'tools': True},
        'pro':     {'daily_msgs': 9999,'max_iter': 7, 'tools': True},
        'enterprise': {'daily_msgs': 99999,'max_iter': 10, 'tools': True},
    }
    _lim = _limits.get(_plan, _limits['pro'])
    history          = await get_history(str(user_id))
    if len(history) > 10:
        kept = history[:2] + history[-6:]
        dropped = len(history) - len(kept)
        resumo = "sem resumo"
        history = [{"role":"system","content":f"[{dropped} msgs omitidas. Resumo: {resumo}]"}] + kept
        # print(f"[HISTORY] comprimido para {len(history)} msgs")
    provider_name = "deepseek"  # placeholder - substituido em 1447
    model = PROVIDERS["deepseek"].default_model  # placeholder
    treat            = os.getenv('AGENT_TREATMENT', 'usuário')
    name_field       = treat.replace(' ', '_')
    context_summary  = await get_context_summary(str(user_id))

    # ── DETECTOR DE COMPLEXIDADE ─────────────────────────────────
    # Mensagens simples usam prompt compacto — economiza 70% dos tokens
    complex_keywords = ['search_flights', 'voo', 'passagem', 'envie mensagem', 'mande mensagem', 'envia mensagem', 'manda mensagem', 'escreva para', 'diga para', 'avise', 'telegram para', 'whatsapp para', 'email para', 'gmail', 'voar', 'aeroporto', 'companhia aerea', 
        'implemente', 'crie', 'construa', 'desenvolva', 'instale', 'configure',
        'auto-aprimoramento', 'self_improve', 'self improve', 'melhore a si', 'ciclo de', 'aprimoramento', 'execute seu', 'melhore',
        'analise', 'diagnostique', 'verifique todos', 'faça um', '/tarefa',
        'continue', 'retome', 'prossiga', 'termine', 'finalize',
        'browse_web', 'use browse_web', 'fill_form', 'take_screenshot', 'web_search_deep',
        'acesse', 'abra o site', 'abra a página', 'pesquise no site', 'entre no site', 'navegue',
    ]
    simple_keywords = [
        'olá', 'oi', 'tudo bem', 'obrigado', 'ok', 'entendi',
        'qual', 'quando', 'quanto', 'onde', 'quem', 'o que é'
    ]
    # Comandos shell diretos - forçar execução imediata
    shell_commands = [
        'pwd', 'ls', 'whoami', 'date', 'echo', 'cat ', 'grep ', 'find ', 'ps ', 'df ', 'du ',
        'mkdir ', 'rm ', 'cp ', 'mv ', 'chmod ', 'chown ', 'zip ', 'unzip ',
        'docker ', 'git ', 'npm ', 'pip ', 'python ', 'node ', 'curl ', 'wget '
    ]

    msg_lower = user_message.lower()

    # Detectar se é um pedido para enviar mensagem (não é shell)
    # Inclui detecção de "use [plataforma]_send" e outras variações
    is_message_request = any(phrase in msg_lower for phrase in [
        'envie uma mensagem', 'enviar mensagem', 'manda mensagem', 'mandar mensagem',
        'envie para ', 'enviar para ', 'manda para ', 'mandar para ',
        'use telegram_send', 'usar telegram_send', 'telegram_send para',
        'use whatsapp_send', 'usar whatsapp_send', 'whatsapp_send para',
        'use signal_send', 'usar signal_send', 'signal_send para'
    ]) or 'send' in msg_lower and ('message' in msg_lower or 'mensagem' in msg_lower)

    # Detectar se é um comando shell direto (apenas se não for pedido de mensagem)
    # Melhor detecção: verifica se a mensagem COMEÇA com o comando shell ou tem espaço antes
    is_shell_command = False
    if not is_message_request:
        for cmd in shell_commands:
            cmd_clean = cmd.strip()
            # Verifica se a mensagem começa com o comando (com ou sem espaço depois)
            # ou se tem espaço antes do comando (para evitar falsos positivos como "tar" em "para")
            if (msg_lower.startswith(cmd_clean) or
                f' {cmd_clean}' in msg_lower or
                f'\n{cmd_clean}' in msg_lower):
                is_shell_command = True
                break
    # Também detectar comandos entre aspas ou com "execute"
    is_shell_execute = (not is_message_request) and any(phrase in msg_lower for phrase in ['execute "', 'execute o comando', 'rodar comando', 'executar comando'])

    is_complex = (
        any(k in msg_lower for k in complex_keywords) or
        len(user_message) > 100 or
        is_shell_command or  # Comandos shell são complexos (precisam de ferramentas)
        is_shell_execute or  # Execução de comandos também
        False
    )
    is_simple = any(k in msg_lower for k in simple_keywords) and len(user_message) < 60 and not is_shell_command

    # Complexo tem prioridade sobre simples
    # Simples só é compacto se NÃO for complexo
    if is_complex:
        prompt_mode = 'full'
    elif is_simple:
        prompt_mode = 'compact'
    else:
        prompt_mode = 'full'

    # Mensagens com URL sempre exigem tools — forçar DeepSeek
    if 'http://' in user_message or 'https://' in user_message:
        is_complex = True
        prompt_mode = 'full'

    # Comandos shell sempre exigem tools — forçar DeepSeek
    if is_shell_command or is_shell_execute:
        is_complex = True
        prompt_mode = 'full'
        if not is_cli_channel:
            print(f'[SHELL] Comando shell detectado: forçando modo full')

    # Pedidos de envio de mensagem também exigem tools — forçar modo full
    if is_message_request:
        is_complex = True
        prompt_mode = 'full'
        if not is_cli_channel:
            print(f'[MESSAGE] Pedido de envio de mensagem detectado: forçando modo full')

    # Suprimir logs para canal CLI
    if not is_cli_channel:
        print(f'[MODE] simple={is_simple} complex={is_complex} mode={prompt_mode} len={len(user_message)} shell_cmd={is_shell_command}')

    # Forçar modo full para canal CLI
    if is_cli_channel:
        prompt_mode = 'full'
        is_complex = True
        if not is_cli_channel:  # Manter dupla verificação para segurança
            print(f'[CLI] Forçando modo full para canal CLI')

    # ── PERSONA DO USUÁRIO ───────────────────────────────────────
    _persona_prefix = ''
    try:
        import sqlite3 as _sqp
        _pconn = _sqp.connect('/app/data/users.db')
        _pconn.row_factory = _sqp.Row
        _prow = _pconn.execute('SELECT * FROM user_persona WHERE user_id=?', (str(user_id),)).fetchone()
        _pconn.close()
        if _prow:
            _pd = dict(_prow)
            _parts = []
            if _pd.get('nome'):        _parts.append(f"Nome: {_pd['nome']}")
            if _pd.get('profissao'):   _parts.append(f"Profissão: {_pd['profissao']}")
            if _pd.get('cidade'):      _parts.append(f"Cidade: {_pd['cidade']}")
            if _pd.get('familia'):     _parts.append(f"Família: {_pd['familia']}")
            if _pd.get('interesses'):  _parts.append(f"Interesses: {_pd['interesses']}")
            if _pd.get('estilo_comunicacao'): _parts.append(f"Estilo: {_pd['estilo_comunicacao']}")
            if _pd.get('instrucoes_especiais'): _parts.append(f"Instruções especiais: {_pd['instrucoes_especiais']}")
            if _parts:
                _persona_prefix = "VOCÊ ESTÁ FALANDO COM: " + ", ".join(_parts) + "\n\n"
    except Exception:
        pass

    system = get_system(profile, context_summary, mode=prompt_mode, is_shell_command=(is_shell_command or is_shell_execute))
    if _persona_prefix:
        system = _persona_prefix + system

    # Saudações — resposta instantânea, zero API calls
    # Perguntas de identidade sempre usam modo full
    identity_triggers = ['quem você é', 'quem voce e', 'sua essência', 'sua essencia',
                         'sua natureza', 'o que você é', 'fale sobre você', 'se apresente']
    if any(t in msg_lower for t in identity_triggers):
        prompt_mode = 'full'
        system = (_persona_prefix if _persona_prefix else '') + get_system(profile, context_summary, mode='full')

    greetings = ['oi', 'olá', 'ola', 'tudo bem', 'bom dia', 'boa tarde', 'boa noite', 'hey']
    _action_words = ['quero', 'preciso', 'crie', 'implemente', 'faça', 'faca', 'ajude', 'pode', 'consegue']
    if (any(user_message.lower().strip().startswith(g) for g in greetings)
            and len(user_message) < 25
            and not any(w in msg_lower for w in _action_words)):
        treat = os.getenv('AGENT_TREATMENT', 'usuário')
        resp = "Olá! Como posso ajudar?"
        await save_message(str(user_id), 'user', user_message)   # B7: salva mensagem do usuário
        await save_message(str(user_id), 'assistant', resp)
        return resp

    # Histórico adaptativo — simples usa 10 msgs, complexo usa 20
    history_limit = 10 if is_simple else 20

    # B2: preserva mensagem original — apenas ela é salva no banco
    original_user_message = user_message

    # ── PRÉ-PROCESSAMENTO: contexto comprimido antes de chamar a API ──
    retomada_keywords = ['continue', 'retome', 'prossiga', 'siga', 'termine', 'finalize', 'o que falta', 'continue o curso', 'proximo topico', 'próximo tópico']
    msg_lower = user_message.lower()
    is_retomada = any(k in msg_lower for k in retomada_keywords)

    user_message_for_api = user_message  # acumula injeções — nunca salvo no banco

    if is_retomada:
        task_ctx = await _task_status(str(user_id))
        if "Nenhuma tarefa" not in task_ctx:
            user_message_for_api = (
                f"{user_message_for_api}\n\n"
                f"[ESTADO DA TAREFA — LEIA ANTES DE AGIR]:\n{task_ctx}\n\n"
                f"INSTRUÇÃO CRÍTICA: Você JÁ explorou a estrutura. Não repita inspeções já feitas. "
                f"Vá DIRETO ao próximo passo indicado acima. Primeiro comando = execução, não exploração."
            )

    # Comprime memórias relevantes — injetadas apenas no contexto da API
    mem_ctx = await recall(str(user_id), original_user_message[:50])
    if "Nenhuma memoria" not in mem_ctx:
        user_message_for_api = f"{user_message_for_api}\n\n[MEMÓRIAS RELEVANTES]:\n{mem_ctx}"

    await save_message(str(user_id), 'user', original_user_message)  # B2: salva original limpo
    if progress is not None:
        progress['text'] = '⚙️ Analisando...'

    # cliente criado pelo rate manager abaixo

    # Busca rápida — injeta resultado apenas no contexto da API
    quick_search_patterns = [
        'cotação', 'cotacao', 'preço', 'preco', 'valor', 'quanto custa',
        'clima', 'tempo em', 'temperatura', 'notícia', 'noticia', 'news',
        'dólar', 'dolar', 'euro', 'bitcoin', 'btc', 'eth',
        'resultado', 'placar', 'jogo', 'quem ganhou',
        'quando é', 'quando foi', 'o que é', 'o que foi',
        'quem é', 'quem foi', 'onde fica', 'como funciona'
    ]
    is_quick = (
        len(original_user_message) < 120 and  # B2: usa tamanho original
        any(p in msg_lower for p in quick_search_patterns)
    )

    if is_quick:
        try:
            search_result = await _search(original_user_message)
            if search_result and 'Erro' not in search_result:
                user_message_for_api = (
                    f"{user_message_for_api}\n\n"
                    f"[RESULTADO DA BUSCA - use isto para responder diretamente]:\n"
                    f"{search_result[:800]}"
                )
        except Exception:
            pass

    user_msg = {'role': 'user', 'content': user_message_for_api, 'name': name_field}
    messages = [{'role': 'system', 'content': system}] + history[-history_limit:] + [user_msg]

    # Ferramentas com user_id injetado
    async def _remember_fn(key, value, category='geral'):
        return await remember(str(user_id), key, value, category)
    async def _recall_fn(query):
        return await recall(str(user_id), query)
    async def _recall_all_fn():
        return await recall_all(str(user_id))

    tool_fn = {
        'self_analyze':  lambda **kw: analyze_performance(str(user_id)),
        'self_diagnose': lambda **kw: diagnose(str(user_id)),
        'self_patch':   self_patch,
        'task_update': lambda **kw: _task_update(**kw, user_id=str(user_id)),
        'task_status':  lambda **kw: _task_status(user_id=str(user_id)),
        'analyze':    _analyze,
        'remember':   _remember_fn,
        'recall':     _recall_fn,
        'recall_all': _recall_all_fn,
        'status':     _status,
        'search_web': _search,
        'telegram_send': _telegram_send,
        'run_shell':  _shell,
        'read_file':  _read_file,
        'write_file': _write_file,
        'ast_analyze':      lambda **kw: _ast_analyze(**kw),
        'localize_bug':     lambda **kw: _localize_bug(**kw),
        'tdd_cycle':        lambda **kw: _tdd_cycle(**kw),
        'security_scan':    lambda **kw: _security_scan(**kw),
        'run_tests':
          lambda **kw: _run_tests(**kw),
        'lint_code':          lambda **kw: _lint_code(**kw),
        'apply_diff':         lambda **kw: _apply_diff(**kw),
        'analyze_codebase':   lambda **kw: _analyze_codebase(**kw),
        'edit_file':
          _edit_file,
        'github':     _github,
        'agent':      _agent_tool,
        'self_stats': lambda period=24, **kw: get_stats_report(int(period)),
        'ask_user':   _ask_user,
        'notify':     _notify,
        'wordpress_post':      lambda **kw: _wordpress_post(**kw, _user_id=str(user_id)),
        'wordpress_get_posts': lambda **kw: _wordpress_get_posts(**kw, _user_id=str(user_id)),
        'clickup_create_task': lambda **kw: _clickup_create_task(**kw, _user_id=str(user_id)),
        'clickup_get_tasks':   lambda **kw: _clickup_get_tasks(**kw, _user_id=str(user_id)),
        'tts': _tts,
        'stt': _stt,
        'browse_web':        lambda **kw: _browser_browse(**kw),
        'fill_form':         lambda **kw: _browser_fill(**kw),
        'take_screenshot':   lambda **kw: _browser_screenshot(**kw),
        'web_search_deep':   lambda **kw: _browser_search(**kw),
        'platform_login':    lambda **kw: _browser_login(**kw),
        'browse_as_user':    lambda **kw: _browser_auth(**kw),
        'check_login_status':lambda **kw: _browser_check(**kw),
        'search_flights':    _search_flights,
    }

    # Limite dinamico inteligente baseado no contexto real
    has_code  = any(k in msg_lower for k in ['implemente', 'crie', 'construa', 'desenvolva'])
    has_infra = any(k in msg_lower for k in ['instale', 'configure', 'docker', 'nginx', 'servidor'])
    has_research = any(k in msg_lower for k in ['analise', 'pesquise', 'compare', 'debate', 'aprenda'])
    has_git   = any(k in msg_lower for k in ['git', 'github', 'commit', 'push'])
    has_self  = any(k in msg_lower for k in ['self_improve', 'self improve', 'auto-aprimoramento', 'aprimoramento'])
    has_curso = any(k in msg_lower for k in ['curso', 'estude', 'aprenda tudo', 'topicos', 'sequencia'])
    is_question = (not is_complex and len(user_message) < 80 and
                   any(k in msg_lower for k in ['o que', 'qual', 'como', 'quando', 'onde', 'quem', 'explique']))
    if is_question:
        max_iter = 8
    elif is_simple:
        max_iter = 8
    elif has_self:
        max_iter = 30
    elif has_curso:
        max_iter = 25
    elif has_code and has_infra:
        max_iter = 25
    elif has_code:
        max_iter = 20
    elif has_infra:
        max_iter = 20
    elif has_git:
        max_iter = 15
    elif has_research:
        max_iter = 20
    elif is_shell_command or is_shell_execute:
        # Comandos shell: máximo 1-2 iterações para ser direto
        # Comandos muito simples (pwd, whoami, date, echo): 1 iteração
        # Verificar se é exatamente o comando (ou começa com ele)
        import re
        simple_shell_patterns = [
            r'^pwd$', r'^whoami$', r'^date$', r'^echo\s+',
            r'^ls$', r'^ls\s+-', r'^ls\s+[a-zA-Z]'
        ]

        is_simple_shell = False
        for pattern in simple_shell_patterns:
            if re.search(pattern, msg_lower.strip()):
                is_simple_shell = True
                break

        if is_simple_shell:
            max_iter = 1
            if not is_cli_channel:
                print(f'[SHELL] Comando shell SIMPLES: limite de 1 iteração')
        else:
            max_iter = 15
            if not is_cli_channel:
                print(f'[SHELL] Comando shell: limite de {max_iter} iterações')
    elif is_complex:
        max_iter = 20
    else:
        max_iter = 15

    # ── ROTEAMENTO INTELIGENTE ─────────────────────────────────
    import time as _time
    # Forçar uso de ferramentas para canal CLI (user_id='cli_user' ou username='cli')
    # is_cli_channel já definido no início da função
    # Comandos shell sempre precisam de ferramentas
    tools_needed = is_complex or is_cli_channel or is_shell_command or is_shell_execute

    # Roteamento inteligente APÓS calcular complexidade
    _has_groq=bool(os.environ.get('GROQ_API_KEY'))
    _has_gemini=bool(os.environ.get('GEMINI_API_KEY'))
    _has_deepseek=bool(os.environ.get('DEEPSEEK_API_KEY'))
    _has_cerebras=bool(os.environ.get('CEREBRAS_API_KEY'))
    if profile.provider:
        provider_name=profile.provider
    else:
        _ctx_size = sum(len(str(m.get('content',''))) for m in messages) + len(system)

        # ROTEAMENTO INTELIGENTE POR TIPO DE TAREFA
        # Baseado em pesquisa: rotear por tarefa reduz custo em 75-85%

        if _ctx_size > 10000:
            # Contexto grande → Gemini (1M tokens, gratuito)
            provider_name='gemini' if _has_gemini else 'deepseek'
            _route_reason = f'contexto grande ({_ctx_size} chars)'

        elif tools_needed or is_complex:
            # Tarefas com ferramentas/complexas → Gemini (melhor em tool use)
            # ou Cerebras Qwen 235B para raciocínio puro
            if is_shell_command or is_shell_execute:
                provider_name='gemini' if _has_gemini else ('cerebras' if _has_cerebras else 'deepseek')
                _route_reason = 'shell/tools → Gemini'
            else:
                provider_name='cerebras' if _has_cerebras else ('gemini' if _has_gemini else 'deepseek')
                _route_reason = 'complexo → Cerebras Qwen'

        elif is_simple or len(user_message) < 50:
            # Cerebras tem limite 8K tokens — só usar se contexto couber
            # Cerebras é rápido mas tem limite 8K — sempre usar com ctx truncado
            if _has_cerebras:
                provider_name = 'cerebras'
                _route_reason = 'simples/curto → Cerebras fast'
            elif _has_groq:
                provider_name = 'groq'
                _route_reason = 'simples/curto → Groq'
            else:
                provider_name = 'gemini'
                _route_reason = 'simples/curto → Gemini'
        else:
            # Default → Groq (rápido e gratuito para contexto médio)
            provider_name='groq' if _has_groq else ('cerebras' if _has_cerebras else 'gemini')
            _route_reason = 'médio → Groq'

        # print(f'[SMART-ROUTING] {_route_reason} | ctx={_ctx_size} | complex={is_complex} | tools={tools_needed} → {provider_name}')
    model=profile.model if profile.provider else PROVIDERS.get(provider_name,PROVIDERS['deepseek']).default_model
    # print(f'[ROUTING] complex={is_complex} tools={tools_needed} -> {provider_name}')

    # Criar cliente com RateManager - rotacao inteligente
    available = [p for p in ['cerebras','groq','gemini','deepseek'] 
                 if PROVIDERS.get(p) and PROVIDERS[p].api_key]
    
    # Forcar provider do perfil se configurado
    if profile.provider and profile.provider in available:
        provider_name = profile.provider
    else:
        # Escolher melhor provider disponivel (gratuitos primeiro)
        best = _rm.best(available)
        if best:
            provider_name = best
        # Se todos em cooldown, aguardar ate 30s
        elif not _rm.can_use(provider_name):
            import asyncio
            best = await asyncio.wait_for(
                _rm.wait_best(available, timeout=30),
                timeout=35
            ) or provider_name
            provider_name = best
    
    model = profile.model if profile.provider else PROVIDERS.get(provider_name, PROVIDERS['deepseek']).default_model
    # print(f'[RATE] Usando {provider_name} | Status: {_rm.status().get(provider_name,{})}')
    # Cerebras tem limite 8K tokens — truncar histórico se necessário
    if provider_name == 'cerebras' and len(messages) > 4:
        messages = messages[:1] + messages[-3:]  # system + últimas 3 msgs
        print(f'[CEREBRAS] Histórico truncado para {len(messages)} msgs (limite 8K)')
    
    client = None
    try:
        client = get_client(provider_name)
        _rm.record_request(provider_name)
    except Exception as e:
        # print(f'[RATE] Erro ao criar cliente {provider_name}: {e}')
        raise Exception(f'Nenhum provider disponivel: {e}')
    if is_shell_command or is_shell_execute:
        if not is_cli_channel:
            print(f'[SHELL] Forçando uso de ferramentas para comando shell')

    tools_used = []

    _tg_keywords = ['envie mensagem', 'mande mensagem', 'envia mensagem', 'manda mensagem', 'escreva para', 'diga para', 'avise', 'comunique', 'notifique', 'telegram para']
    _force_tg = any(k in msg_lower for k in _tg_keywords) and tools_needed

    _413_providers = set()  # providers com 413 nesta sessão
    # Semantic cache (Fase 5)
    _sem_cached = semantic_cache.get(str(user_id), original_user_message)
    if _sem_cached:
        await save_message(str(user_id), 'assistant', _sem_cached)
        return _sem_cached
    for i in range(max_iter):
        _tool_choice = {'type':'function','function':{'name':'telegram_send'}} if (_force_tg and i == 0) else 'auto'
        # Cerebras não suporta tools grandes — para mensagens simples, sem tools
        # C2: Tool grouping por intenção — não envia 60+ schemas de uma vez
        if not tools_needed:
            _tools_para_chamada = None
        elif provider_name == 'cerebras':
            # Cerebras: só essenciais
            _CEREBRAS_NAMES = {'run_shell','write_file','read_file','edit_file',
                               'remember','task_update','run_tests','search_web'}
            _tools_para_chamada = [t for t in TOOLS if t.get('function',{}).get('name') in _CEREBRAS_NAMES]
        elif any(k in msg_lower for k in ['test','pytest','unittest','coverage','assert']):
            _TEST_NAMES = {'run_tests','run_shell','read_file','edit_file','write_file','remember'}
            _tools_para_chamada = [t for t in TOOLS if t.get('function',{}).get('name') in _TEST_NAMES]
        elif any(k in msg_lower for k in ['git','commit','push','pull','branch','merge','pr','github']):
            _GIT_NAMES = {'run_shell','read_file','edit_file','write_file','github','remember','task_update'}
            _tools_para_chamada = [t for t in TOOLS if t.get('function',{}).get('name') in _GIT_NAMES]
        elif any(k in msg_lower for k in ['busca','pesquisa','search','web','internet','notícia']):
            _WEB_NAMES = {'search_web','run_shell','remember','telegram_send'}
            _tools_para_chamada = [t for t in TOOLS if t.get('function',{}).get('name') in _WEB_NAMES]
        else:
            # Default: coding tools essenciais
            _CODE_NAMES = {'run_shell','write_file','read_file','edit_file','run_tests',
                           'remember','task_update','agent','search_web','github'}
            _tools_para_chamada = [t for t in TOOLS if t.get('function',{}).get('name') in _CODE_NAMES]
        # Schema minification (Fase 5)
        if _tools_para_chamada:
            _tools_para_chamada = minify_tool_schemas(_tools_para_chamada, get_schema_mode(is_simple, is_complex))
        _tool_choice_para_chamada = _tool_choice if _tools_para_chamada else 'none'
        # ── RETRY COM TROCA DE PROVIDER ──────────────────────────
        resp = None
        # Smart routing: começar pelo provider escolhido, depois fallback pela prioridade
        _smart_first = [provider_name] if provider_name in available and provider_name not in _413_providers else []
        _rest = [p for p in _rm.PRIORITY if p in available and p not in _413_providers and p != provider_name]
        _retry_providers = _smart_first + _rest
        if not _retry_providers:
            _413_providers.clear()
            _retry_providers = [p for p in _rm.PRIORITY if p in available]
        for _attempt_provider in _retry_providers:
            if not _rm.can_use(_attempt_provider):
                continue
            try:
                if _attempt_provider != provider_name:
                    provider_name = _attempt_provider
                    model = profile.model if profile.provider else PROVIDERS.get(provider_name, PROVIDERS['deepseek']).default_model
                    client = get_client(provider_name)
                    print(f'[RETRY] Trocando para {provider_name}')
                _rm.record_request(_attempt_provider)
                _model_attempt = model
                # Se Groq com contexto grande, usar modelo menor
                if _attempt_provider == 'groq':
                    _model_attempt = 'llama-3.1-8b-instant'
                # Para Cerebras sem tools, não enviar parâmetros de tools
                if _tools_para_chamada:
                    resp = await client.chat.completions.create(
                        model=_model_attempt,
                        messages=messages,
                        tools=_tools_para_chamada,
                        tool_choice=_tool_choice_para_chamada,
                        max_tokens=1024 if _attempt_provider == 'cerebras' else 4096,
                        temperature=0.0 if is_complex else 0.7)  # C1: temp=0 para código (DeepSeek)
                else:
                    resp = await client.chat.completions.create(
                        model=_model_attempt,
                        messages=messages,
                        max_tokens=1024,
                        temperature=0.0 if is_complex else 0.7)  # C1
                _rm.record_success(_attempt_provider)
                break
            except Exception as _api_err:
                _err_str = str(_api_err)
                # print(f'[RATE] Erro com {_attempt_provider}: {_err_str[:120]}')
                # 413 = mensagem muito grande, nao e rate limit — nao colocar em cooldown
                if '413' in _err_str:
                    # print(f'[RATE] {_attempt_provider} 413 (contexto grande) — pulando para sempre nesta tarefa')
                    _413_providers.add(_attempt_provider)
                elif '402' in _err_str or 'Insufficient Balance' in _err_str:
                    # print(f'[RATE] {_attempt_provider} sem saldo (402) — cooldown 5min, voltando aos gratuitos')
                    _rm._cooldowns[_attempt_provider] = __import__('time').time() + 300
                    _413_providers.add(_attempt_provider)
                else:
                    _rm.record_error(_attempt_provider, _err_str)
                if _attempt_provider == _retry_providers[-1]:
                    raise Exception(f'Todos os providers falharam. Ultimo erro: {_err_str[:200]}')
                continue
        if resp is None:
            raise Exception('Nenhum provider disponivel para responder.')

        choice     = resp.choices[0]
        # Tratar MALFORMED_FUNCTION_CALL como stop
        if choice.finish_reason == 'MALFORMED_FUNCTION_CALL' or choice.finish_reason == 'function_call_filter':
            print(f'[iter {i}] MALFORMED tool call — tratando como stop')
            choice.finish_reason = 'stop'
            choice.message.tool_calls = None
        tool_names = [tc.function.name for tc in (choice.message.tool_calls or [])]
        if not is_cli_channel:
            print(f'[iter {i}] finish={choice.finish_reason} tools={tool_names}')

        # ── GATILHO DE CONSOLIDAÇÃO ─────────────────────────────────
        # Na penúltima iteração, força o agente a consolidar e salvar
        if i == max_iter - 2 and choice.finish_reason == 'tool_calls':
            consolidation_msg = {
                'role': 'user',
                'content': (
                    "ATENÇÃO: Você está na penúltima iteração disponível.\n"
                    "OBRIGATÓRIO antes de responder:\n"
                    "1. Use remember() para salvar TUDO que foi construído/descoberto:\n"
                    "   - Arquivos criados (com paths completos)\n"
                    "   - Serviços rodando (URLs, portas)\n"
                    "   - Comandos para iniciar/parar\n"
                    "   - Estado atual do projeto\n"
                    "2. Use task_update(status='concluido') com lista completa do que foi feito\n"
                    "3. Depois responda com relatório final completo\n"
                    "NÃO use mais run_shell — apenas remember, task_update e sua resposta final."
                ),
                'name': name_field
            }
            messages.append(consolidation_msg)

        if choice.finish_reason == 'tool_calls' and choice.message.tool_calls:
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                fn   = tool_fn.get(tc.function.name)
                if not is_cli_channel:
                    print(f'  → {tc.function.name}({json.dumps(args, ensure_ascii=False)[:150]})')
                # Notificar CLI sobre tool call
                if os.environ.get('_tool_callback'):
                    import json as _json
                    _info = _json.dumps({'tool': tc.function.name, 'args': args})
                    print(f'__TOOL_START__{_info}__TOOL_END__', flush=True)
                
                # CLI callback: notify tool start
                if progress is not None and callable(progress.get('on_tool_start')):
                    try:
                        progress['on_tool_start'](tc.function.name, args)
                    except Exception:
                        pass
                elif os.environ.get('_CLI_MODE'):
                    print(f"\n● {tc.function.name}({str(args)[:100]})", flush=True)
                result = await fn(**args) if fn else (handle_google_tool(tc.function.name, args) if tc.function.name in GOOGLE_TOOL_NAMES else (handle_whatsapp_tool(tc.function.name, args) if tc.function.name in WHATSAPP_TOOL_NAMES else (handle_signal_tool(tc.function.name, args) if tc.function.name in SIGNAL_TOOL_NAMES else (await handle_telegram_tool(tc.function.name, args) if tc.function.name in TELEGRAM_TOOL_NAMES else f'Ferramenta desconhecida: {tc.function.name}'))))
                # CLI callback: notify tool result
                if progress is not None and callable(progress.get('on_tool_result')):
                    try:
                        progress['on_tool_result'](result)
                    except Exception:
                        pass
                elif not is_cli_channel:
                    print(f'  ← {str(result)[:300]}')
                if progress is not None:
                    progress['text'] = f"⚙️ Executando {tc.function.name}...\n{str(result)[:120]}"
                tools_used.append(tc.function.name)
                messages.append({'role': 'tool', 'tool_call_id': tc.id, 'content': str(result)})
            continue

        final = choice.message.content or '...'
        if progress is not None:
            progress['text'] = final

        # ── AUTOCRÍTICA ──────────────────────────────────────────
        if is_complex and len(final) < 100 and i > 2:
            messages.append({'role': 'assistant', 'content': final})
            messages.append({
                'role': 'user',
                'content': 'Resposta muito breve. Complemente: o que foi feito, estado atual, próximo passo.',
                'name': name_field
            })
            resp2 = await client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=1024, temperature=0.5)
            final = resp2.choices[0].message.content or final

        # Garante tratamento em toda resposta
        # tratamento pessoal removido 

        # ── APRENDIZADO AUTOMÁTICO ─────────────────────────────────────
        # Extrai conhecimento das ferramentas usadas e salva em memória
        relevant = {'run_shell','write_file','edit_file','github','remember','search_web','agent'}
        if any(t in relevant for t in tools_used):
            ts = datetime.now().strftime('%d/%m %H:%M')
            entry = f"[{ts}] {user_message[:120]} → {', '.join(dict.fromkeys(tools_used))}"
            old_ctx = context_summary or ''
            await update_context_summary(str(user_id), (old_ctx + '\n' + entry).strip()[-3000:])

        # Extrai memórias automáticas das mensagens de ferramentas
        if 'run_shell' in tools_used or 'write_file' in tools_used:
            await _auto_extract_memories(str(user_id), messages, user_message)

        await save_message(str(user_id), 'assistant', final)
        # Registra para auto-aprimoramento
        await log_interaction(str(user_id), user_message[:200], final,
                             list(dict.fromkeys(tools_used)), i, True)
        return final

    await log_interaction(str(user_id), user_message[:200], 'LIMITE_ATINGIDO',
                         list(dict.fromkeys(tools_used)), max_iter, False)

    # ── CONTINUAÇÃO AUTOMÁTICA NOS BASTIDORES ─────────────────
    # Salva estado atual e continua sem interromper o usuário
    import asyncio as _asyncio

    # Resumo do que foi feito até agora
    tools_summary = ", ".join(dict.fromkeys(tools_used)) if tools_used else "nenhuma"
    estado = (
        f"CONTINUAÇÃO AUTOMÁTICA — etapa anterior usou {max_iter} operações. "
        f"Ferramentas usadas: {tools_summary}. "
        f"Continue EXATAMENTE de onde parou, sem repetir o que já foi feito. "
        f"Objetivo original: {original_user_message[:300]}"
    )

    async def _continuar_nos_bastidores():
        try:
            print(f"[AUTO] Continuando tarefa nos bastidores para user {user_id}")
            await run_agent(user_id, estado, username=username)
            print(f"[AUTO] Continuação concluída para user {user_id}")
        except Exception as _e:
            print(f"[AUTO] Erro na continuação: {_e}")

    _asyncio.create_task(_continuar_nos_bastidores())

    # Avisa o usuário que está continuando (sem pedir permissão)
    aviso = f"⚙️ Atingi {max_iter} operações nesta etapa — continuando automaticamente nos bastidores..."
    await save_message(str(user_id), 'assistant', aviso)
    return aviso


# ── WhatsApp Tools ─────────────────────────────────────────────────────────────
try:
    from whatsapp_integration import send_message as _wa_send, get_status as _wa_status, get_chats as _wa_chats

    WHATSAPP_TOOLS = [
        {"name": "whatsapp_send", "description": "Envia mensagem WhatsApp para um número", "input_schema": {"type": "object", "properties": {"to": {"type": "string", "description": "Número com DDI, ex: 5511999999999"}, "message": {"type": "string", "description": "Texto a enviar"}}, "required": ["to", "message"]}},
        {"name": "whatsapp_chats", "description": "Lista conversas recentes do WhatsApp", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}},
        {"name": "whatsapp_status", "description": "Verifica se o WhatsApp está conectado", "input_schema": {"type": "object", "properties": {}}},
    ]

    def handle_whatsapp_tool(name, args):
        if not _wa_status().get('connected'):
            return "WhatsApp não conectado. Acesse o painel de integrações para conectar."
        if name == "whatsapp_send":
            r = _wa_send(args.get('to',''), args.get('message',''))
            return f"Mensagem enviada para {args.get('to')}" if r.get('success') else f"Erro: {r.get('error')}"
        if name == "whatsapp_chats":
            chats = _wa_chats(args.get('limit', 10))
            if not chats: return "Nenhuma conversa encontrada."
            return "\n".join([f"- {c.get('name','?')} ({c.get('id','').replace('@s.whatsapp.net','')})" for c in chats])
        if name == "whatsapp_status":
            s = _wa_status()
            return f"WhatsApp {'conectado' if s.get('connected') else 'desconectado'} — estado: {s.get('state')}"
        return f"Ferramenta desconhecida: {name}"

    WHATSAPP_TOOL_NAMES = {t['name'] for t in WHATSAPP_TOOLS}
    TOOLS.extend(_normalize_tools(WHATSAPP_TOOLS))
except Exception as _e:
    WHATSAPP_TOOL_NAMES = set()
    def handle_whatsapp_tool(name, args): return "WhatsApp não disponível."


# ── Signal Tools ───────────────────────────────────────────────────────────────
try:
    from signal_integration import send_message as _sig_send, get_status as _sig_status, get_messages as _sig_msgs

    SIGNAL_TOOLS = [
        {"name": "signal_send", "description": "Envia mensagem Signal para um número", "input_schema": {"type": "object", "properties": {"to": {"type": "string", "description": "Número com DDI, ex: +5511999999999"}, "message": {"type": "string", "description": "Texto a enviar"}}, "required": ["to", "message"]}},
        {"name": "signal_messages", "description": "Recebe mensagens Signal pendentes", "input_schema": {"type": "object", "properties": {}}},
        {"name": "signal_status", "description": "Verifica se o Signal está conectado", "input_schema": {"type": "object", "properties": {}}},
    ]

    def handle_signal_tool(name, args):
        if name == "signal_status":
            s = _sig_status()
            return f"Signal {'conectado' if s.get('connected') else 'desconectado'} — número: {s.get('number','não configurado')}"
        if not _sig_status().get('connected'):
            return "Signal não conectado. Acesse o painel de integrações para registrar seu número."
        if name == "signal_send":
            r = _sig_send(args.get('to',''), args.get('message',''))
            return f"Mensagem Signal enviada para {args.get('to')}" if r.get('success') else f"Erro: {r.get('error')}"
        if name == "signal_messages":
            msgs = _sig_msgs()
            if not msgs: return "Nenhuma mensagem Signal pendente."
            return "\n".join([f"De {m.get('envelope',{}).get('source','?')}: {m.get('envelope',{}).get('dataMessage',{}).get('message','')}" for m in msgs[:10]])
        return f"Ferramenta desconhecida: {name}"

    SIGNAL_TOOL_NAMES = {t['name'] for t in SIGNAL_TOOLS}
    TOOLS.extend(_normalize_tools(SIGNAL_TOOLS))
except Exception:
    SIGNAL_TOOL_NAMES = set()
    def handle_signal_tool(name, args): return "Signal não disponível."


# ── Telegram Tools ───────────────────────────────────────────────────────────────
try:
    from telegram_userbot_enhanced import (
        send_message_to_contact as _tg_send,
        get_contact_info as _tg_info,
        list_contacts as _tg_list,
        update_config as _tg_update_config,
        get_status as _tg_status
    )

    # Flag para saber se userbot está disponível
    _userbot_available = True

except Exception as e:
    print(f"[TELEGRAM] Userbot não disponível: {e}")
    _userbot_available = False

    # Funções dummy para userbot não disponível
    async def _tg_send(*args, **kwargs):
        return {"success": False, "error": "Userbot do Telegram não disponível. Configure o userbot ou use username com @ para enviar via bot."}

    async def _tg_info(*args, **kwargs):
        return None

    async def _tg_list(*args, **kwargs):
        return []

    async def _tg_update_config(*args, **kwargs):
        return {"success": False, "error": "Userbot não disponível"}

    async def _tg_status(*args, **kwargs):
        return {"connected": False, "error": "Userbot não disponível"}

# Definição das ferramentas Telegram (fora do bloco try/except)
TELEGRAM_TOOLS = [
    {"name": "telegram_send", "description": "Envia mensagem Telegram para um contato (por username ou nome)", "input_schema": {"type": "object", "properties": {"username_ou_nome": {"type": "string", "description": "Username (com @) ou nome do contato"}, "mensagem": {"type": "string", "description": "Texto a enviar"}}, "required": ["username_ou_nome", "mensagem"]}},
    {"name": "telegram_contact_info", "description": "Obtém informações de um contato do Telegram", "input_schema": {"type": "object", "properties": {"contato": {"type": "string", "description": "Username, ID ou nome do contato"}}, "required": ["contato"]}},
    {"name": "telegram_list_contacts", "description": "Lista contatos do Telegram", "input_schema": {"type": "object", "properties": {"limite": {"type": "integer", "description": "Número máximo de contatos a listar", "default": 20}}, "required": []}},
    {"name": "telegram_userbot_status", "description": "Verifica status do userbot do Telegram", "input_schema": {"type": "object", "properties": {}}},
    {"name": "telegram_update_config", "description": "Atualiza configuração do userbot", "input_schema": {"type": "object", "properties": {"config_json": {"type": "string", "description": "Configuração em formato JSON"}}, "required": ["config_json"]}},
]

async def handle_telegram_tool(name, args):
    if name == "telegram_send":
        username = args.get('username_ou_nome', '')
        message = args.get('mensagem', '')

        # Primeiro tenta com userbot
        result = await _tg_send(username, message)

        # Se userbot falhou mas temos username com @, tenta com bot
        if not result.get('success') and username.startswith('@'):
            # Importa função do bot se necessário
            try:
                from telegram_bot_send import send_message_to_contact_bot
                bot_result = await send_message_to_contact_bot(username, message)
                if bot_result.get('success'):
                    return f"Mensagem Telegram enviada via BOT para {username}"
                else:
                    return f"Erro ao enviar mensagem Telegram (userbot e bot falharam): {bot_result.get('error', 'erro desconhecido')}"
            except ImportError:
                pass  # Módulo do bot não disponível

        # Retorna resultado do userbot (sucesso ou erro)
        if result.get('success'):
            return f"Mensagem Telegram enviada para {result.get('to', 'contato')} (@{result.get('username', '?')})"
        else:
            return f"Erro ao enviar mensagem Telegram: {result.get('error', 'erro desconhecido')}"

    elif name == "telegram_contact_info":
        info = await _tg_info(args.get('contato', ''))
        if info:
            return f"Informações do contato:\n" \
                   f"• Nome: {info.get('first_name', '')} {info.get('last_name', '')}\n" \
                   f"• Username: @{info.get('username', 'N/A')}\n" \
                   f"• ID: {info.get('id', 'N/A')}\n" \
                   f"• Telefone: {info.get('phone', 'N/A')}\n" \
                   f"• Bot: {'Sim' if info.get('bot') else 'Não'}"
        else:
            return "Contato não encontrado ou erro ao obter informações."

    elif name == "telegram_list_contacts":
        limit = args.get('limite', 20)
        contacts = await _tg_list(limit)
        if not contacts:
            return "Nenhum contato encontrado ou erro ao listar."

        result_lines = [f"Contatos do Telegram (mostrando {len(contacts)}):"]
        for i, contact in enumerate(contacts, 1):
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            username = f"@{contact.get('username', '')}" if contact.get('username') else "N/A"
            result_lines.append(f"{i}. {name} {username}")

        return "\n".join(result_lines)

    elif name == "telegram_userbot_status":
        status = await _tg_status()
        return f"Status do Userbot Telegram:\n" \
               f"• Conectado: {'Sim' if status.get('connected') else 'Não'}\n" \
               f"• Horário ativo: {'Sim' if status.get('active_hours') else 'Não'}\n" \
               f"• Usuários em cooldown: {status.get('cooldown_users', 0)}"

    elif name == "telegram_update_config":
        try:
            import json
            config_data = json.loads(args.get('config_json', '{}'))
            updated = await _tg_update_config(config_data)
            return f"Configuração do userbot atualizada com sucesso."
        except Exception as e:
            return f"Erro ao atualizar configuração: {str(e)}"

    return f"Ferramenta desconhecida: {name}"

TELEGRAM_TOOL_NAMES = {t['name'] for t in TELEGRAM_TOOLS}
TOOLS.extend(_normalize_tools(TELEGRAM_TOOLS))
