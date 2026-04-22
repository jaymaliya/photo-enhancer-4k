---
name: photo-enhancer-4k
description: Enhance portrait photos to premium 4K editorial quality using Google's Gemini Nano Banana (gemini-2.5-flash-image) model. Use this skill whenever the user wants to upscale, enhance, restore, clean up, retouch, or "make 4K" a photo — especially portraits. Triggers on phrases like "make this 4K", "enhance my photo", "clean up this picture", "upscale this image", "make this look professional/cinematic", "retouch my portrait", "nano banana enhance", "give my photo a Sony A1 look", or whenever the user uploads a portrait and asks for improvement. Also triggers for "restore old photo", "sharpen photo", "fix this photo", and similar intents, even when the user doesn't explicitly say "4K".
---

# Photo Enhancer 4K (Gemini Nano Banana)

Enhance portrait photos to premium editorial 4K quality using Google's Gemini 2.5 Flash Image model (aka **Nano Banana**). The skill preserves the subject's identity and background while re-rendering the shot as if captured on a Sony A1 + 85mm f1.4 — soft directional light, cinematic contrast, real skin texture, no face morphing.

## When this skill applies

Use this skill whenever the user wants any of:

- Upscale / enhance / "make 4K" a photo
- Clean up, restore, or retouch a portrait
- Give a photo a cinematic / editorial / Sony A1 look
- "Fix this picture" where the subject is a person

If the input is clearly not a portrait (product shot, landscape, document), warn the user that the prompt is tuned for portraits — they can still proceed, but results may be off. If the user wants a different creative style (watercolor, cartoon, background change), this skill is the wrong tool; tell them so.

## Prerequisites

1. **`GEMINI_API_KEY`** environment variable must be set. If missing, tell the user:
   > "You need a Gemini API key. Get one free at https://aistudio.google.com/apikey, then set it with `export GEMINI_API_KEY=your_key_here` (add it to your shell profile to make it permanent)."
   Do not try to proceed without a key.
2. Python 3.10+. The script auto-installs `google-genai` and `pillow` on first run.

## How to run it

Invoke the bundled script with the input photo path:

```bash
python3 scripts/enhance.py <path/to/photo.jpg>
```

The enhanced image is written next to the input with an `_enhanced.png` suffix (e.g. `selfie.jpg` → `selfie_enhanced.png`). To override:

```bash
python3 scripts/enhance.py <input> --output <custom/output.png>
```

The script:

1. Reads `GEMINI_API_KEY` from the environment
2. Loads the input image
3. Calls `gemini-2.5-flash-image-preview` with the embedded enhancement prompt + image
4. Extracts the returned image bytes and saves them as PNG
5. Exits with code 0 on success, 1 on setup errors (missing key / missing file), 2 if the model returned no image

## After running

Tell the user the output path. In Cowork, emit a `computer://` link so they can open it in place. If they want a different look, point them at `scripts/enhance.py` — the prompt lives in the `ENHANCEMENT_PROMPT` constant and can be edited directly, or a fork of this skill can be made.

## Prompt details

The embedded prompt strictly preserves:

- Subject identity and facial geometry (no face morphing)
- The original background and environment
- Lighting direction from the source

And re-renders with:

- Sony A1 + 85mm f1.4 @ f1.6, ISO 100, 1/200 camera simulation
- Cinematic shallow depth of field, subject-focused light
- Real skin texture (not plastic), subtle film grain
- 10-bit color, expanded dynamic range, editorial-neutral palette

## Caveats to flag to the user

- **Native output resolution** from Nano Banana is typically ~1024px on the long edge. The prompt asks for 4K, but actual pixel dimensions depend on the model — the output will be premium *quality*, not necessarily 3840×2160 *pixels*. If true-4K pixel dimensions are needed, a separate upscaler (e.g., Real-ESRGAN, Topaz) can be run after.
- **Safety blocks** can cause the model to return text instead of an image. The script surfaces the text response and exits 2. Usually means the input tripped a safety filter — try a different photo.
- **Cost**: each call bills against the user's Gemini API quota. Remind the user on batch runs.
