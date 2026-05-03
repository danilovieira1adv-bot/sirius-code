"""
subagent.py — Sub-agents com contexto isolado para tarefas longas.

Técnica: chama run_agent() com user_id temporário único.
Como run_agent carrega histórico pelo user_id, um ID novo = contexto limpo.
O pai passa apenas o prompt da tarefa; o sub-agent executa e retorna só o resultado.
Histórico temporário é apagado após execução.

Uso como tool no agent.py:
    result = await run_subagent(
        parent_user_id="123",
        task="Analise o repo github.com/x/y e liste os arquivos principais",
        context="Projeto Python, foco em performance"
    )
"""
from __future__ import annotations
import asyncio
import hashlib
import time
from typing import Optional

# Limite de chars do resultado retornado ao agente pai
RESULT_MAX_CHARS = 2000


async def run_subagent(
    parent_user_id: str,
    task: str,
    context: str = "",
    timeout: int = 120,
) -> str:
    """
    Executa uma tarefa em sub-agent com contexto isolado.

    Args:
        parent_user_id: user_id do agente pai (para gerar ID único)
        task: descrição completa da tarefa a executar
        context: contexto adicional relevante (opcional, max 500 chars)
        timeout: timeout em segundos (padrão: 120s)

    Returns:
        Resultado final do sub-agent (max RESULT_MAX_CHARS chars)
    """
    from agent import run_agent
    from memory import clear_history

    # ID isolado: sub_{hash do pai+task+timestamp}
    uid_hash = hashlib.md5(
        f"{parent_user_id}:{task[:50]}:{time.time()}".encode()
    ).hexdigest()[:10]
    sub_user_id = f"sub_{uid_hash}"

    # Monta prompt completo para o sub-agent
    ctx_block = f"\n\nCONTEXTO ADICIONAL:\n{context[:500]}" if context else ""
    full_prompt = (
        f"[TAREFA DELEGADA — execute e retorne apenas o resultado final]\n\n"
        f"{task}"
        f"{ctx_block}\n\n"
        f"INSTRUÇÕES: Execute a tarefa completamente. "
        f"Responda com o resultado final de forma objetiva e completa. "
        f"Não peça confirmações."
    )

    print(f"[subagent] Iniciando {sub_user_id} | tarefa: {task[:80]}...")
    t0 = time.time()

    try:
        result = await asyncio.wait_for(
            run_agent(
                user_id=sub_user_id,
                user_message=full_prompt,
                username="subagent",
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = f"[Sub-agent timeout após {timeout}s]"
    except Exception as e:
        result = f"[Sub-agent erro: {str(e)[:200]}]"
    finally:
        # Limpa histórico temporário do sub-agent
        try:
            await clear_history(sub_user_id)
        except Exception:
            pass

    elapsed = time.time() - t0
    result_str = str(result) if result else "[sem resultado]"

    # Trunca resultado longo
    if len(result_str) > RESULT_MAX_CHARS:
        result_str = (
            result_str[:RESULT_MAX_CHARS]
            + f"\n...[resultado truncado, {len(result_str) - RESULT_MAX_CHARS} chars omitidos]"
        )

    print(f"[subagent] {sub_user_id} concluído em {elapsed:.1f}s | {len(result_str)} chars")
    return result_str
