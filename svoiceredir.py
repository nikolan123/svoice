import json

with open("config.json", "r") as f:
    config = json.load(f)

def request(flow):
    # Redirect S-Voice Vlingo servers to local server
    vlingo_hosts = [
        "samsungbuiasr.vlingo.com",         # ASR (Speech Recognition)
        "samsungbuitts.vlingo.com",         # TTS (Text-to-Speech)
        "samsungbuilocalsearch.vlingo.com"  # VCS (Local Search)
    ]

    target_host = config["server"]["host"]
    target_port = config["server"]["port"]

    if flow.request.pretty_host in vlingo_hosts:
        print(f"[*] Redirecting {flow.request.pretty_host} -> {target_host}")
        flow.request.host = target_host
        flow.request.port = target_port
