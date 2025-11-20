# main.py - EmotiCare backend (FastAPI)
# Usage:
#   pip install fastapi uvicorn python-multipart requests python-dotenv pillow
#   uvicorn main:app --reload

import os
import json
import base64
from io import BytesIO
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# If you are using a different Gemini model or endpoint, update this URL accordingly.
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

app = FastAPI(title="EmotiCare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for demo only; tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS_FILE = "sessions.json"

# --- Prompt templates (these are used to make Gemini do the reasoning) ---
MOOD_PROMPT = """
You are an empathetic psychologist assistant. Given this user message, return a JSON ONLY response with keys:
- "mood_label": one of ["happy","calm","neutral","sad","anxious","angry","overwhelmed","depressed","suicidal_risk"]
- "confidence": float between 0 and 1
- "mood_intensity": integer 1-10
- "key_phrases": list of up to 3 short phrases found in the text that explain the mood.
Provide only valid JSON. Use conservative labeling for suicidal_risk.
User message: <<USER_MESSAGE>>
"""

THERAPY_PROMPT = """
You are an empathetic, non-judgmental therapy coach. Use the mood label, intensity and key_phrases and produce a JSON ONLY response:
- "empathetic_response": one short paragraph (max 60 words) acknowledging feeling
- "immediate_actions": list of 3 short actionable steps (one should be a 1-minute breathing exercise)
- "journaling_prompt": a single question to help user reflect
- "follow_up_suggestion": one suggestion for longer-term help (learning resource, therapist search, exercise, sleep hygiene)
- "tone": "gentle", "neutral", or "firm" based on mood intensity
Return valid JSON only.
Inputs:
mood_label: <<MOOD_LABEL>>
mood_intensity: <<INTENSITY>>
key_phrases: <<PHRASES>>
"""

CRISIS_PROMPT = """
You are a safety screener. Given the user message, return JSON with:
- "is_high_risk": true/false
- "risk_reasons": list of phrases that indicated risk (if any)
- "recommended_action": one of ["call_emergency","contact_support_person","seek_professional","standard_guidance"]
- "safety_script": exactly 2 simple sentences instructing the user what to do now.
Criteria: flag as high risk only for explicit self-harm or clear imminent risk statements.
User message: <<USER_MESSAGE>>
"""

IMAGE_PROMPT = """
You are an AI that can analyze an image (provided as base64) and describe facial expression and likely emotion. Return JSON:
- "mood_label": same label set as above
- "confidence": 0-1
- "key_phrases": short observations
Return JSON only.
Image (base64): <<IMAGE_B64>>
"""

SUMMARY_PROMPT = """
Produce a 2-line summary and a 6-word title for this session given the following analysis output.
Return JSON: {"title":"...", "summary":"..."}
"""

# --- helper: call Gemini ---
def call_gemini(prompt_text, retries=2, timeout=25):
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not configured. Set environment variable."}
    payload = {"contents":[{"parts":[{"text": prompt_text}]}]}
    for attempt in range(retries + 1):
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=timeout)
            r.raise_for_status()
            j = r.json()
            # Parse response text
            text = ""
            try:
                text = j.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            except Exception:
                text = json.dumps(j)
            return {"text": text, "raw": j}
        except Exception as e:
            last_err = str(e)
    return {"error": f"Request failed after retries: {last_err}"}

# --- sessions persistence (server-side copy) ---
def load_sessions():
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_session(obj):
    s = load_sessions()
    s.append(obj)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(s[-500:], f, ensure_ascii=False, indent=2)

# --- Models ---
class TextIn(BaseModel):
    text: str

# --- Endpoints ---
@app.get("/")
def root():
    return {"status": "EmotiCare API running"}

@app.post("/analyze_text")
def analyze_text(payload: TextIn):
    text = payload.text.strip()
    timestamp = datetime.utcnow().isoformat()
    if not text:
        return {"error": "Empty text"}

    # 1) crisis safety check first
    crisis_prompt = CRISIS_PROMPT.replace("<<USER_MESSAGE>>", text)
    crisis_resp = call_gemini(crisis_prompt)
    if "error" in crisis_resp:
        return {"error": crisis_resp["error"]}
    try:
        crisis_json = json.loads(crisis_resp["text"])
    except:
        crisis_json = {"is_high_risk": False}

    if crisis_json.get("is_high_risk"):
        out = {
            "mood_label": "suicidal_risk",
            "confidence": 1.0,
            "mood_intensity": 10,
            "key_phrases": crisis_json.get("risk_reasons", []),
            "therapy": {
                "empathetic_response": crisis_json.get("safety_script", "If you are in danger, call emergency services."),
                "immediate_actions": ["Call local emergency services", "Stay near someone you trust", "If possible, remove harmful objects"],
                "journaling_prompt": "Can you tell someone where you are and how you feel?",
                "follow_up_suggestion": "Contact local emergency services or a mental health professional."
            },
            "crisis": crisis_json,
            "timestamp": timestamp
        }
        save_session(out)
        return out

    # 2) mood detection
    mood_prompt = MOOD_PROMPT.replace("<<USER_MESSAGE>>", text)
    mood_resp = call_gemini(mood_prompt)
    if "error" in mood_resp:
        return {"error": mood_resp["error"]}
    try:
        mood_json = json.loads(mood_resp["text"])
    except:
        # fallback: neutral
        mood_json = {"mood_label": "neutral", "confidence": 0.6, "mood_intensity": 4, "key_phrases": []}

    # 3) therapy generation
    therapy_prompt = THERAPY_PROMPT.replace("<<MOOD_LABEL>>", mood_json.get("mood_label","neutral")) \
                                   .replace("<<INTENSITY>>", str(mood_json.get("mood_intensity",4))) \
                                   .replace("<<PHRASES>>", json.dumps(mood_json.get("key_phrases",[])))
    therapy_resp = call_gemini(therapy_prompt)
    try:
        therapy_json = json.loads(therapy_resp["text"])
    except:
        therapy_json = {
            "empathetic_response": "I hear you. It's valid to feel this way. Small steps can help.",
            "immediate_actions": ["Try a 1-minute breathing exercise", "Drink water", "Step outside for 5 minutes"],
            "journaling_prompt": "What happened right before you felt this way?",
            "follow_up_suggestion": "Consider speaking with a trusted friend or counselor."
        }

    out = {
        "mood_label": mood_json.get("mood_label", "neutral"),
        "confidence": mood_json.get("confidence", 0.6),
        "mood_intensity": mood_json.get("mood_intensity", 4),
        "key_phrases": mood_json.get("key_phrases", []),
        "therapy": therapy_json,
        "crisis": crisis_json,
        "timestamp": timestamp
    }
    save_session(out)
    return out

@app.post("/analyze_image")
async def analyze_image(file: UploadFile = File(...)):
    # Read image bytes, convert to base64 and send to Gemini Vision prompt placeholder
    content = await file.read()
    try:
        # ensure it is a valid image
        img = Image.open(BytesIO(content)).convert("RGB")
        # optionally resize to reduce upload size
        img.thumbnail((800, 800))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return {"error": "Invalid image file."}

    # Build image prompt and call Gemini (vision)
    image_prompt = IMAGE_PROMPT.replace("<<IMAGE_B64>>", b64)
    image_resp = call_gemini(image_prompt)
    if "error" in image_resp:
        return {"error": image_resp["error"]}
    try:
        mood_json = json.loads(image_resp["text"])
    except:
        # fallback: neutral
        mood_json = {"mood_label": "neutral", "confidence": 0.5, "key_phrases": ["face detected"]}

    # therapy generation similar to text flow
    therapy_prompt = THERAPY_PROMPT.replace("<<MOOD_LABEL>>", mood_json.get("mood_label","neutral")) \
                                   .replace("<<INTENSITY>>", str(mood_json.get("mood_intensity",4) if mood_json.get("mood_intensity") else "4")) \
                                   .replace("<<PHRASES>>", json.dumps(mood_json.get("key_phrases",[])))
    therapy_resp = call_gemini(therapy_prompt)
    try:
        therapy_json = json.loads(therapy_resp["text"])
    except:
        therapy_json = {
            "empathetic_response": "Thanks for sharing your photo. Reach out if you feel overwhelmed.",
            "immediate_actions": ["Take three slow breaths", "Find a comfortable place to sit", "Call a friend"],
            "journaling_prompt": "How do you feel after seeing this picture of yourself?",
            "follow_up_suggestion": "Consider taking short walks daily."
        }

    out = {
        "mood_label": mood_json.get("mood_label", "neutral"),
        "confidence": mood_json.get("confidence", 0.6),
        "mood_intensity": mood_json.get("mood_intensity", 4),
        "key_phrases": mood_json.get("key_phrases", []),
        "therapy": therapy_json,
        "crisis": {"is_high_risk": False},
        "timestamp": datetime.utcnow().isoformat()
    }
    save_session(out)
    return out

@app.get("/sessions")
def get_sessions():
    return load_sessions()
