#!/usr/bin/env python3
"""
Webtack — Universal Image Enrichment & Alt-Text Module
Resolves rich accessibility descriptions using a multi-tiered priority:
  Tier 1: Embedded image metadata (EXIF/IPTC/PNG) — Zero AI, zero keys
  Tier 2: Upstream web page metadata (HTML alt, <figcaption>, OpenGraph) — Zero AI, zero keys
  Tier 3: Multi-provider Cloud Vision AI (Gemini, OpenAI, Anthropic, Groq, OpenRouter)
  Tier 4: Clean fallback to atom title or curator description
"""

import os
import sys
import re
import json
import shutil
import subprocess
import base64
import mimetypes
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import requests
from PIL import Image, ExifTags, IptcImagePlugin
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env(env_path: Path = None):
    """Load key-value pairs from .env into os.environ if not already set."""
    if env_path is None:
        env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


# Automatically load .env on module import
load_env()


# ─── Placeholder Detection ───────────────────────────────────────────────────

def is_placeholder_alt(alt: str | None) -> bool:
    """Detect if an alt text string is missing, generic, or just a filename."""
    if not alt:
        return True
    alt = alt.strip()
    if not alt:
        return True
    # Filenames
    if re.search(r"\.(png|jpg|jpeg|webp|gif|svg)$", alt, re.I):
        return True
    # Platform defaults
    if alt.startswith("Image from ") or alt.startswith("Are.na - "):
        return True
    if alt.lower() in ("are.na block", "visual asset", "image", "cover image", "photo", "screenshot", "untitled"):
        return True
    if alt.startswith("media_") or alt.startswith("IMG_") or alt.startswith("DSC_"):
        return True
    # Uninformative single words
    if len(alt) < 15 and " " not in alt:
        return True
    return False


# ─── Tier 1: Embedded Metadata (Zero AI, Zero Keys) ─────────────────────────

def extract_embedded_alt_text(image_path: Path) -> str | None:
    """
    Extract descriptive captions embedded in the image file itself:
    - EXIF ImageDescription (0x010E)
    - EXIF UserComment (0x9286)
    - EXIF XPTitle / XPComment (0x9c9b, 0x9c9c)
    - IPTC Caption/Abstract ((2, 120)) or Headline ((2, 105))
    - PNG text chunks (Description, Comment, Title)
    """
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        return None

    try:
        with Image.open(image_path) as img:
            # 1. EXIF Metadata
            exif = img.getexif()
            if exif:
                # Direct ImageDescription
                desc = exif.get(0x010E)
                if desc and isinstance(desc, str) and not is_placeholder_alt(desc):
                    return desc.strip()

                # UserComment or XPTitle / XPComment
                for tag_id, val in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, "")
                    if tag_name in ("ImageDescription", "UserComment") and isinstance(val, str):
                        val_clean = val.strip().replace("\x00", "")
                        if not is_placeholder_alt(val_clean):
                            return val_clean
                    elif tag_id in (0x9c9b, 0x9c9c) and isinstance(val, (bytes, str)):
                        # Windows XP tags (UCS-2 encoded bytes)
                        if isinstance(val, bytes):
                            try:
                                val = val.decode("utf-16le").strip().rstrip("\x00")
                            except Exception:
                                val = ""
                        if val and not is_placeholder_alt(val):
                            return val.strip()

            # 2. IPTC Metadata
            try:
                iptc = IptcImagePlugin.getiptcinfo(img)
                if iptc:
                    caption = iptc.get((2, 120)) or iptc.get((2, 105))
                    if caption:
                        if isinstance(caption, bytes):
                            caption = caption.decode("utf-8", errors="ignore")
                        if isinstance(caption, str) and not is_placeholder_alt(caption):
                            return caption.strip()
            except Exception:
                pass

            # 3. PNG Text Chunks
            if hasattr(img, "text") and isinstance(img.text, dict):
                for k in ("Description", "description", "Comment", "comment", "Title", "title"):
                    txt = img.text.get(k)
                    if txt and isinstance(txt, str) and not is_placeholder_alt(txt):
                        return txt.strip()
    except Exception:
        pass

    return None


# ─── Tier 2: Upstream Web Metadata (Zero AI, Zero Keys) ──────────────────────

def extract_web_alt_text(source_url: str, image_url: str = None) -> str | None:
    """
    Fetch the source webpage and extract upstream human-written alt text:
    - OpenGraph <meta property="og:image:alt">
    - Twitter <meta name="twitter:image:alt">
    - Matching <img alt="..."> or enclosing <figure><figcaption>
    """
    if not source_url or not source_url.startswith(("http://", "https://")):
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0 Webtack/1.0 (Metadata Resolver)"}
        resp = requests.get(source_url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. OpenGraph / Twitter Image Alt
        og_alt = (
            soup.find("meta", property="og:image:alt") or
            soup.find("meta", attrs={"name": "twitter:image:alt"})
        )
        if og_alt and og_alt.get("content"):
            content = og_alt["content"].strip()
            if not is_placeholder_alt(content):
                return content

        # 2. If direct image_url provided, search for matching <img> or <figure>
        if image_url:
            img_filename = Path(image_url.split("?")[0]).name
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if img_filename and img_filename in src:
                    alt = img.get("alt", "").strip()
                    if alt and not is_placeholder_alt(alt):
                        return alt
                    # Check parent figure caption
                    fig = img.find_parent("figure")
                    if fig:
                        cap = fig.find("figcaption")
                        if cap:
                            txt = cap.get_text(strip=True)
                            if txt and not is_placeholder_alt(txt):
                                return txt

        # 3. First informative figure caption on page
        first_fig = soup.find("figure")
        if first_fig:
            cap = first_fig.find("figcaption")
            if cap:
                txt = cap.get_text(strip=True)
                if txt and not is_placeholder_alt(txt):
                    return txt

    except Exception:
        pass

    return None


# ─── Tier 3: Native macOS Vision (Apple Neural Engine, Zero AI Keys) ────────

def get_macos_vision_binary() -> Path | None:
    """Find or auto-compile the native macOS Vision CLI helper."""
    if sys.platform != "darwin":
        return None
    bin_path = REPO_ROOT / "scripts" / "bin" / "macos_vision"
    swift_src = REPO_ROOT / "scripts" / "macos_vision.swift"
    if bin_path.exists():
        return bin_path
    if swift_src.exists() and shutil.which("swiftc"):
        try:
            bin_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["swiftc", "-O", str(swift_src), "-o", str(bin_path)],
                check=True,
                capture_output=True,
                timeout=30
            )
            return bin_path
        except Exception:
            pass
    return None


def extract_macos_vision_alt(image_path: Path) -> str | None:
    """
    Run native Apple Vision framework (OCR + Scene Classification) locally.
    Uses the Apple Neural Engine offline with zero network and zero API keys.
    """
    if sys.platform != "darwin":
        return None

    image_path = Path(image_path).resolve()
    if not image_path.exists():
        return None

    bin_path = get_macos_vision_binary()
    if not bin_path or not bin_path.exists():
        return None

    try:
        proc = subprocess.run(
            [str(bin_path), str(image_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None

        data = json.loads(proc.stdout)
        ocr = (data.get("ocr_text") or "").strip()
        tags = data.get("tags") or []

        meaningful_tags = [t for t in tags if t.lower() not in ("document", "item", "object", "screenshot")]
        scene = ", ".join(meaningful_tags[:3]) if meaningful_tags else None

        if ocr and scene:
            desc = f"{scene.capitalize()} with visible text: \"{ocr}\""
            if not is_placeholder_alt(desc):
                return desc
        elif ocr:
            desc = f"Image with visible text: \"{ocr}\""
            if not is_placeholder_alt(desc):
                return desc
        elif scene:
            desc = f"Image depicting {scene}"
            if not is_placeholder_alt(desc):
                return desc
    except Exception:
        pass

    return None


# ─── Tier 4: Multi-Provider Vision AI ────────────────────────────────────────

def get_available_ai_provider() -> tuple[str, str] | tuple[None, None]:
    """Detect which vision AI API key is configured (Gemini, OpenAI, Anthropic, Groq, OpenRouter)."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini", os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ.get("OPENAI_API_KEY")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ.get("ANTHROPIC_API_KEY")
    if os.environ.get("GROQ_API_KEY"):
        return "groq", os.environ.get("GROQ_API_KEY")
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter", os.environ.get("OPENROUTER_API_KEY")
    return None, None


def _get_image_b64_and_mime(image_path: Path) -> tuple[str, str] | tuple[None, None]:
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        return None, None

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type or not mime_type.startswith("image/"):
        ext = image_path.suffix.lower().lstrip(".")
        mime_type = "image/png" if ext == "png" else ("image/webp" if ext == "webp" else "image/jpeg")

    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return b64, mime_type
    except Exception:
        return None, None


ALT_PROMPT = (
    "Provide a concise, highly descriptive accessibility alt text for this image (1-2 sentences). "
    "Do not start with 'image of' or 'picture of'. Be specific about subjects, style, colors, composition, and setting."
)


def _call_gemini(api_key: str, b64_data: str, mime_type: str, model: str = "gemini-3.8-flash") -> str | None:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": ALT_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}}
                ]
            }],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 150}
        }
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            cands = r.json().get("candidates", [])
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        else:
            print(f"⚠️ Gemini API returned HTTP {r.status_code}: {r.text[:120]}")
    except Exception:
        pass
    return None


def _call_openai(api_key: str, b64_data: str, mime_type: str, model: str = "gpt-4o-mini") -> str | None:
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": ALT_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]
            }],
            "max_tokens": 150,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def _call_anthropic(api_key: str, b64_data: str, mime_type: str, model: str = "claude-3-5-haiku-20241022") -> str | None:
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model,
            "max_tokens": 150,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64_data}},
                    {"type": "text", "text": ALT_PROMPT}
                ]
            }]
        }
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            content = r.json().get("content", [])
            if content:
                return content[0].get("text", "").strip()
    except Exception:
        pass
    return None


def _call_groq(api_key: str, b64_data: str, mime_type: str, model: str = "llama-3.2-11b-vision-preview") -> str | None:
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": ALT_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]
            }],
            "max_tokens": 150,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def _call_openrouter(api_key: str, b64_data: str, mime_type: str, model: str = "google/gemini-2.0-flash-001") -> str | None:
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": ALT_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]
            }],
            "max_tokens": 150
        }
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def generate_ai_alt_text(image_path: Path) -> tuple[str | None, str | None]:
    """
    Generate alt text using whichever Cloud AI provider is configured in environment:
    Gemini -> OpenAI -> Anthropic -> Groq -> OpenRouter.
    Returns (alt_text, provider_name).
    """
    provider, key = get_available_ai_provider()
    if not provider or not key:
        return None, None

    b64_data, mime_type = _get_image_b64_and_mime(image_path)
    if not b64_data:
        return None, None

    alt = None
    if provider == "gemini":
        alt = _call_gemini(key, b64_data, mime_type)
    elif provider == "openai":
        alt = _call_openai(key, b64_data, mime_type)
    elif provider == "anthropic":
        alt = _call_anthropic(key, b64_data, mime_type)
    elif provider == "groq":
        alt = _call_groq(key, b64_data, mime_type)
    elif provider == "openrouter":
        alt = _call_openrouter(key, b64_data, mime_type)

    return alt, provider if alt else None


# ─── Article Summarization (Level 3 Multi-Provider) ──────────────────────────

ARTICLE_SUMMARY_PROMPT = (
    "Provide a concise, dense, highly informative 2-3 sentence summary of the following article. "
    "Focus on the core thesis, key insights, and primary takeaways. "
    "Do not use filler phrases like 'This article discusses', 'The author explains', or 'In this piece'. "
    "Directly state the essential ideas."
)


def _call_gemini_text(api_key: str, text: str, title: str = None, model: str = "gemini-flash-latest") -> str | None:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        user_content = f"{ARTICLE_SUMMARY_PROMPT}\n\n"
        if title:
            user_content += f"Article Title: {title}\n\n"
        user_content += f"Article Text:\n{text[:25000]}"
        payload = {
            "contents": [{"parts": [{"text": user_content}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000}
        }
        r = requests.post(url, json=payload, timeout=25)
        if r.status_code == 200:
            cands = r.json().get("candidates", [])
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts if p.get("text")]
                if text_parts:
                    return "".join(text_parts).strip()
        else:
            print(f"⚠️ Gemini API returned HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"⚠️ Gemini request failed: {e}")
    return None


def _call_openai_text(api_key: str, text: str, title: str = None, model: str = "gpt-4o-mini") -> str | None:
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        user_content = f"{ARTICLE_SUMMARY_PROMPT}\n\n"
        if title:
            user_content += f"Article Title: {title}\n\n"
        user_content += f"Article Text:\n{text[:25000]}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": 400,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def _call_anthropic_text(api_key: str, text: str, title: str = None, model: str = "claude-3-5-haiku-20241022") -> str | None:
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        user_content = f"{ARTICLE_SUMMARY_PROMPT}\n\n"
        if title:
            user_content += f"Article Title: {title}\n\n"
        user_content += f"Article Text:\n{text[:25000]}"
        payload = {
            "model": model,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": user_content}]
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            content = r.json().get("content", [])
            if content:
                return content[0].get("text", "").strip()
    except Exception:
        pass
    return None


def _call_groq_text(api_key: str, text: str, title: str = None, model: str = "llama-3.3-70b-versatile") -> str | None:
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        user_content = f"{ARTICLE_SUMMARY_PROMPT}\n\n"
        if title:
            user_content += f"Article Title: {title}\n\n"
        user_content += f"Article Text:\n{text[:25000]}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": 400,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def _call_openrouter_text(api_key: str, text: str, title: str = None, model: str = "google/gemini-2.0-flash-001") -> str | None:
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        user_content = f"{ARTICLE_SUMMARY_PROMPT}\n\n"
        if title:
            user_content += f"Article Title: {title}\n\n"
        user_content += f"Article Text:\n{text[:25000]}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": 400
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def generate_ai_article_summary(article_text: str, title: str = None) -> tuple[str | None, str | None]:
    """
    Generate a 2-3 sentence summary of article text using whichever Cloud AI provider
    is configured in environment: Gemini -> OpenAI -> Anthropic -> Groq -> OpenRouter.
    Returns (summary_text, provider_name).
    """
    if not article_text or len(article_text.strip()) < 60:
        return None, None

    provider, key = get_available_ai_provider()
    if not provider or not key:
        return None, None

    summary = None
    if provider == "gemini":
        summary = _call_gemini_text(key, article_text, title=title)
    elif provider == "openai":
        summary = _call_openai_text(key, article_text, title=title)
    elif provider == "anthropic":
        summary = _call_anthropic_text(key, article_text, title=title)
    elif provider == "groq":
        summary = _call_groq_text(key, article_text, title=title)
    elif provider == "openrouter":
        summary = _call_openrouter_text(key, article_text, title=title)

    if summary:
        return summary.strip(), provider
    return None, None


def format_ai_summary(summary: str, provider: str = None) -> str:
    """Format an AI summary with a clear label (e.g. [AI Summary: Gemini] ...)."""
    label = f"[AI Summary: {provider.capitalize()}]" if provider else "[AI Summary]"
    return f"{label} {summary.strip()}"


# ─── Unified Multi-Tier Resolver ─────────────────────────────────────────────

def resolve_image_alt_text(image_path: Path, source_url: str = None, upstream_img_url: str = None, fallback_title: str = None) -> tuple[str | None, str]:
    """
    Unified 5-tier alt-text resolver:
    1. Embedded metadata (EXIF/IPTC/PNG) — Zero AI, zero network
    2. Upstream webpage metadata (HTML img alt, <figcaption>, og:image:alt) — Zero AI
    3. Multi-provider Cloud AI (Gemini, OpenAI, Anthropic, Groq, OpenRouter)
    4. Native macOS Vision (Apple Neural Engine OCR & scene tags) — Offline fallback
    5. Fallback title
    Returns (alt_text, source_method)
    """
    image_path = Path(image_path).resolve()

    # Tier 1: Embedded image metadata (instant, zero network)
    embedded = extract_embedded_alt_text(image_path)
    if embedded and not is_placeholder_alt(embedded):
        return embedded, "embedded_exif"

    # Tier 2: Upstream web page scraping (zero AI keys)
    if source_url:
        web_alt = extract_web_alt_text(source_url, image_url=upstream_img_url)
        if web_alt and not is_placeholder_alt(web_alt):
            return web_alt, "web_metadata"

    # Tier 3: Multi-Provider Cloud AI (Gemini, OpenAI, Claude, Groq, OpenRouter)
    ai_alt, provider = generate_ai_alt_text(image_path)
    if ai_alt and not is_placeholder_alt(ai_alt):
        return ai_alt, f"ai_{provider}"

    # Tier 4: Native macOS Vision (offline fallback on Apple Silicon Neural Engine)
    macos_alt = extract_macos_vision_alt(image_path)
    if macos_alt and not is_placeholder_alt(macos_alt):
        return macos_alt, "macos_vision"

    # Tier 5: Fallback
    if fallback_title and not is_placeholder_alt(fallback_title):
        return fallback_title, "fallback_title"

    return None, "none"


def generate_image_alt_text(image_path: Path, source_url: str = None, fallback_title: str = None) -> str | None:
    """Convenience wrapper that returns just the resolved alt text string."""
    alt, _ = resolve_image_alt_text(image_path, source_url=source_url, fallback_title=fallback_title)
    return alt


def batch_enrich_articles(vault_dir: Path, limit: int = None, force: bool = False) -> int:
    """
    Scan article atoms in vault for missing or unsummarized descriptions,
    generating 2-3 sentence AI summaries labeled [AI Summary: Provider].
    """
    vault_dir = Path(vault_dir).resolve()
    db_path = vault_dir / "vault.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}. Run 'python3 curate.py reindex' first.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT id, created_at, atom_title, notes, raw_json
        FROM atoms
        WHERE kind = 'article'
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()

    provider, _ = get_available_ai_provider()
    if not provider:
        print("⚠️ No AI provider configured in .env (add GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or GROQ_API_KEY).")
        conn.close()
        return 0

    print(f"⚙️ Article Summarizer Engine: Using {provider.upper()}")

    to_process = []
    for r in rows:
        aid = r["id"]
        notes = r["notes"] or ""
        doc = json.loads(r["raw_json"]) if r["raw_json"] else {}
        atom_folder = vault_dir / "atoms" / r['created_at'][:4] / r['created_at'][5:7] / aid
        article_path = atom_folder / "article.md"

        if not article_path.exists():
            continue

        has_ai_summary = "[AI Summary" in notes
        if force or not notes or not has_ai_summary:
            to_process.append({
                "id": aid,
                "title": r["atom_title"],
                "notes": notes,
                "article_path": article_path,
                "atom_json_path": atom_folder / "atom.json",
                "doc": doc
            })

    print(f"🔍 Found {len(to_process)} article atoms eligible for AI summarization.")
    if limit and limit > 0:
        to_process = to_process[:limit]
        print(f"⚡ Limiting run to {limit} articles.")

    if not to_process:
        print("✅ All article atoms already have AI summaries!")
        conn.close()
        return 0

    updated_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, item in enumerate(to_process, 1):
        aid = item["id"]
        title = item["title"]
        art_path = item["article_path"]
        atom_json = item["atom_json_path"]
        doc = item["doc"]
        existing_notes = item["notes"]

        print(f"\n[{idx}/{len(to_process)}] Summarizing {aid} ({title[:35]}...):")
        try:
            with open(art_path, "r", encoding="utf-8") as f:
                article_body = f.read()
        except Exception as e:
            print(f"   ⚠️ Could not read {art_path}: {e}")
            continue

        ai_summary, prov_name = generate_ai_article_summary(article_body, title=title)
        if not ai_summary:
            print("   ⚠️ Could not generate AI summary. Skipping.")
            continue

        labeled_summary = format_ai_summary(ai_summary, prov_name)
        print(f"   ✨ [{prov_name.upper()}] \"{labeled_summary[:80]}...\"")

        # Combine with existing curator notes if present and not already having an AI summary
        if existing_notes and "[AI Summary" not in existing_notes:
            new_notes = f"{existing_notes}\n\n{labeled_summary}"
        else:
            new_notes = labeled_summary

        # Update document
        curation = doc.setdefault("curation", {})
        curation["description"] = new_notes
        curation["notes"] = new_notes
        doc["updated_at"] = now_iso

        # Write to disk
        try:
            with open(atom_json, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ⚠️ Failed to write {atom_json}: {e}")
            continue

        # Update SQLite
        with conn:
            conn.execute(
                "UPDATE atoms SET notes = ?, updated_at = ?, raw_json = ? WHERE id = ?",
                (new_notes, now_iso, json.dumps(doc, ensure_ascii=False), aid)
            )

        updated_count += 1

    conn.close()
    print(f"\n🎉 Successfully summarized and updated {updated_count} article atoms!")
    return updated_count


# ─── Batch Vault Enrichment ──────────────────────────────────────────────────

def batch_enrich_images(vault_dir: Path, limit: int = None, force: bool = False) -> int:
    """
    Scan image atoms in vault for missing or placeholder alt text,
    resolving descriptions through EXIF -> Web Metadata -> Cloud AI -> Title.
    """
    vault_dir = Path(vault_dir).resolve()
    db_path = vault_dir / "vault.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}. Run 'python3 curate.py reindex' first.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT id, created_at, atom_title, source_url, destination_url, cover_file_path, raw_json
        FROM atoms
        WHERE kind = 'image'
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()

    provider, _ = get_available_ai_provider()
    if provider:
        print(f"⚙️ Vision Engine: Using {provider.upper()} for generative descriptions")
    elif sys.platform == "darwin":
        print(f"⚙️ Vision Engine: Using Native macOS Vision (Apple Silicon Neural Engine, 100% offline, zero keys)")
        print(f"   💡 Tip: Add GEMINI_API_KEY or OPENAI_API_KEY to .env if you prefer generative prose")
    else:
        print(f"⚙️ Vision Engine: Using embedded EXIF/IPTC and web metadata fallback (zero keys)")
        print(f"   💡 Tip: Add GEMINI_API_KEY or OPENAI_API_KEY to .env for generative descriptions")

    to_process = []
    for r in rows:
        raw = r["raw_json"]
        doc = json.loads(raw) if raw else {}
        cover_info = (doc.get("content") or doc.get("payload") or {}).get("cover_image", {})
        alt = cover_info.get("alt_text")

        if force or is_placeholder_alt(alt):
            atom_folder = vault_dir / "atoms" / r['created_at'][:4] / r['created_at'][5:7] / r['id']
            full_img_path = atom_folder / (cover_info.get("file") or "cover.jpg")
            if not full_img_path.exists():
                cpath = cover_info.get("relative_path") or cover_info.get("path")
                if cpath:
                    full_img_path = vault_dir / cpath

            if full_img_path.exists():
                src_url = r["source_url"] or r["destination_url"]
                to_process.append({
                    "id": r["id"],
                    "title": r["atom_title"],
                    "source_url": src_url,
                    "image_path": full_img_path,
                    "atom_json_path": full_img_path.parent / "atom.json",
                    "doc": doc
                })

    print(f"🔍 Found {len(to_process)} image atoms requiring alt text.")
    if limit and limit > 0:
        to_process = to_process[:limit]
        print(f"⚡ Limiting run to {limit} atoms.")

    if not to_process:
        print("✅ All image atoms already have rich alt text descriptions!")
        conn.close()
        return 0

    updated_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, item in enumerate(to_process, 1):
        aid = item["id"]
        title = item["title"]
        img_path = item["image_path"]
        atom_json = item["atom_json_path"]
        doc = item["doc"]
        src_url = item["source_url"]

        print(f"\n[{idx}/{len(to_process)}] Resolving {aid} ({title[:35]}...):")
        alt, source_method = resolve_image_alt_text(
            image_path=img_path,
            source_url=src_url,
            fallback_title=title
        )

        if not alt:
            print("   ⚠️ Could not resolve alt text. Skipping.")
            continue

        print(f"   ✨ [{source_method.upper()}] \"{alt[:80]}...\"")

        # Update document
        content_tier = doc.setdefault("content", doc.setdefault("payload", {}))
        cover_tier = content_tier.setdefault("cover_image", {})
        cover_tier["alt_text"] = alt
        doc["updated_at"] = now_iso

        # Write to disk
        try:
            with open(atom_json, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ⚠️ Failed to write {atom_json}: {e}")
            continue

        # Update SQLite
        with conn:
            conn.execute(
                "UPDATE atoms SET updated_at = ?, raw_json = ? WHERE id = ?",
                (now_iso, json.dumps(doc, ensure_ascii=False), aid)
            )

        updated_count += 1

    conn.close()
    print(f"\n🎉 Successfully enriched {updated_count} image atoms!")
    return updated_count


def batch_enrich_vault(vault_dir: Path, target: str = "all", limit: int = None, force: bool = False) -> dict[str, int]:
    """
    Unified enrichment entrypoint: processes images, articles, or all.
    """
    vault_dir = Path(vault_dir).resolve()
    results = {"images": 0, "articles": 0}

    if target in ("all", "articles"):
        print("\n=== 📖 Article AI Summarization ===")
        results["articles"] = batch_enrich_articles(vault_dir, limit=limit, force=force)

    if target in ("all", "images"):
        print("\n=== 🖼️ Image Accessibility Alt-Text ===")
        results["images"] = batch_enrich_images(vault_dir, limit=limit, force=force)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Webtack Multi-Tier Enrichment Engine")
    parser.add_argument("--vault", default="vault", help="Path to vault directory (default: vault)")
    parser.add_argument("--target", choices=["all", "images", "articles"], default="all", help="Target atoms: images, articles, or all (default)")
    parser.add_argument("--limit", type=int, default=None, help="Max atoms to enrich per category")
    parser.add_argument("--force", action="store_true", help="Re-generate descriptions even if already present")
    args = parser.parse_args()

    batch_enrich_vault(Path(args.vault), target=args.target, limit=args.limit, force=args.force)
