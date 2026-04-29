import os, json, sqlite3, ast
from datetime import datetime

DB_PATH = '/app/data/memory.db'

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS interaction_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, message TEXT, response_len INTEGER,
        tools TEXT, iter_count INTEGER, success INTEGER, timestamp TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS patches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT, backup_path TEXT, applied_at TEXT
    )''')
    conn.commit()
    return conn

async def log_interaction(user_id, user_message, response, tools_used, iter_count, success):
    conn = _get_db()
    conn.execute("INSERT INTO interaction_log VALUES (NULL,?,?,?,?,?,?,?)",
        (user_id, user_message[:200], len(response),
         json.dumps(list(dict.fromkeys(tools_used))),
         iter_count, int(success), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

async def analyze_performance(user_id):
    conn = _get_db()
    rows = conn.execute(
        "SELECT tools, iter_count, success, message FROM interaction_log WHERE user_id=? ORDER BY timestamp DESC LIMIT 100",
        (user_id,)).fetchall()
    conn.close()

    if not rows:
        return "Nenhuma interacao registrada ainda."

    total = len(rows)
    success_count = sum(1 for r in rows if r[2])
    avg_iter = sum(r[1] for r in rows) / total
    high_iter = sum(1 for r in rows if r[1] > 20)
    low_iter = sum(1 for r in rows if r[1] <= 3)

    tool_counts = {}
    for r in rows:
        for t in json.loads(r[0] or "[]"):
            tool_counts[t] = tool_counts.get(t, 0) + 1
    top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
    failed = [r[3][:80] for r in rows if not r[2]]

    lines = [
        "RELATORIO DE PERFORMANCE - " + datetime.now().strftime('%d/%m/%Y %H:%M'),
        "",
        "METRICAS:",
        "  Total: " + str(total) + " interacoes",
        "  Sucesso: " + str(round(success_count/total*100, 1)) + "% (" + str(success_count) + "/" + str(total) + ")",
        "  Media iteracoes: " + str(round(avg_iter, 1)),
        "  Tarefas simples (<=3): " + str(low_iter),
        "  Tarefas complexas (>20): " + str(high_iter),
        "",
        "TOP FERRAMENTAS:",
    ]
    for t, c in top_tools:
        lines.append("  " + t + ": " + str(c) + "x")
    if failed:
        lines.append("\nFALHAS:")
        for f in failed[:3]:
            lines.append("  - " + f)
    return "\n".join(lines)

async def diagnose(user_id):
    conn = _get_db()
    rows = conn.execute(
        "SELECT tools, iter_count, success, message FROM interaction_log WHERE user_id=? ORDER BY timestamp DESC LIMIT 100",
        (user_id,)).fetchall()
    conn.close()

    if not rows:
        return "Sem dados para diagnostico."

    total = len(rows)
    diagnoses = []

    shell_heavy = [r for r in rows if json.loads(r[0] or "[]").count("run_shell") > 5 and r[1] > 15]
    if len(shell_heavy) > 2:
        diagnoses.append({
            "problema": "Loop de exploracao excessiva com run_shell",
            "evidencia": str(len(shell_heavy)) + " tarefas com run_shell >5x e >15 iteracoes",
            "causa_raiz": "Falta de contexto previo - reexplora o que ja sabe",
            "solucao": "Usar recall() antes de qualquer run_shell em containers conhecidos"
        })

    no_analyze = [r for r in rows if r[1] > 8 and "analyze" not in json.loads(r[0] or "[]")]
    if len(no_analyze) > 3:
        diagnoses.append({
            "problema": "Tarefas longas sem planejamento",
            "evidencia": str(len(no_analyze)) + " tarefas >8 iter sem analyze()",
            "causa_raiz": "Acao impulsiva antes de pensar",
            "solucao": "Usar analyze() para tarefas complexas"
        })

    failures = [r for r in rows if not r[2]]
    if len(failures) > total * 0.15:
        diagnoses.append({
            "problema": "Taxa de falha acima de 15%",
            "evidencia": str(len(failures)) + " falhas em " + str(total),
            "causa_raiz": "Tarefas muito complexas sem divisao",
            "solucao": "Dividir em subtarefas via /tarefa"
        })

    if not diagnoses:
        return "Nenhum padrao problematico. Performance dentro do esperado."

    lines = ["DIAGNOSTICO", ""]
    for i, d in enumerate(diagnoses, 1):
        lines.append(str(i) + ". " + d["problema"])
        lines.append("   Evidencia: " + d["evidencia"])
        lines.append("   Causa: " + d["causa_raiz"])
        lines.append("   Solucao: " + d["solucao"])
        lines.append("")
    return "\n".join(lines)

async def suggest_improvements(user_id):
    diag = await diagnose(user_id)
    suggestions = []
    if "exploracao" in diag:
        suggestions.append("Cache de contexto: recall() antes de docker exec")
    if "planejamento" in diag:
        suggestions.append("Analyze obrigatorio em tarefas complexas")
    if "falha" in diag:
        suggestions.append("Divisao automatica de tarefas longas")
    if not suggestions:
        return "Nenhuma melhoria urgente."
    lines = ["PROPOSTAS DE MELHORIA", ""]
    for i, s in enumerate(suggestions, 1):
        lines.append(str(i) + ". " + s)
    lines.append("\nPara aplicar: use self_patch.")
    return "\n".join(lines)

async def self_patch(description, old_code, new_code):
    agent_path = '/app/agent.py'
    with open(agent_path, "r") as f:
        current = f.read()
    if old_code not in current:
        return "Trecho nao encontrado. Verifique o codigo exato antes de self_patch."
    patched = current.replace(old_code, new_code, 1)
    try:
        ast.parse(patched)
    except SyntaxError as e:
        return "Erro de sintaxe (linha " + str(e.lineno) + "): " + e.msg
    backup_dir = '/app/data/backups'
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = backup_dir + "/agent_" + datetime.now().strftime('%Y%m%d_%H%M%S') + ".py"
    with open(backup_path, "w") as f:
        f.write(current)
    with open(agent_path, "w") as f:
        f.write(patched)
    conn = _get_db()
    conn.execute("INSERT INTO patches VALUES (NULL,?,?,?)",
        (description, backup_path, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return "Patch aplicado! Backup: " + backup_path + " | Reinicie: docker restart sirius-open"

async def aprender_e_aplicar(topico, user_id):
    """Aprende com Gemini sobre um topico e salva o conhecimento em memoria persistente."""
    try:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return "Gemini nao configurado."

        client = genai.Client(api_key=key)
        prompt = (
            "Voce esta ensinando o Sirius, um agente de IA autonomo criado pela SiriusCompany. "
            "Ensine sobre: " + topico + ". "
            "Seja tecnico, pratico e didatico. Inclua: "
            "1. Conceitos fundamentais "
            "2. Melhores praticas atuais "
            "3. Exemplos de codigo comentados "
            "4. Erros comuns e como evitar "
            "5. Recursos para aprofundar"
        )
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        conhecimento = response.text

        # Salva em memoria persistente
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, key TEXT, value TEXT, category TEXT, timestamp TEXT,
            UNIQUE(user_id, key)
        )''')
        key_mem = "aprendizado_" + topico[:30].replace(" ", "_").lower()
        conn.execute(
            "INSERT OR REPLACE INTO memories VALUES (NULL,?,?,?,?,?)",
            (user_id, key_mem, conhecimento[:2000], "aprendizado", datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()

        # Salva no log de debates
        log_path = "/app/data/debates.json"
        debates = []
        if os.path.exists(log_path):
            try:
                debates = json.loads(open(log_path).read())
            except:
                debates = []
        debates.append({
            "ts": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "topico": "APRENDIZADO: " + topico[:60],
            "sirius": "Estudando com Gemini sobre: " + topico,
            "gemini": conhecimento
        })
        open(log_path, "w").write(json.dumps(debates[-100:], ensure_ascii=False))

        return "Aprendi sobre " + topico + " com o Gemini e salvei em memoria.\n\nRESUMO:\n" + conhecimento[:500] + "..."

    except Exception as e:
        return "Erro no aprendizado: " + str(e)

async def ciclo_aprimoramento_com_gemini(user_id):
    """Ciclo completo: analisa performance, consulta Gemini sobre melhorias, salva aprendizado."""
    try:
        perf = await analyze_performance(user_id)
        diag = await diagnose(user_id)

        from google import genai
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            sugestoes_gemini = "Gemini nao disponivel."
        else:
            client = genai.Client(api_key=key)
            prompt = (
                "Voce e um especialista em IA e sistemas autonomos. "
                "O agente Sirius apresentou este relatorio de performance:\n\n" +
                perf + "\n\nDiagnostico:\n" + diag +
                "\n\nBaseado nisso, sugira 3 melhorias concretas e implementaveis "
                "para tornar o Sirius mais eficiente, preciso e util. "
                "Seja especifico sobre O QUE mudar e COMO mudar."
            )
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            sugestoes_gemini = response.text

            # Salva o aprendizado
            log_path = "/app/data/debates.json"
            debates = []
            if os.path.exists(log_path):
                try:
                    debates = json.loads(open(log_path).read())
                except:
                    debates = []
            debates.append({
                "ts": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "topico": "AUTO-APRIMORAMENTO: Ciclo de melhoria",
                "sirius": perf + "\n\n" + diag,
                "gemini": sugestoes_gemini
            })
            open(log_path, "w").write(json.dumps(debates[-100:], ensure_ascii=False))

        return (
            perf + "\n\n" +
            diag + "\n\n" +
            "SUGESTOES DO GEMINI:\n" + sugestoes_gemini + "\n\n" +
            "PROXIMOS PASSOS:\n"
            "1. Analise as sugestoes acima\n"
            "2. Use self_patch para implementar as melhorias aprovadas\n"
            "3. Execute docker restart sirius-open para ativar\n"
            "4. Repita o ciclo para medir impacto"
        )
    except Exception as e:
        return "Erro no ciclo: " + str(e)

async def full_self_improvement_cycle(user_id):
    """Alias para ciclo completo com Gemini."""
    return await ciclo_aprimoramento_com_gemini(user_id)

async def push_to_github(description="Auto-aprimoramento automatico"):
    import asyncio
    cmd = (
        'cd /docker/sirius-open && '
        'git add -A && '
        'git commit -m "' + description + ' - ' + datetime.now().strftime("%d/%m/%Y %H:%M") + '" && '
        'git push origin main'
    )
    p = await asyncio.create_subprocess_shell(cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    o, e = await p.communicate()
    return o.decode()[:500] or e.decode()[:500]

# Função para análise detalhada de falhas - Melhoria 2 do Gemini
async def analyze_failure_patterns(user_id):
    """Analisa padrões de falha detalhados"""
    try:
        from failure_logger import failure_logger
        analysis = failure_logger.analyze_failure_patterns()
        if analysis.get("total", 0) == 0:
            return "Nenhuma falha registrada no sistema detalhado."
        
        lines = ["ANALISE DE PADROES DE FALHA - SISTEMA DETALHADO:", ""]
        lines.append(f"Total falhas registradas: {analysis.get("total", 0)}")
        lines.append(f"Falhas recentes (últimas 50): {analysis.get("recent", 0)}")
        
        if analysis.get("tool_patterns", []):
            lines.append("\nPADRÕES POR FERRAMENTA:")
            for tool, count in analysis.get("tool_patterns", [])[:5]:
                lines.append(f"  - {tool}: {count} falhas")
                # Sugestões de recuperação
                suggestions = failure_logger.get_recovery_suggestions(tool)
                if suggestions:
                    for s in suggestions:
                        lines.append(f"    → {s}")
        
        if analysis["reason_patterns"]:
            lines.append("\nPADRÕES POR MOTIVO SUGERIDO:")
            for reason, count in analysis["reason_patterns"][:5]:
                lines.append(f"  - {reason}: {count} falhas")
        
        if analysis["last_failures"]:
            lines.append("\nÚLTIMAS 5 FALHAS:")
            for i, f in enumerate(analysis["last_failures"], 1):
                ts = f.get("timestamp", "")[:16]
                tool = f.get("ferramenta_envolvida", "unknown")
                reason = f.get("motivo_sugerido", "")[:80]
                lines.append(f"  {i}. [{ts}] {tool}: {reason}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Erro na análise de falhas: {str(e)}"
