import uuid
import re
import base64
import json
from typing import Optional


class SVoiceResponse:
    """S Voice XML response generator"""

    def __init__(self, user_text: str, dialog_state: dict = None):
        self.guttid = str(uuid.uuid4())
        self.user_text = user_text
        self.actions = []
        self.dialog_guid = str(uuid.uuid4())
        self.dialog_state = dialog_state if dialog_state else {"turn": 1}
        self.dialog_turn = self.dialog_state.get("turn", 1)

    def add_user_turn(self) -> 'SVoiceResponse':
        """Add ShowUserTurn action to display what the user said"""
        self.actions.append({
            "name": "ShowUserTurn",
            "params": {"utterance.results": self.user_text}
        })
        return self

    def add_message(self, message: str, msg_type: str = "info") -> 'SVoiceResponse':
        """Add ShowMessage action to display a message to the user"""
        self.actions.append({
            "name": "ShowMessage",
            "params": {"Message": message, "Type": msg_type}
        })
        return self

    def add_open_app(self, app_name: str) -> 'SVoiceResponse':
        """Add ShowOpenAppWidget action to open an app"""
        self.actions.append({
            "name": "ShowOpenAppWidget",
            "params": {"Name": app_name.title()}
        })
        return self

    def add_set_timer(self, canonical_time: str) -> 'SVoiceResponse':
        """Add ShowSetTimerWidget action to set a timer"""
        if not self._validate_canonical_time(canonical_time):
            return self.add_message(f"Invalid time format: {canonical_time}. Expected +HH:mm:ss", "error")

        self.actions.append({
            "name": "ShowSetTimerWidget",
            "params": {"time": canonical_time, "doit": "true"}
        })
        return self

    def add_setting_change(self, setting_name: str, state: str) -> 'SVoiceResponse':
        """Add SettingChange action to change a device setting"""
        setting_map = {
            "wifi": "wifi",
            "bluetooth": "bt",
            "driving_mode": "safereader"
        }

        internal_name = setting_map.get(setting_name.lower())
        if not internal_name:
            return self.add_message(f"Unsupported setting: {setting_name}", "error")

        if state.lower() not in ["on", "off", "toggle"]:
            return self.add_message(f"Invalid state: {state}. Use 'on', 'off', or 'toggle'", "error")

        display_names = {
            "wifi": "WiFi",
            "bt": "Bluetooth",
            "safereader": "Driving Mode"
        }

        display_name = display_names.get(internal_name, setting_name.title())

        self.actions.append({
            "name": "SettingChange",
            "params": {
                "name": internal_name,
                "state": state.lower(),
                "confirmOn": f"{display_name} is now on",
                "confirmOff": f"{display_name} is now off"
            }
        })
        return self

    def add_record_voice(self, title: Optional[str] = None) -> 'SVoiceResponse':
        """Add RecordVoice action to start voice recording"""
        params = {}
        if title:
            params["Title"] = title

        self.actions.append({
            "name": "RecordVoice",
            "params": params
        })
        return self

    def add_web_search(self, query: str) -> 'SVoiceResponse':
        """Add DefaultWebSearch action to search the web"""
        self.actions.append({
            "name": "DefaultWebSearch",
            "params": {"query": query}
        })
        return self

    def add_web_search_prompt(self, question: str) -> 'SVoiceResponse':
        """Add SearchWebPrompt action to prompt user to search web with a clickable button"""
        self.actions.append({
            "name": "SearchWebPrompt",
            "params": {"Question": question}
        })
        return self

    def add_play_music(self, play_type: str = "PLAY", name: Optional[str] = None) -> 'SVoiceResponse':
        """Add music control action to play/pause/skip or play specific content"""
        play_type_upper = play_type.upper()

        if play_type_upper in ["PLAY", "PAUSE", "NEXT", "PREVIOUS"]:
            intent_map = {
                "PLAY": "com.sec.android.music.intent.action.PLAY",
                "PAUSE": "com.sec.android.app.music.intent.action.STOP",
                "NEXT": "com.sec.android.app.music.intent.action.PLAY_NEXT",
                "PREVIOUS": "com.sec.android.app.music.intent.action.PLAY_PREVIOUS"
            }
            self.actions.append({
                "name": "Intent",
                "params": {
                    "IntentName": intent_map[play_type_upper],
                    "broadcast": "false"
                }
            })
        elif play_type_upper in ["TITLE", "ALBUM", "ARTIST", "PLAYLIST"]:
            widget_map = {
                "TITLE": "ShowPlayTitleWidget",
                "ALBUM": "ShowPlayAlbumWidget",
                "ARTIST": "ShowPlayArtistWidget",
                "PLAYLIST": "ShowPlayPlaylistWidget"
            }
            type_map = {
                "TITLE": "Music:Title",
                "ALBUM": "Music:Album",
                "ARTIST": "Music:Artist",
                "PLAYLIST": "Music:Playlist"
            }
            self.actions.append({
                "name": widget_map[play_type_upper],
                "params": {
                    "Type": type_map[play_type_upper],
                    "Query": name if name else ""
                }
            })
        else:
            return self.add_message(f"Invalid play type: {play_type}", "error")

        return self

    def generate_xml(self) -> str:
        """Generate the final XML response"""
        # idk what this does
        words = self.user_text.lower().split()[:2]
        if not words:
            words = ["hello", "world"]

        # Build alternates section
        wl_items = []
        ul_words = []
        for i, word in enumerate(words):
            wl_items.append(f'<w id="{i}" n="1"><c r="1">{word}</c></w>')
            ul_words.append(f'<w id="{i}">{word}</w>')

        wl_section = '\n'.join(wl_items)
        ul_section = '\n'.join(ul_words)

        # Build actions section
        action_items = []
        for action in self.actions:
            params = []
            for key, value in action["params"].items():
                escaped_value = str(value).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
                params.append(f'<Param n="{key}" v="{escaped_value}"/>')

            param_section = '\n'.join(params)
            action_items.append(f'''<Action n="{action["name"]}">
{param_section}
</Action>''')

        actions_section = '\n'.join(action_items)

        # Build dialog state section (VV element + DialogState)
        vv_section = f'<VV dialog-guid="{self.dialog_guid}" turn="{self.dialog_turn}"/>'

        dialog_state_section = ""
        if self.dialog_state:
            # Base64 encode the dialog state JSON
            state_json = json.dumps(self.dialog_state)
            state_b64 = base64.b64encode(state_json.encode()).decode()
            dialog_state_section = f'<DialogState>{state_b64}</DialogState>'

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Recognition guttid="{self.guttid}">
<Alternates>
<WL n="{len(words)}">
{wl_section}
</WL>
<UL n="1">
<c c="0.95" n="{len(words)}">
{ul_section}
</c>
</UL>
</Alternates>
{vv_section}
{dialog_state_section}
<ActionList>
{actions_section}
</ActionList>
</Recognition>'''

        return xml

    @staticmethod
    def _validate_canonical_time(canonical_time: str) -> bool:
        """Validate canonical time format +HH:mm:ss"""
        pattern = r'^\+\d{2}:\d{2}:\d{2}$'
        return bool(re.match(pattern, canonical_time))


def generate_regular_response(user_text: str, response_text: str, dialog_state: dict = None) -> str:
    """Generate regular text response XML"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_message(response_text)
            .generate_xml())

def generate_open_app_response(user_text: str, app_name: str, dialog_state: dict = None) -> str:
    """Generate XML response for opening an app"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_open_app(app_name)
            .generate_xml())

def generate_set_timer_response(user_text: str, canonical_time: str, dialog_state: dict = None) -> str:
    """Generate XML response for setting a timer"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_set_timer(canonical_time)
            .generate_xml())

def generate_setting_change_response(user_text: str, setting_name: str, state: str, dialog_state: dict = None) -> str:
    """Generate XML response for changing device settings"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_setting_change(setting_name, state)
            .generate_xml())


def generate_record_voice_response(user_text: str, title: Optional[str] = None, dialog_state: dict = None) -> str:
    """Generate XML response for starting voice recording"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_record_voice(title)
            .generate_xml())

def generate_web_search_response(user_text: str, query: str, dialog_state: dict = None) -> str:
    """Generate XML response for web search"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_web_search(query)
            .generate_xml())

def generate_web_search_prompt_response(user_text: str, question: str = None, dialog_state: dict = None) -> str:
    """Generate XML response prompting user to search web with clickable button"""
    if not question:
        question = user_text
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_web_search_prompt(question)
            .generate_xml())


def generate_play_music_response(user_text: str, play_type: str = "PLAY", name: Optional[str] = None, dialog_state: dict = None) -> str:
    """Generate XML response for music control"""
    return (SVoiceResponse(user_text, dialog_state)
            .add_user_turn()
            .add_play_music(play_type, name)
            .generate_xml())
