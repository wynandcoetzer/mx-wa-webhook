import openai
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
import asyncpg, os
from .packages import whatsapp, env, db, prompts, action as act
import logging

logging.basicConfig(level=logging.INFO)
logging.info("App has started! 1")

# --- GLOBAL STATE ---
chat_history = {}
input_maps   = {}

# --- Open AI ---
#openai.api_key = env.OPEN_AI_KEY


def resetChatHistory(tel_str):
    prompt                   = prompts.prompts['initial']['prompt']
    chat_history[tel_str]    = [{'role': 'system', 'content': prompt}]
    #print("chat_history 1 =", chat_history[tel_str])

def limitChatHistory(tel_str):
    beg_len   = len(chat_history[tel_str])
    if len(chat_history[tel_str]) > 10:
        chats = chat_history[tel_str][-10:]
        resetChatHistory(tel_str)
        chat_history[tel_str]   += chats
    #print("chat_history len beg=", beg_len, ", after len =", len(chat_history[tel_str]), ", tel_str =", tel_str)


# --- FASTAPI APP ---
app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

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
    openai.api_key = env.OPEN_AI_KEY
    print("env.OPEN_AI_KEY =", env.OPEN_AI_KEY)

    # Create pool once for the app
    app.state.db_pool = await asyncpg.create_pool(
        env.databaseUrl(),
        min_size=1,      # minimum number of connections
        max_size=10,     # maximum number of connections
        command_timeout=60
    )
    app.state.pg = db.pgDB(app.state.db_pool)
    db.init_global(app.state.pg)  # 👈 pass pg into db package
    act.init_global(app.state.pg, input_maps)  # 👈 pass pg into action package

    print("environ = ", os.environ.get('WEBSITE_SITE_NAME', 'localhost'))


@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()



# -------- chat GPT -----
async def chat_gpt(tel_str):
    try:
        #print("chat_history 2 =", chat_history[tel_str])
        tools    = prompts.prompts['initial']['tools']
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o",
            messages =  chat_history[tel_str],
            tools = tools,
            tool_choice="auto",
        )

        assistant_msg = response.choices[0].message
        #print("assistent_msg =", assistant_msg)
        #chat_history[tel_str].append(assistant_msg)
        #print(chat_history[tel_str])

        return assistant_msg
    except Exception as e:
        return f"chat_gpt error: {e}"


# ---------------- process user message with help of ChatGpt -------
async def agentResponse(ask_text, tel_str):
    print("agentResponse ask_text =", ask_text, " ,tel_str =", tel_str)
    try:
        db.step = 2
        #print("telephone =", tel_str, "ask_text =", ask_text)

        if tel_str not in chat_history:
            db.step = 3
            resetChatHistory(tel_str)

        if ask_text:
            db.step = 4
            map_entry = input_maps.get(tel_str, "")
            if map_entry and ask_text in map_entry:
                db.step = 5
                ask_text = map_entry[ask_text]  # map user input if exists

            db.step = 6
            # Append user message first
            chat_history[tel_str].append({'role': 'user', 'content': ask_text})

            # Call GPT
            assistant_msg = await chat_gpt(tel_str)

            # --- ✅ append assistant message BEFORE processing tool_calls ---
            chat_history[tel_str].append(assistant_msg)

            if hasattr(assistant_msg, "tool_calls"):

                db.step = 7
                if tel_str in input_maps:
                    db.step = 8
                    input_maps.pop(tel_str)

                user     = await db.getUser(tel_str)
                db.step  = 9

                
                tool_obj = assistant_msg.tool_calls[0].function
                result   = await act.parseAsk(user, tool_obj)
                #print("\nresult =", result)

                # Handle clearing history before tool execution
                if result.get('func', '') == 'clear_before':
                    resetChatHistory(tel_str)

                # Append tool response
                if result.get('chat'):
                    db.step = 10
                    tool_rec = {
                        "role": "tool",
                        "tool_call_id": assistant_msg.tool_calls[0].id,
                        "content": result['chat']
                    }
                    chat_history[tel_str].append(tool_rec)

                # Append memory to chat history (system role, no tool_call_id)
                if result.get('memory'):
                    db.step = 21
                    mem_rec = {
                        "role": "system",
                        "content": result['memory']
                    }
                    chat_history[tel_str].append(mem_rec)

                # Handle INVALID / AMBIGUOUS retry
                if result.get('retry'):
                    db.step = 11
                    retry_rec = {
                        "role": "system",
                        "content": result['retry']
                    }
                    chat_history[tel_str].append(retry_rec)

                    # Call GPT again so it can politely re-ask
                    assistant_msg = await chat_gpt(tel_str)
                    db.step = 12
                    #print("assistant_msg 12 =", assistant_msg)

                    if hasattr(assistant_msg, "tool_calls"):
                        chat_history[tel_str].append(assistant_msg)
                        print("\n~~~~~~~~assistant_msg tool_calls =", assistant_msg)
                    else:
                        reply = str(assistant_msg.content.strip())
                else:
                    reply = result.get('reply', '')

                # Handle clearing history after tool execution
                if result.get('func', '') == 'clear_after':
                    resetChatHistory(tel_str)

                limitChatHistory(tel_str)

            else:
                db.step = 15
                print("assistant_msg (no tool_calls) =", assistant_msg)
                reply = str(assistant_msg.content.strip())

            await db.logChat(tel_str, ask_text, reply)
            db.step = 16

        return str(reply), True

    except Exception as e:
        if True:
            print("\n\n==== chat history:\n")
            hist = chat_history.get(tel_str, [])
            for h in hist:
                print("\n\n========================", h)
        resetChatHistory(tel_str)
        reply = "I am really sorry, but I have a sudden memory lapse. Could you please start from the beginning?"
        err_str = f"\n\n ----------->\n Ask error, step = {db.step}: {e}"
        print(err_str)
        return err_str, False

# ----------- handle requests ----------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    #print('hub_verify_token =', hub_verify_token)
    if hub_mode == "subscribe" and hub_verify_token == env.waVerifyToken():
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def handle_webhook(
    request: Request,
    #db_user: AzureUser = Depends(get_db_user_by_wa_id),
    #db_session: Session = Depends(get_db),
    ):
    body = await request.json()
    result = whatsapp.parse_incoming_message(body)
    if result:
        ask_text   = result[1]
        tel_str    = result[0]

        reply, success    = await agentResponse(ask_text, tel_str)
        #if not success:
        #    raise HTTPException(status_code=400, detail="Invalid request")
        await whatsapp.respond_to_client(reply, tel_str)


@app.post("/ask")
async def ask(request: Request):
    global chat_history, step
    db.step= 1
    body = await request.json()
    ask_text = body.get("Ask", "").strip()
    tel_str  = str(body.get("Telephone", "").strip())
    reply, success    = await agentResponse(ask_text, tel_str)
    return {"History": ask_text + '\n\n' + str(reply)}
    if False:
        if success:
            return {"History": ask_text + '\n\n' + str(reply)}
        else:
            raise HTTPException(status_code=400, detail="Invalid request")

@app.post("/clear")
async def clear():
    #global msg_history
    #msg_history = ""
    #return {"History": msg_history}

    return 'Cleared'

@app.post("/reset")
async def reset():
    #global msg_history
    #msg_history = ""
    #return {"History": msg_history}
    return "Reset"
