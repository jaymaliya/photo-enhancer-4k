#!/usr/bin/env python3
"""Flask backend for the Photo Enhancer 4K web app."""

import os
import uuid
import threading
from io import BytesIO

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# In-memory job store: job_id -> {"status": "pending"|"done"|"error", "data": bytes|str}
JOBS = {}
JOBS_LOCK = threading.Lock()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

ENHANCEMENT_PROMPT = (
    "Enhance the portrait while strictly preserving the subject's identity with "
    "accurate facial geometry. Do not change their expression or face shape. "
    "Only allow subtle feature cleanup without altering who they are. Keep the "
    "exact same background from the reference image. No replacements, no "
    "changes, no new objects, no layout shifts. The environment must look "
    "identical. The image must be recreated as if it was shot on a Sony A1, "
    "using an 85mm f1.4 lens, at f1.6, ISO 100, 1/200 shutter speed, cinematic "
    "shallow depth of field, perfect facial focus, and an editorial-neutral "
    "color profile. This Sony A1 + 85mm f1.4 setup is mandatory. The final "
    "image must clearly look like premium full-frame Sony A1 quality. Lighting "
    "must match the exact direction, angle, and mood of the reference photo. "
    "Upgrade the lighting into a cinematic, subject-focused style: soft "
    "directional light, warm highlights, cool shadows, deeper contrast, "
    "expanded dynamic range, micro-contrast boost, smooth gradations, and zero "
    "harsh shadows. Maintain neutral premium color tone, cinematic contrast "
    "curve, natural saturation, real skin texture (not plastic), and subtle "
    "film grain. No fake glow, no runway lighting, no over smoothing. Render "
    "in 4K resolution, 10-bit color, cinematic editorial style, premium "
    "clarity, portrait crop, and keep the original environmental vibe "
    "untouched. Re-render the subject with improved realism, depth, texture, "
    "and lighting while keeping identity and background fully preserved. "
    "NEGATIVE INSTRUCTIONS: No new background. No background change. No overly "
    "dramatic lighting. No face morphing. No fake glow. No flat lighting. No "
    "over-smooth skin."
)

MODEL = "gemini-3.1-flash-image-preview"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_enhancement(job_id: str, img_bytes: bytes, api_key: str):
    """Runs in a background thread. Stores result in JOBS."""
    print(f"[{job_id}] Thread started")
    try:
        from google import genai
        from google.genai import types
        from PIL import Image

        with JOBS_LOCK:
            JOBS[job_id]["log"] = "Loading image..."
        input_image = Image.open(BytesIO(img_bytes)).convert("RGB")
        print(f"[{job_id}] Image loaded: {input_image.size}")

        with JOBS_LOCK:
            JOBS[job_id]["log"] = "Creating API client..."
        client = genai.Client(api_key=api_key)
        print(f"[{job_id}] Client created")

        with JOBS_LOCK:
            JOBS[job_id]["log"] = "Calling Gemini API..."
        print(f"[{job_id}] Calling Gemini API with model: {MODEL}")

        response = client.models.generate_content(
            model=MODEL,
            contents=[ENHANCEMENT_PROMPT, input_image],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        print(f"[{job_id}] Gemini response received")
        parts = []
        try:
            parts = response.candidates[0].content.parts
        except (AttributeError, IndexError):
            pass

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                print(f"[{job_id}] Image data received, size: {len(inline.data)} bytes")
                with JOBS_LOCK:
                    JOBS[job_id] = {"status": "done", "data": inline.data, "log": "Done"}
                return

        text_parts = [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
        reason = " ".join(text_parts) if text_parts else "No image returned by the model."
        print(f"[{job_id}] No image in response: {reason}")
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "error", "data": f"Enhancement failed: {reason}", "log": reason}

    except Exception as exc:
        msg = str(exc)
        print(f"[{job_id}] Exception: {msg}")
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            msg = "Invalid Gemini API key."
        elif "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            msg = "Gemini quota exhausted. Please try again later."
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "error", "data": f"Enhancement failed: {msg}", "log": msg}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/enhance", methods=["POST"])
def enhance():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        return jsonify({"error": "Gemini API key is not configured on the server."}), 500

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file. Please upload a JPG, PNG, or WEBP image."}), 400

    img_bytes = file.read()
    job_id = uuid.uuid4().hex

    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "data": None}

    thread = threading.Thread(target=_run_enhancement, args=(job_id, img_bytes, api_key), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "error":
        return jsonify({"status": "error", "error": job["data"]}), 200
    return jsonify({"status": job["status"], "log": job.get("log", "")}), 200


@app.route("/result/<job_id>")
def result(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Result not ready"}), 404
    buf = BytesIO(job["data"])
    buf.seek(0)
    with JOBS_LOCK:
        del JOBS[job_id]
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"enhanced_{job_id[:8]}.png")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
