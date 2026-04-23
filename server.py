#!/usr/bin/env python3
import os
import uuid
import threading
import socket
from io import BytesIO

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MODEL = "gemini-3.1-flash-image-preview"

JOBS = {}
JOBS_LOCK = threading.Lock()

PROMPT = (
    "Enhance this portrait photo. Improve lighting, sharpness, color grading. "
    "Make it look professional and cinematic. Keep the person's face and "
    "background identical. Output only the enhanced image."
)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_job(job_id, img_bytes, api_key):
    # Set socket timeout so the Gemini call can't hang forever
    socket.setdefaulttimeout(90)
    print(f"[{job_id}] Job started")
    try:
        from PIL import Image
        from google import genai
        from google.genai import types

        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((800, 800), Image.LANCZOS)

        jpeg_buf = BytesIO()
        img.save(jpeg_buf, format="JPEG", quality=85)
        jpeg_bytes = jpeg_buf.getvalue()
        print(f"[{job_id}] Image prepared: {img.size}, {len(jpeg_bytes)} bytes")

        with JOBS_LOCK:
            JOBS[job_id]["log"] = "Calling Gemini..."

        client = genai.Client(api_key=api_key)
        print(f"[{job_id}] Calling {MODEL}")

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        print(f"[{job_id}] Got response")
        parts = []
        try:
            parts = response.candidates[0].content.parts
        except Exception:
            pass

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                print(f"[{job_id}] Success! Image size: {len(inline.data)} bytes")
                with JOBS_LOCK:
                    JOBS[job_id] = {"status": "done", "data": inline.data}
                return

        text = " ".join(getattr(p, "text", "") for p in parts if getattr(p, "text", ""))
        raise Exception(text or "Gemini returned no image in response.")

    except Exception as e:
        err = str(e)
        print(f"[{job_id}] ERROR: {err}")
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "error", "error": err}


@app.errorhandler(404)
def not_found(e):
    return send_from_directory("static", "index.html")

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/test")
def test_api():
    """Quick test to verify the Gemini API key works at all."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "error": "No GEMINI_API_KEY set"}), 500
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Say: API key works!"
        )
        return jsonify({"ok": True, "reply": response.text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/enhance", methods=["POST"])
def enhance():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not set on server."}), 500

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Please upload a JPG, PNG, or WEBP file."}), 400

    img_bytes = file.read()
    job_id = uuid.uuid4().hex

    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "log": "Starting..."}

    t = threading.Thread(target=_run_job, args=(job_id, img_bytes, api_key), daemon=True)
    t.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job), 200


@app.route("/result/<job_id>")
def result(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 404
    data = job["data"]
    with JOBS_LOCK:
        del JOBS[job_id]
    buf = BytesIO(data)
    buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"enhanced_{job_id[:8]}.png")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
