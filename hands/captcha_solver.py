"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Free CAPTCHA Solver (Vision LLM)                 ║
╠══════════════════════════════════════════════════════════════╣
║  Solves CAPTCHAs using vision LLM (Gemini) instead of paid  ║
║  services like 2Captcha. Takes a screenshot, sends it to    ║
║  the vision model, and follows its instructions.             ║
║                                                              ║
║  Supports:                                                   ║
║    - reCAPTCHA v2 checkbox ("I'm not a robot")               ║
║    - reCAPTCHA v2 image challenges                           ║
║    - Cloudflare Turnstile                                    ║
║    - hCaptcha checkbox                                       ║
║    - Press-and-hold CAPTCHAs                                 ║
║    - Text-based CAPTCHAs (distorted text)                    ║
║    - Simple math/logic CAPTCHAs                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import base64
import json
import time
import logging
import os
import re

logger = logging.getLogger("TARS")


def _get_vision_client():
    """Get a Gemini vision client from config."""
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        if not os.path.exists(config_path):
            return None, None

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Try brain_llm first (usually Gemini), then agent_llm
        for llm_key in ("brain_llm", "agent_llm", "fallback_llm"):
            llm_cfg = config.get(llm_key, {})
            if llm_cfg.get("provider") == "gemini" and llm_cfg.get("api_key"):
                try:
                    from google import genai as _genai
                    client = _genai.Client(api_key=llm_cfg["api_key"])
                    model = llm_cfg.get("model", "gemini-2.5-flash")
                    return client, model
                except ImportError:
                    continue

        return None, None
    except Exception as e:
        logger.warning(f"[CAPTCHASolver] Failed to get vision client: {e}")
        return None, None


def analyze_captcha_screenshot(screenshot_b64):
    """Send a screenshot to vision LLM and get CAPTCHA analysis.

    Args:
        screenshot_b64: Base64-encoded screenshot image

    Returns:
        dict with:
            type: CAPTCHA type detected
            action: What action to take
            details: Specific instructions (coordinates, text, etc.)
    """
    client, model = _get_vision_client()
    if not client:
        return {"type": "unknown", "action": "none", "details": "No vision LLM available"}

    try:
        from google.genai import types as _types

        prompt = """Analyze this screenshot for CAPTCHA challenges. Respond in JSON format only.

Look for:
1. reCAPTCHA checkbox ("I'm not a robot") - identify its screen position
2. reCAPTCHA image grid (select all images with X) - identify which tiles to click
3. Cloudflare Turnstile verification widget
4. hCaptcha checkbox or challenge
5. "Press and hold" buttons
6. Text/distorted text CAPTCHAs - read the text
7. Math/logic CAPTCHAs - solve them
8. Any other verification challenge

Respond ONLY with JSON:
{
    "captcha_found": true/false,
    "type": "recaptcha_checkbox|recaptcha_image|turnstile|hcaptcha|press_hold|text_captcha|math_captcha|other|none",
    "action": "click_checkbox|select_tiles|click_verify|press_and_hold|type_text|none",
    "details": {
        "description": "What you see",
        "text_to_type": "if text CAPTCHA, the text to type",
        "tiles_to_click": [1,2,5] (1-9 grid positions if image grid),
        "checkbox_location": "approximate position description",
        "challenge_text": "the challenge prompt if any (e.g., 'Select all images with traffic lights')"
    }
}"""

        image_part = _types.Part.from_bytes(
            data=base64.b64decode(screenshot_b64),
            mime_type="image/jpeg",
        )

        response = client.models.generate_content(
            model=model,
            contents=[
                _types.Content(
                    role="user",
                    parts=[
                        _types.Part.from_text(text=prompt),
                        image_part,
                    ],
                )
            ],
        )

        # Parse the JSON response
        text = response.text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)

        result = json.loads(text)
        logger.info(f"[CAPTCHASolver] Vision analysis: type={result.get('type')}, action={result.get('action')}")
        return result

    except json.JSONDecodeError:
        logger.warning(f"[CAPTCHASolver] Vision response not JSON: {text[:200]}")
        return {"type": "unknown", "action": "none", "details": f"Vision response: {text[:300]}"}
    except Exception as e:
        logger.warning(f"[CAPTCHASolver] Vision analysis failed: {e}")
        return {"type": "error", "action": "none", "details": str(e)}


def solve_recaptcha_checkbox(cdp_module):
    """Click the reCAPTCHA "I'm not a robot" checkbox.

    Finds the reCAPTCHA iframe, calculates the checkbox position,
    and clicks it with human-like timing.
    """
    from hands.browser import _js, _cdp, _ensure
    _ensure()

    # Find reCAPTCHA iframe
    iframe_info = _js("""
        (function() {
            var frames = document.querySelectorAll('iframe[src*="recaptcha"], iframe[title*="reCAPTCHA"]');
            for (var i = 0; i < frames.length; i++) {
                var r = frames[i].getBoundingClientRect();
                if (r.width > 30 && r.height > 30) {
                    return JSON.stringify({x: r.x + 28, y: r.y + 28, w: r.width, h: r.height, src: frames[i].src.substring(0, 100)});
                }
            }
            // Also check for Turnstile
            var turnstile = document.querySelectorAll('iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]');
            for (var i = 0; i < turnstile.length; i++) {
                var r = turnstile[i].getBoundingClientRect();
                if (r.width > 30 && r.height > 30) {
                    return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height, src: turnstile[i].src.substring(0, 100), type: 'turnstile'});
                }
            }
            return '';
        })()
    """)

    if not iframe_info:
        return None  # No CAPTCHA iframe found

    try:
        info = json.loads(iframe_info)
    except json.JSONDecodeError:
        return None

    import random
    x = int(info["x"]) + random.randint(-3, 3)
    y = int(info["y"]) + random.randint(-3, 3)

    # Human-like click sequence
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": x, "y": y,
    })
    time.sleep(random.uniform(0.1, 0.3))

    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })
    time.sleep(random.uniform(0.05, 0.15))

    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })

    captcha_type = info.get("type", "recaptcha")
    logger.info(f"[CAPTCHASolver] Clicked {captcha_type} checkbox at ({x}, {y})")
    return f"Clicked {captcha_type} checkbox at ({x}, {y})"


def solve_with_vision(screenshot_func, click_func, type_func):
    """Full CAPTCHA solving flow using vision LLM.

    Args:
        screenshot_func: Function that returns base64 screenshot
        click_func: Function that clicks at (x, y) coordinates
        type_func: Function that types text

    Returns:
        str: Result description
    """
    # Step 1: Take screenshot and analyze
    screenshot_b64 = screenshot_func()
    if not screenshot_b64:
        return "Failed to capture screenshot for CAPTCHA analysis"

    analysis = analyze_captcha_screenshot(screenshot_b64)

    if not analysis.get("captcha_found"):
        return "No CAPTCHA detected in screenshot"

    captcha_type = analysis.get("type", "unknown")
    action = analysis.get("action", "none")
    details = analysis.get("details", {})

    # Step 2: Execute based on analysis
    if captcha_type in ("recaptcha_checkbox", "turnstile", "hcaptcha"):
        # Try to click the checkbox
        result = solve_recaptcha_checkbox(None)
        if result:
            time.sleep(2)
            return f"CAPTCHA: {result}. Wait 2-3 seconds then check if it's solved."
        return f"CAPTCHA detected ({captcha_type}) but couldn't find the checkbox element. Try screenshot to see the exact layout."

    elif captcha_type == "text_captcha" and details.get("text_to_type"):
        text = details["text_to_type"]
        return f"CAPTCHA text recognized: '{text}' — type this into the CAPTCHA input field."

    elif captcha_type == "math_captcha" and details.get("text_to_type"):
        answer = details["text_to_type"]
        return f"CAPTCHA math answer: '{answer}' — type this into the CAPTCHA input field."

    elif captcha_type == "press_hold":
        return "Press-and-hold CAPTCHA detected. Use hold(target='captcha', duration=10) to solve it."

    elif captcha_type == "recaptcha_image":
        challenge = details.get("challenge_text", "unknown challenge")
        tiles = details.get("tiles_to_click", [])
        if tiles:
            return (
                f"reCAPTCHA image challenge: '{challenge}'\n"
                f"Vision LLM suggests clicking tiles: {tiles} (1-9 grid, left-to-right, top-to-bottom)\n"
                f"Use screenshot() to see the grid, then click each tile by coordinates.\n"
                f"After clicking all tiles, click the 'Verify' button."
            )
        return f"reCAPTCHA image challenge: '{challenge}'. Take a screenshot to see the grid and click matching tiles."

    else:
        desc = details.get("description", "Unknown challenge") if isinstance(details, dict) else str(details)
        return f"CAPTCHA detected: {captcha_type}. {desc}. The Screen Agent may handle this better — it uses real mouse/keyboard input."
