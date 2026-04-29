import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy import String, Text, DateTime, Integer, select, delete, or_

DATABASE_URL = os.getenv("DATABASE_URL","sqlite+aiosqlite:////app/data/memory.db")
MAX_HISTORY = int(os.getenv("MAX_HISTORY","50"))
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase): pass

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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ContextSummary(Base):
    __tablename__ = "context_summary"
    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    summary: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_message(user_id, role, content):
    async with AsyncSessionLocal() as s:
        s.add(Message(user_id=str(user_id), role=role, content=content))
        await s.commit()
        r = await s.execute(
            select(Message.id).where(Message.user_id==str(user_id))
            .order_by(Message.id.desc()).offset(MAX_HISTORY))
        ids = [x[0] for x in r.fetchall()]
        if ids:
            await s.execute(delete(Message).where(Message.id.in_(ids)))
            await s.commit()

async def get_history(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Message).where(Message.user_id==str(user_id))
            .order_by(Message.id.asc()).limit(MAX_HISTORY))
        return [{"role": m.role, "content": m.content} for m in r.scalars().all()]

async def clear_history(user_id):
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Message).where(Message.user_id==str(user_id)))
        await s.commit()

async def get_or_create_profile(user_id, username=None):
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(UserProfile).where(UserProfile.user_id==str(user_id)))
        p = r.scalar_one_or_none()
        if not p:
            p = UserProfile(user_id=str(user_id), username=username, last_seen=datetime.utcnow())
            s.add(p)
        else:
            p.last_seen = datetime.utcnow()
            if username: p.username = username
        await s.commit()
        await s.refresh(p)
        return p

async def set_user_provider(user_id, provider, model=None):
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(UserProfile).where(UserProfile.user_id==str(user_id)))
        p = r.scalar_one_or_none()
        if p:
            p.provider = provider
            if model: p.model = model
            await s.commit()

async def set_user_prompt(user_id, prompt):
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(UserProfile).where(UserProfile.user_id==str(user_id)))
        p = r.scalar_one_or_none()
        if p:
            p.system_prompt = prompt
            await s.commit()

async def remember(user_id, key, value, category="geral"):
    now = datetime.utcnow()
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory).where(Memory.user_id==str(user_id), Memory.key==key))
        m = r.scalar_one_or_none()
        if m:
            m.value = value
            m.category = category
            m.updated_at = now
        else:
            s.add(Memory(user_id=str(user_id), category=category, key=key, value=value, updated_at=now))
        await s.commit()
    return f"Memoria salva: [{category}] {key}"

async def recall(user_id, query):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory).where(Memory.user_id==str(user_id)).where(
                or_(Memory.value.contains(query),
                    Memory.key.contains(query),
                    Memory.category.contains(query))
            ).order_by(Memory.updated_at.desc()).limit(15))
        rows = r.scalars().all()
    if not rows:
        return f"Nenhuma memoria encontrada para: {query}"
    return "\n".join([f"[{m.category}] {m.key}: {m.value}" for m in rows])

async def recall_all(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Memory).where(Memory.user_id==str(user_id))
            .order_by(Memory.category, Memory.updated_at.desc()))
        rows = r.scalars().all()
    if not rows:
        return "Nenhuma memoria registrada ainda."
    by_cat = {}
    for m in rows:
        by_cat.setdefault(m.category, []).append(f"  {m.key}: {m.value}")
    return "\n".join([f"[{cat}]\n" + "\n".join(items) for cat, items in by_cat.items()])

async def get_context_summary(user_id):
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(ContextSummary).where(ContextSummary.user_id==str(user_id)))
        row = r.scalar_one_or_none()
    return row.summary if row else None

async def update_context_summary(user_id, summary):
    now = datetime.utcnow()
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(ContextSummary).where(ContextSummary.user_id==str(user_id)))
        row = r.scalar_one_or_none()
        if row:
            row.summary = summary[-3000:]
            row.updated_at = now
        else:
            s.add(ContextSummary(user_id=str(user_id), summary=summary, updated_at=now))
        await s.commit()
