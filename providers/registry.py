import os
from dataclasses import dataclass
from openai import AsyncOpenAI
import httpx

@dataclass
class Provider:
    name: str
    label: str
    base_url: str
    api_key: str
    models: list
    default_model: str
    context_window: int
    free: bool

def _key(e): return os.getenv(e,'')

PROVIDERS = {
  'cerebras': Provider(name='cerebras',label='Cerebras',base_url=os.getenv('CEREBRAS_BASE_URL','https://api.cerebras.ai/v1'),api_key=_key('CEREBRAS_API_KEY'),models=['qwen-3-235b-a22b-instruct-2507','llama3.1-8b'],default_model='qwen-3-235b-a22b-instruct-2507',context_window=8192,free=True),
  'deepseek': Provider(name='deepseek',label='DeepSeek',base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1'),api_key=_key('DEEPSEEK_API_KEY'),models=['deepseek-chat','deepseek-reasoner'],default_model='deepseek-chat',context_window=64000,free=False),
  'groq': Provider(name='groq',label='Groq',base_url=os.getenv('GROQ_BASE_URL','https://api.groq.com/openai/v1'),api_key=_key('GROQ_API_KEY'),models=['llama-3.3-70b-versatile','llama-3.1-8b-instant'],default_model='llama-3.3-70b-versatile',context_window=128000,free=True),
  'gemini': Provider(name='gemini',label='Gemini',base_url=os.getenv('GEMINI_BASE_URL','https://generativelanguage.googleapis.com/v1beta/openai'),api_key=_key('GEMINI_API_KEY'),models=['gemini-2.5-flash','gemini-2.0-flash'],default_model='gemini-2.5-flash',context_window=1000000,free=True),
  'openai': Provider(name='openai',label='OpenAI',base_url=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'),api_key=_key('OPENAI_API_KEY'),models=['gpt-4o','gpt-4o-mini'],default_model='gpt-4o-mini',context_window=128000,free=False),
}

def get_provider(name):
  p=PROVIDERS.get(name)
  if not p: raise ValueError(f'Provedor {name} nao encontrado')
  if not p.api_key: raise ValueError(f'Provedor {p.label} sem chave no .env')
  return p

def get_client(name):
  p=get_provider(name)
  return AsyncOpenAI(api_key=p.api_key,base_url=p.base_url,http_client=httpx.AsyncClient(timeout=180.0))

def list_available(): return [p for p in PROVIDERS.values() if p.api_key]

def default_provider_name(): return os.getenv('DEFAULT_PROVIDER','cerebras')
