"""
metrics.py — Coleta e consulta de métricas de uso do Sirius Open.

Registra por chamada: provider, tempo de resposta, tokens estimados,
cache hits (stale+llmlingua+tool_cache), tools usadas.

Uso no agent.py:
    from metrics import record_call, get_stats_report
"""
from __future__ import annotations
import os
import time
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("METRICS_DB", "/app/data/metrics.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    user_id     TEXT    NOT NULL,
    provider    TEXT,
    model       TEXT,
    response_ms INTEGER,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    tools_used  TEXT,
    cache_hits  INTEGER DEFAULT 0,
    is_complex  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS idx_calls_user ON calls(user_id);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_metrics_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conn() as c:
        c.executescript(_CREATE_SQL)


def record_call(
    user_id: str,
    provider: str,
    model: str,
    response_ms: int,
    tokens_in: int   = 0,
    tokens_out: int  = 0,
    tools_used: list = None,
    cache_hits: int  = 0,
    is_complex: bool = False,
):
    """Registra uma chamada ao agente."""
    try:
        tools_str = ",".join(tools_used) if tools_used else ""
        with _conn() as c:
            c.execute(
                "INSERT INTO calls (ts,user_id,provider,model,response_ms,"
                "tokens_in,tokens_out,tools_used,cache_hits,is_complex) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), str(user_id), provider, model, response_ms,
                 tokens_in, tokens_out, tools_str, cache_hits, int(is_complex))
            )
    except Exception as e:
        print(f"[metrics] Erro ao registrar: {e}")


def get_stats_report(period_hours: int = 24) -> str:
    """Retorna relatório de métricas em texto."""
    try:
        cutoff = time.time() - period_hours * 3600
        with _conn() as c:
            rows = c.execute(
                "SELECT * FROM calls WHERE ts > ? ORDER BY ts DESC", (cutoff,)
            ).fetchall()

        if not rows:
            return f"Nenhuma chamada registrada nas últimas {period_hours}h."

        total       = len(rows)
        providers   = {}
        total_ms    = 0
        total_tok_in  = 0
        total_tok_out = 0
        total_cache   = 0
        tools_count   = {}
        complex_calls = 0

        for r in rows:
            providers[r["provider"]] = providers.get(r["provider"], 0) + 1
            total_ms      += r["response_ms"] or 0
            total_tok_in  += r["tokens_in"]   or 0
            total_tok_out += r["tokens_out"]  or 0
            total_cache   += r["cache_hits"]  or 0
            complex_calls += r["is_complex"]  or 0
            for t in (r["tools_used"] or "").split(","):
                if t:
                    tools_count[t] = tools_count.get(t, 0) + 1

        avg_ms = total_ms // total if total else 0
        top_tools = sorted(tools_count.items(), key=lambda x: -x[1])[:5]
        provider_str = " | ".join(f"{p}:{n}" for p, n in sorted(providers.items(), key=lambda x: -x[1]))
        tools_str = " | ".join(f"{t}:{n}" for t, n in top_tools) if top_tools else "nenhuma"

        # Última chamada
        last = datetime.fromtimestamp(rows[0]["ts"]).strftime("%d/%m %H:%M")

        lines = [
            f"📊 Métricas — últimas {period_hours}h (até {last})",
            f"",
            f"Chamadas:     {total} total  ({complex_calls} complexas)",
            f"Tempo médio:  {avg_ms}ms",
            f"Providers:    {provider_str}",
            f"Tokens in:    ~{total_tok_in:,}",
            f"Tokens out:   ~{total_tok_out:,}",
            f"Cache hits:   {total_cache}",
            f"Top tools:    {tools_str}",
        ]

        # Tendência última hora
        hour_cutoff = time.time() - 3600
        last_hour = [r for r in rows if r["ts"] > hour_cutoff]
        if last_hour:
            lines.append(f"Última hora:  {len(last_hour)} chamadas")

        return "\n".join(lines)

    except Exception as e:
        return f"Erro ao consultar métricas: {e}"


# Inicializa DB ao importar
try:
    init_metrics_db()
except Exception:
    pass


def record(event_type: str, provider: str = "", tokens_in: int = 0,
           tokens_out: int = 0, user_id: str = "default", **kwargs):
    """Alias compatível com a chamada existente no agent.py."""
    record_call(
        user_id=user_id,
        provider=provider,
        model=kwargs.get("model", ""),
        response_ms=kwargs.get("response_ms", 0),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tools_used=kwargs.get("tools_used"),
        cache_hits=kwargs.get("cache_hits", 0),
        is_complex=kwargs.get("is_complex", False),
    )
