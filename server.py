#!/usr/bin/env python3
import os
import uuid
import threading
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
    "You are a professional photo retoucher. Enhance this portrait photo: "
    "improve lighting, sharpness, color grading, and overall quality. "
    "Make it look like it was shot on a Sony A1 camera with cinematic quality. "
    "Keep the person's face, identity, and background exactly the same. "
    "Output only the enhanced image."
)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_job(job_id, img_bytes, api_key):
    try:
        from PIL import Image
        from google import genai
        from google.genai import types

        # Resize to max 800px — keeps Gemini fast and avoids timeouts
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        max_dim = 800
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Convert to JPEG bytes for API
        jpeg_buf = BytesIO()
        img.save(jpeg_buf, format="JPEG", quality=90)
        jpeg_bytes = jpeg_buf.getvalue()

        print(f"[{job_id}] Image size: {img.size}, JPEG bytes: {len(jpeg_bytes)}, calling Gemini...")

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        print(f"[{job_id}] Gemini responded")

        parts = []
        try:
            parts = response.candidates[0].content.parts
        except Exception:
            pass

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                print(f"[{job_id}] Got image back!")
                with JOBS_LOCK:
                    JOBS[job_id] = {"status": "done", "data": inline.data}
                return

        # No image returned — check text reason
        text = " ".join(getattr(p, "text", "") for p in parts if getattr(p, "text", ""))
        raise Exception(text or "Gemini returned no image.")

    except Exception as e:
        print(f"[{job_id}] Error: {e}")
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "error", "error": str(e)}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


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
        JOBS[job_id] = {"status": "pending"}

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
