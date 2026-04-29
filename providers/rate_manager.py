import time, asyncio
from collections import defaultdict

class RateManager:
    RATE_LIMITS = {
        'cerebras':   {'rpm': 30,  'cooldown': 62},
        'groq':       {'rpm': 28,  'cooldown': 62},
        'gemini':     {'rpm': 14,  'cooldown': 62},
        'deepseek':   {'rpm': 999, 'cooldown': 0},
        'openai':     {'rpm': 60,  'cooldown': 62},
    }
    PRIORITY = ['cerebras', 'groq', 'gemini', 'openai', 'deepseek']

    def __init__(self):
        self._requests = defaultdict(list)
        self._cooldowns = {}
        self._errors = defaultdict(int)

    def _clean(self, p):
        now = time.time()
        self._requests[p] = [t for t in self._requests[p] if now - t < 60]

    def in_cooldown(self, p):
        return time.time() < self._cooldowns.get(p, 0)

    def cooldown_left(self, p):
        return max(0, self._cooldowns.get(p, 0) - time.time())

    def can_use(self, p):
        if self.in_cooldown(p): return False
        self._clean(p)
        return len(self._requests[p]) < self.RATE_LIMITS.get(p, {}).get('rpm', 999)

    def record_request(self, p):
        self._requests[p].append(time.time())

    def record_success(self, p):
        self._errors[p] = 0

    def record_error(self, p, err=''):
        self._errors[p] += 1
        rate_kw = ['rate','limit','429','quota','exceeded','too many']
        cd = self.RATE_LIMITS.get(p, {}).get('cooldown', 60)
        if any(k in str(err).lower() for k in rate_kw):
            self._cooldowns[p] = time.time() + cd
            print(f'[RATE] {p} cooldown {cd}s (rate limit)')
        elif self._errors[p] >= 3:
            self._cooldowns[p] = time.time() + 30
            print(f'[RATE] {p} cooldown 30s (3 erros)')

    def best(self, available):
        ordered = [p for p in self.PRIORITY if p in available]
        ordered += [p for p in available if p not in ordered]
        for p in ordered:
            if self.can_use(p):
                return p
        # todos em cooldown - retorna o que vai liberar mais cedo
        soonest = min(ordered, key=lambda p: self.cooldown_left(p), default=None)
        if soonest:
            print(f'[RATE] Todos em cooldown. Mais rapido: {soonest} ({self.cooldown_left(soonest):.0f}s)')
        return soonest

    async def wait_best(self, available, timeout=120):
        start = time.time()
        while time.time() - start < timeout:
            p = self.best(available)
            if p and self.can_use(p):
                return p
            wait = min(5, self.cooldown_left(p) if p else 5)
            print(f'[RATE] Aguardando {wait:.0f}s...')
            await asyncio.sleep(wait)
        return self.best(available)

    def status(self):
        out = {}
        for p in self.RATE_LIMITS:
            self._clean(p)
            out[p] = {
                'ok': self.can_use(p),
                'cooldown': round(self.cooldown_left(p)),
                'rpm_usado': len(self._requests[p]),
                'rpm_limite': self.RATE_LIMITS[p]['rpm'],
            }
        return out

_rm = None
def get_rate_manager():
    global _rm
    if _rm is None: _rm = RateManager()
    return _rm
