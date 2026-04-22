#!/usr/bin/env python3
"""Enhance a portrait photo to premium 4K editorial quality via Gemini Nano Banana.

Usage:
    python3 enhance.py <input_image> [--output OUTPUT_PATH]

Requires:
    - GEMINI_API_KEY in the environment
    - Python 3.10+
    - google-genai, pillow  (auto-installed on first run)

Exit codes:
    0  success
    1  setup/API error (missing key, invalid key, missing file, quota, ...)
    2  API returned no image (usually a safety block)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# The enhancement prompt. Edit here to change the style the skill produces.
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

MODEL = "gemini-2.5-flash-image-preview"


def ensure_deps() -> None:
    """Install google-genai + pillow on first use. Safe to call every run."""
    try:
        import google.genai  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("[photo-enhancer-4k] Installing google-genai and pillow...", file=sys.stderr)
        subprocess.check_call(
            [
                sys.executable, "-m", "pip", "install", "--quiet",
                "google-genai", "pillow", "--break-system-packages",
            ]
        )


def enhance(input_path: Path, output_path: Path) -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "ERROR: GEMINI_API_KEY is not set.\n"
            "Get a free key at https://aistudio.google.com/apikey and run:\n"
            "  export GEMINI_API_KEY=your_key_here",
            file=sys.stderr,
        )
        return 1

    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    ensure_deps()

    from io import BytesIO
    from google import genai
    from PIL import Image

    client = genai.Client(api_key=api_key)

    with Image.open(input_path) as src:
        src.load()
        input_image = src.convert("RGB")

    print(f"[photo-enhancer-4k] Calling {MODEL} on {input_path.name}...", file=sys.stderr)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[ENHANCEMENT_PROMPT, input_image],
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            print(
                "ERROR: Gemini rejected the API key. Double-check GEMINI_API_KEY "
                "is set correctly (no stray quotes or whitespace) and that the "
                "key is active at https://aistudio.google.com/apikey.",
                file=sys.stderr,
            )
            return 1
        if "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            print(
                "ERROR: Gemini quota exhausted. Wait a bit or check usage in "
                "Google AI Studio.",
                file=sys.stderr,
            )
            return 1
        print(f"ERROR: Gemini API call failed: {exc}", file=sys.stderr)
        return 1

    image_saved = False
    text_parts: list[str] = []
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        parts = []

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            Image.open(BytesIO(inline.data)).save(output_path)
            image_saved = True
        text = getattr(part, "text", None)
        if text:
            text_parts.append(text)

    if not image_saved:
        print("ERROR: model returned no image.", file=sys.stderr)
        if text_parts:
            print("Model said:\n" + "\n".join(text_parts), file=sys.stderr)
        return 2

    print(f"[photo-enhancer-4k] Saved: {output_path}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enhance a portrait to premium 4K editorial quality via Gemini Nano Banana."
    )
    parser.add_argument("input", type=Path, help="Path to the input photo (.jpg/.jpeg/.png/.webp)")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output path (defaults to <input-stem>_enhanced.png next to the input)",
    )
    args = parser.parse_args()

    output = args.output or args.input.with_name(args.input.stem + "_enhanced.png")
    return enhance(args.input, output)


if __name__ == "__main__":
    sys.exit(main())
