# 🧠 Socratic Tutor

A multimodal AI tutor that **never gives the answer**. A student uploads a photo of a problem
(circuit diagrams, physics, math), says where they're stuck by typing or voice note, and the
tutor responds with **one guiding question**, spoken aloud, with **visual overlays drawn on
their diagram** pointing at what to look at.

> Built solo for a multimodal AI hackathon (IIT Delhi).

## Demo
- Live app: _add link_
- Demo video: _add link_

## How it works

```
 photo + voice note
        |
        v
  [Streamlit UI] --voice--> [Whisper (Groq)] --text--+
        |                                            |
        +--------------------------------------------+
                          |
                          v
                 [tutor_core.py]  <- enforces hint ladder, no repeated questions,
                          |          retries on bad JSON / rate limits
                          v
                 [providers.py]  -> vision LLM (Groq Qwen VL or Gemini)
                          |
                  JSON: question, overlays[], hint_level, misconception, reasoning
                          |
                          v
        overlays drawn on the image (Pillow) + question spoken (browser TTS)
```

**Modalities:** text, audio (voice Q&A), vision (image/diagram understanding + overlay drawing).

## Features
- **Socratic by design:** one guiding question per turn, never the final answer
- **Visual overlays:** circles, boxes and arrows drawn on the student's own diagram
- **3-level hint ladder:** escalates only when the student stays stuck
- **Voice input** (Whisper) and **spoken replies**
- **Tutor's reasoning panel:** shows how the tutor read the diagram and what misconception it suspects
- **Provider switch:** Groq or Gemini behind one interface

## Design decisions (what I learned)
- **The LLM proposes, the code enforces.** The model alone drifted: it repeated questions and
  mis-tracked hint levels. Hint level, stuck-count and "never repeat a question" now live in
  `tutor_core.py`, and a repeated question triggers an automatic retry.
- **LLM output is untrusted input.** Responses are parsed defensively, validated, clamped
  (overlay coordinates), and retried on malformed JSON.
- **A confident tutor can be wrong.** An early version told me an ideal voltmeter acts "like a
  wire" (it is an open circuit). Fixes: a physics-facts guardrail in the system prompt, a
  "verify before asserting" rule, a rule against praising vague guesses, and a visible
  "I read the circuit as..." line so misreads are easy to spot.
- **Vision coordinates are approximate.** Overlays use generous sizes instead of pixel-perfect shapes.
- **Free-tier rate limits are real.** The app trims old turns, normalizes images, and waits and
  retries on 429 errors.

## Limitations / next steps
- Dense or blurry diagrams reduce reading accuracy (a tap-to-confirm step would help)
- Optional hidden "teacher answer key" so the tutor can guide toward a verified solution
- Per-student progress tracking across sessions

## Run locally
```bash
pip install -r requirements.txt
# put keys in .streamlit/secrets.toml (see secrets.toml.example) or a .env file
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub
2. share.streamlit.io -> New app -> pick the repo, branch `main`, main file `app.py`
3. Advanced settings -> Secrets -> paste the contents of `.streamlit/secrets.toml.example` with your real key
