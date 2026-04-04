# S Voice Server

A custom server for S Voice that makes it work again locally. Works with S Voice versions that shipped until Android 5, tested with 11.2.2.0.x.

<p align="center">
  <img src="https://github.com/user-attachments/assets/870095ea-9a97-4262-a512-8d1a309bc969" width="200" />
  <img src="https://github.com/user-attachments/assets/3eb900c1-e1bf-4c35-bbcc-ac9c68832432" width="200" />
</p>

<details>
  <summary>All tested versions</summary>
  <ul>
    <li>11.2.2.0.39002 (r1) on S4 (I9505)</li>
    <li>11.2.2.0.37791 (r1) on Note 3 (N9005)</li>
    <li>11.2.2.0.32948 (r1) on S3 Mini (I8200)</li>
    <li>11.2.2.0.32564 (r1) on S3 Neo (I9301I)</li>
    <li>11.2.2.0.33209 (r1) on S4 Mini (I9195)</li>
  </ul>
</details>

## How it works

It works by redirecting requests sent from S Voice to a local server. The server then decodes the audio and uses OpenAI Whisper to transcribe it and passes it to an LLM. The LLM then chooses whether to respond with plain text or an action such as setting a timer, opening an app, etc.

The current supported actions are opening apps, setting timers, toggling bt/wifi, starting voice recordings, searching the web, and controlling music.

## Setup

### Prerequesites

- New-ish Python version (3.13.5 tested)
- Ollama (`brew install --cask ollama-app`)
- mitmproxy (`brew install mitmproxy`)
- ffmpeg in path (`brew install ffmpeg`)
- Ollama model - I use qwen3:4b instruct as it runs good on my laptop (`ollama pull qwen3:4b-instruct-2507-q4_K_M`, about 2.5GB)
- Decent CPU or GPU and enough RAM to load the LLM and Whisper model.
- Wi-Fi on the phone
  
### Configure the server

Open `config.json` and update the settings:

API Configuration:
- `api.provider`: Choose "ollama" or "openai" for your LLM backend
- `api.ollama.base_url`: Ollama server URL (default: http://localhost:11434)
- `api.openai.base_url`: OpenAI-compatible API endpoint (e.g., http://localhost:8000/v1)
- `api.openai.api_key`: API key for OpenAI-compatible services

Server Configuration:
- `server.host`: Your local IP address (find with `ifconfig`, `ip addr`, or `ipconfig`)
- `server.port`: Server port (default 5067)
- `models.llm`: Your model name (e.g., `qwen3:4b-instruct-2507-q4_K_M` for Ollama)
- `models.whisper`: Whisper model size (tiny/base/small/medium/large)

Options:
- `options.whisper_language`: Language code for transcription ("en", "es", "fr", etc)
- `options.max_history_messages`: Number of messages to keep in conversation memory
- `options.conversation_timeout_minutes`: Auto-cleanup inactive conversations
- `options.keep_audio_files`: Set to true to keep audio files

### Start the proxy server

This allows the computer to read and modify http traffic on the phone

- The svoiceredir.py script is used along with mitmproxy to achieve that
- Run the `run_svoiceredir.sh` script, or just `mitmproxy -s svoiceredir.py`
- It will run at port 8080 by default
- Allow mitmproxy through your firewall if needed

### Configure the phone

The phone needs to be configured to use our proxy server

- This may vary across devices, but is generally something like this
- Go to Settings > Wi-Fi and forget your current network if already connected
- Tap on your network, input your password but do not connect yet
- Check "Show Advanced Options"
- In the proxy settings, select "Manual"
- In the ip address field, enter your computer's ip address (from config.json)
- In the port field, enter 8080 unless you have changed the port manually during step 2
- If you open S Voice, you should see a failing request in the mitmproxy window from step 2

### Setup the Python environment

Now we need to set up the S Voice server itself

- You need the packages listed in requirements.txt
- To install the packages: `pip install -r requirements.txt` or `uv sync`

> [!NOTE]
> Installing the requirements in a venv instead of the global Python installation is recommended.
> 
> `python -m venv .venv` to create it, `source .venv/bin/activate` to activate on macOS/Linux, `.venv\Scripts\activate` on Windows

### Start the server

- Type `python main.py` to start the server
- The first start may take a while as it needs to download and load the Whisper model
- If everything is set up correctly, you should see `Application startup complete.`
- Visit http://localhost:5067/dash (or your configured port) to access the dashboard
- 