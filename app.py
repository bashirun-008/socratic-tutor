import hashlib
import io
import json
import math
import os

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()
try:  # Streamlit Cloud secrets -> environment variables (providers.py reads os.environ)
    for _k in st.secrets:
        if isinstance(st.secrets[_k], str):
            os.environ.setdefault(_k, st.secrets[_k])
except Exception:
    pass

from providers import transcribe  # noqa: E402
from tutor_core import new_session, run_turn  # noqa: E402

st.set_page_config(page_title="Socratic Tutor", page_icon="🧠", layout="wide")

YELLOW = (255, 211, 61)


def prepare_image(file) -> bytes:
    """Normalize any upload to a reasonably small RGB JPEG (keeps API calls cheap)."""
    img = Image.open(file).convert("RGB")
    img.thumbnail((1280, 1280))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def draw_overlays(img_bytes: bytes, overlays: list) -> Image.Image:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if not overlays:
        return img
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    lw = max(3, W // 200)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(14, W // 45))
    except Exception:
        font = ImageFont.load_default()
    for o in overlays:
        x, y = o.get("x", 0) / 100 * W, o.get("y", 0) / 100 * H
        lx, ly = x, y + lw * 3
        if o["type"] == "box":
            w, h = o.get("w", 10) / 100 * W, o.get("h", 10) / 100 * H
            d.rectangle([x, y, x + w, y + h], outline=YELLOW, width=lw)
            ly = y + h + 4
        elif o["type"] == "circle":
            r = o.get("r", 6) / 100 * min(W, H)
            d.ellipse([x - r, y - r, x + r, y + r], outline=YELLOW, width=lw)
            lx, ly = x - r, y + r + 4
        elif o["type"] == "arrow":
            x2, y2 = o.get("x2", 0) / 100 * W, o.get("y2", 0) / 100 * H
            d.line([x, y, x2, y2], fill=YELLOW, width=lw)
            a, hd = math.atan2(y2 - y, x2 - x), lw * 5
            d.polygon(
                [(x2, y2),
                 (x2 - hd * math.cos(a - 0.4), y2 - hd * math.sin(a - 0.4)),
                 (x2 - hd * math.cos(a + 0.4), y2 - hd * math.sin(a + 0.4))],
                fill=YELLOW,
            )
        if o.get("label"):
            bb = d.textbbox((lx, ly), o["label"], font=font)
            d.rectangle([bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2], fill=(0, 0, 0, 200))
            d.text((lx, ly), o["label"], fill=YELLOW, font=font)
    return img


def speak(text: str):
    """Browser text-to-speech (best effort; some browsers block autoplay)."""
    components.html(
        f"<script>try{{speechSynthesis.cancel();"
        f"speechSynthesis.speak(new SpeechSynthesisUtterance({json.dumps(text)}));}}catch(e){{}}</script>",
        height=0,
    )


# ---------------- session state ----------------
S = st.session_state
S.setdefault("sess", new_session())
S.setdefault("img", None)
S.setdefault("img_key", None)
S.setdefault("chat", [])
S.setdefault("overlays", [])
S.setdefault("meta", None)
S.setdefault("last_audio", None)


def reset():
    S.sess, S.chat, S.overlays, S.meta, S.last_audio = new_session(), [], [], None, None


st.title("🧠 Socratic Tutor")
st.caption("Upload a problem, say where you're stuck. It asks questions instead of giving answers.")

left, right = st.columns([1.3, 1], gap="large")

with left:
    up = st.file_uploader("Photo or diagram of your problem", type=["png", "jpg", "jpeg", "webp"])
    if up is not None:
        key = f"{up.name}-{up.size}"
        if S.img_key != key:
            reset()
            S.img, S.img_key = prepare_image(up), key
            S.chat.append(("tutor", "Got your problem. Tell me (type or use the mic) where you're stuck."))

with left:
    with st.expander("🔑 Teacher notes (optional): reference solution"):
        st.caption("Hidden ground truth for the tutor. It steers toward this but never reveals it.")
        st.text_area("Reference solution", key="ref", height=150, label_visibility="collapsed")

with right:
    ai = st.selectbox("AI provider", ["default", "groq", "gemini"], index=0)
    use_tts = st.checkbox("Speak replies", value=True)
    audio = st.audio_input("🎤 Record a voice note")

typed = st.chat_input("Where are you stuck? Or answer the tutor...")

# ---------------- handle new input ----------------
message = typed
if audio is not None:
    data = audio.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h != S.last_audio:
        S.last_audio = h
        try:
            with st.spinner("Transcribing..."):
                message = transcribe(data, "voice.wav")
        except Exception as e:
            S.chat.append(("err", f"Voice failed: {e}"))

spoke = None
if message and message.strip():
    if S.img is None:
        st.warning("Upload an image of your problem first.")
    else:
        S.chat.append(("you", message))
        first = S.sess["turns"] == 0 and not S.sess["history"]
        try:
            with st.spinner("Thinking..."):
                r = run_turn(
                    S.sess, message,
                    image=(S.img, "image/jpeg") if first else None,
                    provider=None if ai == "default" else ai,
                    reference=S.get("ref", ""),
                )
            S.chat.append(("tutor", r["spoken_question"]))
            S.overlays, S.meta, spoke = r["overlays"], r, r["spoken_question"]
        except Exception as e:
            S.chat.append(("err", str(e)))

# ---------------- render ----------------
with left:
    if S.img:
        st.image(draw_overlays(S.img, S.overlays), use_container_width=True)
        if st.button("Start over"):
            reset()
            S.img, S.img_key = None, None
            st.rerun()

with right:
    if S.meta:
        st.caption(f"hint level {S.meta['hint_level']}/3  ·  {S.meta['student_progress']}  ·  {S.meta['misconception'] or '-'}")
    for who, text in S.chat:
        if who == "you":
            st.chat_message("user").write(text)
        elif who == "tutor":
            st.chat_message("assistant").write(text)
        else:
            st.error(text)
    if S.meta:
        with st.expander("Tutor's reasoning"):
            st.write(S.meta["reasoning"])

if spoke and use_tts:
    speak(spoke)
