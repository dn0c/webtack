"""
Generate high-fidelity standalone SVG diagram matching the editorial aesthetic
of the reference architecture diagram (warm ivory paper, serif typography,
monospace floating pill cards, dark header system card, bezier branch tree,
and wine-accented footer payoff card).
"""

import os

SVG_OUTPUT = "docs/assets/webtack-architecture.svg"
HTML_OUTPUT = "docs/assets/webtack-architecture.html"

# Canvas dimensions
WIDTH = 1000
HEIGHT = 1140

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" height="100%" style="background-color: #FAF6F0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,500;1,6..72,600&amp;family=Space+Mono:ital,wght@0,400;0,700;1,400&amp;display=swap');
      
      .serif-title {{
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif;
        font-style: italic;
        font-weight: 400;
        fill: #1C1917;
      }}
      .mono-pill {{
        font-family: Menlo, 'Courier New', 'Space Mono', Courier, monospace;
        font-size: 12.5px;
        font-weight: 700;
        fill: #1C1917;
      }}
      .system-header {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-weight: 700;
        font-size: 13.5px;
        letter-spacing: 2.2px;
        fill: #FAF6F0;
      }}
      .system-rule {{
        font-family: Menlo, 'Courier New', 'Space Mono', Courier, monospace;
        font-size: 13.5px;
        font-weight: 700;
        fill: #1C1917;
      }}
      .system-sub {{
        font-family: Menlo, 'Courier New', 'Space Mono', Courier, monospace;
        font-size: 12px;
        font-weight: 600;
        fill: #1C1917;
      }}
      .system-enrich {{
        font-family: Menlo, 'Courier New', 'Space Mono', Courier, monospace;
        font-size: 11px;
        font-weight: 600;
        fill: #57534E;
      }}
      .app-title {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 13px;
        font-weight: 700;
        fill: #1C1917;
      }}
      .app-sub {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 11px;
        font-weight: 500;
        fill: #78716C;
      }}
      .payoff-title {{
        font-family: 'Newsreader', Georgia, 'Times New Roman', serif;
        font-style: italic;
        font-weight: 500;
        font-size: 19px;
        fill: #1C1917;
      }}
      .payoff-body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 12.5px;
        font-weight: 500;
        fill: #1C1917;
      }}
    </style>

    <!-- Filters & Shadows -->
    <filter id="pill-shadow" x="-8%" y="-15%" width="120%" height="140%">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1" flood-color="#000000" flood-opacity="0.06"/>
    </filter>
    <filter id="box-shadow" x="-5%" y="-10%" width="110%" height="125%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.05"/>
    </filter>
    <filter id="icon-shadow" x="-10%" y="-10%" width="120%" height="125%">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.08"/>
    </filter>

    <!-- Marker Arrow -->
    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#1C1917"/>
    </marker>
  </defs>

  <!-- Background -->
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#FAF6F0"/>

  <!-- ========================================== -->
  <!-- 1. TOP HEADER TITLE                        -->
  <!-- ========================================== -->
  <text x="500" y="52" text-anchor="middle" class="serif-title" font-size="34">WebTack System Architecture</text>

  <!-- ========================================== -->
  <!-- 2. INGRESS FUNNEL                          -->
  <!-- ========================================== -->
  <!-- Funnel polygon background & outline -->
  <polygon points="50,80 950,80 500,345" fill="#F2EAE1" stroke="#C8BFAF" stroke-width="1.2" stroke-dasharray="4,4"/>
  
  <!-- Corner anchor dots -->
  <circle cx="50" cy="80" r="3.5" fill="#1C1917"/>
  <circle cx="950" cy="80" r="3.5" fill="#1C1917"/>

  <!-- Dashed trajectory rays converging to funnel spout -->
  <g stroke="#C8BFAF" stroke-width="1" stroke-dasharray="3,3">
    <line x1="220" y1="125" x2="495" y2="340"/>
    <line x1="400" y1="120" x2="498" y2="340"/>
    <line x1="600" y1="120" x2="502" y2="340"/>
    <line x1="780" y1="125" x2="505" y2="340"/>
    <line x1="280" y1="180" x2="496" y2="340"/>
    <line x1="495" y1="180" x2="500" y2="340"/>
    <line x1="720" y1="180" x2="504" y2="340"/>
    <line x1="420" y1="240" x2="498" y2="340"/>
    <line x1="580" y1="240" x2="502" y2="340"/>
  </g>

  <!-- FLOATING PILL CARDS (WebTack Ingress Types) -->
  
  <!-- Row 1: Article, Quote, Longform, Video -->
  <!-- Pill 1: Article / Longform -->
  <g transform="translate(130, 95) rotate(-2)" filter="url(#pill-shadow)">
    <rect width="170" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Document outline icon -->
    <path d="M 18 10 L 28 10 L 33 15 L 33 24 L 18 24 Z" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <line x1="21" y1="16" x2="27" y2="16" stroke="#1C1917" stroke-width="1.3"/>
    <line x1="21" y1="20" x2="30" y2="20" stroke="#1C1917" stroke-width="1.3"/>
    <text x="42" y="22" class="mono-pill">Article / Essay</text>
  </g>

  <!-- Pill 2: Video / Talk -->
  <g transform="translate(325, 92) rotate(1)" filter="url(#pill-shadow)">
    <rect width="160" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Play triangle icon -->
    <polygon points="21,12 30,17 21,22" fill="#1C1917"/>
    <text x="40" y="22" class="mono-pill">Video / Talk</text>
  </g>

  <!-- Pill 3: Bookmarklet -->
  <g transform="translate(510, 90) rotate(-1)" filter="url(#pill-shadow)">
    <rect width="175" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Bookmark ribbon icon -->
    <path d="M 21 11 L 30 11 L 30 23 L 25.5 19.5 L 21 23 Z" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <text x="39" y="22" class="mono-pill">Web Bookmarklet</text>
  </g>

  <!-- Pill 4: PDF / Doc -->
  <g transform="translate(710, 96) rotate(3)" filter="url(#pill-shadow)">
    <rect width="155" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Book/Doc icon -->
    <rect x="20" y="11" width="11" height="13" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <line x1="24" y1="11" x2="24" y2="24" stroke="#1C1917" stroke-width="1.1"/>
    <text x="39" y="22" class="mono-pill">PDF / Document</text>
  </g>

  <!-- Row 2: Fleeting Note, Memorable Quote, CLI Ingress -->
  <!-- Pill 5: Fleeting Note -->
  <g transform="translate(200, 155) rotate(2)" filter="url(#pill-shadow)">
    <rect width="160" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Check / Note icon -->
    <rect x="20" y="12" width="11" height="11" rx="2" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <polyline points="23,17 25,19 29,14" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <text x="39" y="22" class="mono-pill">Fleeting Note</text>
  </g>

  <!-- Pill 6: CLI Capture -->
  <g transform="translate(425, 155) rotate(-0.5)" filter="url(#pill-shadow)">
    <rect width="155" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Terminal prompt icon -->
    <polyline points="20,13 24,17 20,21" fill="none" stroke="#1C1917" stroke-width="1.4"/>
    <line x1="26" y1="21" x2="31" y2="21" stroke="#1C1917" stroke-width="1.4"/>
    <text x="39" y="22" class="mono-pill">webtack CLI</text>
  </g>

  <!-- Pill 7: Memorable Quote -->
  <g transform="translate(650, 155) rotate(-2)" filter="url(#pill-shadow)">
    <rect width="170" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Quote marks icon -->
    <text x="21" y="24" font-family="Georgia, serif" font-size="19" font-weight="bold" fill="#1C1917">“</text>
    <text x="40" y="22" class="mono-pill">Memorable Quote</text>
  </g>

  <!-- Row 3: Visual Reference, Are.na / Instapaper Sync -->
  <!-- Pill 8: Visual Reference / Image -->
  <g transform="translate(320, 218) rotate(-1)" filter="url(#pill-shadow)">
    <rect width="170" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Starburst / Image icon -->
    <polygon points="26,11 28,15 32,16 29,19 30,23 26,21 22,23 23,19 20,16 24,15" fill="#1C1917"/>
    <text x="41" y="22" class="mono-pill">Visual Reference</text>
  </g>

  <!-- Pill 9: Batch Importers -->
  <g transform="translate(515, 220) rotate(1.5)" filter="url(#pill-shadow)">
    <rect width="175" height="34" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.4"/>
    <!-- Sync arrows icon -->
    <circle cx="26" cy="17" r="5" fill="none" stroke="#1C1917" stroke-width="1.3"/>
    <polyline points="29,12 32,15 29,18" fill="none" stroke="#1C1917" stroke-width="1.2"/>
    <text x="40" y="22" class="mono-pill">Are.na &amp; Web Sync</text>
  </g>

  <!-- Converging Feed Lines into System Block -->
  <line x1="480" y1="330" x2="480" y2="375" stroke="#1C1917" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="500" y1="345" x2="500" y2="375" stroke="#1C1917" stroke-width="1.8" marker-end="url(#arrow)"/>
  <line x1="520" y1="330" x2="520" y2="375" stroke="#1C1917" stroke-width="1.5" marker-end="url(#arrow)"/>


  <!-- ========================================== -->
  <!-- 3. CENTRAL ENGINE / VAULT BLOCK            -->
  <!-- ========================================== -->
  <g transform="translate(190, 375)" filter="url(#box-shadow)">
    <!-- Container outer border -->
    <rect width="620" height="152" rx="4" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.8"/>

    <!-- Dark header block -->
    <rect width="620" height="42" rx="3" fill="#1C1917"/>
    <!-- Prevent rounding at bottom of header -->
    <rect y="36" width="620" height="6" fill="#1C1917"/>
    <text x="310" y="26" text-anchor="middle" class="system-header">WEBTACK CANONICAL VAULT &amp; LOCAL ENGINE</text>

    <!-- Rule 1: Filesystem Truth -->
    <text x="310" y="74" text-anchor="middle" class="system-rule">
      Rule: The filesystem is canonical truth. The database is disposable.
    </text>

    <!-- Rule 2: Durability -->
    <text x="310" y="98" text-anchor="middle" class="system-sub">
      Per-atom sidecars (atom.json + raw markdown &amp; media) guarantee 30-year permanence.
    </text>

    <!-- Rule 3: Enrichment line -->
    <line x1="60" y1="114" x2="560" y2="114" stroke="#D6D3D1" stroke-width="1"/>
    <text x="310" y="133" text-anchor="middle" class="system-enrich">
      Automatic Sync Enrichment: Readability markdown • OG metadata • Dominant colors • Blurhash
    </text>
  </g>


  <!-- ========================================== -->
  <!-- 4. DISTRIBUTION TREE (BRANCHES)            -->
  <!-- ========================================== -->
  <!-- Central trunk line down from central block -->
  <line x1="500" y1="527" x2="500" y2="570" stroke="#1C1917" stroke-width="1.6"/>
  <circle cx="500" cy="570" r="3.5" fill="#1C1917"/>

  <!-- Horizontal Distribution Spine (Curved Bezier Trunk) -->
  <!-- Left wing: to col 1 (140) and col 2 (380) -->
  <!-- Right wing: to col 3 (620) and col 4 (860) -->
  <path d="M 500 570 C 500 585, 380 585, 380 600" fill="none" stroke="#1C1917" stroke-width="1.4"/>
  <path d="M 500 570 C 500 585, 140 585, 140 600" fill="none" stroke="#1C1917" stroke-width="1.4"/>
  <path d="M 500 570 C 500 585, 620 585, 620 600" fill="none" stroke="#1C1917" stroke-width="1.4"/>
  <path d="M 500 570 C 500 585, 860 585, 860 600" fill="none" stroke="#1C1917" stroke-width="1.4"/>

  <!-- Junction dots at column drop points -->
  <circle cx="140" cy="600" r="3" fill="#1C1917"/>
  <circle cx="380" cy="600" r="3" fill="#1C1917"/>
  <circle cx="620" cy="600" r="3" fill="#1C1917"/>
  <circle cx="860" cy="600" r="3" fill="#1C1917"/>

  <!-- Vertical lines dropping to Row 1 -->
  <line x1="140" y1="600" x2="140" y2="628" stroke="#1C1917" stroke-width="1.4"/>
  <line x1="380" y1="600" x2="380" y2="628" stroke="#1C1917" stroke-width="1.4"/>
  <line x1="620" y1="600" x2="620" y2="628" stroke="#1C1917" stroke-width="1.4"/>
  <line x1="860" y1="600" x2="860" y2="628" stroke="#1C1917" stroke-width="1.4"/>

  <!-- Feed-through lines dropping to Row 2 -->
  <line x1="140" y1="748" x2="140" y2="780" stroke="#1C1917" stroke-width="1.2"/>
  <line x1="380" y1="748" x2="380" y2="780" stroke="#1C1917" stroke-width="1.2"/>
  <line x1="620" y1="748" x2="620" y2="780" stroke="#1C1917" stroke-width="1.2"/>
  <line x1="860" y1="748" x2="860" y2="780" stroke="#1C1917" stroke-width="1.2"/>


  <!-- ========================================== -->
  <!-- 5. DESTINATION TIERS                       -->
  <!-- ========================================== -->

  <!-- ROW 1 (Y_icon = 630) -->

  <!-- App 1: WebTack Viewer Studio (Col 1: cx = 140) -->
  <g transform="translate(102, 630)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Studio / Gallery eye & window glyph -->
    <rect x="18" y="20" width="40" height="36" rx="6" fill="#F4FBF7" stroke="#059669" stroke-width="2"/>
    <line x1="18" y1="30" x2="58" y2="30" stroke="#059669" stroke-width="1.5"/>
    <circle cx="25" cy="25" r="2" fill="#059669"/>
    <circle cx="31" cy="25" r="2" fill="#059669"/>
    <!-- Eye glyph in center -->
    <path d="M 27 43 C 32 37, 44 37, 49 43 C 44 49, 32 49, 27 43 Z" fill="none" stroke="#059669" stroke-width="1.8"/>
    <circle cx="38" cy="43" r="2.8" fill="#059669"/>
  </g>
  <text x="140" y="728" text-anchor="middle" class="app-title">WebTack Studio</text>
  <text x="140" y="744" text-anchor="middle" class="app-sub">Visual Gallery &amp; Reader</text>


  <!-- App 2: Obsidian Vault (Col 2: cx = 380) -->
  <g transform="translate(342, 630)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Obsidian Faceted Crystal Logo in purple -->
    <path d="M 38 16 L 54 27 L 49 53 L 38 60 L 27 53 L 22 27 Z" fill="#F3E8FF" stroke="#7C3AED" stroke-width="2" stroke-linejoin="round"/>
    <polyline points="38,16 38,60" fill="none" stroke="#7C3AED" stroke-width="1.4"/>
    <polyline points="38,16 49,53 22,27" fill="none" stroke="#7C3AED" stroke-width="1.2"/>
    <polyline points="38,16 27,53 54,27" fill="none" stroke="#7C3AED" stroke-width="1.2"/>
  </g>
  <text x="380" y="728" text-anchor="middle" class="app-title">Obsidian Vault</text>
  <text x="380" y="744" text-anchor="middle" class="app-sub">Markdown Vault (.zip)</text>


  <!-- App 3: NotebookLM (Col 3: cx = 620) -->
  <g transform="translate(582, 630)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- NotebookLM Notebook / AI Sparkle Icon -->
    <rect x="20" y="19" width="36" height="40" rx="5" fill="#EFF6FF" stroke="#2563EB" stroke-width="2"/>
    <!-- Notebook spiral rings on left -->
    <line x1="17" y1="26" x2="23" y2="26" stroke="#2563EB" stroke-width="2" stroke-linecap="round"/>
    <line x1="17" y1="34" x2="23" y2="34" stroke="#2563EB" stroke-width="2" stroke-linecap="round"/>
    <line x1="17" y1="42" x2="23" y2="42" stroke="#2563EB" stroke-width="2" stroke-linecap="round"/>
    <line x1="17" y1="50" x2="23" y2="50" stroke="#2563EB" stroke-width="2" stroke-linecap="round"/>
    <!-- Sparkle inside notebook -->
    <path d="M 38 27 Q 38 37 46 37 Q 38 37 38 47 Q 38 37 30 37 Q 38 37 38 27 Z" fill="#2563EB"/>
  </g>
  <text x="620" y="728" text-anchor="middle" class="app-title">NotebookLM</text>
  <text x="620" y="744" text-anchor="middle" class="app-sub">Source Digest (.md)</text>


  <!-- App 4: AI Agents & Claude MCP (Col 4: cx = 860) -->
  <g transform="translate(822, 630)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Anthropic Claude asterisk / AI Agent emblem -->
    <g transform="translate(38, 38)">
      <line x1="0" y1="-18" x2="0" y2="18" stroke="#D97706" stroke-width="4.5" stroke-linecap="round"/>
      <line x1="-15.5" y1="-9" x2="15.5" y2="9" stroke="#D97706" stroke-width="4.5" stroke-linecap="round"/>
      <line x1="-15.5" y1="9" x2="15.5" y2="-9" stroke="#D97706" stroke-width="4.5" stroke-linecap="round"/>
    </g>
  </g>
  <text x="860" y="728" text-anchor="middle" class="app-title">Claude &amp; Cursor</text>
  <text x="860" y="744" text-anchor="middle" class="app-sub">Model Context Protocol (MCP)</text>


  <!-- ROW 2 (Y_icon = 780) -->

  <!-- App 5: RSS 2.0 Feed (Col 1: cx = 140) -->
  <g transform="translate(102, 780)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Classic RSS Broadcast Signal in Orange -->
    <circle cx="27" cy="49" r="4" fill="#F97316"/>
    <path d="M 23 37 A 16 16 0 0 1 39 53" fill="none" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
    <path d="M 23 27 A 26 26 0 0 1 49 53" fill="none" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
  </g>
  <text x="140" y="878" text-anchor="middle" class="app-title">RSS 2.0 Feed</text>
  <text x="140" y="894" text-anchor="middle" class="app-sub">Syndicated Web Garden</text>


  <!-- App 6: llms.txt (Col 2: cx = 380) -->
  <g transform="translate(342, 780)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Clean document with 'llm' typography badge -->
    <rect x="22" y="19" width="32" height="38" rx="4" fill="#F8FAFC" stroke="#475569" stroke-width="2"/>
    <line x1="28" y1="27" x2="48" y2="27" stroke="#475569" stroke-width="2"/>
    <line x1="28" y1="34" x2="48" y2="34" stroke="#475569" stroke-width="2"/>
    <!-- txt badge -->
    <rect x="26" y="40" width="24" height="12" rx="3" fill="#0F172A"/>
    <text x="38" y="49" text-anchor="middle" font-family="'Space Mono', monospace" font-size="8" font-weight="bold" fill="#F8FAFC">TXT</text>
  </g>
  <text x="380" y="878" text-anchor="middle" class="app-title">llms.txt Index</text>
  <text x="380" y="894" text-anchor="middle" class="app-sub">AI-Native Digest</text>


  <!-- App 7: Raindrop & Are.na (Col 3: cx = 620) -->
  <g transform="translate(582, 780)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Are.na style asterisks in crisp black -->
    <g transform="translate(32, 38)">
      <line x1="0" y1="-10" x2="0" y2="10" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="-8.6" y1="-5" x2="8.6" y2="5" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="-8.6" y1="5" x2="8.6" y2="-5" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
    </g>
    <g transform="translate(48, 38)">
      <line x1="0" y1="-10" x2="0" y2="10" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="-8.6" y1="-5" x2="8.6" y2="5" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="-8.6" y1="5" x2="8.6" y2="-5" stroke="#18181B" stroke-width="2.5" stroke-linecap="round"/>
    </g>
  </g>
  <text x="620" y="878" text-anchor="middle" class="app-title">Are.na &amp; Raindrop</text>
  <text x="620" y="894" text-anchor="middle" class="app-sub">Open CSV Interchange</text>


  <!-- App 8: Lossless JSON & JSONL (Col 4: cx = 860) -->
  <g transform="translate(822, 780)" filter="url(#icon-shadow)">
    <rect width="76" height="76" rx="20" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    <!-- Code Brackets in Navy -->
    <text x="38" y="47" text-anchor="middle" font-family="Menlo, 'Space Mono', monospace" font-size="24" font-weight="bold" fill="#1D4ED8">{{ }}</text>
  </g>
  <text x="860" y="878" text-anchor="middle" class="app-title">JSON &amp; JSONL</text>
  <text x="860" y="894" text-anchor="middle" class="app-sub">100% Loss-Free Backup</text>


  <!-- ========================================== -->
  <!-- 6. FOOTER BANNER ("THE PAYOFF")            -->
  <!-- ========================================== -->
  <g transform="translate(150, 940)" filter="url(#box-shadow)">
    <!-- Container -->
    <rect width="700" height="96" rx="8" fill="#FFFFFF" stroke="#1C1917" stroke-width="1.6"/>
    
    <!-- Oxblood / Deep Wine Left Accent Bar (matching reference) -->
    <path d="M 0 8 Q 0 0 8 0 L 10 0 L 10 96 L 8 96 Q 0 96 0 88 Z" fill="#6B1724"/>

    <!-- Content -->
    <text x="355" y="36" text-anchor="middle" class="payoff-title">
      The Payoff: 30-Year Longevity &amp; Total Digital Sovereignty
    </text>
    
    <text x="355" y="62" text-anchor="middle" class="payoff-body">
      Zero vendor lock-in • Offline-first speed • Instant full-text search across 10,000+ items
    </text>

    <text x="355" y="80" text-anchor="middle" class="payoff-body" fill="#44403C" font-weight="600">
      Your web vault lives in human-readable files on your drive — readable today, readable in 2056.
    </text>
  </g>

</svg>'''

with open(SVG_OUTPUT, "w") as f:
    f.write(svg)

print(f"Generated {SVG_OUTPUT} ({len(svg)} bytes)")

# Generate companion responsive HTML preview
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebTack Architecture Diagram</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,500;1,6..72,600&family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
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
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    .container {{
      max-width: 1040px;
      width: 100%;
      background: #FAF6F0;
      box-shadow: 0 10px 30px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.05);
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #E2D9CC;
    }}
    .toolbar {{
      padding: 16px 24px;
      background: #F2ECE1;
      border-bottom: 1px solid #E2D9CC;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .toolbar h1 {{
      font-family: 'Newsreader', Georgia, serif;
      font-style: italic;
      font-size: 20px;
      font-weight: 500;
      color: #1C1917;
    }}
    .btn {{
      padding: 8px 16px;
      background: #1C1917;
      color: #FAF6F0;
      text-decoration: none;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      transition: background 0.15s ease;
      cursor: pointer;
      border: none;
    }}
    .btn:hover {{
      background: #44403C;
    }}
    .diagram-wrap {{
      padding: 20px;
      display: flex;
      justify-content: center;
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
      <h1>WebTack Announcement Graphic</h1>
      <div>
        <a href="webtack-architecture.svg" download="webtack-architecture.svg" class="btn">Download Standalone SVG</a>
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

print(f"Generated {HTML_OUTPUT} ({len(html)} bytes)")
