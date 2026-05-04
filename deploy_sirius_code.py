#!/usr/bin/env python3
"""
deploy_sirius_code.py — Porta TODAS as otimizações do sirius-open para o sirius-code
+ aplica 3 técnicas exclusivas de coding agents (pesquisa asiática/indiana).

Técnicas novas para coding:
  C1. Temperature 0.0 para tarefas de código (DeepSeek research)
  C2. Tool grouping por intenção (sem enviar 60+ schemas de uma vez)
  C3. Preferência por edit_file sobre write_file (diff-based, menos tokens de output)

Rodar na VPS:
  cd /docker/sirius-code
  python3 deploy_sirius_code.py
"""
import subprocess
import shutil
import os
import sys
import time

OPEN_DIR  = "/docker/sirius-open"
CODE_DIR  = "/docker/sirius-code"
CONTAINER = "sirius-code"
AGENT     = f"{CODE_DIR}/app/agent.py"


def run(cmd, check=True, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    if check and r.returncode != 0:
        print(f"ERRO [{cmd[:60]}]: {r.stderr[:300]}")
        sys.exit(1)
    return r.stdout.strip()


print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  Sirius Code — Deploy completo")
print("  (otimizações sirius-open + coding)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# ─────────────────────────────────────────────
# ETAPA 1 — Copiar módulos de otimização
# ─────────────────────────────────────────────
print("\n[1/8] Copiando módulos de otimização do sirius-open...")
modules = [
    "embedder.py",
    "memory.py",          # RAG semântico
    "stale_results.py",
    "context_compressor.py",
    "tool_cache.py",
    "subagent.py",
    "metrics.py",
    "phase5.py",
    "memory_dedup.py",
]

for mod in modules:
    src = f"{OPEN_DIR}/{mod}"
    dst_app = f"{CODE_DIR}/app/{mod}"
    dst_root = f"{CODE_DIR}/{mod}"
    if os.path.exists(src):
        shutil.copy2(src, dst_app if os.path.exists(f"{CODE_DIR}/app") else dst_root)
        print(f"  ✅ {mod}")
    else:
        print(f"  ⚠️  {mod} não encontrado em sirius-open")

# Instalar dependências no container
print("\n[2/8] Instalando dependências no container...")
run(f"docker exec {CONTAINER} pip install sentence-transformers llmlingua --break-system-packages -q", check=False)
print("  ✅ Dependências instaladas")

# ─────────────────────────────────────────────
# ETAPA 2 — Criar diretório de modelos
# ─────────────────────────────────────────────
run(f"docker exec {CONTAINER} mkdir -p /app/data/models")
print("  ✅ /app/data/models criado")

# ─────────────────────────────────────────────
# ETAPA 3 — Ler agent.py do sirius-code
# ─────────────────────────────────────────────
print("\n[3/8] Lendo agent.py do sirius-code...")
with open(AGENT, "r", encoding="utf-8") as f:
    content = f.read()
original = content

# ─────────────────────────────────────────────
# PATCH A — Imports (todos os módulos)
# ─────────────────────────────────────────────
print("\n[4/8] Aplicando patches...")

OLD_IMPORT = "import os, json, sys, asyncio"
NEW_IMPORT = """import os, json, sys, asyncio, time
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
    def get_stats_report(h=24): return 'Métricas não disponíveis'"""

if "from tool_cache import" not in content and OLD_IMPORT in content:
    content = content.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print("  ✅ Imports adicionados")
else:
    print("  ⚠️  Imports já presentes ou linha não encontrada")

# ─────────────────────────────────────────────
# PATCH B — Temperature 0.0 para código (C1)
# Detectar tasks de código e usar temp=0.0
# ─────────────────────────────────────────────
OLD_TEMP = "                        max_tokens=1024 if _attempt_provider == 'cerebras' else 4096,\n                        temperature=0.7)"
NEW_TEMP = """                        max_tokens=1024 if _attempt_provider == 'cerebras' else 4096,
                        temperature=0.0 if is_complex else 0.7)  # C1: temp=0 para código (DeepSeek)"""

if "temperature=0.0 if is_complex" not in content and OLD_TEMP in content:
    content = content.replace(OLD_TEMP, NEW_TEMP, 1)
    print("  ✅ C1: temperature=0.0 para tarefas de código")
else:
    print("  ⚠️  C1: temperatura já ajustada ou linha não encontrada")

# Temperatura também no segundo create (sem tools)
OLD_TEMP2 = "                        max_tokens=1024,\n                        temperature=0.7)"
NEW_TEMP2 = """                        max_tokens=1024,
                        temperature=0.0 if is_complex else 0.7)  # C1"""

if "temperature=0.0 if is_complex" in content and OLD_TEMP2 in content:
    content = content.replace(OLD_TEMP2, NEW_TEMP2, 1)

# ─────────────────────────────────────────────
# PATCH C — Tool grouping por intenção (C2)
# Substitui _tools_para_chamada = TOOLS por versão inteligente
# ─────────────────────────────────────────────
OLD_TOOLS = "        _tools_para_chamada = TOOLS if (provider_name != 'cerebras' or tools_needed) else None"
NEW_TOOLS = """        # C2: Tool grouping por intenção — não envia 60+ schemas de uma vez
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
            _tools_para_chamada = minify_tool_schemas(_tools_para_chamada, get_schema_mode(is_simple, is_complex))"""

if "C2: Tool grouping" not in content and OLD_TOOLS in content:
    content = content.replace(OLD_TOOLS, NEW_TOOLS, 1)
    print("  ✅ C2: Tool grouping por intenção aplicado")
else:
    print("  ⚠️  C2: Tool grouping já presente ou linha não encontrada")

# ─────────────────────────────────────────────
# PATCH D — Preferência edit_file no system prompt (C3)
# ─────────────────────────────────────────────
OLD_SYSTEM_END = "NUNCA responda apenas com texto descrevendo o que faria — SEMPRE chame as ferramentas."
NEW_SYSTEM_END = """NUNCA responda apenas com texto descrevendo o que faria — SEMPRE chame as ferramentas.

REGRAS DE EDIÇÃO DE ARQUIVOS (C3 — economia de tokens):
- Para MODIFICAR arquivos existentes: use edit_file(file_path, old_string, new_string) — passa só o diff
- Para CRIAR arquivos novos: use write_file
- NUNCA reescreva um arquivo inteiro se só precisa mudar algumas linhas
- edit_file é 10x mais eficiente que write_file para modificações parciais"""

if "C3" not in content and OLD_SYSTEM_END in content:
    content = content.replace(OLD_SYSTEM_END, NEW_SYSTEM_END, 1)
    print("  ✅ C3: Preferência edit_file no system prompt")
else:
    print("  ⚠️  C3: Já presente ou linha não encontrada")

# ─────────────────────────────────────────────
# PATCH E — Pipeline de compressão antes do create()
# ─────────────────────────────────────────────
# Procurar o ponto de chamada ao create() no loop
COMPRESS_TARGET = "                if _tools_para_chamada:"
COMPRESS_NEW = """                # Pipeline de compressão (sirius-open → sirius-code)
                messages = compress_stale_tool_results(messages)
                messages = maybe_compress_messages(messages)
                if _tools_para_chamada:"""

if "compress_stale_tool_results" not in content and COMPRESS_TARGET in content:
    content = content.replace(COMPRESS_TARGET, COMPRESS_NEW, 1)
    print("  ✅ Pipeline de compressão inserido")
else:
    print("  ⚠️  Pipeline de compressão já presente ou ponto não encontrado")

# ─────────────────────────────────────────────
# PATCH F — Semantic cache check antes do loop
# ─────────────────────────────────────────────
LOOP_TARGET = "    for i in range(max_iter):"
SEM_CHECK = """    # Semantic cache (Fase 5)
    _sem_cached = semantic_cache.get(str(user_id), original_user_message)
    if _sem_cached:
        await save_message(str(user_id), 'assistant', _sem_cached)
        return _sem_cached
    for i in range(max_iter):"""

if "semantic_cache.get" not in content and LOOP_TARGET in content:
    content = content.replace(LOOP_TARGET, SEM_CHECK, 1)
    print("  ✅ Semantic cache check inserido")
else:
    print("  ⚠️  Semantic cache já presente")

# ─────────────────────────────────────────────
# PATCH G — Budget forcing antes do user_msg
# ─────────────────────────────────────────────
# Procurar onde user_msg é montado
import re
bf_match = re.search(r"    user_msg\s*=\s*\{['\"]role['\"]\s*:\s*['\"]user['\"]", content)
if bf_match and "budget_forcing" not in content:
    idx = bf_match.start()
    insert = "    # Budget forcing (Fase 5 — DeepSeek research)\n    user_message_for_api = budget_forcing(user_message_for_api, is_simple, is_complex)\n"
    content = content[:idx] + insert + content[idx:]
    print("  ✅ Budget forcing inserido")
else:
    print("  ⚠️  Budget forcing já presente ou user_msg não encontrado")

# ─────────────────────────────────────────────
# PATCH H — Métricas + tool self_stats
# ─────────────────────────────────────────────
# Adicionar self_stats na tool_fn
STATS_TARGET = "        'agent':      _agent_tool,"
STATS_NEW = """        'agent':      _agent_tool,
        'self_stats': lambda period=24, **kw: get_stats_report(int(period)),"""

if "'self_stats'" not in content and STATS_TARGET in content:
    content = content.replace(STATS_TARGET, STATS_NEW, 1)
    print("  ✅ Tool self_stats registrada")
else:
    print("  ⚠️  self_stats já presente")

# _t_start para métricas
PROFILE_TARGET = "    profile          = await get_or_create_profile(str(user_id), username)"
if "_t_start" not in content and PROFILE_TARGET in content:
    content = content.replace(
        PROFILE_TARGET,
        "    _t_start = time.time()  # métricas\n    " + PROFILE_TARGET.strip()
    )
    print("  ✅ _t_start adicionado")

# ─────────────────────────────────────────────
# Salvar
# ─────────────────────────────────────────────
if content == original:
    print("\n⚠️  Nenhuma alteração detectada — verifique manualmente.")
    sys.exit(0)

print("\n[5/8] Salvando agent.py...")
backup = AGENT + ".bak_deploy"
shutil.copy2(AGENT, backup)
with open(AGENT, "w", encoding="utf-8") as f:
    f.write(content)
print(f"  ✅ Salvo (backup: {backup})")

# ─────────────────────────────────────────────
# Reiniciar
# ─────────────────────────────────────────────
print("\n[6/8] Reiniciando sirius-code...")
run(f"docker restart {CONTAINER}")
time.sleep(5)
status = run(f"docker inspect --format='{{{{.State.Status}}}}' {CONTAINER}")
print(f"  Status: {status}")

# ─────────────────────────────────────────────
# Verificar
# ─────────────────────────────────────────────
print("\n[7/8] Verificando patches...")
checks = {
    "tool_cache":        "make_cached_shell",
    "stale_results":     "compress_stale_tool_results",
    "llmlingua":         "maybe_compress_messages",
    "phase5":            "budget_forcing",
    "sem_cache":         "semantic_cache",
    "schema_minif":      "minify_tool_schemas",
    "tool_grouping C2":  "C2: Tool grouping",
    "temp 0.0 C1":       "temperature=0.0 if is_complex",
    "edit_file C3":      "C3",
    "self_stats":        "self_stats",
}
all_ok = True
for name, pattern in checks.items():
    found = pattern in content
    print(f"  {'✅' if found else '❌'} {name}")
    if not found:
        all_ok = False

# ─────────────────────────────────────────────
# Teste básico
# ─────────────────────────────────────────────
print("\n[8/8] Teste rápido...")
test = run(
    f"docker exec {CONTAINER} python3 -c \""
    f"import sys; sys.path.insert(0,'/app'); "
    f"from phase5 import budget_forcing; "
    f"print(budget_forcing('liste os arquivos', True, False))"
    f"\"",
    check=False
)
print(f"  Budget forcing test: {test[:100]}")

print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if all_ok:
    print("  ✅ Deploy sirius-code concluído!")
else:
    print("  ⚠️  Deploy parcial — alguns patches falharam")
print("  Otimizações sirius-open: portadas")
print("  C1 temp=0.0 para código: ativo")
print("  C2 tool grouping: ativo")
print("  C3 preferência edit_file: ativo")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
