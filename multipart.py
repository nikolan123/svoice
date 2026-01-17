import json
import logging

logger = logging.getLogger(__name__)

MULTIPART_BOUNDARY = b'\r\n-------------------------------1878979834'


def extract_multipart_field(body: bytes, field_name: str) -> bytes | None:
    """Extract raw data from a multipart field by name."""
    marker = f'name="{field_name}"'.encode()
    pos = body.find(marker)
    if pos == -1:
        return None

    # Find data after headers (blank line)
    data_start = body.find(b'\r\n\r\n', pos)
    if data_start == -1:
        return None
    data_start += 4

    # Find end boundary
    data_end = body.find(MULTIPART_BOUNDARY, data_start)
    if data_end == -1:
        data_end = len(body)

    return body[data_start:data_end]


def extract_dialog_state(body: bytes) -> dict | None:
    """Extract and decode dialog-data from multipart request."""
    state_bytes = extract_multipart_field(body, "dialog-data")
    if not state_bytes:
        return None

    try:
        return json.loads(state_bytes.decode('utf-8'))
    except Exception as e:
        logger.warning(f"Failed to decode dialog state: {e}")
        return None


def extract_audio_data(body: bytes) -> bytes | None:
    """Extract raw audio data from multipart request.

    Returns raw audio bytes if valid Ogg/Speex, None otherwise.
    """
    audio_data = extract_multipart_field(body, "audio")
    if audio_data and audio_data.startswith(b'OggS'):
        return audio_data
    return None


def extract_text(body: bytes) -> str:
    """Extract text input from multipart request."""
    marker = b'name="text"\r\nContent-Type:text/plain'
    pos = body.find(marker)
    if pos == -1:
        return ""

    data_start = body.find(b'\r\n\r\n', pos)
    if data_start == -1:
        return ""
    data_start += 4

    data_end = body.find(MULTIPART_BOUNDARY, data_start)
    if data_end == -1:
        return ""

    return body[data_start:data_end].decode('utf-8', errors='ignore')
