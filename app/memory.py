"""
memory.py — Com RAG semântico para memórias.
recall() usa embeddings + coseno em vez de SQL LIKE.
"""
import os
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy import String, Text, DateTime, Integer, select, delete, or_
from memory_dedup import dedup_on_remember as _dedup_on_remember

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/memory.db")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Quantas memórias retornar no recall semântico
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
# Similaridade mínima para incluir (0.0 = tudo, 0.3 = só relevante)
RAG_MIN_SIM = float(os.getenv("RAG_MIN_SIM", "0.25"))


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True)
    category: Mapped[str] = mapped_column(String(50), default="geral")
    key: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text, nullable=True)   # JSON list[float]
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContextSummary(Base):
    __tablename__ = "context_summary"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    summary: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Migração: adiciona coluna embedding se não existir
    try:
        async with engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE memories ADD COLUMN embedding TEXT"
                )
            )
    except Exception:
        pass  # Coluna já existe


async def save_message(user_id, role, content):
    async with AsyncSessionLocal() as s:
        s.add(Message(user_id=str(user_id), role=role, content=content))
        await s.commit()
        r = await s.execute(
            select(Message.id)
            .where(Message.user_id == str(user_id))
            .order_by(Message.id.desc())
            .offset(MAX_HISTORY)
        )
        ids = [x[0] for x in r.fetchall()]
        if ids:
            await s.execute(delete(Message).where(Message.id.in_(ids)))
            await s.commit()


async def get_history(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Message)
            .where(Message.user_id == str(user_id))
            .order_by(Message.id.asc())
            .limit(MAX_HISTORY)
        )
        return [{"role": m.role, "content": m.content} for m in r.scalars().all()]


async def clear_history(user_id):
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message).where(Message.user_id == str(user_id)))
        await s.commit()


async def get_or_create_profile(user_id, username=None):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(UserProfile).where(UserProfile.user_id == str(user_id))
        )
        p = r.scalar_one_or_none()
        if not p:
            p = UserProfile(
                user_id=str(user_id), username=username, last_seen=datetime.utcnow()
            )
            s.add(p)
        else:
            p.last_seen = datetime.utcnow()
            if username:
                p.username = username
        await s.commit()
        await s.refresh(p)
        return p


async def set_user_provider(user_id, provider, model=None):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(UserProfile).where(UserProfile.user_id == str(user_id))
        )
        p = r.scalar_one_or_none()
        if p:
            p.provider = provider
            if model:
                p.model = model
            await s.commit()


async def set_user_prompt(user_id, prompt):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(UserProfile).where(UserProfile.user_id == str(user_id))
        )
        p = r.scalar_one_or_none()
        if p:
            p.system_prompt = prompt
            await s.commit()


def _make_embed_text(key: str, value: str, category: str) -> str:
    """Texto concatenado para embedar — inclui key+value+category."""
    return f"{category}: {key}. {value}"


async def remember(user_id, key, value, category="geral"):
    """Salva memória com embedding semântico."""
    from embedder import embed_to_json  # import lazy para não atrasar startup

    now = datetime.utcnow()
    emb_json = embed_to_json(_make_embed_text(key, value, category))

    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory).where(Memory.user_id == str(user_id), Memory.key == key)
        )
        m = r.scalar_one_or_none()
        if m:
            m.value = value
            m.category = category
            m.embedding = emb_json
            m.updated_at = now
        else:
            s.add(
                Memory(
                    user_id=str(user_id),
                    category=category,
                    key=key,
                    value=value,
                    embedding=emb_json,
                    updated_at=now,
                )
            )
        await s.commit()
        try:
            _removed = await _dedup_on_remember(str(user_id), key)
            if _removed:
                return f"Memoria salva: [{category}] {key} (dedup: -{_removed} duplicatas)"
        except Exception:
            pass  # dedup falhou silenciosamente
        return f"Memoria salva: [{category}] {key}"


async def recall(user_id, query: str) -> str:
    """
    Busca semântica por RAG:
    1. Embeda a query
    2. Carrega todas as memórias do usuário
    3. Calcula similaridade coseno
    4. Retorna top-K acima do limiar RAG_MIN_SIM
    Fallback: se não há embeddings, usa SQL LIKE original.
    """
    from embedder import embed, json_to_vec, cosine_sim  # import lazy

    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory)
            .where(Memory.user_id == str(user_id))
            .order_by(Memory.updated_at.desc())
        )
        rows = r.scalars().all()

    if not rows:
        return f"Nenhuma memoria encontrada para: {query}"

    # Separa memórias com e sem embedding
    with_emb = [m for m in rows if m.embedding]
    without_emb = [m for m in rows if not m.embedding]

    results = []

    # Busca semântica nas que têm embedding
    if with_emb:
        q_vec = embed(query)
        scored = []
        for m in with_emb:
            try:
                m_vec = json_to_vec(m.embedding)
                sim = cosine_sim(q_vec, m_vec)
                scored.append((sim, m))
            except Exception:
                without_emb.append(m)

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [m for sim, m in scored[:RAG_TOP_K] if sim >= RAG_MIN_SIM]

    # Fallback SQL LIKE para memórias sem embedding
    if without_emb:
        q_lower = query.lower()
        for m in without_emb:
            if (
                q_lower in m.value.lower()
                or q_lower in m.key.lower()
                or q_lower in m.category.lower()
            ):
                results.append(m)
        results = results[:RAG_TOP_K]

    if not results:
        return f"Nenhuma memoria encontrada para: {query}"

    return "\n".join([f"[{m.category}] {m.key}: {m.value}" for m in results])


async def recall_all(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory)
            .where(Memory.user_id == str(user_id))
            .order_by(Memory.category, Memory.updated_at.desc())
        )
        rows = r.scalars().all()
    if not rows:
        return "Nenhuma memoria registrada ainda."
    by_cat = {}
    for m in rows:
        by_cat.setdefault(m.category, []).append(f"  {m.key}: {m.value}")
    return "\n".join(
        [f"[{cat}]\n" + "\n".join(items) for cat, items in by_cat.items()]
    )


async def get_context_summary(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(ContextSummary).where(ContextSummary.user_id == str(user_id))
        )
        row = r.scalar_one_or_none()
    return row.summary if row else None


async def update_context_summary(user_id, summary):
    now = datetime.utcnow()
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(ContextSummary).where(ContextSummary.user_id == str(user_id))
        )
        row = r.scalar_one_or_none()
        if row:
            row.summary = summary[-3000:]
            row.updated_at = now
        else:
            s.add(
                ContextSummary(
                    user_id=str(user_id), summary=summary, updated_at=now
                )
            )
        await s.commit()
