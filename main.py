import os
import logging
import json
import asyncio
import subprocess
from contextlib import asynccontextmanager
import uuid
import time
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
from ollama import AsyncClient
from openai import AsyncOpenAI
import whisper
from responsegen import (
    generate_open_app_response,
    generate_set_timer_response,
    generate_setting_change_response,
    generate_regular_response,
    generate_record_voice_response,
    generate_web_search_response,
    generate_web_search_prompt_response,
    generate_play_music_response,
    generate_chatbot_sing_response
)
from tools import AVAILABLE_TOOLS, get_enabled_tools, get_tools_description
from multipart import extract_dialog_state, extract_audio_data, extract_text

# logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# load config
with open("config.json", "r") as f:
    config = json.load(f)

whisper_model = None
api_provider = config.get("api", {}).get("provider", "ollama")
ollama_client = None
openai_client = None

# Initialize the appropriate client based on provider
if api_provider == "ollama":
    ollama_base_url = config.get("api", {}).get("ollama", {}).get("base_url", "http://localhost:11434")
    ollama_client = AsyncClient(host=ollama_base_url)
    logger.info(f"Using Ollama API at {ollama_base_url}")
elif api_provider == "openai":
    openai_config = config.get("api", {}).get("openai", {})
    openai_client = AsyncOpenAI(
        base_url=openai_config.get("base_url", "http://localhost:8000/v1"),
        api_key=openai_config.get("api_key", "not-needed")
    )
    logger.info(f"Using OpenAI-compatible API at {openai_config.get('base_url')}")
else:
    logger.error(f"Unknown API provider: {api_provider}")
    raise ValueError(f"Unknown API provider: {api_provider}. Use 'ollama' or 'openai'")

recent_queries = deque(maxlen=10) # for web ui logging
recent_transcriptions = deque(maxlen=20)  # Store recent transcriptions with metadata
last_request_stats = None  # timing stats for last request
MAX_HISTORY_MESSAGES = config["options"]["max_history_messages"]
KEEP_AUDIO_FILES = config["options"]["keep_audio_files"]
WHISPER_LANGUAGE = config["options"]["whisper_language"]
CONVERSATION_TIMEOUT_MINUTES = config["options"]["conversation_timeout_minutes"]
FFMPEG_PATH = config["options"].get("ffmpeg_path", "ffmpeg")
DEMO_MODE = config.get("demo_mode", False)
conversation_history = {}
conversation_last_access = {}  # last access time for each conversation

# Demo conversation script
DEMO_SCRIPT = [
    {"user": "Hello.", "response": "Hello! How can I assist you today?", "tool": None},
    {"user": "Turn Bluetooth off.", "response": "Turning Bluetooth off", "tool": {"name": "change_setting", "args": {"setting_name": "bluetooth", "state": "off"}}},
    {"user": "Set a timer for 5 minutes.", "response": "Setting timer for 5 minutes", "tool": {"name": "set_timer", "args": {"canonical_time": "+00:05:00"}}},
    {"user": "What did I just ask you to do?", "response": "You asked me to set a 5-minute timer. I have done that for you.", "tool": None},
    {"user": "What date is it?", "response": "Today's date is April 4, 2026", "tool": None},
    {"user": "Open the dashboard.", "response": "Opening dashboard", "tool": {"name": "web_search", "args": {"query": f"http://{config['server']['host']}:{config['server']['port']}/dash"}}}
]
demo_conversation_step = {}


async def transcribe_audio(audio_data: bytes) -> tuple[str, dict]:
    """Convert audio data to text using Whisper."""
    stats = {"save_audio": 0, "ffmpeg_convert": 0, "whisper_transcribe": 0}

    if not audio_data:
        return "", stats

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    speex_file = f"audio_{timestamp}.speex"
    wav_file = f"audio_{timestamp}.wav"

    try:
        # Save speex file
        t0 = time.perf_counter()
        with open(speex_file, 'wb') as f:
            f.write(audio_data)
        stats["save_audio"] = time.perf_counter() - t0
        logger.info(f"Saved {len(audio_data)} bytes to {speex_file}")

        # Convert to wav
        t0 = time.perf_counter()
        result = await asyncio.to_thread(
            subprocess.run,
            [FFMPEG_PATH, '-i', speex_file, '-y', wav_file],
            capture_output=True
        )
        stats["ffmpeg_convert"] = time.perf_counter() - t0

        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed")
            return "", stats
        logger.info(f"Converted to {wav_file}")

        # Transcribe
        if whisper_model is None:
            logger.warning("Whisper model not loaded")
            return "", stats

        t0 = time.perf_counter()
        result = await asyncio.to_thread(
            whisper_model.transcribe,
            wav_file,
            fp16=False,
            language=WHISPER_LANGUAGE
        )
        stats["whisper_transcribe"] = time.perf_counter() - t0
        transcription = result.get("text", "")
        logger.info(f"Transcription: {transcription}")
        return transcription, stats

    except Exception as e:
        logger.exception(f"Error processing audio: {e}")
        return "", stats
    finally:
        if not KEEP_AUDIO_FILES:
            for f in [speex_file, wav_file]:
                if os.path.exists(f):
                    os.remove(f)


def clean_old_conversations():
    """Remove conversations that haven't been accessed recently"""
    current_time = datetime.now()
    timeout_seconds = CONVERSATION_TIMEOUT_MINUTES * 60

    expired_convs = []
    for conv_id, last_access in conversation_last_access.items():
        if (current_time - last_access).total_seconds() > timeout_seconds:
            expired_convs.append(conv_id)

    for conv_id in expired_convs:
        if conv_id in conversation_history:
            del conversation_history[conv_id]
        del conversation_last_access[conv_id]
        logger.info(f"Cleaned up expired conversation: {conv_id[:8]}...")


def get_or_create_conversation(dialog_state: dict | None) -> tuple[str, list]:
    """Get existing conversation or create new one."""
    clean_old_conversations()

    if dialog_state and "conversation_id" in dialog_state:
        conv_id = dialog_state["conversation_id"]
        history = conversation_history.get(conv_id, [])
        conversation_last_access[conv_id] = datetime.now()
        return conv_id, history

    # New conversation
    conv_id = str(uuid.uuid4())
    conversation_history[conv_id] = []
    conversation_last_access[conv_id] = datetime.now()
    return conv_id, []


def add_to_conversation(conv_id: str, user_text: str, assistant_text: str, tool_call: str = None):
    """Add a turn to conversation history."""
    if conv_id not in conversation_history:
        conversation_history[conv_id] = []

    conversation_history[conv_id].append({"role": "user", "content": user_text})

    if tool_call:
        conversation_history[conv_id].append({"role": "tool", "content": tool_call})

    conversation_history[conv_id].append({"role": "assistant", "content": assistant_text})

    # Trim to max history
    if len(conversation_history[conv_id]) > MAX_HISTORY_MESSAGES:
        conversation_history[conv_id] = conversation_history[conv_id][-MAX_HISTORY_MESSAGES:]

    # Update last access time
    conversation_last_access[conv_id] = datetime.now()

async def ai_response(transcription: str, history: list = None) -> tuple[str, list]:
    """Get AI response from configured API provider"""
    tools = get_enabled_tools()
    tools_text = get_tools_description()

    messages = [
        {
            "role": "system",
            "content": f"You are a digital voice assistant for a mobile phone. Keep responses short and concise, 1-2 sentences. The user's local time is {datetime.now()}. {tools_text}."
        }
    ]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": transcription})

    if api_provider == "ollama":
        response = await ollama_client.chat(
            model=config["models"]["llm"],
            messages=messages,
            tools=tools if tools else None,
            think=False,
            stream=False
        )
        message = response["message"]
        return message.get("content", ""), message.get("tool_calls", [])
    
    elif api_provider == "openai":
        response = await openai_client.chat.completions.create(
            model=config["models"]["llm"],
            messages=messages,
            tools=tools if tools else None,
            stream=False
        )
        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "function": {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                })
        return message.content or "", tool_calls

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load and unload Whisper model."""
    global whisper_model
    
    # Check ffmpeg availability
    try:
        result = subprocess.run(
            [FFMPEG_PATH, '-version'],
            capture_output=True,
            timeout=5,
            text=True
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0] if result.stdout else "unknown version"
            logger.info(f"ffmpeg found: {version_line}")
        else:
            logger.error(f"ffmpeg at {FFMPEG_PATH} returned error code {result.returncode}")
            raise RuntimeError(f"ffmpeg check failed")
    except FileNotFoundError:
        logger.error(f"ffmpeg not found at: {FFMPEG_PATH}")
        raise RuntimeError(f"ffmpeg not found at {FFMPEG_PATH}. Please install ffmpeg or update ffmpeg_path in config.json")
    except Exception as e:
        logger.error(f"Failed to check ffmpeg: {e}")
        raise RuntimeError(f"ffmpeg check failed: {e}")
    
    # Load Whisper model
    try:
        whisper_model_name = config["models"]["whisper"]
        logger.info(f"Loading Whisper {whisper_model_name}")
        whisper_model = whisper.load_model(whisper_model_name)
        logger.info("Whisper model loaded")
    except Exception as e:
        logger.exception("Failed to load Whisper: %s", e)
        whisper_model = None
    try:
        yield
    finally:
        logger.info("Unloading Whisper model")
        whisper_model = None

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.post("/voicepad/sr")
async def asr_endpoint(request: Request):
    global last_request_stats, demo_conversation_step
    stats = {}

    logger.info("POST /voicepad/sr")

    t0 = time.perf_counter()
    body = await request.body()
    stats["read_body"] = time.perf_counter() - t0

    # Extract dialog state
    dialog_state = extract_dialog_state(body)
    if dialog_state:
        logger.info("Dialog state received: %s", dialog_state)
    else:
        logger.info("No dialog state, new conversation")

    # Get or create conversation
    conv_id, history = get_or_create_conversation(dialog_state)
    logger.info("Conversation: %s (history: %d messages)", conv_id[:8], len(history))

    # DEMO MODE: Use scripted responses
    if DEMO_MODE:
        # Use a fixed demo conversation ID
        demo_conv_id = "demo-conversation-fixed"
        
        # Get current step for demo (ignore actual conv_id)
        step = demo_conversation_step.get(demo_conv_id, 0)
        
        if step < len(DEMO_SCRIPT):
            script_item = DEMO_SCRIPT[step]
            transcription = script_item["user"]
            response_text = script_item["response"]
            tool_info = script_item["tool"]
            
            logger.info(f"[DEMO MODE] Step {step}: '{transcription}' -> '{response_text}'")
            
            # Increment step for next request
            demo_conversation_step[demo_conv_id] = step + 1
            
            # Build dialog state with demo conv id
            turn = step + 1
            new_dialog_state = {"turn": turn, "conversation_id": demo_conv_id}
            
            # Generate appropriate response based on tool
            if tool_info:
                if tool_info["name"] == "change_setting":
                    xml = generate_setting_change_response(
                        transcription,
                        tool_info["args"]["setting_name"],
                        tool_info["args"]["state"],
                        new_dialog_state
                    )
                    tool_used = f"change_setting({tool_info['args']['setting_name']}, {tool_info['args']['state']})"
                elif tool_info["name"] == "set_timer":
                    xml = generate_set_timer_response(
                        transcription,
                        tool_info["args"]["canonical_time"],
                        new_dialog_state
                    )
                    tool_used = f"set_timer({tool_info['args']['canonical_time']})"
                elif tool_info["name"] == "web_search":
                    xml = generate_web_search_response(
                        transcription,
                        tool_info["args"]["query"],
                        new_dialog_state
                    )
                    tool_used = f"web_search({tool_info['args']['query']})"
                else:
                    xml = generate_regular_response(transcription, response_text, new_dialog_state)
                    tool_used = None
            else:
                xml = generate_regular_response(transcription, response_text, new_dialog_state)
                tool_used = None
            
            # Store in conversation history with demo conv id
            add_to_conversation(demo_conv_id, transcription, response_text, tool_used)
            
            # Add to recent queries
            recent_queries.append(transcription)
            recent_transcriptions.append({
                "id": len(recent_transcriptions),
                "timestamp": datetime.now().isoformat(),
                "transcription": transcription,
                "audio_file": None
            })
            
            # Mock stats
            stats = {
                "read_body": 0.002,
                "save_audio": 0.001,
                "ffmpeg_convert": 0.150,
                "whisper_transcribe": 0.320,
                "llm_response": 0.450,
                "xml_generation": 0.003,
                "total": 0.926
            }
            last_request_stats = stats
            
            xml = xml.replace('\n', '')
            logger.info(f"Full Response XML: {xml}")
            return Response(content=xml, media_type="text/xml")
        else:
            # Demo script finished, reset
            demo_conversation_step[demo_conv_id] = 0
            logger.info("[DEMO MODE] Script finished, resetting")

    # NORMAL MODE: Continue with regular processing
    # Try audio first, then text
    audio_data = extract_audio_data(body)
    transcription, audio_stats = await transcribe_audio(audio_data)
    stats.update(audio_stats)

    if not transcription:
        transcription = extract_text(body)
        if transcription:
            logger.info("Text input received: %s", transcription)

    if not transcription:
        logger.warning("No audio or text data found in request")
    else:
        recent_queries.append(transcription)

    # generate
    logger.info("Generating response")

    t0 = time.perf_counter()
    response_text, tool_calls = await ai_response(transcription, history)
    stats["llm_response"] = time.perf_counter() - t0

    logger.info(f"AI tool_calls: {tool_calls}")

    t0 = time.perf_counter()

    # Determine the response text for history storage
    final_response_text = response_text or "I'm not sure how to help with that."

    # Build new dialog state with conversation_id
    turn = (dialog_state.get("turn", 0) + 1) if dialog_state else 1
    new_dialog_state = {"turn": turn, "conversation_id": conv_id}

    # Check if AI wants to use any tools
    tool_used = None
    if tool_calls:
        for tool_call in tool_calls:
            if tool_call["function"]["name"] == "open_app":
                app_name = tool_call["function"]["arguments"]["app_name"]
                logger.info("AI requested to open app: %s", app_name)
                xml = generate_open_app_response(transcription, app_name, new_dialog_state)
                final_response_text = f"Opening {app_name}"
                tool_used = f"open_app({app_name})"
                break
            elif tool_call["function"]["name"] == "set_timer":
                canonical_time = tool_call["function"]["arguments"]["canonical_time"]
                logger.info("AI requested to set timer: %s", canonical_time)
                xml = generate_set_timer_response(transcription, canonical_time, new_dialog_state)
                final_response_text = f"Setting timer for {canonical_time}"
                tool_used = f"set_timer({canonical_time})"
                break
            elif tool_call["function"]["name"] == "change_setting":
                setting_name = tool_call["function"]["arguments"]["setting_name"]
                state = tool_call["function"]["arguments"]["state"]
                logger.info("AI requested to change setting: %s to %s", setting_name, state)
                xml = generate_setting_change_response(transcription, setting_name, state, new_dialog_state)
                final_response_text = f"Changing {setting_name} to {state}"
                tool_used = f"change_setting({setting_name}, {state})"
                break
            elif tool_call["function"]["name"] == "record_voice":
                title = tool_call["function"]["arguments"].get("title")
                logger.info("AI requested to start voice recording with title: %s", title)
                xml = generate_record_voice_response(transcription, title, new_dialog_state)
                final_response_text = "Starting voice recording"
                tool_used = f"record_voice({title or ''})"
                break
            elif tool_call["function"]["name"] == "web_search":
                query = tool_call["function"]["arguments"]["query"]
                logger.info("AI requested web search for: %s", query)
                xml = generate_web_search_response(transcription, query, new_dialog_state)
                final_response_text = f"Searching for {query}"
                tool_used = f"web_search({query})"
                break
            elif tool_call["function"]["name"] == "web_search_prompt":
                logger.info("AI requested web search prompt")
                xml = generate_web_search_prompt_response(transcription, transcription, new_dialog_state)
                final_response_text = "Here's a search option"
                tool_used = "web_search_prompt()"
                break
            elif tool_call["function"]["name"] == "play_music":
                play_type = tool_call["function"]["arguments"].get("play_type", "PLAY")
                name = tool_call["function"]["arguments"].get("name")
                logger.info("AI requested music control: %s%s", play_type, f" - {name}" if name else "")
                xml = generate_play_music_response(transcription, play_type, name, new_dialog_state)
                final_response_text = f"Music: {play_type}" + (f" {name}" if name else "")
                tool_used = f"play_music({play_type}" + (f", {name})" if name else ")")
                break
            elif tool_call["function"]["name"] == "chatbot_sing":
                logger.info("AI requested ChatbotSing")
                xml = generate_chatbot_sing_response(transcription, new_dialog_state)
                final_response_text = "Singing"
                tool_used = "chatbot_sing()"
                break
        else:
            # No recognized tool calls, generate regular response
            logger.info(f"No recognized tool calls, generating regular response: {final_response_text}")
            xml = generate_regular_response(transcription, final_response_text, new_dialog_state)
    else:
        # No tool calls, generate regular response
        logger.info(f"Got regular response: {final_response_text}")
        xml = generate_regular_response(transcription, final_response_text, new_dialog_state)

    # Store in conversation history
    if transcription:
        add_to_conversation(conv_id, transcription, final_response_text, tool_used)

    # Remove newlines
    xml = xml.replace('\n', '')
    stats["xml_generation"] = time.perf_counter() - t0

    stats["total"] = sum(stats.values())
    last_request_stats = stats

    # Log the response
    logger.info(f"Full Response XML: {xml}")

    return Response(content=xml, media_type="text/xml")

@app.get("/dash")
async def dashboard(request: Request):
    """Render the dashboard page."""
    demo_mode = request.query_params.get("demo") == "1"
    
    if demo_mode:
        # Scripted demo conversation
        demo_conversations = {
            "demo-conv-001": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "Hello! How can I assist you today?"},
                {"role": "user", "content": "turn bluetooth off"},
                {"role": "tool", "content": "change_setting(bluetooth, off)"},
                {"role": "assistant", "content": "Turning Bluetooth off"},
                {"role": "user", "content": "set a timer for 5 minutes"},
                {"role": "tool", "content": "set_timer(+00:05:00)"},
                {"role": "assistant", "content": "Setting timer for 5 minutes"},
                {"role": "user", "content": "what did i just ask you to do?"},
                {"role": "assistant", "content": "You asked me to set a 5-minute timer. I have done that for you."},
                {"role": "user", "content": "what date is it?"},
                {"role": "assistant", "content": "Today's date is April 4, 2026"}
            ]
        }
        demo_queries = ["hello", "turn bluetooth off", "set a timer for 5 minutes", "what did i just ask you to do?", "what date is it?"]
        demo_transcriptions = [
            {"id": 0, "timestamp": "2026-04-04T10:30:00", "transcription": "hello", "audio_file": None},
            {"id": 1, "timestamp": "2026-04-04T10:30:15", "transcription": "turn bluetooth off", "audio_file": None},
            {"id": 2, "timestamp": "2026-04-04T10:30:30", "transcription": "set a timer for 5 minutes", "audio_file": None},
            {"id": 3, "timestamp": "2026-04-04T10:30:45", "transcription": "what did i just ask you to do?", "audio_file": None},
            {"id": 4, "timestamp": "2026-04-04T10:31:00", "transcription": "what date is it?", "audio_file": None}
        ]
        demo_stats = {
            "read_body": 0.002,
            "save_audio": 0.001,
            "ffmpeg_convert": 0.150,
            "whisper_transcribe": 0.320,
            "llm_response": 0.450,
            "xml_generation": 0.003,
            "total": 0.926
        }
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "tools": AVAILABLE_TOOLS,
            "recent_queries": list(reversed(demo_queries)),
            "recent_transcriptions": list(reversed(demo_transcriptions)),
            "stats": demo_stats,
            "conversations": demo_conversations,
            "examples": [],
            "corrections": [],
            "demo_mode": True
        })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "tools": AVAILABLE_TOOLS,
        "recent_queries": list(reversed(recent_queries)),
        "recent_transcriptions": list(reversed(recent_transcriptions)),
        "stats": last_request_stats,
        "conversations": conversation_history,
        "examples": [],
        "corrections": []
    })

@app.post("/dash/tools")
async def update_tools(request: Request):
    """Update enabled tools from dashboard form."""
    form_data = await request.form()
    enabled_tools = form_data.getlist("tools")

    for tool_name in AVAILABLE_TOOLS:
        AVAILABLE_TOOLS[tool_name]["enabled"] = tool_name in enabled_tools

    logger.info(f"Updated tool settings: {[name for name, t in AVAILABLE_TOOLS.items() if t['enabled']]}")

    return RedirectResponse(url="/dash", status_code=303)

@app.post("/dash/upload")
async def upload_image(request: Request):
    """Upload an image and save it to root directory."""
    form_data = await request.form()
    file = form_data.get("image")
    
    if not file:
        return RedirectResponse(url="/dash", status_code=303)
    
    # Save file to root directory
    filename = file.filename
    file_path = os.path.join(".", filename)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"Uploaded image: {filename}")
    return RedirectResponse(url="/dash", status_code=303)

if __name__ == "__main__":
    bind_host = config["server"].get("bind", "0.0.0.0")
    uvicorn.run("main:app", host=bind_host, port=config["server"]["port"], reload=True)
