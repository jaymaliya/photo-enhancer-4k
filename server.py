#!/usr/bin/env python3
"""Flask backend for the Photo Enhancer 4K web app."""

import os
import uuid
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

load_dotenv()


def _supabase_log():
    """Insert one row into `enhancements` to count a button click. Silent on failure."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key or "your_supabase" in url:
        return
    try:
        from supabase import create_client
        create_client(url, key).table("enhancements").insert({}).execute()
    except Exception:
        pass

app = Flask(__name__, static_folder="static", static_url_path="")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

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

MODEL = "gemini-2.0-flash-preview-image-generation"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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

    try:
        from google import genai
        from PIL import Image

        img_bytes = file.read()
        input_image = Image.open(BytesIO(img_bytes)).convert("RGB")

        from google.genai import types

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        response = client.models.generate_content(
            model=MODEL,
            contents=[ENHANCEMENT_PROMPT, input_image],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        parts = []
        try:
            parts = response.candidates[0].content.parts
        except (AttributeError, IndexError):
            pass

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                output_buf = BytesIO(inline.data)
                output_buf.seek(0)
                _supabase_log()
                filename = f"enhanced_{uuid.uuid4().hex[:8]}.png"
                return send_file(
                    output_buf,
                    mimetype="image/png",
                    as_attachment=True,
                    download_name=filename,
                )

        text_parts = [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
        reason = " ".join(text_parts) if text_parts else "No image returned by the model."
        return jsonify({"error": f"Enhancement failed: {reason}"}), 502

    except Exception as exc:
        msg = str(exc)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            return jsonify({"error": "Invalid Gemini API key. Check server configuration."}), 500
        if "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            return jsonify({"error": "Gemini quota exhausted. Please try again later."}), 429
        return jsonify({"error": f"Enhancement failed: {msg}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
