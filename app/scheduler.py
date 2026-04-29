"""
scheduler.py — Autonomia proativa do Sirius
Briefing matinal às 7h + monitor de servidor a cada 30min
"""

import asyncio
import logging
import os
import sqlite3
import threading
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("sirius.scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [scheduler] %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TARGET_USER_ID = int(os.getenv("ALLOWED_USER_IDS", "598373504").split(",")[0].strip())
DB_PATH = "/app/data/memory.db"

DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# ── Telegram helpers ──────────────────────────────────────────────────────────

async def send_telegram(chat_id: int, text: str) -> bool:
    """Envia mensagem via Telegram Bot API."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN não configurado — mensagem não enviada.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                logger.info(f"Mensagem enviada para {chat_id}")
                return True
            else:
                logger.error(f"Telegram API erro {r.status_code}: {r.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"Erro ao enviar Telegram: {e}")
        return False


# ── DB helpers (sync, rodando em executor) ────────────────────────────────────

def _fetch_recent_memories(user_id: int, limit: int = 8) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        rows = conn.execute(
            "SELECT category, key, value, updated_at FROM memories "
            "WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
        conn.close()
        return [{"cat": r[0], "key": r[1], "val": r[2], "ts": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Erro ao buscar memórias: {e}")
        return []


def _fetch_recent_interactions(user_id: int, limit: int = 5) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        rows = conn.execute(
            "SELECT message, iter_count, success, timestamp FROM interaction_log "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (str(user_id), limit),
        ).fetchall()
        conn.close()
        return [{"msg": r[0], "iters": r[1], "ok": r[2], "ts": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Erro ao buscar interações: {e}")
        return []


def _log_monitor_event(status: str, detail: str):
    """Registra evento do monitor na tabela interaction_log."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        # Verifica se a tabela existe — criação lazy
        conn.execute(
            "CREATE TABLE IF NOT EXISTS scheduler_log "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            " event TEXT, detail TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO scheduler_log (event, detail) VALUES (?, ?)",
            (status, detail[:500]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao logar monitor: {e}")


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def job_briefing_matinal():
    """Briefing matinal enviado às 7h para o usuário principal."""
    logger.info("Executando briefing matinal…")
    loop = asyncio.get_event_loop()

    now = datetime.now()
    dia_semana = DIAS_PT[now.weekday()]
    data_fmt = now.strftime("%d/%m/%Y")

    memories = await loop.run_in_executor(None, _fetch_recent_memories, TARGET_USER_ID)
    interactions = await loop.run_in_executor(None, _fetch_recent_interactions, TARGET_USER_ID)

    # Montar texto do briefing
    lines = [
        f"🌅 <b>Bom dia! Briefing Sirius — {dia_semana}, {data_fmt}</b>",
        "",
    ]

    if memories:
        lines.append("🧠 <b>Memórias recentes:</b>")
        for m in memories:
            lines.append(f"  • [{m['cat']}] <b>{m['key']}</b>: {m['val'][:80]}")
        lines.append("")

    if interactions:
        lines.append("📋 <b>Últimas interações:</b>")
        for i in interactions:
            status = "✅" if i["ok"] else "❌"
            msg_preview = (i["msg"] or "")[:60].replace("\n", " ")
            lines.append(f"  {status} {msg_preview}")
        lines.append("")

    lines.append("💡 <i>Sirius está ativo e pronto para o dia.</i>")

    text = "\n".join(lines)
    await send_telegram(TARGET_USER_ID, text)
    _log_monitor_event("briefing_matinal", f"Enviado em {now.isoformat()}")


async def job_monitor_servidor():
    """Verifica saúde do container e porta 5001 a cada 30 minutos."""
    logger.info("Executando monitor de servidor…")
    now = datetime.now().isoformat(timespec="seconds")
    issues = []

    # Verifica porta 5001
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("http://127.0.0.1:5001/")
            if r.status_code < 500:
                logger.info(f"Porta 5001 OK ({r.status_code})")
                _log_monitor_event("monitor_ok", f"porta=5001 status={r.status_code} ts={now}")
            else:
                issues.append(f"porta 5001 respondeu {r.status_code}")
    except Exception as e:
        issues.append(f"porta 5001 inacessível: {e}")

    if issues:
        detail = "; ".join(issues)
        logger.warning(f"Monitor: {detail}")
        _log_monitor_event("monitor_alerta", detail)
        alerta = f"⚠️ <b>Alerta Sirius</b> ({now})\n\n{detail}"
        await send_telegram(TARGET_USER_ID, alerta)
    else:
        logger.info("Monitor: todos os serviços OK")


# ── Inicialização do scheduler ────────────────────────────────────────────────

def start_scheduler():
    """
    Cria um loop asyncio dedicado em background thread e
    inicia o AsyncIOScheduler nele.
    Chamado a partir do webserver.py no startup do Flask.
    """
    loop = asyncio.new_event_loop()

    def _run(loop_: asyncio.AbstractEventLoop):
        asyncio.set_event_loop(loop_)
        scheduler = AsyncIOScheduler(event_loop=loop_)

        # Briefing matinal às 07:00 (horário do servidor)
        scheduler.add_job(
            job_briefing_matinal,
            trigger="cron",
            hour=7,
            minute=0,
            id="briefing_matinal",
            replace_existing=True,
        )

        # Monitor a cada 30 minutos
        scheduler.add_job(
            job_monitor_servidor,
            trigger="interval",
            minutes=30,
            id="monitor_servidor",
            replace_existing=True,
        )

        scheduler.start()
        logger.info(
            f"Scheduler iniciado — briefing às 07:00, monitor a cada 30min. "
            f"Target user_id={TARGET_USER_ID}"
        )
        loop_.run_forever()

    t = threading.Thread(target=_run, args=(loop,), daemon=True, name="sirius-scheduler")
    t.start()
    return loop


async def send_briefing_now():
    """Dispara o briefing imediatamente (para teste)."""
    await job_briefing_matinal()


if __name__ == "__main__":
    # Teste standalone: envia briefing imediato
    asyncio.run(send_briefing_now())
