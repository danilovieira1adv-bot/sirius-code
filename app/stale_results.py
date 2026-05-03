"""
stale_results.py — Comprime tool results "stale" no histórico de mensagens.

Um tool result é considerado stale quando já existe uma mensagem do assistente
APÓS ele — ou seja, o modelo já tomou uma decisão com base naquele resultado.

Resultados stale são comprimidos para 1 linha (~80 chars) e o conteúdo
completo é salvo em /tmp/sirius_results/ para referência se necessário.

Uso no agent.py — chamar logo antes de cada request à API:
    from stale_results import compress_stale_tool_results
    messages = compress_stale_tool_results(messages)
"""
from __future__ import annotations
import os
import re
import hashlib
import time
from typing import Any

STALE_DIR = "/tmp/sirius_results"
# Mantém os N últimos tool results intactos (o mais recente não é stale ainda)
KEEP_LAST_N = 1
# Chars máximos para o sumário de 1 linha
SUMMARY_MAX = 80


def _ensure_dir():
    os.makedirs(STALE_DIR, exist_ok=True)


def _save_full(content: str) -> str:
    """Salva conteúdo em disco e retorna o path."""
    _ensure_dir()
    uid = hashlib.md5(content.encode()).hexdigest()[:8]
    ts  = int(time.time())
    path = f"{STALE_DIR}/r_{ts}_{uid}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _make_summary(tool_call_id: str, content: str) -> str:
    """Gera sumário de 1 linha para um tool result."""
    # Remove whitespace excessivo
    clean = re.sub(r'\s+', ' ', content.strip())

    # Detecta tipo de resultado pelo conteúdo
    if content.startswith("CONTAINER ID") or "IMAGE" in content[:50]:
        first = clean.split("\\n")[0] if "\\n" in clean else clean[:60]
        return f"[docker ps: {first[:60]}]"

    if "error" in content.lower()[:30] or "traceback" in content.lower()[:50]:
        first_line = clean.split("\\n")[0] if "\\n" in clean else clean
        return f"[ERRO: {first_line[:70]}]"

    if content.startswith("{") or content.startswith("["):
        return f"[JSON: {len(content)} chars]"

    # Conta linhas para dar contexto
    lines = content.strip().split("\n")
    n = len(lines)
    preview = lines[0].strip() if lines else clean

    if n > 1:
        return f"[{preview[:60]}... ({n} linhas)]"

    return f"[{clean[:SUMMARY_MAX]}]"


def compress_stale_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Percorre a lista de mensagens e comprime tool results stale.

    Stale = existe uma mensagem do assistente APÓS o tool result.

    Retorna nova lista (não modifica in-place).
    """
    if not messages:
        return messages

    # Identifica índices de mensagens 'tool' e 'assistant'
    tool_indices = [i for i, m in enumerate(messages) if _get_role(m) == 'tool']

    if len(tool_indices) <= KEEP_LAST_N:
        return messages  # Nada a comprimir

    # Tool results que têm um 'assistant' depois deles = stale
    stale_indices = set()
    for idx in tool_indices:
        has_assistant_after = any(
            _get_role(messages[j]) == 'assistant'
            for j in range(idx + 1, len(messages))
        )
        if has_assistant_after:
            stale_indices.add(idx)

    # Mantém os KEEP_LAST_N mais recentes intactos mesmo se stale
    sorted_tool = sorted(tool_indices)
    protected = set(sorted_tool[-KEEP_LAST_N:])
    stale_indices -= protected

    if not stale_indices:
        return messages

    # Comprime
    new_messages = []
    compressed = 0
    saved_chars = 0

    for i, msg in enumerate(messages):
        if i not in stale_indices:
            new_messages.append(msg)
            continue

        content = _get_content(msg)
        if not content or len(content) <= SUMMARY_MAX:
            new_messages.append(msg)
            continue

        # Já foi comprimido antes (tem [...])?
        if content.startswith('[') and content.endswith(']') and len(content) < 120:
            new_messages.append(msg)
            continue

        tool_call_id = msg.get('tool_call_id', f'stale_{i}')
        path = _save_full(content)
        summary = _make_summary(tool_call_id, content)
        full_summary = f"{summary} [full: {path}]"

        saved_chars += len(content) - len(full_summary)
        compressed += 1

        new_msg = dict(msg)
        new_msg['content'] = full_summary
        new_messages.append(new_msg)

    if compressed:
        print(f"[stale] {compressed} tool results comprimidos, -{saved_chars} chars")

    return new_messages


def _get_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return msg.get('role', '')
    return getattr(msg, 'role', '')


def _get_content(msg: Any) -> str:
    if isinstance(msg, dict):
        c = msg.get('content', '')
        return c if isinstance(c, str) else str(c)
    c = getattr(msg, 'content', '')
    return c if isinstance(c, str) else str(c)
