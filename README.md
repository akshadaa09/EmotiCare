
EmotiCare — local demo

Prereqs:
 - Python 3.10+
 - GEMINI_API_KEY environment variable (Google AI Studio / Gemini key)

Setup:
 1. create a virtual env:
    python -m venv venv
    source venv/bin/activate   (Windows: venv\Scripts\activate)

 2. install:
    pip install -r requirements.txt

 3. set your Gemini key:
    echo "GEMINI_API_KEY=YOUR_KEY_HERE" > .env
    OR export GEMINI_API_KEY="YOUR_KEY" (linux/mac)
    OR set env var on Windows

 4. start backend:
    uvicorn main:app --reload

 5. open index.html in your browser (or serve it with a simple static server). The front-end expects the backend at http://127.0.0.1:8000

Notes:
 - This is a demo. DO NOT upload extremely sensitive personal data.
 - For production, do not allow CORS from '*', add authentication, secure API keys, and obey privacy & medical regulations.
