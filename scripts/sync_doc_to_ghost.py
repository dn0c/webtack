#!/usr/bin/env python3
"""
Sync finalized WebTack introduction blog post to Ghost with callout cards and diagrams.
"""

import json
import os
import sys
import time
import jwt
import requests

def main():
    config_path = os.path.expanduser("~/.gemini/antigravity/ghost_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_url = cfg["api_url"].rstrip("/")
    key_id, secret = cfg["admin_api_key"].split(":")

    iat = int(time.time())
    token = jwt.encode(
        {"iat": iat, "exp": iat + 300, "aud": "/admin/"},
        bytes.fromhex(secret),
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT", "kid": key_id}
    )

    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
        "Accept-Version": "v5.0"
    }

    post_id = "6af2affe52a1940001bb8624"

    # Fetch current post to obtain updated_at
    resp = requests.get(f"{api_url}/ghost/api/admin/posts/{post_id}/", headers=headers)
    resp.raise_for_status()
    current_post = resp.json()["posts"][0]
    updated_at = current_post["updated_at"]

    img_reflection = "https://storage.ghost.io/c/5d/97/5d978d6c-7b8d-4f8a-9b0a-641815cdd124/content/images/2026/11/webtack-reflection.png"
    img_architecture = "https://storage.ghost.io/c/5d/97/5d978d6c-7b8d-4f8a-9b0a-641815cdd124/content/images/2026/11/webtack-architecture.png"
    img_schema = "https://storage.ghost.io/c/5d/97/5d978d6c-7b8d-4f8a-9b0a-641815cdd124/content/images/2026/11/webtack-schema.png"

    html_content = f"""<p>Bookmarking tools have long been some of my favorite corners of the internet.</p>
<p>Between <a href="https://www.pinterest.com">Pinterest</a>, <a href="https://pinboard.in">Pinboard</a>, <a href="https://www.instapaper.com">Instapaper</a>, <a href="https://www.are.na">Are.na</a>, <a href="https://sublime.app">Sublime</a>, <a href="https://www.cosmos.so">Cosmos</a>, <a href="https://raindrop.io">Raindrop.io</a>, and countless more, they’re largely free of “<a href="https://en.wikipedia.org/wiki/Dark_pattern">dark patterns</a>” and algorithmic feeds, and they provide users with a quiet (or private) place to save the things that are important to them—links, recipes, outfits, online shopping lists, articles, notes, inspiration, etc.</p>
<p>In a world where so much of one’s online life is mediated by the social graph, I think they’re capable of reflecting one’s “true” self in a way other online tools can’t.</p>
<p>The downside of these tools is that they often make it difficult for you to get your content “out”, leading to limited portability and high switching costs if another player comes on the market.</p>
<p>I’ve been a very happy (paying) customer of tools like <a href="https://www.are.na">Are.na</a> and <a href="https://www.instapaper.com">Instapaper</a> for many years, and I want to continue paying them for their incredible product designers, engineers, and apps.</p>
<div class="kg-card kg-callout-card kg-callout-card-accent"><div class="kg-callout-emoji">💡</div><div class="kg-callout-text">But I want to pay them for their software as an interface layer <em>on top</em> of my contextual data, not the data itself.</div></div>
<p>If another tool comes around that has better social features, a more pleasant UI, or advanced technical capabilities, I want to switch and bring my data with me.</p>
<p>Over the last decade-plus, I’ve saved nearly 15,000 pieces of content—quotes, articles, links, images, etc. In contrast to “digital exhaust” (the valuable digital detritus that we passively accumulate as a result of living online), these items reflect an intentional choice: “this is important to me; this is something I want to save.”</p>
<p>This is a bit of a twist on—or perhaps the logical conclusion of—what I’ve been <a href="https://www.linkedin.com/feed/update/urn:li:activity:7464732747652071424/">thinking about lately</a>, and discussed in a <a href="https://www.drewshannon.net/a-series-of-tubes/">recent post</a> about stimulation overload and information processing. In a world where lots of stuff is coming at you, it’s crucial to have a system to triage and process that information. Some of that information will become tasks, other information will become reference material you want to save for later.</p>
<figure class="kg-card kg-image-card"><img src="{img_reflection}" class="kg-image" alt="Triaging the stream: separating transient digital exhaust from reference material worth saving." loading="lazy"><figcaption>Triaging the stream: separating transient digital exhaust from reference material worth saving.</figcaption></figure>
<hr>
<h2>Introducing WebTack</h2>
<p>Introducing <a href="https://webtack.net">WebTack</a>, a project I’ve been working on lately: an open-source framework for saving and storing content from the web.</p>
<p>It’s pretty simple:</p>
<ul>
  <li><strong>Save the online content that’s important to you</strong> (whether it’s imported from an existing service, or added via our Bookmarklet or CLI)
    <ul>
      <li>7 content types: Bookmarks, Articles, Images, Files, Quotes, Notes, or Videos</li>
      <li>50+ optional metadata fields</li>
    </ul>
  </li>
  <li><strong>Your content is saved to your local machine in a specific file structure, simultaneously building:</strong>
    <ul>
      <li>A <a href="https://www.sqlite.org">SQLite</a> database created to give you instant search capabilities</li>
      <li>Structured <a href="https://json-schema.org">JSON schema</a> designed to capture important metadata such as Privacy, Source, Author, File Size, image dimensions, Tags, etc</li>
    </ul>
  </li>
  <li><strong>Once you’ve built your database, the data is yours, to do what you wish. You could:</strong>
    <ul>
      <li>Sync it to the cloud, for access on any device.</li>
      <li>Build a custom UI on top of it as an alternative to the public platforms</li>
      <li>Use the included <a href="https://modelcontextprotocol.io">MCP Server</a> to hook it up to your local Agentic AI tool to enrich your data (“look through all my saved images and suggest alt text to add to improve accessibility”)</li>
      <li>AI assisted search (“based on these YouTube videos I’ve saved, what other creators might I be interested in?”)</li>
    </ul>
  </li>
  <li><strong>(Optional) Export your data</strong>
    <ul>
      <li>We provide 10+ export templates to prepare your data for ingestion into tools like <a href="https://obsidian.md">Obsidian</a>, <a href="https://readwise.io">Readwise</a>, RSS, and more.</li>
      <li>We also support exports for Gemini Notebook and <a href="https://llmstxt.org">llms.txt</a></li>
      <li>Out of the box, WebTack ships with a visual gallery viewer, which lets you see &amp; browse your database, and supports full text search, embedded YouTube playback, lightweight capture tools, and more.</li>
      <li>Publish on the web. Want to see an example? Visit <a href="https://drewshannon.net/garden">drewshannon.net/garden</a></li>
    </ul>
  </li>
</ul>
<figure class="kg-card kg-image-card"><img src="{img_architecture}" class="kg-image" alt="WebTack architecture: local-first vault, open JSON sidecars, disposable SQLite cache, and extensible interfaces." loading="lazy"><figcaption>WebTack architecture: local-first vault, open JSON sidecars, disposable SQLite cache, and extensible interfaces.</figcaption></figure>
<hr>
<h2>Why Local-First Archiving Matters</h2>
<p>Even if you choose to continue using an established tool like <a href="https://www.pinterest.com">Pinterest</a>, there are great benefits to WebTack as an offline backup or archive:</p>
<ul>
  <li><strong>Redundancy / backups</strong> - these platforms could theoretically go down at any moment, so if you’ve put sentimental, professional, or creative importance on this content, having a local copy will give you peace-of-mind.</li>
  <li><strong>Cross-platform utility</strong> - I’ve personally imported Articles from <a href="https://www.instapaper.com">Instapaper</a>, Images from <a href="https://www.are.na">Are.na</a>, and Quotes from Kindle. Having them all in 1 place is pretty cool.</li>
  <li><strong>Expandability</strong> - Bookmarking tools only have so much metadata, but it may be important for you to store other important context.</li>
  <li><strong>Flexibility</strong> - Having local copies of your saved content, as well as a robust schema of metadata, gives you nearly unlimited control over what to do with it.</li>
  <li><strong>Own your Data</strong> - When you store your data with a major provider, you’re at the whim of their product &amp; business decisions. Take that control into your own hands.</li>
  <li><strong>Avoid linkrot</strong> - WebTack doesn't just save a bookmark pointer, it also supports saving the full text of articles, YouTube video transcripts (transcript.txt), and high-res photos, protecting against link rot and paywalls.</li>
  <li><strong>Privacy</strong> - WebTack is Zero-AI by default and runs 100% offline with no dependencies or API keys needed. Because it’s open-source and you own the data, you’re of course welcome to connect your database to any tools you’d like (I gotta say, giving Antigravity access to it feels magical), but that’s all opt-in.</li>
</ul>
<p><strong>A few other things to mention:</strong></p>
<figure class="kg-card kg-image-card"><img src="{img_schema}" class="kg-image" alt="The WebTack Atom Schema: a 3-tier decoupled model preserving editorial intent, source provenance, and raw content." loading="lazy"><figcaption>The WebTack Atom Schema: a 3-tier decoupled model preserving editorial intent, source provenance, and raw content.</figcaption></figure>
<hr>
<p>Curious to check it out or build with it? Visit <a href="https://webtack.net">https://webtack.net</a> and get started in less than 1 minute. Free forever, no account needed.</p>"""

    payload = {
        "posts": [{
            "id": post_id,
            "title": "Introducing WebTack - a new open-source framework for saving and storing content from the web.",
            "html": html_content,
            "updated_at": updated_at,
            "status": "draft",
            "tags": ["WebTack", "Open Source"]
        }]
    }

    print(f"Updating Ghost post {post_id}...")
    update_resp = requests.put(
        f"{api_url}/ghost/api/admin/posts/{post_id}/?source=html",
        headers=headers,
        json=payload
    )

    if not update_resp.ok:
        print(f"Error {update_resp.status_code}: {update_resp.text}", file=sys.stderr)
        sys.exit(1)

    updated_post = update_resp.json()["posts"][0]
    print("Success! Ghost draft updated.")
    print(f"  Title: {updated_post.get('title')}")
    print(f"  ID: {updated_post.get('id')}")
    print(f"  Preview URL: {updated_post.get('url')}")
    print(f"  Ghost Editor: {api_url}/ghost/#/editor/post/{updated_post.get('id')}")

if __name__ == "__main__":
    main()
