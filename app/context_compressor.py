"""
context_compressor.py — Compressão semântica de contexto via LLMLingua-2.

Usa um modelo BERT leve (multilingual, ~400MB) para remover tokens
redundantes do histórico mantendo o significado.

Ativado automaticamente quando o contexto total ultrapassa COMPRESS_THRESHOLD chars.
Taxa de compressão padrão: 0.5 (mantém 50% dos tokens — preserva sentido).

Uso no agent.py:
    from context_compressor import maybe_compress_messages
    messages = maybe_compress_messages(messages)
"""
from __future__ import annotations
import threading
from typing import Any

# Threshold: só comprime se contexto total > N chars
COMPRESS_THRESHOLD = int(__import__('os').getenv("LLMLINGUA_THRESHOLD", "4000"))
# Taxa de compressão: 0.5 = mantém 50% dos tokens
COMPRESS_RATIO = float(__import__('os').getenv("LLMLINGUA_RATIO", "0.5"))
# Não comprime as N mensagens mais recentes (preserva contexto imediato)
KEEP_RECENT = 3

_lock = threading.Lock()
_compressor = None
_available = None  # None = não testado ainda


def _get_compressor():
    global _compressor, _available
    if _available is False:
        return None
    if _compressor is not None:
        return _compressor
    with _lock:
        if _compressor is not None:
            return _compressor
        try:
            from llmlingua import PromptCompressor
            _compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
                use_llmlingua2=True,
                device_map="cpu",
            )
            _available = True
            print("[llmlingua] Modelo carregado ✅")
            return _compressor
        except Exception as e:
            _available = False
            print(f"[llmlingua] Não disponível: {e}")
            return None


def _get_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "role", "")


def _get_content(msg: Any) -> str:
    if isinstance(msg, dict):
        c = msg.get("content", "")
        return c if isinstance(c, str) else ""
    c = getattr(msg, "content", "")
    return c if isinstance(c, str) else ""


def _set_content(msg: dict, content: str) -> dict:
    m = dict(msg)
    m["content"] = content
    return m


def _total_chars(messages: list) -> int:
    return sum(len(_get_content(m)) for m in messages)


def maybe_compress_messages(messages: list) -> list:
    """
    Comprime semanticamente as mensagens antigas do histórico se o
    contexto total ultrapassar COMPRESS_THRESHOLD.

    - Mantém system prompt intacto
    - Mantém as KEEP_RECENT mensagens mais recentes intactas
    - Comprime apenas mensagens de role user/assistant com conteúdo longo
    - Mensagens tool já comprimidas pelo stale_results são puladas
    """
    total = _total_chars(messages)
    if total <= COMPRESS_THRESHOLD:
        return messages

    compressor = _get_compressor()
    if compressor is None:
        return messages  # LLMLingua não disponível, passa sem compressão

    # Separa system, corpo comprimível e recentes
    system_msgs = [m for m in messages if _get_role(m) == "system"]
    non_system  = [m for m in messages if _get_role(m) != "system"]

    if len(non_system) <= KEEP_RECENT:
        return messages

    compressible = non_system[:-KEEP_RECENT]
    recent       = non_system[-KEEP_RECENT:]

    chars_before = sum(len(_get_content(m)) for m in compressible)
    compressed_msgs = []
    chars_after = 0

    for msg in compressible:
        role    = _get_role(msg)
        content = _get_content(msg)

        # Só comprime user/assistant com conteúdo substancial
        # Tool messages stale já foram comprimidas; system nunca chega aqui
        if role not in ("user", "assistant") or len(content) < 200:
            compressed_msgs.append(msg)
            chars_after += len(content)
            continue

        # Já tem marcador de compressão anterior?
        if "[llmlingua]" in content or "...[resumido" in content:
            compressed_msgs.append(msg)
            chars_after += len(content)
            continue

        try:
            result = compressor.compress_prompt(
                context=[content],
                rate=COMPRESS_RATIO,
                force_tokens=["\n", ".", "!", "?"],
            )
            compressed = result.get("compressed_prompt", content)

            # Garante que não ficou vazio nem cresceu
            if not compressed or len(compressed) >= len(content):
                compressed_msgs.append(msg)
                chars_after += len(content)
                continue

            # Adiciona marcador para não recomprimir
            compressed = compressed + f" [llmlingua:{len(content)}→{len(compressed)}]"
            compressed_msgs.append(_set_content(msg, compressed))
            chars_after += len(compressed)

        except Exception as e:
            # Falha silenciosa — mantém original
            compressed_msgs.append(msg)
            chars_after += len(content)

    saved = chars_before - chars_after
    if saved > 50:
        pct = int(saved / chars_before * 100) if chars_before else 0
        print(f"[llmlingua] Comprimido {saved} chars ({pct}%) no histórico")

    return system_msgs + compressed_msgs + recent
