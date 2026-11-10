#!/usr/bin/env python3
"""
Create a draft post in Ghost with uploaded diagrams via the Ghost Admin API.
"""

import argparse
import datetime
import os
import sys
import jwt
import requests
import markdown

def generate_ghost_token(api_key: str) -> str:
    if ':' not in api_key:
        raise ValueError("Invalid Ghost Admin API Key format. Expected 'id:secret'")
    key_id, secret = api_key.split(':', 1)
    iat = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    header = {'alg': 'HS256', 'typ': 'JWT', 'kid': key_id}
    payload = {
        'iat': iat,
        'exp': iat + 5 * 60,
        'aud': '/admin/'
    }
    return jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers=header)

def upload_image(api_url: str, token: str, image_path: str) -> str:
    url = f"{api_url.rstrip('/')}/ghost/api/admin/images/upload/"
    headers = {
        'Authorization': f'Ghost {token}',
        'Accept-Version': 'v5.0'
    }
    with open(image_path, 'rb') as f:
        files = {'file': (os.path.basename(image_path), f, 'image/png'), 'purpose': (None, 'image')}
        resp = requests.post(url, headers=headers, files=files)
        resp.raise_for_status()
        data = resp.json()
        return data['images'][0]['url']

def load_credentials(args):
    api_url = args.api_url or os.environ.get("GHOST_ADMIN_API_URL")
    api_key = args.api_key or os.environ.get("GHOST_ADMIN_API_KEY")

    if not api_url or not api_key:
        config_path = os.path.expanduser("~/.gemini/antigravity/ghost_config.json")
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    api_url = api_url or cfg.get("api_url")
                    api_key = api_key or cfg.get("admin_api_key")
            except Exception as e:
                print(f"Warning: Failed to load {config_path}: {e}", file=sys.stderr)

    return api_url, api_key

def main():
    parser = argparse.ArgumentParser(description="Create Ghost draft post")
    parser.add_argument("--api-url", default=None, help="Ghost Admin URL")
    parser.add_argument("--api-key", default=None, help="Ghost Admin API key (id:secret)")
    parser.add_argument("--draft-file", default="docs/webtack-ghost-draft.md", help="Path to markdown draft")
    args = parser.parse_args()

    api_url, api_key = load_credentials(args)

    if not api_url or not api_key:
        print("Error: Missing Ghost Admin API URL or API Key.", file=sys.stderr)
        print("Please provide --api-url and --api-key or set GHOST_ADMIN_API_URL and GHOST_ADMIN_API_KEY.", file=sys.stderr)
        sys.exit(1)

    api_url = api_url.rstrip('/')
    token = generate_ghost_token(api_key)

    print(f"Connecting to Ghost at {api_url}...")

    # Upload the three diagrams
    diagram_map = {
        "assets/webtack-reflection.png": "docs/assets/webtack-reflection.png",
        "assets/webtack-architecture.png": "docs/assets/webtack-architecture.png",
        "assets/webtack-schema.png": "docs/assets/webtack-schema.png"
    }

    uploaded_urls = {}
    for placeholder, local_path in diagram_map.items():
        if os.path.exists(local_path):
            print(f"Uploading {local_path} to Ghost...")
            ghost_url = upload_image(api_url, token, local_path)
            uploaded_urls[placeholder] = ghost_url
            print(f"  -> Uploaded: {ghost_url}")
        else:
            print(f"Warning: Local image not found at {local_path}", file=sys.stderr)

    with open(args.draft_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace image links with Ghost media URLs
    for placeholder, ghost_url in uploaded_urls.items():
        content = content.replace(placeholder, ghost_url)

    # Extract title from first line if markdown heading
    lines = content.strip().splitlines()
    title = "Introducing WebTack - a new open-source framework for saving and storing content from the web"
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        body_md = "\n".join(lines[1:]).strip()
    else:
        body_md = content

    # Convert markdown body to HTML for Ghost
    html_content = markdown.markdown(body_md, extensions=['extra', 'sane_lists'])

    # Post draft to Ghost Admin API
    posts_url = f"{api_url}/ghost/api/admin/posts/?source=html"
    headers = {
        'Authorization': f'Ghost {token}',
        'Content-Type': 'application/json',
        'Accept-Version': 'v5.0'
    }
    payload = {
        "posts": [{
            "title": title,
            "html": html_content,
            "status": "draft",
            "tags": ["WebTack", "Open Source"]
        }]
    }

    print("Creating draft post in Ghost...")
    resp = requests.post(posts_url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    created_post = resp.json()['posts'][0]
    print(f"Success! Draft post created:")
    print(f"  Title: {created_post.get('title')}")
    print(f"  ID: {created_post.get('id')}")
    print(f"  URL: {created_post.get('url')}")
    print(f"  Edit in Ghost Admin: {api_url}/ghost/#/editor/post/{created_post.get('id')}")

if __name__ == "__main__":
    main()
