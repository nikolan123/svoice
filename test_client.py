#!/usr/bin/env python3

import json
import base64
import xml.etree.ElementTree as ET
import requests

with open("config.json", "r") as f:
    config = json.load(f)

# SERVER_URL = f"http://{config['server']['host']}:{config['server']['port']}/voicepad/sr"
SERVER_URL = f"http://localhost:5067/voicepad/sr"


class SVoiceClient:
    def __init__(self):
        self.dialog_state = None
        self.conversation_id = None

    def send_text(self, text: str) -> dict:
        boundary_line = b'\r\n-------------------------------1878979834'

        body_parts = []
        body_parts.append(b'---------------------------------1878979834\r\n')
        body_parts.append(b'Content-Disposition: form-data; name="text"\r\n')
        body_parts.append(b'Content-Type:text/plain\r\n\r\n')
        body_parts.append(text.encode('utf-8'))

        if self.dialog_state:
            state_json = json.dumps(self.dialog_state)
            body_parts.append(boundary_line)
            body_parts.append(b'\r\nContent-Disposition: form-data; name="dialog-data"\r\n\r\n')
            body_parts.append(state_json.encode('utf-8'))

        body_parts.append(boundary_line)
        body_parts.append(b'--\r\n')

        body = b''.join(body_parts)

        headers = {
            'Content-Type': 'multipart/form-data; boundary=-------------------------------1878979834'
        }

        try:
            response = requests.post(SERVER_URL, data=body, headers=headers)
            response.raise_for_status()
            return self._parse_response(response.text)
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {e}"}

    def _parse_response(self, xml_text: str) -> dict:
        try:
            root = ET.fromstring(xml_text)
            result = {"actions": [], "conversation_id": None, "turn": None}

            dialog_state_elem = root.find('DialogState')
            if dialog_state_elem is not None and dialog_state_elem.text:
                state_json = base64.b64decode(dialog_state_elem.text).decode()
                self.dialog_state = json.loads(state_json)
                result["conversation_id"] = self.dialog_state.get("conversation_id")
                result["turn"] = self.dialog_state.get("turn")

            vv_elem = root.find('VV')
            if vv_elem is not None and not result["turn"]:
                result["turn"] = vv_elem.get("turn")

            action_list = root.find('ActionList')
            if action_list is not None:
                for action in action_list.findall('Action'):
                    params = {}
                    for param in action.findall('Param'):
                        params[param.get('n')] = param.get('v')
                    result["actions"].append({"name": action.get('n'), "params": params})

            return result
        except ET.ParseError as e:
            return {"error": f"Failed to parse XML: {e}"}

    def format_response(self, response: dict) -> str:
        if "error" in response:
            return f"Error: {response['error']}"

        lines = []
        if response.get("conversation_id"):
            lines.append(f"Conversation: {response['conversation_id'][:8]}... (Turn {response.get('turn', '?')})")

        if response.get("actions"):
            for action in response["actions"]:
                name, params = action["name"], action["params"]

                if name == "ShowMessage":
                    lines.append(f"Message: {params.get('Message', '')}")
                elif name == "ShowUserTurn":
                    lines.append(f"You: {params.get('utterance.results', '')}")
                elif name == "ShowOpenAppWidget":
                    lines.append(f"Opening: {params.get('Name', '')}")
                elif name == "ShowSetTimerWidget":
                    lines.append(f"Timer: {params.get('time', '')}")
                elif name == "SettingChange":
                    lines.append(f"Setting {params.get('name', '')} -> {params.get('state', '')}")
                elif name == "RecordVoice":
                    lines.append(f"Recording" + (f": {params.get('Title')}" if params.get('Title') else ""))
                elif name == "DefaultWebSearch":
                    lines.append(f"Search: {params.get('query', '')}")
                elif name == "SearchWebPrompt":
                    lines.append(f"Search prompt: {params.get('Question', '')}")
                elif name == "Intent":
                    lines.append(f"Music: {params.get('IntentName', '').split('.')[-1]}")
                elif name.startswith("ShowPlay"):
                    lines.append(f"Play {params.get('Type', '')}: {params.get('Query', '')}")
                else:
                    lines.append(f"{name}")

        return "\n".join(lines) if lines else "No response"

    def reset(self):
        self.dialog_state = None
        self.conversation_id = None
        print("New conversation")


def main():
    print("S Voice Test Client")
    print(f"Server: {SERVER_URL}")
    print("Commands: /reset /quit /help\n")

    client = SVoiceClient()

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd in ["/quit", "/exit", "/q"]:
                    print("By by")
                    break
                elif cmd in ["/reset", "/new"]:
                    client.reset()
                    continue
                elif cmd in ["/help", "/h"]:
                    print("Commands: /reset /quit /help")
                    print("Examples: 'Open Chrome' 'Set timer 5 minutes' 'Turn on WiFi'")
                    continue
                else:
                    print(f"Unknown: {user_input}")
                    continue

            response = client.send_text(user_input)
            print(client.format_response(response))

        except KeyboardInterrupt:
            print("\nBy by")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
