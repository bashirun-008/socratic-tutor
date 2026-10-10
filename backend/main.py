import base64
import json
import os
import re
import uuid
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from prompt import SYSTEM_PROMPT

load_dotenv()
client = Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")

app = FastAPI(title="Socratic Tutor API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# In-memory sessions: {session_id: [anthropic-format messages]}
SESSIONS: dict[str, list] = {}

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def parse_tutor_json(text: str) -> dict:
    """Models sometimes wrap JSON in fences or add chatter. Be forgiving."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def sanitize(data: dict) -> dict:
    """Clamp overlay coords to 0-100 so the frontend never draws off-image."""
    def clamp(v):
        try:
            return max(0.0, min(100.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    clean_overlays = []
    for o in data.get("overlays", []) or []:
        if o.get("type") not in {"box", "circle", "arrow"}:
            continue
        item = {"type": o["type"], "label": str(o.get("label", ""))[:40]}
        for key in ("x", "y", "w", "h", "r", "x2", "y2"):
            if key in o:
                item[key] = clamp(o[key])
        clean_overlays.append(item)

    return {
        "spoken_question": str(data.get("spoken_question", "")).strip(),
        "overlays": clean_overlays,
        "misconception": data.get("misconception"),
        "hint_level": int(data.get("hint_level", 1) or 1),
        "student_progress": data.get("student_progress", "stuck"),
        "reasoning": str(data.get("reasoning", "")).strip(),
    }


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}


@app.post("/tutor/turn")
async def tutor_turn(
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    """One conversational turn. Send the image on the FIRST turn only."""
    sid = session_id or str(uuid.uuid4())
    history = SESSIONS.setdefault(sid, [])

    content: list = []
    if image is not None:
        if image.content_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported image type: {image.content_type}")
        raw = await image.read()
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(400, "Image too large (max 5 MB).")
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.content_type,
                    "data": base64.b64encode(raw).decode(),
                },
            }
        )
    elif not history:
        raise HTTPException(400, "First turn needs an image.")

    content.append({"type": "text", "text": message})
    history.append({"role": "user", "content": content})

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        raw_text = resp.content[0].text
        result = sanitize(parse_tutor_json(raw_text))
    except Exception as e:
        history.pop()  # don't poison the session with a failed turn
        raise HTTPException(502, f"Tutor error: {e}")

    # Store the assistant turn as the raw JSON so the model sees its own prior hint level
    history.append({"role": "assistant", "content": json.dumps(result)})
    return {"session_id": sid, **result}


@app.post("/tutor/reset")
def reset(session_id: str = Form(...)):
    SESSIONS.pop(session_id, None)
    return {"ok": True}
