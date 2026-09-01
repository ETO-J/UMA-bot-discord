"""Dynamic input-token billing for the AI drawing assistant.

Billing mirrors DeepSeek's vision pricing: an image is converted to input
tokens by its (post-resize) dimensions, capped at 384 tokens per image; text
tokens are estimated the same way the model counts CJK vs ASCII.

The cost of a chat message equals its estimated input-token count, floored at
1 and capped at CHAT_MAX_COST so a single message never spends more than the
budget. Only the *new* user input for this request (message text + the image
attached to it) is billed; previously saved history is not re-billed.
"""
import base64
import math
import struct

from config import (
    CHAT_MAX_COST,
    CHAT_MAX_IMAGES,
    CHAT_IMAGE_MAX_TOKEN,
    CHAT_IMAGE_TOKEN_PX,
)


def estimate_text_tokens(text: str | None) -> int:
    """Estimate tokens for text.

    CJK / full-width characters count ~1 token each (the model encodes them
    roughly 1:1), while ASCII counts ~4 chars per token. This mirrors common
    tokenizer behavior closely enough for a pre-billing estimate.
    """
    if not text:
        return 0
    tokens = 0.0
    for ch in text:
        if ord(ch) >= 0x2E80:  # CJK, kana, hangul, full-width punctuation
            tokens += 1.0
        else:
            tokens += 0.25
    return max(0, int(math.ceil(tokens)))


def estimate_image_tokens(width: int | None, height: int | None) -> int:
    """Estimate tokens for one image using DeepSeek's vision rule.

    Tokens scale with dimensions but are capped at CHAT_IMAGE_MAX_TOKEN (384).
    DeepSeek rescales images before inference (large ones to ~800x800
    equivalent), so 800*800 / CHAT_IMAGE_TOKEN_PX lands at roughly the cap.
    """
    if not width or not height or width <= 0 or height <= 0:
        return CHAT_IMAGE_MAX_TOKEN
    tokens = round(width * height / CHAT_IMAGE_TOKEN_PX)
    return max(1, min(CHAT_IMAGE_MAX_TOKEN, tokens))


def _parse_png_dimensions(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return None
    try:
        w, h = struct.unpack(">II", data[16:24])  # IHDR width/height
        return w, h
    except Exception:  # noqa: BLE001
        return None


def _parse_jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 9 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # Skip standalone/stuffed markers and RST markers.
        if marker in (0xD8, 0x01) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        # SOF markers (start of frame) carry height/width, excluding DHT/DAC/RST.
        if (
            marker >= 0xC0
            and marker <= 0xCF
            and marker not in (0xC4, 0xC8, 0xCC)
        ):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + seg_len
    return None


def read_image_dimensions(image_b64: str | None) -> tuple[int, int] | None:
    """Parse width/height from a base64 or data-URL encoded PNG/JPEG."""
    if not image_b64:
        return None
    if image_b64.startswith("data:"):
        _, sep, payload = image_b64.partition(",")
        if not sep:
            return None
    else:
        payload = image_b64
    try:
        data = base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        return None
    return _parse_png_dimensions(data) or _parse_jpeg_dimensions(data)


def estimate_chat_cost(
    message: str | None,
    images: list[str] | None = None,
    image_sizes: list[list[int]] | None = None,
) -> dict:
    """Estimate the quota cost of one chat message (capped at CHAT_MAX_COST).

    ``images`` are base64 data URLs and ``image_sizes`` are [[w, h], ...].
    Either source may be omitted during pure estimation (only sizes needed);
    when sizes are missing the base64 payload is decoded to recover dims.
    """
    images = (images or [])[:CHAT_MAX_IMAGES]
    sizes = (image_sizes or [])[:CHAT_MAX_IMAGES]
    text_tokens = estimate_text_tokens(message)
    image_tokens = 0
    count = min(len(images) if images else len(sizes), CHAT_MAX_IMAGES)
    for i in range(count):
        dims = None
        if i < len(sizes) and sizes[i] and len(sizes[i]) >= 2:
            w, h = sizes[i][0], sizes[i][1]
            if w > 0 and h > 0:
                dims = (w, h)
        if dims is None and i < len(images):
            dims = read_image_dimensions(images[i])
        if dims:
            image_tokens += estimate_image_tokens(*dims)
        else:
            # Unknown size -> assume the DeepSeek per-image cap.
            image_tokens += CHAT_IMAGE_MAX_TOKEN
    total_tokens = text_tokens + image_tokens
    cost = max(1, min(CHAT_MAX_COST, total_tokens))
    return {
        "text_tokens": text_tokens,
        "image_tokens": image_tokens,
        "image_count": count,
        "total_tokens": total_tokens,
        "cost": cost,
        "max_cost": CHAT_MAX_COST,
    }
