"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Image Generation (DALL-E 3)                  ║
╠══════════════════════════════════════════════════════════╣
║  Generate images via OpenAI DALL-E 3 API.                ║
║  Saves to ~/Documents/TARS_Reports/                      ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
import urllib.request
import tempfile
from datetime import datetime

logger = logging.getLogger("tars.image_gen")

REPORT_DIR = os.path.expanduser("~/Documents/TARS_Reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def generate_image(prompt, api_key, size="1024x1024", quality="standard", style="vivid", filename=None):
    """Generate an image using DALL-E 3.
    
    Args:
        prompt: Image description
        api_key: OpenAI API key
        size: 1024x1024, 1792x1024, or 1024x1792
        quality: "standard" or "hd"
        style: "vivid" or "natural"
        filename: Custom filename (auto-generated if None)
    
    Returns:
        Standard tool result dict with path to saved image
    """
    if not api_key:
        return {"success": False, "error": True, "content": "OpenAI API key required for image generation. Set image_generation.api_key in config.yaml."}

    try:
        payload = json.dumps({
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "style": style,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())

        image_url = result["data"][0]["url"]
        revised_prompt = result["data"][0].get("revised_prompt", prompt)

        # Download the image
        img_req = urllib.request.Request(image_url)
        with urllib.request.urlopen(img_req, timeout=60) as resp:
            image_data = resp.read()

        # Save to file
        if not filename:
            safe_prompt = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt[:50])
            filename = f"image_{safe_prompt}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image_data)

        logger.info(f"Image generated: {filepath}")

        return {
            "success": True,
            "path": filepath,
            "content": f"Image generated and saved to {filepath}\nRevised prompt: {revised_prompt}"
        }

    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if hasattr(e, 'read') else str(e)
        return {"success": False, "error": True, "content": f"DALL-E API error ({e.code}): {error_body[:300]}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Image generation error: {e}"}
