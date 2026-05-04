"""
Sirius Code API — Produto independente
Agent próprio, rate manager próprio, sem depender do Sirius Open
"""
import asyncio, json, os, uuid, time, sys
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, '/app')
sys.path.insert(0, '/app/providers')

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

def validate_key(key):
    if not key:
        raise HTTPException(401, "API key obrigatoria. Use: sirius config --key SUA_CHAVE")
    if key not in API_KEYS:
        raise HTTPException(401, "API key invalida.")
    user = API_KEYS[key]
    if user.get("credits", 0) <= 0:
        raise HTTPException(402, "Creditos insuficientes. Recarregue em siriusopen.ai")
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

_LONG_FIELDS = {"content", "old_str", "new_str", "old", "new", "text", "body", "code"}
def _truncate_arg(k, v):
    s = str(v)
    return s[:1500] if k in _LONG_FIELDS else s[:120]

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

@app.get("/api/cli/usage")
async def usage(x_api_key: str = Header(None)):
    user = validate_key(x_api_key)
    return {
        "name": user.get("name", ""),
        "credits_remaining": user.get("credits", 0),
        "total_calls": user.get("total_calls", 0),
        "total_tools": user.get("total_tools", 0),
        "total_credits_used": user.get("total_credits_used", 0),
    }

@app.post("/api/cli/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(None)):
    user = validate_key(x_api_key)

    async def generate():
        session_id = req.session_id or str(uuid.uuid4())
        yield "data: " + json.dumps({"event": "session", "session_id": session_id}) + chr(10)+chr(10)
        try:
            from agent import run_agent
            from memory import init_db
            await init_db()
            user_id = f"sc_{x_api_key[:8]}"

            queue = asyncio.Queue()
            tools_count = [0]

            def on_tool_start(tool_name, args):
                tools_count[0] += 1
                try:
                    safe_args = {k: _truncate_arg(k, v) for k, v in (args or {}).items()}
                except Exception:
                    safe_args = {}
                queue.put_nowait(json.dumps({
                    "event": "tool_start",
                    "name": tool_name,
                    "args": safe_args
                }))

            def on_tool_result(result):
                queue.put_nowait(json.dumps({
                    "event": "tool_result",
                    "result": str(result)[:500]
                }))

            progress = {
                "text": "",
                "on_tool_start": on_tool_start,
                "on_tool_result": on_tool_result,
            }

            agent_task = asyncio.create_task(
                run_agent(user_id, req.message, username="cli", progress=progress)
            )

            while not agent_task.done():
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield "data: " + evt + chr(10)+chr(10)
                except asyncio.TimeoutError:
                    continue

            while not queue.empty():
                evt = queue.get_nowait()
                yield "data: " + evt + chr(10)+chr(10)

            result = agent_task.result()

            credits_used = 1 + tools_count[0]
            API_KEYS[x_api_key]["credits"] = max(0, API_KEYS[x_api_key].get("credits", 0) - credits_used)
            API_KEYS[x_api_key]["total_calls"] = API_KEYS[x_api_key].get("total_calls", 0) + 1
            API_KEYS[x_api_key]["total_tools"] = API_KEYS[x_api_key].get("total_tools", 0) + tools_count[0]
            API_KEYS[x_api_key]["total_credits_used"] = API_KEYS[x_api_key].get("total_credits_used", 0) + credits_used
            save_keys()
            yield "data: " + json.dumps({
                "event": "done",
                "text": result,
                "credits_used": credits_used,
                "tools_count": tools_count[0]
            }) + chr(10)+chr(10)
        except Exception as e:
            yield "data: " + json.dumps({"event": "error", "message": str(e)}) + chr(10)+chr(10)

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
