"""
tool_cache.py — Cache TTL para resultados de tools idempotentes.

Comandos read-only (docker ps, ls, cat, git status...) são cacheados
por TTL_SHELL segundos. Segunda chamada idêntica: 0 tokens, 0 latência.

Comandos com efeitos colaterais (write, rm, pip install...) NUNCA são cacheados.

Integração em agent.py — substituir as funções _shell e _read_file:
    from tool_cache import cached_shell, cached_read_file
    ...
    'run_shell':  cached_shell,
    'read_file':  cached_read_file,
"""
from __future__ import annotations
import asyncio
import hashlib
import re
import time
from typing import Any, Callable, Coroutine

# TTL em segundos
TTL_SHELL = int(__import__('os').getenv("TOOL_CACHE_TTL_SHELL", "60"))
TTL_FILE  = int(__import__('os').getenv("TOOL_CACHE_TTL_FILE",  "30"))

# Tamanho máximo do cache (entradas)
MAX_ENTRIES = 150

# Padrões de comandos que NUNCA devem ser cacheados (escrita/efeitos)
_WRITE_PATTERNS = re.compile(
    r'\b(pip\s+install|apt|apt-get|npm\s+install|yarn\s+add|'
    r'docker\s+(run|start|stop|rm|restart|build|pull|push|exec\s+-[a-z]*i)|'
    r'git\s+(commit|push|pull|clone|checkout|merge|rebase|reset|add)|'
    r'rm\s|mv\s|cp\s|mkdir|touch|chmod|chown|kill|pkill|'
    r'systemctl|service\s|cron|'
    r'>\s*\S|>>\s*\S|'           # redirecionamentos de escrita
    r'tee\s|dd\s|truncate|'
    r'curl\s.*-[dXPpouT]|wget\s.*-[oO]|'  # HTTP com escrita
    r'python3?\s+.*\.(py)|'      # execução de scripts Python
    r'bash\s+|sh\s+)',
    re.IGNORECASE
)

# Padrões de comandos sabidamente read-only (cacheáveis)
_READ_PATTERNS = re.compile(
    r'^(docker\s+(ps|stats|inspect|images|logs|top|version|info)|'
    r'ls(\s|$)|ll(\s|$)|find\s|cat\s|head\s|tail\s|grep\s|'
    r'git\s+(status|log|diff|show|branch|remote|tag|stash\s+list)|'
    r'ps\s|top\s|htop|free(\s|$)|df(\s|$)|du(\s|$)|uname|'
    r'echo\s|printf\s|env(\s|$)|printenv|'
    r'which\s|whereis\s|type\s|'
    r'cat\s+/proc|cat\s+/sys|'
    r'ping\s|curl\s+-[sS]?[gGI]|'
    r'wc\s|sort\s|uniq\s|awk\s|sed\s+-n)',
    re.IGNORECASE
)


class _TTLCache:
    """Cache em memória com TTL e LRU simples."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._store: dict[str, tuple[Any, float]] = {}
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    def _key(self, *parts: str) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, *key_parts: str) -> tuple[bool, Any]:
        k = self._key(*key_parts)
        entry = self._store.get(k)
        if entry is None:
            self._misses += 1
            return False, None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[k]
            self._misses += 1
            return False, None
        self._hits += 1
        return True, value

    def set(self, value: Any, ttl: int, *key_parts: str) -> None:
        if len(self._store) >= self._max:
            # Remove a entrada mais antiga
            oldest = min(self._store.items(), key=lambda x: x[1][1])
            del self._store[oldest[0]]
        k = self._key(*key_parts)
        self._store[k] = (value, time.time() + ttl)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove entradas cujos valores contenham o prefixo."""
        to_delete = [k for k, (v, _) in self._store.items() if prefix in str(v)]
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    @property
    def stats(self) -> dict:
        now = time.time()
        active = sum(1 for _, (_, exp) in self._store.items() if exp > now)
        total = self._hits + self._misses
        ratio = f"{100*self._hits//total}%" if total else "n/a"
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": ratio,
            "active_entries": active,
        }


# Singleton global
_cache = _TTLCache()


def _is_cacheable_shell(command: str) -> bool:
    """Retorna True se o comando é seguro para cachear."""
    cmd = command.strip()
    # Primeiro verifica se tem padrão de escrita — sempre rejeita
    if _WRITE_PATTERNS.search(cmd):
        return False
    # Pipe com comandos de escrita
    if "|" in cmd:
        parts = cmd.split("|")
        if any(_WRITE_PATTERNS.search(p.strip()) for p in parts):
            return False
    # Verifica se é explicitamente read-only
    return bool(_READ_PATTERNS.match(cmd))


def make_cached_shell(original_shell_fn: Callable) -> Callable:
    """
    Retorna versão cacheada de _shell.
    Uso: cached_shell = make_cached_shell(_shell)
    """
    async def cached_shell(command: str, **kwargs) -> str:
        if not _is_cacheable_shell(command):
            return await original_shell_fn(command, **kwargs)

        hit, cached_result = _cache.get("shell", command)
        if hit:
            print(f"[tool_cache] HIT shell: {command[:60]}")
            return f"{cached_result} [cache]"

        result = await original_shell_fn(command, **kwargs)

        # Só cacheia resultados bem-sucedidos
        if result and "Erro" not in result[:20] and "Timeout" not in result[:20]:
            _cache.set(result, TTL_SHELL, "shell", command)

        return result

    return cached_shell


def make_cached_read_file(original_read_fn: Callable) -> Callable:
    """
    Retorna versão cacheada de _read_file.
    Uso: cached_read_file = make_cached_read_file(_read_file)
    """
    async def cached_read_file(filename: str, **kwargs) -> str:
        hit, cached_result = _cache.get("file", filename)
        if hit:
            print(f"[tool_cache] HIT file: {filename}")
            return f"{cached_result} [cache]"

        result = await original_read_fn(filename, **kwargs)

        if result and "nao encontrado" not in result.lower():
            _cache.set(result, TTL_FILE, "file", filename)

        return result

    return cached_read_file


def get_cache_stats() -> dict:
    return _cache.stats


def invalidate_file(filename: str) -> None:
    """Invalida cache de um arquivo após write_file."""
    _cache.invalidate_prefix(filename)
