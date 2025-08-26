from openai import AsyncOpenAI
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
import asyncpg, os, logging
from pathlib import Path
from .packages import whatsapp, env, db, prompts, action as act

logging.basicConfig(level=logging.INFO)
logging.info("App has started! 1")

# --- GLOBAL STATE ---
chat_history = {}
input_maps   = {}

# --- paths & jinja (create ONCE) ---
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

logging.info("CWD: %s", os.getcwd())
logging.info("BASE_DIR: %s", BASE_DIR)
logging.info("TEMPLATES_DIR: %s (exists=%s)", TEMPLATES_DIR, TEMPLATES_DIR.exists())
logging.info("INDEX_HTML: %s (exists=%s)", TEMPLATES_DIR / "index.html", (TEMPLATES_DIR / "index.html").exists())

_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logging.info("Jinja loader searchpath: %s", getattr(_templates.env.loader, "searchpath", "N/A"))
try:
    _ = _templates.env.get_template("index.html")
    logging.info("Jinja can load index.html at startup ✅")
except Exception:
    logging.exception("Jinja failed to load index.html at startup ❌")

# --- FASTAPI APP ---
app = FastAPI()
app.state.templates = _templates   # single source of truth

# ---------- Health Check -------
@app.get("/healthz")
def healthz():
    return {"ok": True}

# ---------- Startup & Shutdown ----------
@app.on_event("startup")
async def startup():
    logging.info("App has started! 2")
    logging.info("environ = " + os.environ.get('WEBSITE_SITE_NAME', 'localhost'))

    env.initEnv()
    print("env.OPEN_AI_KEY =", env.OPEN_AI_KEY)

    app.state.db_pool = await asyncpg.create_pool(
        env.databaseUrl(),
        min_size=1,
        max_size=10,
        command_timeout=60,
    )
    app.state.pg = db.pgDB(app.state.db_pool)
    db.init_global(app.state.pg)
    act.init_global(app.state.pg, input_maps)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

# --- OpenAI async client ---
async_client = AsyncOpenAI(api_key=os.getenv("OPEN_AI_KEY"))

async def chat_gpt(tel_str):
    try:
        tools = prompts.prompts['initial']['tools']
        response = await async_client.chat.completions.create(
            model="gpt-4o",
            messages=chat_history[tel_str],
            tools=tools,
            tool_choice="auto",
        )
        return response.choices[0].message
    except Exception as e:
        return f"chat_gpt error: {e}"

# ---- chat helpers ----
def resetChatHistory(tel_str):
    prompt = prompts.prompts['initial']['prompt']
    chat_history[tel_str] = [{'role': 'system', 'content': prompt}]

def limitChatHistory(tel_str):
    if len(chat_history[tel_str]) > 10:
        chats = chat_history[tel_str][-10:]
        resetChatHistory(tel_str)
        chat_history[tel_str] += chats

async def agentResponse(ask_text, tel_str):
    try:
        db.step = 2
        if tel_str not in chat_history:
            db.step = 3
            resetChatHistory(tel_str)

        if ask_text:
            db.step = 4
            map_entry = input_maps.get(tel_str, "")
            if map_entry and ask_text in map_entry:
                db.step = 5
                ask_text = map_entry[ask_text]

            db.step = 6
            chat_history[tel_str].append({'role': 'user', 'content': ask_text})
            assistant_msg = await chat_gpt(tel_str)
            chat_history[tel_str].append(assistant_msg)

            if hasattr(assistant_msg, "tool_calls"):
                db.step = 7
                if tel_str in input_maps:
                    input_maps.pop(tel_str)

                user = await db.getUser(tel_str)
                tool_obj = assistant_msg.tool_calls[0].function
                result = await act.parseAsk(user, tool_obj)

                if result.get('func') == 'clear_before':
                    resetChatHistory(tel_str)

                if result.get('chat'):
                    chat_history[tel_str].append({
                        "role": "tool",
                        "tool_call_id": assistant_msg.tool_calls[0].id,
                        "content": result['chat']
                    })

                if result.get('memory'):
                    chat_history[tel_str].append({"role": "system", "content": result['memory']})

                if result.get('retry'):
                    chat_history[tel_str].append({"role": "system", "content": result['retry']})
                    assistant_msg = await chat_gpt(tel_str)
                    if hasattr(assistant_msg, "tool_calls"):
                        chat_history[tel_str].append(assistant_msg)
                    else:
                        reply = str(assistant_msg.content.strip())
                else:
                    reply = result.get('reply', '')

                if result.get('func') == 'clear_after':
                    resetChatHistory(tel_str)

                limitChatHistory(tel_str)

            else:
                reply = str(assistant_msg.content.strip())

            await db.logChat(tel_str, ask_text, reply)
        return str(reply), True

    except Exception as e:
        resetChatHistory(tel_str)
        err_str = f"\n\n ----------->\n Ask error, step = {db.step}: {e}"
        print(err_str)
        reply = "I am really sorry, but I have a sudden memory lapse. Could you please start from the beginning?"
        return err_str, False

# ----------- Routes ---------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # log the active searchpath so you can verify at request time
    sp = getattr(request.app.state.templates.env.loader, "searchpath", None)
    logging.info("TEMPLATES id=%s searchpath=%s", id(request.app.state.templates), sp)
    return request.app.state.templates.TemplateResponse("index.html", {"request": request})

@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == env.waVerifyToken():
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    result = whatsapp.parse_incoming_message(body)
    if result:
        ask_text, tel_str = result
        reply, _success = await agentResponse(ask_text, tel_str)
        await whatsapp.respond_to_client(reply, tel_str)

@app.post("/ask")
async def ask(request: Request):
    db.step = 1
    body = await request.json()
    ask_text = body.get("Ask", "").strip()
    tel_str  = str(body.get("Telephone", "").strip())
    reply, _success = await agentResponse(ask_text, tel_str)
    return {"History": ask_text + '\n\n' + str(reply)}

@app.post("/clear")
async def clear():
    return 'Cleared'

@app.post("/reset")
async def reset():
    return "Reset"
