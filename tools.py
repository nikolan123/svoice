AVAILABLE_TOOLS = {
    "open_app": {
        "enabled": True,
        "display_name": "Open App",
        "example": "Hi Galaxy, open camera",
        "web_description": "Launches any application on your device",
        "definition": {
            "type": "function",
            "function": {
                "name": "open_app",
                "description": "Open an application on the device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "The name of the app to open (e.g., 'calculator', 'camera', 'settings')"
                        }
                    },
                    "required": ["app_name"]
                }
            }
        }
    },
    "set_timer": {
        "enabled": True,
        "display_name": "Set Timer",
        "example": "Hi Galaxy, set a timer for 5 minutes",
        "web_description": "Creates a countdown timer for any duration",
        "definition": {
            "type": "function",
            "function": {
                "name": "set_timer",
                "description": "Set a timer for a specified duration",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "canonical_time": {
                            "type": "string",
                            "description": "Timer duration in canonical format +HH:mm:ss (e.g., '+00:05:00' for 5 minutes, '+00:00:30' for 30 seconds, '+01:00:00' for 1 hour)",
                            "pattern": "^\\+\\d{2}:\\d{2}:\\d{2}$"
                        }
                    },
                    "required": ["canonical_time"]
                }
            }
        }
    },
    "change_setting": {
        "enabled": True,
        "display_name": "Change Setting",
        "example": "Hi Galaxy, turn on WiFi",
        "web_description": "Controls device settings like WiFi, Bluetooth, and Driving Mode",
        "definition": {
            "type": "function",
            "function": {
                "name": "change_setting",
                "description": "Change device settings like WiFi, Bluetooth, or Driving Mode",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "setting_name": {
                            "type": "string",
                            "description": "The setting to change",
                            "enum": ["wifi", "bluetooth", "driving_mode"]
                        },
                        "state": {
                            "type": "string",
                            "description": "The desired state for the setting",
                            "enum": ["on", "off", "toggle"]
                        }
                    },
                    "required": ["setting_name", "state"]
                }
            }
        }
    },
    "record_voice": {
        "enabled": True,
        "display_name": "Record Voice",
        "example": "Hi Galaxy, start a voice recording",
        "web_description": "Starts the voice recorder to capture audio notes",
        "definition": {
            "type": "function",
            "function": {
                "name": "record_voice",
                "description": "Start voice recording on the device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Optional title for the voice recording"
                        }
                    },
                    "required": []
                }
            }
        }
    },
    "web_search": {
        "enabled": True,
        "display_name": "Web Search",
        "example": "Hi Galaxy, search for pasta recipes",
        "web_description": "Opens browser and searches the web for information",
        "definition": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    },
    "web_search_prompt": {
        "enabled": True,
        "display_name": "Web Search Prompt",
        "example": "...",
        "web_description": "Shows a button to search your query on Google when the assistant doesn't know the answer",
        "definition": {
            "type": "function",
            "function": {
                "name": "web_search_prompt",
                "description": "Show user a button to search the web",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    },
    "play_music": {
        "enabled": True,
        "display_name": "Music Control",
        "example": "Hi Galaxy, pause the music / Hi Galaxy, play Destroy the Obvious",
        "web_description": "Controls music playback or plays specific songs, albums, or artists",
        "definition": {
            "type": "function",
            "function": {
                "name": "play_music",
                "description": "Control music playback or play specific content. Use PLAY to resume, PAUSE to stop, NEXT to skip, PREVIOUS to go back. Use TITLE/ALBUM/ARTIST/PLAYLIST with name parameter to play specific content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "play_type": {
                            "type": "string",
                            "description": "Type of action",
                            "enum": ["PLAY", "PAUSE", "NEXT", "PREVIOUS", "TITLE", "ALBUM", "ARTIST", "PLAYLIST"]
                        },
                        "name": {
                            "type": "string",
                            "description": "Name of song/album/artist/playlist when using TITLE/ALBUM/ARTIST/PLAYLIST"
                        }
                    },
                    "required": ["play_type"]
                }
            }
        }
    },
    "chatbot_sing": {
        "enabled": False,
        "display_name": "Chatbot Sing",
        "example": "Hi Galaxy, sing me a song",
        "web_description": "Makes the assistant sing goofy audio",
        "definition": {
            "type": "function",
            "function": {
                "name": "chatbot_sing",
                "description": "Make the assistant sing by playing a random musical audio clip. Use when user asks S-Voice to sing, or show off its singing ability.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    }
}


def get_enabled_tools() -> list:
    """Get list of tool definitions for enabled tools."""
    return [tool["definition"] for tool in AVAILABLE_TOOLS.values() if tool["enabled"]]


def get_tools_description() -> str:
    """Get human-readable description of enabled tools for system prompt."""
    descriptions = []
    for name, tool in AVAILABLE_TOOLS.items():
        if not tool["enabled"]:
            continue
        if name == "open_app":
            descriptions.append("open_app (opens apps)")
        elif name == "set_timer":
            descriptions.append("set_timer (sets timers with +HH:mm:ss format)")
        elif name == "change_setting":
            descriptions.append("change_setting (wifi/bluetooth/driving_mode on/off/toggle, do not try any other values)")
        elif name == "record_voice":
            descriptions.append("record_voice (starts voice recording)")
        elif name == "web_search":
            descriptions.append("web_search (searches web with query string)")
        elif name == "web_search_prompt":
            descriptions.append("web_search_prompt (gives the user a button to click that searches your prompt on google)")
        elif name == "play_music":
            descriptions.append("play_music (PLAY/PAUSE/NEXT/PREVIOUS or TITLE/ALBUM/ARTIST/PLAYLIST with name)")
        elif name == "chatbot_sing":
            descriptions.append("chatbot_sing (makes assistant sing)")

    return f"Available tools: {', '.join(descriptions)}." if descriptions else "No tools available."
