"""
memory_dedup.py — Deduplicacao semantica de memorias no SQLite.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/memory.db")
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "0.92"))

logger = logging.getLogger("memory_dedup")

_engine = create_async_engine(DATABASE_URL, echo=False)
_Session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _cosine(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))


async def run_dedup(user_id: Optional[str] = None) -> dict:
    """
    Varredura completa O(n^2) — use via endpoint /dedup ou cron.
    Mantem sempre a mais recente.
    """
    from memory import Memory

    async with _Session() as s:
        q = select(Memory)
        if user_id:
            q = q.where(Memory.user_id == str(user_id))
        q = q.order_by(Memory.updated_at.desc())
        rows = (await s.execute(q)).scalars().all()

    with_emb = []
    for m in rows:
        if m.embedding:
            try:
                with_emb.append((m, json.loads(m.embedding)))
            except Exception:
                pass

    if len(with_emb) < 2:
        return {"scanned": len(rows), "removed": 0, "pairs": []}

    to_delete: set = set()
    pairs: list = []

    for i in range(len(with_emb)):
        m_i, v_i = with_emb[i]
        if m_i.id in to_delete:
            continue
        for j in range(i + 1, len(with_emb)):
            m_j, v_j = with_emb[j]
            if m_j.id in to_delete:
                continue
            sim = _cosine(v_i, v_j)
            if sim >= DEDUP_THRESHOLD:
                to_delete.add(m_j.id)
                pairs.append({
                    "kept":    {"id": m_i.id, "key": m_i.key, "updated_at": str(m_i.updated_at)},
                    "removed": {"id": m_j.id, "key": m_j.key, "updated_at": str(m_j.updated_at)},
                    "sim": round(sim, 4),
                })
                logger.info("Dedup: sim=%.4f | KEEP [%s] | DEL [%s]", sim, m_i.key, m_j.key)

    if to_delete:
        async with _Session() as s:
            await s.execute(delete(Memory).where(Memory.id.in_(list(to_delete))))
            await s.commit()

    return {
        "scanned": len(rows),
        "with_embeddings": len(with_emb),
        "removed": len(to_delete),
        "threshold": DEDUP_THRESHOLD,
        "pairs": pairs,
    }


async def dedup_on_remember(user_id: str, new_key: str) -> int:
    """
    Versao leve O(n) — roda apos cada remember().
    Compara a nova memoria contra todas as outras do usuario.
    Remove as mais antigas duplicatas semanticas.
    Retorna numero de registros removidos.
    """
    from memory import Memory

    async with _Session() as s:
        new_mem = (await s.execute(
            select(Memory).where(
                Memory.user_id == str(user_id),
                Memory.key == new_key,
            )
        )).scalar_one_or_none()

        if not new_mem or not new_mem.embedding:
            return 0

        new_vec = json.loads(new_mem.embedding)

        others = (await s.execute(
            select(Memory).where(
                Memory.user_id == str(user_id),
                Memory.id != new_mem.id,
            )
        )).scalars().all()

    to_delete = []
    for m in others:
        if not m.embedding:
            continue
        try:
            sim = _cosine(new_vec, json.loads(m.embedding))
            if sim >= DEDUP_THRESHOLD:
                to_delete.append(m.id)
                logger.info("Dedup on-write: sim=%.4f | NEW [%s] | DEL [%s]", sim, new_key, m.key)
        except Exception:
            pass

    if to_delete:
        async with _Session() as s:
            await s.execute(delete(Memory).where(Memory.id.in_(to_delete)))
            await s.commit()

    return len(to_delete)