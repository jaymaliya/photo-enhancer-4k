#!/usr/bin/env python3
import os
import uuid
import threading
import json
import socket
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MODEL = "gemini-3.1-flash-image-preview"
JOB_DIR = Path("/tmp/enhance_jobs")
JOB_DIR.mkdir(exist_ok=True)

PROMPT = (
    "Enhance this portrait photo professionally. Improve lighting, sharpness, "
    "color grading and quality. Make it look cinematic. Keep the person's "
    "face and background exactly the same. Output only the enhanced image."
)


def allowed_file(f):
    return "." in f and f.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def job_set(job_id, data: dict):
    (JOB_DIR / f"{job_id}.json").write_text(json.dumps(data))


def job_get(job_id):
    p = JOB_DIR / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def job_set_image(job_id, img_bytes: bytes):
    (JOB_DIR / f"{job_id}.png").write_bytes(img_bytes)


def job_get_image(job_id):
    p = JOB_DIR / f"{job_id}.png"
    return p.read_bytes() if p.exists() else None


def job_delete(job_id):
    for ext in ("json", "png"):
        p = JOB_DIR / f"{job_id}.{ext}"
        if p.exists():
            p.unlink()



def _run_job(job_id, img_bytes, api_key):
    socket.setdefaulttimeout(80)
    print(f"[{job_id}] started")
    try:
        from PIL import Image
        from google import genai
        from google.genai import types

        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((800, 800), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        jpeg = buf.getvalue()
        print(f"[{job_id}] image ready {img.size}")

        job_set(job_id, {"status": "pending", "log": "Calling Gemini AI..."})

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[PROMPT, types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        print(f"[{job_id}] gemini responded")

        parts = []
        try:
            parts = response.candidates[0].content.parts
        except Exception:
            pass

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                print(f"[{job_id}] gemini success {len(inline.data)} bytes")
                job_set_image(job_id, inline.data)
                job_set(job_id, {"status": "done"})
                return

        raise Exception("Gemini returned no image — using enhancement fallback.")

    except Exception as e:
        print(f"[{job_id}] error: {e}")
        job_set(job_id, {"status": "error", "error": str(e)})


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
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "error": "No GEMINI_API_KEY set"})
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        r = client.models.generate_content(model="gemini-2.0-flash", contents="Say: works!")
        return jsonify({"ok": True, "reply": r.text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/enhance", methods=["POST"])
def enhance():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not configured."}), 500
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400
    file = request.files["image"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Please upload JPG, PNG or WEBP."}), 400

    img_bytes = file.read()
    job_id = uuid.uuid4().hex
    job_set(job_id, {"status": "pending", "log": "Starting..."})

    t = threading.Thread(target=_run_job, args=(job_id, img_bytes, api_key), daemon=True)
    t.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/status/<job_id>")
def status(job_id):
    job = job_get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@app.route("/result/<job_id>")
def result(job_id):
    job = job_get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error": "Not ready"}), 404
    data = job_get_image(job_id)
    if not data:
        return jsonify({"error": "Image missing"}), 404
    job_delete(job_id)
    return send_file(BytesIO(data), mimetype="image/png", as_attachment=True,
                     download_name=f"enhanced_{job_id[:8]}.png")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
