"""
Sirius Code API — Produto independente
Agent próprio, rate manager próprio, sem depender do Sirius Open
"""
import asyncio, json, os, uuid, time, sys
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

# Configurar paths
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/providers')

# Carregar .env
from dotenv import load_dotenv
load_dotenv('/app/.env')

app = FastAPI(title="Sirius Code API", version="1.0.0")

MASTER_KEY = os.getenv("SIRIUS_MASTER_KEY", "")
API_KEYS = {}
KEYS_FILE = "/app/data/api_keys.json"

def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            API_KEYS.update(json.load(f))

def save_keys():
    os.makedirs("/app/data", exist_ok=True)
    with open(KEYS_FILE, "w") as f:
        json.dump(API_KEYS, f, indent=2)

def validate_key(key: str) -> dict:
    if not key:
        raise HTTPException(401, "API key obrigatória. Use: sirius config --key SUA_CHAVE")
    if key not in API_KEYS:
        raise HTTPException(401, "API key inválida.")
    user = API_KEYS[key]
    if user.get("credits", 0) <= 0:
        raise HTTPException(402, "Créditos insuficientes. Recarregue em siriusopen.ai")
    return user

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    context_dir: str = "."
    channel: str = "cli"

class KeyRequest(BaseModel):
    name: str
    email: str
    credits: int = 100

@app.on_event("startup")
async def startup():
    load_keys()
    if MASTER_KEY and MASTER_KEY not in API_KEYS:
        API_KEYS[MASTER_KEY] = {
            "name": "Admin",
            "email": "admin@siriusopen.ai",
            "credits": 999999,
            "created_at": time.time()
        }
        save_keys()

@app.get("/")
async def root():
    return {"product": "Sirius Code", "version": "1.0.0", "status": "online"}

@app.get("/status")
async def status(x_api_key: str = Header(None)):
    validate_key(x_api_key)
    return {"ok": True, "message": "Sirius Code online"}

@app.post("/api/cli/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(None)):
    user = validate_key(x_api_key)

    async def generate():
        session_id = req.session_id or str(uuid.uuid4())
        yield f"data: {json.dumps({'event': 'session', 'session_id': session_id})}\n\n"
        try:
            from agent import run_agent
            # Inicializar DB
            from memory import init_db
            await init_db()

            user_id = f"sc_{x_api_key[:8]}"
            result = await run_agent(user_id, req.message, username=user.get("name","user"))

            # Descontar crédito
            API_KEYS[x_api_key]["credits"] -= 1
            API_KEYS[x_api_key]["total_calls"] = API_KEYS[x_api_key].get("total_calls", 0) + 1
            save_keys()

            yield f"data: {json.dumps({'event': 'done', 'text': result})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/admin/keys")
async def create_key(req: KeyRequest, x_api_key: str = Header(None)):
    if x_api_key != MASTER_KEY:
        raise HTTPException(403, "Acesso negado")
    new_key = "sk-sirius-" + str(uuid.uuid4()).replace("-", "")[:32]
    API_KEYS[new_key] = {
        "name": req.name,
        "email": req.email,
        "credits": req.credits,
        "created_at": time.time(),
        "total_calls": 0
    }
    save_keys()
    return {"key": new_key, "name": req.name, "credits": req.credits}

@app.get("/admin/keys")
async def list_keys(x_api_key: str = Header(None)):
    if x_api_key != MASTER_KEY:
        raise HTTPException(403, "Acesso negado")
    return {"keys": [
        {"key": k[:20]+"...", "name": v["name"], 
         "credits": v["credits"], "calls": v.get("total_calls",0)}
        for k, v in API_KEYS.items()
    ]}
