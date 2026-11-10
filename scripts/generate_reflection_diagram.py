"""
Generate high-fidelity SVG, PNG, and HTML diagram updating the "A Series of Tubes"
Information Routing Architecture to include Webtack at the bottom as Step 4: Reflection.

Matches the editorial aesthetic: warm ivory paper background (#FBF7F0), Newsreader serif italics,
JetBrains Mono / monospace labels, crisp dark-ink borders (#2A1F1A), and exact brand badges.
No XML double-hyphens, fully compliant SVG XML.
"""

import os
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "docs", "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SVG_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-reflection.svg")
HTML_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-reflection.html")
PNG_OUTPUT = os.path.join(OUTPUT_DIR, "webtack-reflection.png")

# Canvas dimensions
WIDTH = 1000
HEIGHT = 1220

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" height="100%" style="background-color: #FBF7F0;">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,500;1,6..72,600&amp;family=JetBrains+Mono:wght@400;500;600;700&amp;family=Mulish:wght@400;500;600;700&amp;display=swap');

      /* Ghost / Editorial Palette */
      .canvas-bg {{ fill: #FBF7F0; }}
      .ink-line {{ stroke: #2A1F1A; fill: none; stroke-linecap: round; stroke-linejoin: round; }}
      .ink-dash {{ stroke: rgba(42, 31, 26, 0.38); stroke-dasharray: 4 4; fill: none; }}
      .box-fill {{ fill: #FBF7F0; stroke: #2A1F1A; stroke-width: 1.8; }}
      .shade-fill {{ fill: #F4EDE2; stroke: #2A1F1A; stroke-width: 1.8; }}
      .card-fill {{ fill: #FFFFFF; stroke: #2A1F1A; stroke-width: 1.5; }}
      .logo-badge {{ fill: #FFFFFF; stroke: #2A1F1A; stroke-width: 1.6; rx: 14px; }}
      
      /* Typography */
      .text-title {{ font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-size: 26px; font-weight: 500; fill: #2A1F1A; font-style: italic; letter-spacing: -0.01em; }}
      .text-machine {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; fill: #FBF7F0; letter-spacing: 1.2px; }}
      .text-card {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; fill: #2A1F1A; }}
      .text-logo-name {{ font-family: 'JetBrains Mono', monospace; font-size: 12.5px; font-weight: 700; fill: #2A1F1A; }}
      .text-logo-sub {{ font-family: 'Mulish', -apple-system, sans-serif; font-size: 10.5px; font-weight: 600; fill: rgba(42, 31, 26, 0.72); }}
      .text-dim {{ font-family: 'Mulish', -apple-system, sans-serif; font-size: 11px; font-weight: 600; fill: rgba(42, 31, 26, 0.65); }}
      
      .webtack-header {{ font-family: 'JetBrains Mono', monospace; font-size: 12.5px; font-weight: 700; fill: #FBF7F0; letter-spacing: 1.2px; }}
      .pillar-title {{ font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 700; fill: #2A1F1A; }}
      .pillar-sub {{ font-family: 'Mulish', -apple-system, sans-serif; font-size: 10px; font-weight: 500; fill: #57534E; line-height: 1.35; }}
      .payoff-title {{ font-family: 'Newsreader', Georgia, 'Times New Roman', serif; font-size: 16px; font-weight: 500; fill: #2A1F1A; font-style: italic; letter-spacing: -0.01em; }}
      .watermark {{
        font-family: Menlo, 'JetBrains Mono', 'Space Mono', Courier, monospace;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        fill: #8C827A;
      }}
    </style>

    <marker id="inkArrow" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
      <path d="M 0 0 L 6 3 L 0 6" fill="none" stroke="#2A1F1A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
    </marker>

    <!-- Gemini / MCP Gradient -->
    <linearGradient id="mcpGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2563EB"/>
      <stop offset="50%" stop-color="#4F46E5"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>

    <!-- Soft Card Shadow -->
    <filter id="softShadow" x="-5%" y="-8%" width="110%" height="120%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#2A1F1A" flood-opacity="0.04"/>
    </filter>
  </defs>

  <!-- Canvas Background -->
  <rect width="{WIDTH}" height="{HEIGHT}" class="canvas-bg" />

  <!-- HEADER -->
  <g transform="translate(500, 42)" text-anchor="middle">
    <text class="text-title">Information Routing Architecture</text>
  </g>

  <!-- 1. THE INTAKE FUNNEL -->
  
  <!-- Funnel Hopper Chamber Fill -->
  <polygon points="50,72 950,72 550,332 450,332" fill="#F4EDE2" stroke="none" />
  
  <!-- Dashed open mouth guide at top -->
  <line x1="50" y1="72" x2="950" y2="72" stroke="rgba(42, 31, 26, 0.35)" stroke-width="1.4" stroke-dasharray="6 4" stroke-linecap="round" />
  
  <!-- Chute side walls tapering directly into the central machine -->
  <line x1="50" y1="72" x2="450" y2="332" class="ink-line" stroke-width="2" />
  <line x1="950" y1="72" x2="550" y2="332" class="ink-line" stroke-width="2" />
  
  <!-- Top lip markers -->
  <circle cx="50" cy="72" r="3.5" fill="#2A1F1A" />
  <circle cx="950" cy="72" r="3.5" fill="#2A1F1A" />

  <!-- Gravity / Suction Flow Dash Guides inside the funnel -->
  <path d="M 195,120 C 240,170 420,225 465,295" class="ink-dash" />
  <path d="M 395,115 C 420,160 470,220 485,295" class="ink-dash" />
  <path d="M 605,115 C 580,160 530,220 515,295" class="ink-dash" />
  <path d="M 805,120 C 760,170 580,225 535,295" class="ink-dash" />

  <!-- INPUTS FALLING INSIDE THE FUNNEL -->
  
  <!-- TIER 1 (y ~ 100) -->
  <!-- Packet 1: Email / Slack -->
  <g transform="translate(195, 100) rotate(4.5)">
    <rect x="-75" y="-17" width="150" height="34" rx="6" class="box-fill" />
    <g transform="translate(-63, -9)">
      <rect width="20" height="14" rx="2" class="ink-line" stroke-width="1.2" />
      <path d="M 0,0 L 10,7 L 20,0" class="ink-line" stroke-width="1.2" />
    </g>
    <text x="-34" y="5" class="text-card">Email / Slack</text>
  </g>

  <!-- Packet 2: Movie / TV Rec -->
  <g transform="translate(395, 95) rotate(-2)">
    <rect x="-78" y="-17" width="156" height="34" rx="6" class="box-fill" />
    <polygon points="-60,-5 -60,5 -51,0" fill="#2A1F1A" />
    <text x="-43" y="5" class="text-card">Movie / TV Rec</text>
  </g>

  <!-- Packet 3: Article / Essay -->
  <g transform="translate(605, 95) rotate(2.5)">
    <rect x="-78" y="-17" width="156" height="34" rx="6" class="box-fill" />
    <line x1="-62" y1="-5" x2="-50" y2="-5" class="ink-line" stroke-width="1.4" />
    <line x1="-62" y1="0" x2="-54" y2="0" class="ink-line" stroke-width="1.4" />
    <line x1="-62" y1="5" x2="-50" y2="5" class="ink-line" stroke-width="1.4" />
    <text x="-42" y="5" class="text-card">Article / Essay</text>
  </g>

  <!-- Packet 4: Book Rec -->
  <g transform="translate(805, 100) rotate(-4.5)">
    <rect x="-72" y="-17" width="144" height="34" rx="6" class="box-fill" />
    <rect x="-60" y="-7" width="14" height="14" rx="1.5" class="ink-line" stroke-width="1.2" />
    <line x1="-56" y1="-7" x2="-56" y2="7" class="ink-line" stroke-width="1.2" />
    <text x="-38" y="5" class="text-card">Book Rec</text>
  </g>

  <!-- TIER 2 (y ~ 165) -->
  <!-- Packet 5: Personal Errand -->
  <g transform="translate(265, 165) rotate(5)">
    <rect x="-78" y="-17" width="156" height="34" rx="6" class="box-fill" />
    <rect x="-64" y="-7" width="14" height="14" rx="2" class="ink-line" stroke-width="1.2" />
    <path d="M -61,0 L -58,3 L -53,-3" fill="none" stroke="#2A1F1A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
    <text x="-42" y="5" class="text-card">Personal Errand</text>
  </g>

  <!-- Packet 6: Work Task -->
  <g transform="translate(500, 162)">
    <rect x="-72" y="-17" width="144" height="34" rx="6" class="box-fill" />
    <circle cx="-54" cy="0" r="7" fill="none" stroke="#2A1F1A" stroke-width="1.3" />
    <path d="M -57,0 L -55,2 L -51,-2" fill="none" stroke="#2A1F1A" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
    <text x="-38" y="5" class="text-card">Work Task</text>
  </g>

  <!-- Packet 7: Event / Invite -->
  <g transform="translate(735, 165) rotate(-5)">
    <rect x="-74" y="-17" width="148" height="34" rx="6" class="box-fill" />
    <rect x="-60" y="-7" width="14" height="14" rx="2" class="ink-line" stroke-width="1.2" />
    <line x1="-60" y1="-2" x2="-46" y2="-2" class="ink-line" stroke-width="1.2" />
    <line x1="-56" y1="-9" x2="-56" y2="-6" class="ink-line" stroke-width="1.4" stroke-linecap="round" />
    <line x1="-50" y1="-9" x2="-50" y2="-6" class="ink-line" stroke-width="1.4" stroke-linecap="round" />
    <text x="-38" y="5" class="text-card">Event / Invite</text>
  </g>

  <!-- TIER 3 (y ~ 230) -->
  <!-- Packet 8: Place / Food Rec -->
  <g transform="translate(415, 230) rotate(-2)">
    <rect x="-76" y="-17" width="152" height="34" rx="6" class="box-fill" />
    <path d="M -58,-8 C -61.5,-8 -64,-5.2 -64,-1.5 C -64,3 -58,9 -58,9 C -58,9 -52,3 -52,-1.5 C -52,-5.2 -54.5,-8 -58,-8 Z" fill="#EA4335" />
    <circle cx="-58" cy="-2" r="2" fill="#FFFFFF" />
    <text x="-40" y="5" class="text-card">Place / Food Rec</text>
  </g>

  <!-- Packet 9: Visual Reference -->
  <g transform="translate(595, 230) rotate(2)">
    <rect x="-80" y="-17" width="160" height="34" rx="6" class="box-fill" />
    <path d="M -62,-8 Q -62,0 -70,0 Q -62,0 -62,8 Q -62,0 -54,0 Q -62,0 -62,-8 Z" fill="#2A1F1A" />
    <text x="-44" y="5" class="text-card">Visual Reference</text>
  </g>

  <!-- Clean single stream arrow entering processor neck -->
  <line x1="500" y1="265" x2="500" y2="330" class="ink-line" stroke-width="2" marker-end="url(#inkArrow)" />

  <!-- 2. CENTRAL ENGINE: INFORMATION PROCESSING SYSTEM -->
  <g transform="translate(220, 332)">
    <rect width="560" height="118" class="box-fill" />
    
    <!-- Title banner -->
    <rect x="0" y="0" width="560" height="35" fill="#2A1F1A" />
    <text x="280" y="23" text-anchor="middle" class="text-machine">
      INFORMATION PROCESSING SYSTEM
    </text>

    <!-- Rule Section -->
    <g transform="translate(280, 67)" text-anchor="middle" font-family="'JetBrains Mono', monospace">
      <text font-size="11.5" font-weight="600" fill="#2A1F1A" letter-spacing="0.2px">
        Rule: Clarify and route immediately
      </text>
      <text y="20" font-size="11.5" font-weight="600" fill="#2A1F1A" letter-spacing="0.2px">
        so open loops leave working memory.
      </text>
    </g>
  </g>

  <!-- 3. DOWNWARD DISTRIBUTION PIPES (2 ROWS OF 4) -->

  <!-- Central trunk line from processor into Row 1 distribution junction -->
  <line x1="500" y1="450" x2="500" y2="485" class="ink-line" stroke-width="2" />
  <circle cx="500" cy="485" r="3.5" fill="#2A1F1A" />

  <!-- Pipes to ROW 1 (4 Destinations: x = 160, 385, 615, 840 at y = 538) -->
  <path d="M 500,485 C 500,515 160,512 160,538" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,485 C 500,515 385,512 385,538" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,485 C 500,515 615,512 615,538" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,485 C 500,515 840,512 840,538" class="ink-line" marker-end="url(#inkArrow)" />

  <!-- Central trunk line continuing down through center gap to Row 2 junction -->
  <line x1="500" y1="485" x2="500" y2="660" class="ink-line" stroke-width="2" />
  <circle cx="500" cy="660" r="3.5" fill="#2A1F1A" />

  <!-- Pipes to ROW 2 (4 Destinations: x = 160, 385, 615, 840 at y = 678) -->
  <path d="M 500,660 C 500,674 160,666 160,678" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,660 C 500,674 385,666 385,678" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,660 C 500,674 615,666 615,678" class="ink-line" marker-end="url(#inkArrow)" />
  <path d="M 500,660 C 500,674 840,666 840,678" class="ink-line" marker-end="url(#inkArrow)" />

  <!-- ROW 1 DESTINATIONS (4 APPS) -->

  <!-- ROW 1, COL 1: TODOIST (Personal Tasks) -->
  <g id="app-todoist" transform="translate(160, 574)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(-18, -18)">
      <path d="M 2 10 L 10 18 L 34 2" fill="none" stroke="#E44332" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M 2 20 L 10 28 L 34 12" fill="none" stroke="#E44332" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M 2 30 L 10 38 L 34 22" fill="none" stroke="#E44332" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
    </g>
    <text y="52" class="text-logo-name" font-size="12">Todoist</text>
    <text y="67" class="text-logo-sub" font-size="10">Personal Tasks</text>
  </g>

  <!-- ROW 1, COL 2: GOOGLE TASKS (Work Tasks) -->
  <g id="app-gtasks" transform="translate(385, 574)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(-19, -18) scale(0.073)">
      <polygon fill="#0066DA" points="410.4,58.3 368.8,81.2 348.2,120.6 368.8,168.8 407.8,211 450,187.5 475.9,142.8 450,87.5" />
      <path fill="#2684FC" d="M249.3,219.4l98.9-98.9c29.1,22.1,50.5,53.8,59.6,90.4L272.1,346.7c-12.2,12.2-32,12.2-44.2,0l-91.5-91.5 c-9.8-9.8-9.8-25.6,0-35.3l39-39c9.8-9.8,25.6-9.8,35.3,0L249.3,219.4z M519.8,63.6l-39.7-39.7c-9.7-9.7-25.6-9.7-35.3,0 l-34.4,34.4c27.5,23,49.9,51.8,65.5,84.5l43.9-43.9C529.6,89.2,529.6,73.3,519.8,63.6z M412.5,250c0,89.8-72.8,162.5-162.5,162.5 S87.5,339.8,87.5,250S160.2,87.5,250,87.5c36.9,0,70.9,12.3,98.2,33.1l62.2-62.2C367,21.9,311.1,0,250,0C111.9,0,0,111.9,0,250 s111.9,250,250,250s250-111.9,250-250c0-38.3-8.7-74.7-24.1-107.2L407.8,211C410.8,223.5,412.5,236.6,412.5,250z" />
    </g>
    <text y="52" class="text-logo-name" font-size="12">Google Tasks</text>
    <text y="67" class="text-logo-sub" font-size="10">Work Tasks</text>
  </g>

  <!-- ROW 1, COL 3: GOOGLE CALENDAR (Schedule & Events) -->
  <g id="app-gcal" transform="translate(615, 574)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(-17, -19) scale(0.17)">
      <path fill="#FFFFFF" d="M148.882,43.618l-47.368-5.263l-57.895,5.263L38.355,96.25l5.263,52.632l52.632,6.579l52.632-6.579 l5.263-53.947L148.882,43.618z"/>
      <path fill="#1A73E8" d="M65.211,125.276c-3.934-2.658-6.658-6.539-8.145-11.671l9.132-3.763c0.829,3.158,2.276,5.605,4.342,7.342 c2.053,1.737,4.553,2.592,7.474,2.592c2.987,0,5.553-0.908,7.697-2.724s3.224-4.132,3.224-6.934c0-2.868-1.132-5.211-3.395-7.026 s-5.105-2.724-8.5-2.724h-5.276v-9.039H76.5c2.921,0,5.382-0.789,7.382-2.368c2-1.579,3-3.737,3-6.487 c0-2.447-0.895-4.395-2.684-5.855s-4.053-2.197-6.803-2.197c-2.684,0-4.816,0.711-6.395,2.145s-2.724,3.197-3.447,5.276 l-9.039-3.763c1.197-3.395,3.395-6.395,6.618-8.987c3.224-2.592,7.342-3.895,12.342-3.895c3.697,0,7.026,0.711,9.974,2.145 c2.947,1.434,5.263,3.421,6.934,5.947c1.671,2.539,2.5,5.382,2.5,8.539c0,3.224-0.776,5.947-2.329,8.184 c-1.553,2.237-3.461,3.947-5.724,5.145v0.539c2.987,1.25,5.421,3.158,7.342,5.724c1.908,2.566,2.868,5.632,2.868,9.211 s-0.908,6.776-2.724,9.579c-1.816,2.803-4.329,5.013-7.513,6.618c-3.197,1.605-6.789,2.421-10.776,2.421 C73.408,129.263,69.145,127.934,65.211,125.276z"/>
      <path fill="#1A73E8" d="M121.25,79.961l-9.974,7.25l-5.013-7.605l17.987-12.974h6.895v61.197h-9.895L121.25,79.961z"/>
      <path fill="#EA4335" d="M148.882,196.25l47.368-47.368l-23.684-10.526l-23.684,10.526l-10.526,23.684L148.882,196.25z"/>
      <path fill="#34A853" d="M33.092,172.566l10.526,23.684h105.263v-47.368H43.618L33.092,172.566z"/>
      <path fill="#4285F4" d="M12.039-3.75C3.316-3.75-3.75,3.316-3.75,12.039v136.842l23.684,10.526l23.684-10.526V43.618h105.263 l10.526-23.684L148.882-3.75H12.039z"/>
      <path fill="#188038" d="M-3.75,148.882v31.579c0,8.724,7.066,15.789,15.789,15.789h31.579v-47.368H-3.75z"/>
      <path fill="#FBBC04" d="M148.882,43.618v105.263h47.368V43.618l-23.684-10.526L148.882,43.618z"/>
      <path fill="#1967D2" d="M196.25,43.618V12.039c0-8.724-7.066-15.789-15.789-15.789h-31.579v47.368H196.25z"/>
    </g>
    <text y="52" class="text-logo-name" font-size="12">Google Calendar</text>
    <text y="67" class="text-logo-sub" font-size="10">Schedule &amp; Events</text>
  </g>

  <!-- ROW 1, COL 4: GOOGLE MAPS (Places & Travel) -->
  <g id="app-gmaps" transform="translate(840, 574)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(-13, -19) scale(0.28)">
      <path fill="#1a73e8" d="M60.2 2.2C55.8.8 51 0 46.1 0 32 0 19.3 6.4 10.8 16.5l21.8 18.3L60.2 2.2z"/>
      <path fill="#ea4335" d="M10.8 16.5C4.1 24.5 0 34.9 0 46.1c0 8.7 1.7 15.7 4.6 22l28-33.3-21.8-18.3z"/>
      <path fill="#4285f4" d="M46.2 28.5c9.8 0 17.7 7.9 17.7 17.7 0 4.3-1.6 8.3-4.2 11.4 0 0 13.9-16.6 27.5-32.7-5.6-10.8-15.3-19-27-22.7L32.6 34.8c3.3-3.8 8.1-6.3 13.6-6.3"/>
      <path fill="#fbbc04" d="M46.2 63.8c-9.8 0-17.7-7.9-17.7-17.7 0-4.3 1.5-8.3 4.1-11.3l-28 33.3c4.8 10.6 12.8 19.2 21 29.9l34.1-40.5c-3.3 3.9-8.1 6.3-13.5 6.3"/>
      <path fill="#34a853" d="M59.1 109.2c15.4-24.1 33.3-35 33.3-63 0-7.7-1.9-14.9-5.2-21.3L25.6 98c2.6 3.4 5.3 7.3 7.9 11.3 9.4 14.5 6.8 23.1 12.8 23.1s3.4-8.7 12.8-23.2"/>
    </g>
    <text y="52" class="text-logo-name" font-size="12">Google Maps</text>
    <text y="67" class="text-logo-sub" font-size="10">Places &amp; Travel</text>
  </g>

  <!-- ROW 2 DESTINATIONS (4 APPS) -->

  <!-- ROW 2, COL 1: GOOGLE TV (Movie Recs) -->
  <g id="app-gtv" transform="translate(160, 712)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(0, -2)">
      <rect x="-20" y="-14" width="40" height="28" rx="4" fill="none" stroke="#2A1F1A" stroke-width="2" />
      <line x1="-8" y1="14" x2="-14" y2="20" stroke="#2A1F1A" stroke-width="2" stroke-linecap="round" />
      <line x1="8" y1="14" x2="14" y2="20" stroke="#2A1F1A" stroke-width="2" stroke-linecap="round" />
      <polygon points="-5,-6 -5,6 7,0" fill="#EA580C" stroke="#EA580C" stroke-width="1.5" stroke-linejoin="round" />
    </g>
    <text y="52" class="text-logo-name" font-size="12">Google TV</text>
    <text y="67" class="text-logo-sub" font-size="10">Movie Recs</text>
  </g>

  <!-- ROW 2, COL 2: INSTAPAPER (Articles to Read) -->
  <g id="app-instapaper" transform="translate(385, 712)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <text y="14" font-family="Georgia, serif" font-size="44" font-weight="bold" fill="#2A1F1A">I</text>
    <text y="52" class="text-logo-name" font-size="12">Instapaper</text>
    <text y="67" class="text-logo-sub" font-size="10">Articles to Read</text>
  </g>

  <!-- ROW 2, COL 3: ARE.NA (Inspiration & Craft) -->
  <g id="app-arena" transform="translate(615, 712)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <g transform="translate(-19, -19) scale(0.21)">
      <path fill="#2A1F1A" d="m177.4 111.3-24.6-19.4c-1.5-1.2-1.5-3.1 0-4.3l24.6-19.4c1.5-1.2 2.1-3.2 1.4-4.5-.7-1.3-2.8-1.7-4.6-.9l-29.4 11.7c-1.8.7-3.4-.2-3.8-2.1L136.6 41c-.2-1.9-1.7-3.4-3.2-3.4-1.4 0-3 1.5-3.2 3.4l-4.4 31.4c-.2 1.9-1.9 2.8-3.8 2.1L93.3 62.8c-1.8-.7-4.7-.7-6.5 0l-29 11.5c-1.8.7-3.4-.2-3.8-2.1l-4.3-31.4c-.2-1.9-1.7-3.4-3.2-3.4s-3 1.5-3.2 3.4L39 72.2c-.2 1.9-1.9 2.8-3.8 2.1L5.8 62.6c-1.8-.7-3.9-.2-4.6.9-.7 1.3-.1 3.3 1.4 4.5l24.6 19.4c1.5 1.2 1.5 3.1 0 4.3L2.6 111.1c-1.5 1.2-2.1 3.3-1.4 4.7s2.8 2 4.6 1.3L35 105.5c1.8-.7 3.4.2 3.7 2.1l4.1 31.6c.2 1.9 1.9 3.4 3.7 3.4 1.8 0 3.4-1.5 3.7-3.4l4.1-31.6c.2-1.9 1.9-2.8 3.7-2.1L86.6 117c1.8.7 4.7.7 6.5 0l28.7-11.5c1.8-.7 3.4.2 3.7 2.1l4.3 31.6c.2 1.9 1.9 3.4 3.7 3.4s3.4-1.5 3.7-3.4l4.1-31.6c.2-1.9 1.9-2.8 3.7-2.1l29.1 11.7c1.8.7 3.8.1 4.6-1.3.9-1.3.2-3.5-1.3-4.6zm-62.8-19.2-21.8 16.7c-1.5 1.2-4 1.2-5.6 0L65.5 92.1c-1.5-1.2-1.5-3.1 0-4.3l21.8-17.2c1.5-1.2 4-1.2 5.4 0l21.8 17.2c1.6 1.2 1.6 3.1.1 4.3z"/>
    </g>
    <text y="52" class="text-logo-name" font-size="12">Are.na</text>
    <text y="67" class="text-logo-sub" font-size="10">Inspiration &amp; Craft</text>
  </g>

  <!-- ROW 2, COL 4: GOODREADS (Books to Read) -->
  <g id="app-goodreads" transform="translate(840, 712)" text-anchor="middle">
    <rect x="-35" y="-35" width="70" height="70" class="logo-badge" />
    <text y="14" font-family="'Times New Roman', serif" font-size="44" font-weight="bold" fill="#854D0E">g</text>
    <text y="52" class="text-logo-name" font-size="12">Goodreads</text>
    <text y="67" class="text-logo-sub" font-size="10">Books to Read</text>
  </g>

  <!-- 4. CONVERGENCE CONDUITS: DO -> REFLECT -->
  <!-- Conduits carry saved taste & digital exhaust down from the tubes into Webtack -->
  <g opacity="0.85">
    <path d="M 160,788 C 160,822 430,816 460,836" class="ink-dash" stroke-width="1.3" />
    <path d="M 840,788 C 840,822 570,816 540,836" class="ink-dash" stroke-width="1.3" />
    <path d="M 385,788 C 385,816 480,818 490,836" class="ink-dash" stroke-width="1.3" />
    <path d="M 615,788 C 615,816 520,818 510,836" class="ink-dash" stroke-width="1.3" />
  </g>

  <!-- Central entry arrow into Webtack -->
  <line x1="500" y1="812" x2="500" y2="840" class="ink-line" stroke-width="2" marker-end="url(#inkArrow)" />

  <!-- Label floating above the entry neck -->
  <g transform="translate(500, 824)" text-anchor="middle">
    <rect x="-105" y="-10" width="210" height="20" rx="10" fill="#FBF7F0" stroke="#2A1F1A" stroke-width="1" />
    <text y="3.5" font-family="'JetBrains Mono', monospace" font-size="9.5" font-weight="700" fill="#78350F" letter-spacing="0.5px">
      DIGITAL EXHAUST &amp; SAVED TASTE
    </text>
  </g>

  <!-- 5. WEBTACK: STEP 4 · REFLECT -->
  <g id="webtack-reflection" transform="translate(120, 842)">
    
    <!-- Outer container box with subtle shadow -->
    <rect width="760" height="218" rx="8" fill="#FFFFFF" stroke="#2A1F1A" stroke-width="1.8" filter="url(#softShadow)" />
    
    <!-- Header Banner -->
    <path d="M 0 8 Q 0 0 8 0 L 752 0 Q 760 0 760 8 L 760 38 L 0 38 Z" fill="#1C1917" />
    
    <!-- Header Title: Pin + Title -->
    <g transform="translate(26, 19)">
      <circle cx="0" cy="0" r="4.5" fill="#E44332" />
      <line x1="0" y1="4.5" x2="0" y2="9" stroke="#FBF7F0" stroke-width="1.8" stroke-linecap="round" />
      <text x="14" y="4.5" class="webtack-header">STEP 4: REFLECT · WEBTACK</text>
    </g>

    <!-- Header Right Tag: Local-First Vault -->
    <g transform="translate(734, 19)" text-anchor="end">
      <rect x="-140" y="-10" width="140" height="20" rx="4" fill="#059669" />
      <text x="-70" y="3.5" text-anchor="middle" font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="700" fill="#FFFFFF" letter-spacing="0.5px">
        LOCAL-FIRST VAULT
      </text>
    </g>

    <!-- Subtitle Banner Strip -->
    <rect x="0" y="38" width="760" height="26" fill="#F4EDE2" stroke="#E5DEC9" stroke-width="0.8" />
    <text x="380" y="55" text-anchor="middle" font-family="'Mulish', -apple-system, sans-serif" font-size="11px" font-weight="600" fill="#44403C">
      The missing piece: Turn ambient digital exhaust into a compounding personal vault for AI reflection &amp; synthesis.
    </text>

    <!-- 3 SUB-PILLARS INSIDE WEBTACK -->

    <!-- Pillar 1: Ingest & Universal Capture (X: 18, Width: 228) -->
    <g transform="translate(18, 74)">
      <rect width="228" height="130" rx="6" fill="#FBF7F0" stroke="#2A1F1A" stroke-width="1.2" />
      
      <!-- Icon + Badge Header -->
      <g transform="translate(12, 14)">
        <rect width="24" height="24" rx="5" fill="#F2EAE1" stroke="#2A1F1A" stroke-width="1.1" />
        <path d="M 7 8 L 17 8 L 13 13 L 13 17 L 11 15 L 11 13 Z" fill="none" stroke="#2A1F1A" stroke-width="1.2" stroke-linejoin="round" />
      </g>
      <text x="44" y="24" class="pillar-title">1. Capture &amp; Ingest</text>
      <text x="44" y="37" font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="600" fill="#78350F">From the tubes</text>

      <line x1="12" y1="46" x2="216" y2="46" stroke="#E2D9CC" stroke-width="0.8" />

      <!-- Feature Bullets -->
      <text x="12" y="65" class="pillar-sub">• One-click browser bookmarklet</text>
      <text x="12" y="81" class="pillar-sub">• Instapaper &amp; Are.na sync</text>
      <text x="12" y="97" class="pillar-sub">• YouTube Favorites</text>
      <text x="12" y="113" class="pillar-sub">• CLI &amp; quick-capture studio</text>
    </g>

    <!-- Pillar 2: The Canonical Core (X: 266, Width: 228) -->
    <g transform="translate(266, 74)">
      <rect width="228" height="130" rx="6" fill="#FFFFFF" stroke="#059669" stroke-width="1.6" />
      
      <!-- Canonical Truth Tag -->
      <rect x="134" y="-7" width="86" height="14" rx="3" fill="#059669" />
      <text x="177" y="3.5" text-anchor="middle" font-family="'JetBrains Mono', monospace" font-size="8px" font-weight="700" fill="#FFFFFF">CANONICAL TRUTH</text>

      <!-- Icon + Badge Header -->
      <g transform="translate(12, 14)">
        <rect width="24" height="24" rx="5" fill="#ECFDF5" stroke="#059669" stroke-width="1.1" />
        <path d="M 6 8 L 11 8 L 13 10 L 18 10 L 18 16 L 6 16 Z" fill="none" stroke="#059669" stroke-width="1.3" />
      </g>
      <text x="44" y="24" class="pillar-title" fill="#065F46">2. Sovereign Vault</text>
      <text x="44" y="37" font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="600" fill="#059669">Filesystem on disk</text>

      <line x1="12" y1="46" x2="216" y2="46" stroke="#D1FAE5" stroke-width="0.8" />

      <!-- Feature Bullets -->
      <text x="12" y="65" class="pillar-sub">• Plain <tspan font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="700">atom.json</tspan> + raw media</text>
      <text x="12" y="81" class="pillar-sub">• 7 structured content types</text>
      <text x="12" y="97" class="pillar-sub">• SQLite FTS5 search index</text>
      <text x="12" y="113" class="pillar-sub" font-weight="700" fill="#047857">• 30-year durable · Zero lock-in</text>
    </g>

    <!-- Pillar 3: AI Synthesis & Garden (X: 514, Width: 228) -->
    <g transform="translate(514, 74)">
      <rect width="228" height="130" rx="6" fill="#FBF7F0" stroke="#2A1F1A" stroke-width="1.2" />
      
      <!-- Icon + Badge Header -->
      <g transform="translate(12, 14)">
        <rect width="24" height="24" rx="5" fill="#EEF2FF" stroke="#4F46E5" stroke-width="1.1" />
        <path d="M 12 5 C 12 9, 14.5 11.5, 19 12 C 14.5 12.5, 12 15, 12 19 C 12 15, 9.5 12.5, 5 12 C 9.5 11.5, 12 9, 12 5 Z" fill="url(#mcpGrad)" />
      </g>
      <text x="44" y="24" class="pillar-title">3. AI &amp; Reflection</text>
      <text x="44" y="37" font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="600" fill="#4338CA">Synthesis &amp; Expression</text>

      <line x1="12" y1="46" x2="216" y2="46" stroke="#E2D9CC" stroke-width="0.8" />

      <!-- Feature Bullets -->
      <text x="12" y="65" class="pillar-sub">• <tspan font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="700">MCP Server</tspan> for Claude &amp; AGY</text>
      <text x="12" y="81" class="pillar-sub">• Obsidian &amp; NotebookLM export</text>
      <text x="12" y="97" class="pillar-sub">• Curated <tspan font-family="'JetBrains Mono', monospace" font-size="9px" font-weight="700">llms.txt</tspan> &amp; RSS</text>
      <text x="12" y="113" class="pillar-sub">• Public Garden (<tspan font-style="italic">/garden</tspan>)</text>
    </g>

  </g>

  <!-- Connecting link to Payoff -->
  <line x1="500" y1="1060" x2="500" y2="1084" class="ink-line" stroke-width="2" marker-end="url(#inkArrow)" />

  <!-- 6. OUTCOME (MATCHING GHOST CALLOUT VERBATIM) -->
  <g transform="translate(180, 1086)">
    <rect width="640" height="85" rx="6" class="shade-fill" />
    <!-- Brand Color Left Border (Ghost theme brand-color: #7D2035) -->
    <path d="M 0,6 Q 0,0 6,0 L 6,0 L 6,85 L 6,85 Q 0,85 0,79 Z" fill="#7D2035" />
    <text x="320" y="30" text-anchor="middle" font-family="'Newsreader', Georgia, 'Times New Roman', serif" font-size="16" font-weight="500" fill="#2A1F1A" font-style="italic" letter-spacing="-0.01em">
      The Payoff: An Empty Cache &amp; True Margin
    </text>
    <text x="320" y="52" text-anchor="middle" class="text-dim">
      Working memory is silent • Zero background loops leaking attention
    </text>
    <text x="320" y="70" text-anchor="middle" font-family="Mulish, -apple-system, sans-serif" font-size="11.5" font-weight="700" fill="#2A1F1A">
      Deep Work Focus Blocks (2+ hrs)  |  Family Time (Evenings &amp; Weekends)
    </text>
  </g>

  <!-- Watermark -->
  <text x="{WIDTH // 2}" y="1198" text-anchor="middle" class="watermark">webtack.net</text>

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
  <title>Information Routing Architecture + WebTack Reflection</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,500;1,6..72,600&family=JetBrains+Mono:wght@400;500;600;700&family=Mulish:wght@400;500;600;700&display=swap" rel="stylesheet">
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
      max-width: 1080px;
      width: 100%;
      background: #FBF7F0;
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
      color: #2A1F1A;
    }}
    .btn {{
      padding: 8px 16px;
      background: #2A1F1A;
      color: #FBF7F0;
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
      padding: 24px;
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
      <h1>Information Routing Architecture + WebTack (The Reflection Step)</h1>
      <div>
        <a href="webtack-reflection.svg" download="webtack-reflection.svg" class="btn">Download SVG</a>
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

# Auto-generate high-res PNG (headless Chrome for 2x Retina rendering)
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
        print(f"✓ Generated {PNG_OUTPUT} (Retina PNG via Chrome)")
        rendered = True
    except Exception as e:
        print(f"Notice: Chrome rasterization failed ({e}), falling back to qlmanage...")

if not rendered:
    try:
        res = subprocess.run(
            ["qlmanage", "-t", "-s", "2400", "-o", OUTPUT_DIR, SVG_OUTPUT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        temp_png = f"{SVG_OUTPUT}.png"
        if os.path.exists(temp_png):
            shutil.move(temp_png, PNG_OUTPUT)
            print(f"✓ Generated {PNG_OUTPUT} (PNG via qlmanage)")
    except Exception as e:
        print(f"Notice: PNG generation via qlmanage skipped ({e})")
