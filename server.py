#!/usr/bin/env python3
import os
import uuid
from io import BytesIO
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def enhance_image(img_bytes):
    from PIL import Image, ImageFilter, ImageEnhance

    img = Image.open(BytesIO(img_bytes)).convert("RGB")

    # Upscale 2x with high quality
    new_w = img.width * 2
    new_h = img.height * 2
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Sharpen details
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))

    # Boost contrast
    img = ImageEnhance.Contrast(img).enhance(1.25)

    # Boost color vibrancy
    img = ImageEnhance.Color(img).enhance(1.2)

    # Final sharpness pass
    img = ImageEnhance.Sharpness(img).enhance(1.8)

    # Boost brightness slightly
    img = ImageEnhance.Brightness(img).enhance(1.05)

    return img


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/enhance", methods=["POST"])
def enhance():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file. Please upload a JPG, PNG, or WEBP image."}), 400

    try:
        img_bytes = file.read()
        result = enhance_image(img_bytes)

        buf = BytesIO()
        result.save(buf, format="PNG", optimize=True)
        buf.seek(0)

        filename = f"enhanced_{uuid.uuid4().hex[:8]}.png"
        return send_file(buf, mimetype="image/png", as_attachment=True, download_name=filename)

    except Exception as exc:
        return jsonify({"error": f"Enhancement failed: {str(exc)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
