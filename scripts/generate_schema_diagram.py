"""
Generate high-fidelity SVG diagram of the WebTack JSON Schema & 3-Tiered Framework,
matching the editorial aesthetic of the WebTack Architecture diagram:
warm ivory paper, Tenor Sans title, dark ink headers, monospace property cards,
crisp icons, and snug, balanced columns showing the 4-layer metadata envelope and sidecars.
"""

import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "docs", "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SVG_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-schema.svg")
HTML_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-schema.html")
PNG_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-schema.png")

WIDTH = 1340
HEIGHT = 895

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" height="100%" style="background-color: #FAF6F0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Tenor+Sans&amp;family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&amp;family=Space+Mono:ital,wght@0,400;0,700;1,400&amp;display=swap');
      
      .title {{
        font-family: 'Tenor Sans', -apple-system, sans-serif;
        font-style: normal;
        font-weight: 400;
        font-size: 34px;
        letter-spacing: 0.06em;
        fill: #1C1917;
      }}
      .subtitle {{
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif;
        font-style: italic;
        font-size: 15px;
        fill: #78716C;
      }}
      .stage-title {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-weight: 700;
        font-size: 13.5px;
        letter-spacing: 1.5px;
        fill: #FAF6F0;
      }}
      .stage-subtitle {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 10.5px;
        font-weight: 500;
        fill: #A8A29E;
      }}
      .prop-name {{
        font-family: Menlo, 'Space Mono', 'Courier New', monospace;
        font-size: 12.5px;
        font-weight: 700;
        fill: #1C1917;
      }}
      .prop-type {{
        font-family: Menlo, 'Space Mono', 'Courier New', monospace;
        font-size: 10px;
        font-weight: 600;
        fill: #78716C;
      }}
      .prop-desc {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 10.5px;
        font-weight: 500;
        fill: #57534E;
      }}
      .prop-val {{
        font-family: Menlo, 'Space Mono', monospace;
        font-size: 10px;
        font-weight: 600;
        fill: #059669;
      }}
      .sidecar-badge {{
        font-family: Menlo, 'Space Mono', monospace;
        font-size: 9.5px;
        font-weight: 700;
      }}
      .payoff-title {{
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif;
        font-style: italic;
        font-weight: 500;
        font-size: 18px;
        fill: #1C1917;
      }}
      .payoff-body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 12px;
        font-weight: 500;
        fill: #292524;
      }}
      .watermark {{
        font-family: Menlo, 'Space Mono', 'Courier New', Courier, monospace;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        fill: #8C827A;
      }}
    </style>
  </defs>

  <!-- Background Canvas -->
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#FAF6F0"/>

  <!-- ========================================== -->
  <!-- 1. HEADER                                  -->
  <!-- ========================================== -->
  <text x="{WIDTH // 2}" y="46" text-anchor="middle" class="title">WebTack Atom Schema</text>
  <text x="{WIDTH // 2}" y="68" text-anchor="middle" class="subtitle">Canonical v3 Specification — 4-Layer Metadata Envelope &amp; Content Sidecar Architecture</text>


  <!-- ========================================== -->
  <!-- 2. SYSTEM ENVELOPE (ROOT LEVEL)             -->
  <!-- ========================================== -->
  <g transform="translate(60, 88)">
    <!-- Container Card -->
    <rect width="1220" height="96" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    
    <!-- Dark Ink Left Header Tab -->
    <path d="M 0 8 Q 0 0 8 0 L 160 0 L 160 96 L 8 96 Q 0 96 0 88 Z" fill="#1C1917"/>
    <text x="80" y="42" text-anchor="middle" class="stage-title" font-size="11.5px">SYSTEM</text>
    <text x="80" y="58" text-anchor="middle" class="stage-title" font-size="11.5px">ENVELOPE</text>
    <text x="80" y="76" text-anchor="middle" class="stage-subtitle" fill="#A8A29E" font-size="9.5px">Root: atom.json</text>

    <!-- Core Envelope Attributes -->
    <g transform="translate(180, 14)">
      <!-- 1. id -->
      <g transform="translate(0, 0)">
        <text x="0" y="16" class="prop-name">id</text>
        <text x="24" y="16" font-family="Menlo, monospace" font-size="9px" font-weight="700" fill="#78716C">(required)</text>
        <text x="0" y="34" class="prop-desc">Unique identifier with UTC prefix</text>
        <text x="0" y="52" class="prop-val">atm_YYYYMMDDHHMMSS_xxxxxx</text>
      </g>

      <!-- 2. version & overflow -->
      <g transform="translate(230, 0)">
        <text x="0" y="16" class="prop-name">version</text>
        <text x="0" y="34" class="prop-desc">Schema v3 • metadata_json</text>
        <text x="0" y="52" class="prop-val">3 (canonical standard)</text>
      </g>

      <!-- 3. timestamps -->
      <g transform="translate(400, 0)">
        <text x="0" y="16" class="prop-name">created_at • updated_at</text>
        <text x="0" y="34" class="prop-desc">ISO 8601 UTC timestamps</text>
        <text x="0" y="52" class="prop-val">2026-11-09T18:00:00Z</text>
      </g>

      <!-- Divider line -->
      <line x1="595" y1="6" x2="595" y2="64" stroke="#E7DFD4" stroke-width="1.2"/>

      <!-- 4. kind (Discriminator) + 7 Canonical Badges -->
      <g transform="translate(615, 0)">
        <text x="0" y="16" class="prop-name">kind</text>
        <text x="0" y="34" class="prop-desc">7 first-class semantic roles dictating expected sidecar files:</text>
        
        <!-- 7 Canonical Kinds Badges -->
        <g transform="translate(0, 42)">
          <rect x="0" y="0" width="56" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="28" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">article</text>

          <rect x="62" y="0" width="68" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="96" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">bookmark</text>

          <rect x="136" y="0" width="48" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="160" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">quote</text>

          <rect x="190" y="0" width="42" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="211" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">note</text>

          <rect x="238" y="0" width="48" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="262" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">image</text>

          <rect x="292" y="0" width="48" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="316" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">video</text>

          <rect x="346" y="0" width="40" height="22" rx="4" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1"/>
          <text x="366" y="15" text-anchor="middle" font-family="Menlo, monospace" font-size="9.5px" font-weight="700">file</text>
        </g>
      </g>
    </g>
  </g>


  <!-- ========================================== -->
  <!-- 3. THE 3-TIERED FRAMEWORK COLUMNS          -->
  <!-- ========================================== -->

  <!-- ========================================== -->
  <!-- TIER 1: CURATION LAYER                     -->
  <!-- ========================================== -->
  <g transform="translate(60, 204)">
    <!-- Column Header -->
    <g>
      <rect width="380" height="50" rx="6" fill="#1C1917"/>
      <text x="190" y="31" text-anchor="middle" class="stage-title">TIER 1: CURATION</text>
    </g>

    <!-- Column Track Background -->
    <rect x="0" y="60" width="380" height="472" rx="8" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1.2" stroke-dasharray="3,3"/>

    <!-- FRAMING QUESTION BANNER -->
    <g transform="translate(18, 74)">
      <rect width="344" height="38" rx="6" fill="#FAF6F0" stroke="#C8BFAF" stroke-width="1.2" stroke-dasharray="2,2"/>
      <text x="172" y="24.5" text-anchor="middle" font-family="'Newsreader', Georgia, serif" font-style="italic" font-size="15.5px" font-weight="500" fill="#1C1917">“What do you want to say about this?”</text>
    </g>

    <!-- Card 1: atom_title -->
    <g transform="translate(18, 122)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Title / Heading -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <text x="16" y="22" text-anchor="middle" font-family="'Tenor Sans', serif" font-size="16px" font-weight="bold" fill="#1C1917">T</text>
      </g>
      <!-- Required Tag -->
      <rect x="264" y="10" width="66" height="18" rx="3" fill="#1C1917"/>
      <text x="297" y="22.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="bold" fill="#FAF6F0">REQUIRED</text>

      <text x="56" y="24" class="prop-name">atom_title</text>
      <text x="56" y="41" class="prop-desc">User-assigned headline or curated title</text>
      <text x="56" y="57" class="prop-val">"As We May Think"</text>
    </g>

    <!-- Card 2: description -->
    <g transform="translate(18, 198)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Editorial Note / Pen -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <path d="M 11 21 L 11 18 L 19 10 L 22 13 L 14 21 Z" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <line x1="17" y1="12" x2="20" y2="15" stroke="#1C1917" stroke-width="1.3"/>
      </g>
      <text x="56" y="24" class="prop-name">description</text>
      <text x="56" y="41" class="prop-desc">Editorial reading commentary &amp; notes</text>
      <text x="56" y="57" class="prop-val" fill="#78716C">"Vannevar Bush's 1945 Memex essay..."</text>
    </g>

    <!-- Card 3: tags -->
    <g transform="translate(18, 274)">
      <rect width="344" height="74" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Tag / Hash -->
      <g transform="translate(14, 21)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <text x="16" y="22" text-anchor="middle" font-family="Menlo, monospace" font-size="15px" font-weight="bold" fill="#1C1917">#</text>
      </g>
      <text x="56" y="24" class="prop-name">tags</text>
      <text x="56" y="40" class="prop-desc">Universal tags: ^[a-z0-9.\\-]+$</text>
      
      <!-- Mini Tags -->
      <g transform="translate(56, 48)">
        <rect x="0" y="0" width="76" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="38" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="600">hypertext</text>

        <rect x="82" y="0" width="56" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="110" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="600">memex</text>

        <rect x="144" y="0" width="124" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="206" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="600">computing-history</text>
      </g>
    </g>

    <!-- Card 4: collections -->
    <g transform="translate(18, 356)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Folder Stack -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <path d="M 9 13 L 13 13 L 15 15 L 23 15 L 23 22 L 9 22 Z" fill="none" stroke="#1C1917" stroke-width="1.3"/>
      </g>
      <text x="56" y="24" class="prop-name">collections</text>
      <text x="56" y="41" class="prop-desc">Thematic folders &amp; project groupings</text>
      <text x="56" y="57" class="prop-val">["Foundational Texts", "Web History"]</text>
    </g>

    <!-- Card 5: visibility -->
    <g transform="translate(18, 432)">
      <rect width="344" height="84" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Globe / Egress -->
      <g transform="translate(14, 26)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <circle cx="16" cy="16" r="7" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <line x1="9" y1="16" x2="23" y2="16" stroke="#1C1917" stroke-width="1.2"/>
        <ellipse cx="16" cy="16" rx="3.5" ry="7" fill="none" stroke="#1C1917" stroke-width="1.2"/>
      </g>
      <text x="56" y="24" class="prop-name">visibility</text>
      <text x="56" y="42" class="prop-desc">Intrinsic publishing boundary &amp; egress scope:</text>
      <g transform="translate(56, 52)">
        <rect x="0" y="0" width="60" height="20" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
        <text x="30" y="14" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="700" fill="#047857">public</text>

        <rect x="68" y="0" width="62" height="20" rx="3" fill="#FEF3C7" stroke="#D97706" stroke-width="0.8"/>
        <text x="99" y="14" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="700" fill="#B45309">shared</text>

        <rect x="138" y="0" width="64" height="20" rx="3" fill="#F3F4F6" stroke="#9CA3AF" stroke-width="0.8"/>
        <text x="170" y="14" text-anchor="middle" font-family="Menlo, monospace" font-size="9px" font-weight="700" fill="#4B5563">private</text>
      </g>
    </g>
  </g>


  <!-- ========================================== -->
  <!-- TIER 2: SOURCE LAYER                       -->
  <!-- ========================================== -->
  <g transform="translate(480, 204)">
    <!-- Column Header -->
    <g>
      <rect width="380" height="50" rx="6" fill="#1C1917"/>
      <text x="190" y="31" text-anchor="middle" class="stage-title">TIER 2: SOURCE</text>
    </g>

    <!-- Column Track Background -->
    <rect x="0" y="60" width="380" height="472" rx="8" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1.2" stroke-dasharray="3,3"/>

    <!-- FRAMING QUESTION BANNER -->
    <g transform="translate(18, 74)">
      <rect width="344" height="38" rx="6" fill="#FAF6F0" stroke="#C8BFAF" stroke-width="1.2" stroke-dasharray="2,2"/>
      <text x="172" y="24.5" text-anchor="middle" font-family="'Newsreader', Georgia, serif" font-style="italic" font-size="15.5px" font-weight="500" fill="#1C1917">“Where did this come from?”</text>
    </g>

    <!-- Card 1: source_url & source_title -->
    <g transform="translate(18, 122)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: External Link -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <line x1="12" y1="20" x2="20" y2="12" stroke="#1C1917" stroke-width="1.3"/>
        <polyline points="14,12 20,12 20,18" fill="none" stroke="#1C1917" stroke-width="1.3"/>
      </g>
      <text x="56" y="24" class="prop-name">source_url &amp; title</text>
      <text x="56" y="41" class="prop-desc">Canonical web origin &amp; published headline</text>
      <text x="56" y="57" class="prop-val">https://theatlantic.com/.../as-we-may-think</text>
    </g>

    <!-- Card 2: site_name & author -->
    <g transform="translate(18, 198)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Newspaper / Outlet -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <rect x="10" y="11" width="12" height="10" rx="1.5" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <line x1="13" y1="14" x2="19" y2="14" stroke="#1C1917" stroke-width="1.1"/>
        <line x1="13" y1="17" x2="17" y2="17" stroke="#1C1917" stroke-width="1.1"/>
      </g>
      <text x="56" y="24" class="prop-name">site_name &amp; author</text>
      <text x="56" y="41" class="prop-desc">Publisher brand &amp; creator byline</text>
      <text x="56" y="57" class="prop-val">"The Atlantic" • Vannevar Bush</text>
    </g>

    <!-- Card 3: published_at & favicon -->
    <g transform="translate(18, 274)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Calendar / Clock -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <rect x="10" y="11" width="12" height="11" rx="2" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <line x1="10" y1="14" x2="22" y2="14" stroke="#1C1917" stroke-width="1.1"/>
      </g>
      <text x="56" y="24" class="prop-name">published_at</text>
      <text x="56" y="41" class="prop-desc">Original publication date &amp; publisher favicon</text>
      <text x="56" y="57" class="prop-val">1945-07-01T00:00:00Z • /favicon.ico</text>
    </g>

    <!-- Card 4: capture_method -->
    <g transform="translate(18, 356)">
      <rect width="344" height="74" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Conduit Ingestion -->
      <g transform="translate(14, 21)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <path d="M 10 11 L 22 11 L 18 17 L 18 21 L 14 21 L 14 17 Z" fill="none" stroke="#1C1917" stroke-width="1.3"/>
      </g>
      <text x="56" y="24" class="prop-name">capture_method</text>
      <text x="56" y="40" class="prop-desc">Conduit used to ingest the atom:</text>
      
      <!-- Ingestion Pills -->
      <g transform="translate(56, 48)">
        <rect x="0" y="0" width="34" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="17" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="700">cli</text>

        <rect x="38" y="0" width="80" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="78" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="700">bookmarklet</text>

        <rect x="122" y="0" width="34" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="139" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="700">mcp</text>

        <rect x="160" y="0" width="46" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="183" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="700">arena</text>

        <rect x="210" y="0" width="68" height="18" rx="3" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="0.8"/>
        <text x="244" y="12.5" text-anchor="middle" font-family="Menlo, monospace" font-size="8.5px" font-weight="700">instapaper</text>
      </g>
    </g>

    <!-- Card 5: capture_id & capture_url -->
    <g transform="translate(18, 432)">
      <rect width="344" height="84" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
      <!-- Icon: Chain Link / Anchor -->
      <g transform="translate(14, 26)">
        <rect width="32" height="32" rx="6" fill="#F2EAE1"/>
        <circle cx="13" cy="19" r="4" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <circle cx="19" cy="13" r="4" fill="none" stroke="#1C1917" stroke-width="1.3"/>
        <line x1="15" y1="17" x2="17" y2="15" stroke="#1C1917" stroke-width="1.3"/>
      </g>
      <text x="56" y="24" class="prop-name">capture_id &amp; url</text>
      <text x="56" y="42" class="prop-desc">Upstream platform identifier &amp; link</text>
      <text x="56" y="58" class="prop-desc" fill="#78716C">(Are.na block ID, Instapaper bookmark ID)</text>
      <text x="56" y="74" class="prop-val">"30291048" • https://are.na/block/30291048</text>
    </g>
  </g>


  <!-- ========================================== -->
  <!-- TIER 3: CONTENT LAYER (SIDECAR CONTRACT)   -->
  <!-- ========================================== -->
  <g transform="translate(900, 204)">
    <!-- Column Header -->
    <g>
      <rect width="380" height="50" rx="6" fill="#1C1917"/>
      <text x="190" y="31" text-anchor="middle" class="stage-title">TIER 3: CONTENT</text>
    </g>

    <!-- Column Track Background -->
    <rect x="0" y="60" width="380" height="472" rx="8" fill="#F4EFE6" stroke="#DCD3C5" stroke-width="1.2" stroke-dasharray="3,3"/>

    <!-- FRAMING QUESTION BANNER -->
    <g transform="translate(18, 74)">
      <rect width="344" height="38" rx="6" fill="#FAF6F0" stroke="#C8BFAF" stroke-width="1.2" stroke-dasharray="2,2"/>
      <text x="172" y="24.5" text-anchor="middle" font-family="'Newsreader', Georgia, serif" font-style="italic" font-size="15.5px" font-weight="500" fill="#1C1917">“What is this?”</text>
    </g>

    <!-- Card 1: cover_image -> cover.jpg -->
    <g transform="translate(18, 122)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#059669" stroke-width="1.5"/>
      <!-- Icon: Photo Frame -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#ECFDF5"/>
        <rect x="9" y="10" width="14" height="12" rx="1.5" fill="none" stroke="#059669" stroke-width="1.3"/>
        <circle cx="13" cy="13" r="1.5" fill="#059669"/>
        <polyline points="10,20 14,16 17,19 19,17 22,20" fill="none" stroke="#059669" stroke-width="1.2"/>
      </g>
      <!-- Sidecar File Pill -->
      <rect x="238" y="10" width="94" height="18" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
      <text x="285" y="22.5" text-anchor="middle" class="sidecar-badge" fill="#047857">→ cover.jpg</text>
      
      <text x="56" y="24" class="prop-name">cover_image</text>
      <text x="56" y="41" class="prop-desc">Visual anchor: OG card, poster, photo, or PDF</text>
      <text x="56" y="57" class="prop-val">dimensions • blurhash • color_palette • alt</text>
    </g>

    <!-- Card 2: article -> article.md -->
    <g transform="translate(18, 198)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#059669" stroke-width="1.5"/>
      <!-- Icon: Document / Markdown -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#ECFDF5"/>
        <path d="M 10 9 L 18 9 L 22 13 L 22 23 L 10 23 Z" fill="none" stroke="#059669" stroke-width="1.3"/>
        <line x1="13" y1="16" x2="19" y2="16" stroke="#059669" stroke-width="1.1"/>
        <line x1="13" y1="19" x2="17" y2="19" stroke="#059669" stroke-width="1.1"/>
      </g>
      <!-- Sidecar File Pill -->
      <rect x="238" y="10" width="94" height="18" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
      <text x="285" y="22.5" text-anchor="middle" class="sidecar-badge" fill="#047857">→ article.md</text>
      
      <text x="56" y="24" class="prop-name">article</text>
      <text x="56" y="41" class="prop-desc">Offline readable reader view (article.md)</text>
      <text x="56" y="57" class="prop-val">file • relative_path • word_count • byline</text>
    </g>

    <!-- Card 3: text -> quote.md / note.md -->
    <g transform="translate(18, 274)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#059669" stroke-width="1.5"/>
      <!-- Icon: Quotes -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#ECFDF5"/>
        <text x="16" y="23" text-anchor="middle" font-family="'Newsreader', serif" font-size="18px" font-weight="bold" fill="#059669">“</text>
      </g>
      <!-- Sidecar File Pill -->
      <rect x="200" y="10" width="132" height="18" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
      <text x="266" y="22.5" text-anchor="middle" class="sidecar-badge" fill="#047857">→ quote / note.md</text>
      
      <text x="56" y="24" class="prop-name">text</text>
      <text x="56" y="41" class="prop-desc">Verbatim quote excerpt or personal reflection</text>
      <text x="56" y="57" class="prop-val">file • relative_path • excerpt • word_count</text>
    </g>

    <!-- Card 4: video -> transcript.txt / .json -->
    <g transform="translate(18, 356)">
      <rect width="344" height="68" rx="8" fill="#FFFFFF" stroke="#059669" stroke-width="1.5"/>
      <!-- Icon: Video Play -->
      <g transform="translate(14, 18)">
        <rect width="32" height="32" rx="6" fill="#ECFDF5"/>
        <rect x="8" y="10" width="16" height="12" rx="2" fill="none" stroke="#059669" stroke-width="1.3"/>
        <polygon points="14,13 18,16 14,19" fill="#059669"/>
      </g>
      <!-- Sidecar File Pill -->
      <rect x="210" y="10" width="122" height="18" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
      <text x="271" y="22.5" text-anchor="middle" class="sidecar-badge" fill="#047857">→ transcript.txt</text>
      
      <text x="56" y="24" class="prop-name">video</text>
      <text x="56" y="41" class="prop-desc">Stream metadata &amp; full dialogue transcript</text>
      <text x="56" y="57" class="prop-val">provider • duration • transcript_json (offsets)</text>
    </g>

    <!-- Card 5: file -> document.pdf / binary -->
    <g transform="translate(18, 432)">
      <rect width="344" height="84" rx="8" fill="#FFFFFF" stroke="#059669" stroke-width="1.5"/>
      <!-- Icon: Paperclip / Attachment -->
      <g transform="translate(14, 26)">
        <rect width="32" height="32" rx="6" fill="#ECFDF5"/>
        <path d="M 17 11 L 12 16 A 3.5 3.5 0 0 0 17 21 L 21 17 A 2.2 2.2 0 0 0 18 14 L 13 19" fill="none" stroke="#059669" stroke-width="1.3"/>
      </g>
      <!-- Sidecar File Pill -->
      <rect x="210" y="10" width="122" height="18" rx="3" fill="#ECFDF5" stroke="#059669" stroke-width="0.8"/>
      <text x="271" y="22.5" text-anchor="middle" class="sidecar-badge" fill="#047857">→ document.pdf</text>
      
      <text x="56" y="24" class="prop-name">file</text>
      <text x="56" y="42" class="prop-desc">Original binary attachment or document</text>
      <text x="56" y="58" class="prop-desc" fill="#78716C">(PDF, EPUB, archive, dataset, or audio)</text>
      <text x="56" y="74" class="prop-val">filename • file_size_bytes • page_count</text>
    </g>
  </g>


  <!-- ========================================== -->
  <!-- 4. BOTTOM PAYOFF BANNER                    -->
  <!-- ========================================== -->
  <g transform="translate(180, 762)">
    <!-- Container -->
    <rect width="980" height="88" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    
    <!-- Oxblood / Deep Wine Left Accent Bar -->
    <path d="M 0 8 Q 0 0 8 0 L 10 0 L 10 88 L 8 88 Q 0 88 0 80 Z" fill="#6B1724"/>

    <!-- Content -->
    <text x="495" y="32" text-anchor="middle" class="payoff-title">
      Principles: Metadata Envelope + Files on Disk
    </text>
    
    <text x="495" y="54" text-anchor="middle" class="payoff-body">
      Relative paths from atom.json • Extensible metadata_json • 30-year durable standard
    </text>

    <text x="495" y="72" text-anchor="middle" class="payoff-body" fill="#57534E">
      Every atom is an atomic folder containing atom.json alongside its raw media and markdown sidecars.
    </text>
  </g>

  <!-- Watermark -->
  <text x="{WIDTH // 2}" y="874" text-anchor="middle" class="watermark">webtack.net</text>

</svg>'''

with open(SVG_OUTPUT, "w") as f:
    f.write(svg)

print(f"✓ Generated {SVG_OUTPUT} ({len(svg)} bytes)")

# Companion HTML preview
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebTack Atom Schema Diagram</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Tenor+Sans&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      background: #EFE9DF;
      padding: 40px 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
    }}
    .container {{
      max-width: 1360px;
      width: 100%;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding: 12px 20px;
      background: #FFFFFF;
      border: 1px solid #DCD3C5;
      border-radius: 8px;
    }}
    .toolbar h1 {{
      font-family: 'Tenor Sans', sans-serif;
      font-size: 18px;
      font-weight: normal;
      letter-spacing: 0.05em;
      color: #1C1917;
    }}
    .btn {{
      display: inline-block;
      padding: 8px 16px;
      background: #1C1917;
      color: #FAF6F0;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      border-radius: 6px;
      letter-spacing: 0.02em;
    }}
    .diagram-wrap {{
      background: #FAF6F0;
      border: 1px solid #DCD3C5;
      border-radius: 12px;
      padding: 30px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
    }}
    svg {{
      max-width: 100%;
      height: auto;
      display: block;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="toolbar">
      <h1>WebTack JSON Schema Specification (v3)</h1>
      <div>
        <a href="webtack-schema.svg" download="webtack-schema.svg" class="btn">Download SVG</a>
      </div>
    </div>
    <div class="diagram-wrap">
      {svg}
    </div>
  </div>
</body>
</html>
'''

with open(HTML_OUTPUT, "w") as f:
    f.write(html)

print(f"✓ Generated {HTML_OUTPUT} ({len(html)} bytes)")

# Auto-generate high-res PNG (prefers headless Google Chrome for razor-sharp Retina rendering)
chrome_app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
rendered = False

if os.path.exists(chrome_app):
    try:
        subprocess.run(
            [
                chrome_app,
                "--headless",
                "--disable-gpu",
                "--force-device-scale-factor=2",
                f"--window-size={WIDTH},{HEIGHT}",
                f"--screenshot={PNG_OUTPUT}",
                f"file://{SVG_OUTPUT}"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        print(f"✓ Generated {PNG_OUTPUT} (2680px razor-sharp Retina PNG via Chrome)")
        rendered = True
    except Exception as e:
        print(f"Notice: Chrome rasterization failed ({e}), falling back to qlmanage...")

if not rendered:
    try:
        res = subprocess.run(
            ["qlmanage", "-t", "-s", "2600", "-o", OUTPUT_DIR, SVG_OUTPUT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        temp_png = f"{SVG_OUTPUT}.png"
        if os.path.exists(temp_png):
            shutil.move(temp_png, PNG_OUTPUT)
            print(f"✓ Generated {PNG_OUTPUT} (2600px PNG via qlmanage)")
    except Exception as e:
        print(f"Notice: PNG generation via qlmanage skipped ({e})")
