/**
 * WebTack In-Page Capture Drawer Bookmarklet (Option B)
 * Extracts canonical metadata, OpenGraph, JSON-LD, bylines, and selections
 * into a sleek, isolated Shadow DOM drawer directly on the active webpage.
 */
(function() {
  const DRAWER_ID = 'webtack-drawer-host';
  const existing = document.getElementById(DRAWER_ID);
  if (existing) {
    existing.remove();
    return;
  }

  // 1. DOM Metadata Extraction
  function getMeta(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const val = el.getAttribute('content') || el.getAttribute('value') || el.innerText;
        if (val && val.trim()) return val.trim();
      }
    }
    return '';
  }

  function extractArticleMarkdown() {
    const selectors = [
      'article',
      '[name="articleBody"]',
      'section[name="articleBody"]',
      '.article-body',
      '.story-body',
      '.entry-content',
      '.post-content',
      '[itemprop="articleBody"]',
      'main'
    ];
    let container = null;
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.length > 200) {
        container = el;
        break;
      }
    }
    if (!container) container = document.body;
    if (!container) return null;

    const clone = container.cloneNode(true);
    const stripSelectors = [
      'script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside',
      '.advertisement', '.ad', '[aria-hidden="true"]', 'button', 'iframe',
      '.social-share', '.comments', '.newsletter-signup', '[id*="ad-"]'
    ];
    clone.querySelectorAll(stripSelectors.join(', ')).forEach(el => el.remove());

    const elements = clone.querySelectorAll('h1, h2, h3, h4, p, blockquote, ul, ol');
    if (!elements || elements.length === 0) {
      return clone.innerText ? clone.innerText.trim() : null;
    }

    const lines = [];
    elements.forEach(el => {
      const tag = el.tagName.toLowerCase();
      const text = el.innerText.trim();
      if (!text || text.length < 2) return;

      if (tag === 'h1') lines.push('# ' + text);
      else if (tag === 'h2') lines.push('## ' + text);
      else if (tag === 'h3') lines.push('### ' + text);
      else if (tag === 'h4') lines.push('#### ' + text);
      else if (tag === 'blockquote') lines.push('> ' + text);
      else if (tag === 'p') lines.push(text);
      else if (tag === 'ul' || tag === 'ol') {
        el.querySelectorAll('li').forEach(li => {
          const liText = li.innerText.trim();
          if (liText) lines.push('- ' + liText);
        });
      }
    });

    const md = lines.join('\n\n');
    return md.length > 100 ? md : (clone.innerText ? clone.innerText.trim() : null);
  }

  function getJsonLdMetadata() {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
      try {
        const data = JSON.parse(s.textContent.trim());
        const items = Array.isArray(data) ? data : (data['@graph'] || [data]);
        for (const item of items) {
          if (!item) continue;
          let author = null;
          if (item.author) {
            if (typeof item.author === 'string') author = item.author;
            else if (Array.isArray(item.author)) author = item.author.map(a => a.name || a).join(', ');
            else if (item.author.name) author = item.author.name;
          }
          let date = item.datePublished || item.dateCreated || null;
          let image = null;
          if (typeof item.image === 'string') image = item.image;
          else if (item.image && item.image.url) image = item.image.url;

          if (author || date || image) {
            return { author, date, image };
          }
        }
      } catch (e) {}
    }
    return {};
  }

  const jsonLd = getJsonLdMetadata();
  const canonicalUrl = document.querySelector('link[rel="canonical"]')?.href || window.location.href;
  const pageTitle = getMeta(['meta[property="og:title"]', 'meta[name="twitter:title"]']) || document.title || '';
  const siteName = getMeta(['meta[property="og:site_name"]']) || window.location.hostname.replace(/^www\./, '');
  const author = jsonLd.author || getMeta([
    'meta[name="author"]',
    'meta[name="twitter:creator"]',
    'meta[property="article:author"]',
    '[rel="author"]',
    '.byline',
    '[itemprop="author"]'
  ]);
  const description = getMeta(['meta[property="og:description"]', 'meta[name="description"]']);
  const imageUrl = jsonLd.image || getMeta(['meta[property="og:image:secure_url"]', 'meta[property="og:image"]', 'meta[name="twitter:image"]']);
  const selection = window.getSelection() ? window.getSelection().toString().trim() : '';
  const isVideoPage = /youtube\.com|youtu\.be|vimeo\.com|twitch\.tv|loom\.com/i.test(window.location.hostname);
  const isArticlePage = !!document.querySelector('article') || (document.body ? document.body.textContent.length > 2000 : false);

  // Auto-detect initial kind
  let currentKind = 'bookmark';
  if (selection.length > 0) {
    currentKind = 'quote';
  } else if (isVideoPage) {
    currentKind = 'video';
  } else if (isArticlePage) {
    currentKind = 'article';
  }

  // 2. Create Isolated Shadow DOM Host
  const host = document.createElement('div');
  host.id = DRAWER_ID;
  host.style.position = 'fixed';
  host.style.top = '0';
  host.style.right = '0';
  host.style.width = '0';
  host.style.height = '0';
  host.style.zIndex = '2147483647';
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: 'open' });

  // 3. Inject Scoped CSS & HTML
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      }
      * {
        box-sizing: border-box;
      }
      .webtack-backdrop {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(2px);
        z-index: 2147483646;
      }
      .webtack-card {
        position: fixed;
        top: 20px;
        right: 20px;
        width: 440px;
        max-width: calc(100vw - 40px);
        max-height: calc(100vh - 40px);
        overflow-y: auto;
        background: #0f172a;
        color: #f8fafc;
        border: 1px solid #334155;
        border-radius: 16px;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.08);
        padding: 20px;
        z-index: 2147483647;
        animation: slideIn 0.22s cubic-bezier(0.16, 1, 0.3, 1);
      }
      @keyframes slideIn {
        from { transform: translateX(30px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
        padding-bottom: 12px;
        border-bottom: 1px solid #1e293b;
      }
      .brand {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 700;
        font-size: 15px;
        color: #f1f5f9;
        letter-spacing: -0.01em;
      }
      .brand-dot {
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 8px #10b981;
      }
      .close-btn {
        background: none;
        border: none;
        color: #94a3b8;
        font-size: 18px;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 6px;
        line-height: 1;
        transition: all 0.15s;
      }
      .close-btn:hover {
        color: #f8fafc;
        background: #1e293b;
      }
      .kind-pills {
        display: flex;
        gap: 6px;
        overflow-x: auto;
        padding-bottom: 8px;
        margin-bottom: 14px;
        scrollbar-width: none;
      }
      .kind-pills::-webkit-scrollbar {
        display: none;
      }
      .pill-btn {
        background: #1e293b;
        color: #94a3b8;
        border: 1px solid #334155;
        padding: 5px 10px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.15s;
      }
      .pill-btn:hover {
        background: #334155;
        color: #f8fafc;
      }
      .pill-btn.active {
        background: #2563eb;
        color: #ffffff;
        border-color: #3b82f6;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.4);
      }
      .preview-box {
        display: flex;
        gap: 12px;
        background: #1e293b;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 14px;
        border: 1px solid #334155;
        align-items: center;
      }
      .preview-img {
        width: 84px;
        height: 56px;
        object-fit: cover;
        border-radius: 6px;
        background: #0f172a;
        flex-shrink: 0;
      }
      .preview-meta {
        font-size: 11px;
        color: #94a3b8;
        overflow: hidden;
      }
      .preview-site {
        font-weight: 700;
        color: #38bdf8;
        text-transform: uppercase;
        font-size: 10px;
        letter-spacing: 0.05em;
        margin-bottom: 2px;
      }
      .btn-picker {
        background: #2563eb;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        transition: background 0.15s;
      }
      .btn-picker:hover {
        background: #1d4ed8;
      }
      .btn-picker-preview {
        background: #1e293b;
        color: #38bdf8;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
        margin-left: auto;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        transition: all 0.15s;
      }
      .btn-picker-preview:hover {
        background: #334155;
        color: #ffffff;
        border-color: #38bdf8;
      }
      .form-group {
        margin-bottom: 12px;
      }
      label {
        display: block;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-bottom: 4px;
      }
      input, textarea, select {
        width: 100%;
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #f8fafc;
        font-size: 13px;
        padding: 8px 10px;
        outline: none;
        transition: border-color 0.15s;
        font-family: inherit;
      }
      input:focus, textarea:focus, select:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
      }
      textarea {
        resize: vertical;
        min-height: 56px;
        line-height: 1.4;
      }
      .row {
        display: flex;
        gap: 10px;
      }
      .row > div {
        flex: 1;
      }
      .quote-highlight {
        background: rgba(59, 130, 246, 0.08);
        border-left: 3px solid #3b82f6;
        padding-left: 8px;
      }
      .actions {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 16px;
        padding-top: 14px;
        border-top: 1px solid #1e293b;
      }
      .status-text {
        font-size: 12px;
        color: #94a3b8;
      }
      .status-error {
        color: #f87171 !important;
      }
      .status-success {
        color: #34d399 !important;
        font-weight: 600;
      }
      .btn-group {
        display: flex;
        gap: 8px;
      }
      .btn {
        padding: 8px 14px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        border: none;
        transition: all 0.15s;
      }
      .btn-cancel {
        background: #1e293b;
        color: #94a3b8;
        border: 1px solid #334155;
      }
      .btn-cancel:hover {
        background: #334155;
        color: #f8fafc;
      }
      .btn-save {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        color: #ffffff;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
      }
      .btn-save:hover {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
      }
      .btn-save:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
      .server-warning {
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 8px;
        padding: 10px;
        font-size: 12px;
        color: #fca5a5;
        margin-top: 10px;
        display: none;
        line-height: 1.4;
      }
    </style>

    <div class="webtack-backdrop" id="backdrop"></div>
    <div class="webtack-card">
      <div class="header">
        <div class="brand">
          <div class="brand-dot"></div>
          WebTack Capture
        </div>
        <button class="close-btn" id="closeBtn" title="Close (Esc)">✕</button>
      </div>

      <div class="kind-pills">
        <button class="pill-btn ${currentKind === 'article' ? 'active' : ''}" data-kind="article">📖 Article</button>
        <button class="pill-btn ${currentKind === 'bookmark' ? 'active' : ''}" data-kind="bookmark">🔖 Bookmark</button>
        <button class="pill-btn ${currentKind === 'video' ? 'active' : ''}" data-kind="video">🎬 Video</button>
        <button class="pill-btn ${currentKind === 'quote' ? 'active' : ''}" data-kind="quote">✍️ Quote</button>
        <button class="pill-btn ${currentKind === 'note' ? 'active' : ''}" data-kind="note">📝 Note</button>
        <button class="pill-btn ${currentKind === 'image' ? 'active' : ''}" data-kind="image">🎨 Image</button>
      </div>

      <div class="preview-box" id="previewBox" style="display: ${imageUrl ? 'flex' : 'none'};">
        <img src="${imageUrl || ''}" class="preview-img" id="previewImg" onerror="this.style.display='none'">
        <div class="preview-meta" style="flex: 1; min-width: 0;">
          <div class="preview-site">${siteName}</div>
          <div id="previewTitle" style="color: #cbd5e1; font-weight: 500; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${escapeHtml(pageTitle)}</div>
        </div>
        <button type="button" class="btn-picker-preview" id="btnPickPreview" title="Click any image on the active page to capture it">🎯 Pick Image</button>
      </div>

      <form id="captureForm">
        <div id="articleBadge" style="display: ${currentKind === 'article' ? 'flex' : 'none'}; align-items: center; gap: 6px; font-size: 11.5px; color: #38bdf8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 6px; padding: 6px 10px; margin-bottom: 12px;">
          <span>📖</span>
          <span>In-browser full article text ready for offline reading</span>
        </div>

        <!-- Title Input -->
        <div class="form-group" id="groupTitle">
          <label id="lblTitle">Title</label>
          <input type="text" id="inputTitle" value="${escapeHtml(pageTitle)}" placeholder="Atom Title" required>
        </div>

        <!-- Quote Area (Conditional) -->
        <div class="form-group" id="groupQuote" style="display: ${currentKind === 'quote' ? 'block' : 'none'};">
          <label>Quote Excerpt</label>
          <textarea id="inputQuote" class="quote-highlight" rows="3" placeholder="Verbatim quote...">${escapeHtml(selection)}</textarea>
        </div>

        <!-- Note Text Area (Conditional) -->
        <div class="form-group" id="groupNote" style="display: ${currentKind === 'note' ? 'block' : 'none'};">
          <label>Memo / Thought</label>
          <textarea id="inputNote" rows="3" placeholder="Your note or reflection..."></textarea>
        </div>

        <!-- URL Input -->
        <div class="form-group" id="groupUrl" style="display: ${currentKind === 'note' ? 'none' : 'block'};">
          <label id="lblUrl">Source URL</label>
          <input type="url" id="inputUrl" value="${escapeHtml(canonicalUrl)}" placeholder="https://..." required>
        </div>

        <!-- Image URL Input (Conditional for Image Kind) -->
        <div class="form-group" id="groupImageSrc" style="display: ${currentKind === 'image' ? 'block' : 'none'};">
          <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
            <label style="margin-bottom: 0;">Image Source Link</label>
            <button type="button" class="btn-picker" id="btnPickImage">🎯 Pick from page</button>
          </div>
          <input type="url" id="inputImageSrc" value="${escapeHtml(imageUrl || '')}" placeholder="https://.../photo.jpg">
        </div>

        <!-- Author & Published Meta Row -->
        <div class="row" id="groupAuthorRow" style="display: ${['article', 'quote', 'video', 'image'].includes(currentKind) ? 'flex' : 'none'};">
          <div class="form-group">
            <label id="lblAuthor">Author / Channel</label>
            <input type="text" id="inputAuthor" value="${escapeHtml(author)}" placeholder="Author name">
          </div>
        </div>

        <!-- Description / Editorial Notes -->
        <div class="form-group" id="groupDescription" style="display: ${currentKind === 'note' ? 'none' : 'block'};">
          <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
            <label style="margin-bottom: 0;">Description / Editorial Summary</label>
            <span style="font-size: 10px; color: #94a3b8; font-weight: 500;">Editable</span>
          </div>
          <textarea id="inputDescription" rows="4" style="min-height: 84px; line-height: 1.45;" placeholder="Add or edit summary or personal editorial notes...">${escapeHtml(description)}</textarea>
        </div>

        <!-- Collection & Visibility Row -->
        <div class="row">
          <div class="form-group" style="flex: 1.4;">
            <label>Collection / Channel</label>
            <input type="text" id="inputCollection" list="collectionSuggestions" placeholder="e.g. Design, Wishlist, Ride">
            <datalist id="collectionSuggestions"></datalist>
          </div>
          <div class="form-group" style="flex: 1;">
            <label>Visibility</label>
            <select id="selectVisibility">
              <option value="public" selected>🌐 Public</option>
              <option value="shared">👥 Shared</option>
              <option value="private">🔒 Private</option>
            </select>
          </div>
        </div>

        <!-- Tags Row -->
        <div class="form-group">
          <label>Tags (Comma separated)</label>
          <input type="text" id="inputTags" placeholder="e.g. design, ai, web">
        </div>

        <div class="server-warning" id="serverWarning">
          ⚠️ <strong>Cannot connect to WebTack!</strong><br>
          Make sure WebTack is running by double-clicking <code>Launch WebTack.command</code> or running <code>python3 curate.py view --server</code> on your Mac.
          <div style="margin-top: 6px;">
            <a href="http://127.0.0.1:8080/?capture_url=${encodeURIComponent(canonicalUrl)}&capture_title=${encodeURIComponent(pageTitle)}" target="_blank" style="color: #60a5fa; text-decoration: underline;">Open WebTack in tab instead</a>
          </div>
        </div>

        <div class="actions">
          <div class="status-text" id="statusText">Ready</div>
          <div class="btn-group">
            <button type="button" class="btn btn-cancel" id="btnCancel">Cancel</button>
            <button type="submit" class="btn btn-save" id="btnSave">Save to Vault</button>
          </div>
        </div>
      </form>
    </div>
  `;

  // 4. Helper Functions
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function closeDrawer() {
    host.remove();
  }

  // 5. Kind Switching Logic
  const pills = shadow.querySelectorAll('.pill-btn');
  const groupQuote = shadow.getElementById('groupQuote');
  const groupNote = shadow.getElementById('groupNote');
  const groupUrl = shadow.getElementById('groupUrl');
  const groupImageSrc = shadow.getElementById('groupImageSrc');
  const groupAuthorRow = shadow.getElementById('groupAuthorRow');
  const groupDescription = shadow.getElementById('groupDescription');
  const lblAuthor = shadow.getElementById('lblAuthor');
  const lblTitle = shadow.getElementById('lblTitle');
  const inputTitle = shadow.getElementById('inputTitle');
  const inputTags = shadow.getElementById('inputTags');

  pills.forEach(p => {
    p.addEventListener('click', (e) => {
      e.preventDefault();
      pills.forEach(b => b.classList.remove('active'));
      p.classList.add('active');
      currentKind = p.dataset.kind;

      // Adjust field visibility
      shadow.getElementById('articleBadge').style.display = currentKind === 'article' ? 'flex' : 'none';
      groupQuote.style.display = currentKind === 'quote' ? 'block' : 'none';
      groupNote.style.display = currentKind === 'note' ? 'block' : 'none';
      groupUrl.style.display = currentKind === 'note' ? 'none' : 'block';
      groupImageSrc.style.display = currentKind === 'image' ? 'block' : 'none';
      groupAuthorRow.style.display = ['article', 'quote', 'video', 'image'].includes(currentKind) ? 'flex' : 'none';
      groupDescription.style.display = currentKind === 'note' ? 'none' : 'block';

      if (currentKind === 'video') {
        lblAuthor.textContent = 'Channel / Creator';
      } else {
        lblAuthor.textContent = 'Author';
      }

      if (currentKind === 'note') {
        lblTitle.textContent = 'Note Title (Optional)';
        inputTitle.required = false;
      } else {
        lblTitle.textContent = 'Title';
        inputTitle.required = true;
      }
    });
  });

  // 5.5 Visual Image Picker Logic
  function startImagePicker() {
    const card = shadow.querySelector('.webtack-card');
    const backdrop = shadow.getElementById('backdrop');
    if (card) card.style.display = 'none';
    if (backdrop) backdrop.style.display = 'none';

    const badge = document.createElement('div');
    badge.id = 'webtack-picker-badge';
    badge.style.position = 'fixed';
    badge.style.top = '16px';
    badge.style.left = '50%';
    badge.style.transform = 'translateX(-50%)';
    badge.style.background = '#0f172a';
    badge.style.color = '#38bdf8';
    badge.style.padding = '8px 16px';
    badge.style.borderRadius = '9999px';
    badge.style.fontSize = '13px';
    badge.style.fontWeight = '600';
    badge.style.boxShadow = '0 10px 25px rgba(0,0,0,0.5), 0 0 0 2px #38bdf8';
    badge.style.zIndex = '2147483647';
    badge.style.cursor = 'pointer';
    badge.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    badge.innerHTML = '🎯 Click any image on page to capture • <span style="color:#94a3b8; font-weight:400;">Esc to cancel</span>';
    document.body.appendChild(badge);

    let currentHovered = null;
    let prevOutline = '';
    let prevOffset = '';
    let prevCursor = '';

    function cleanHover() {
      if (currentHovered) {
        currentHovered.style.outline = prevOutline;
        currentHovered.style.outlineOffset = prevOffset;
        currentHovered.style.cursor = prevCursor;
        currentHovered = null;
      }
    }

    function onOver(e) {
      const el = e.target;
      if (!el || el === badge || host.contains(el)) return;
      let imgEl = el.closest('img') || (el.tagName === 'IMG' ? el : null);
      if (!imgEl && el.tagName === 'PICTURE') {
        imgEl = el.querySelector('img');
      }
      if (!imgEl) {
        try {
          const bg = window.getComputedStyle(el).backgroundImage;
          if (bg && bg.startsWith('url(')) imgEl = el;
        } catch (_) {}
      }
      if (imgEl) {
        cleanHover();
        currentHovered = imgEl;
        prevOutline = imgEl.style.outline;
        prevOffset = imgEl.style.outlineOffset;
        prevCursor = imgEl.style.cursor;
        imgEl.style.outline = '3px solid #38bdf8';
        imgEl.style.outlineOffset = '2px';
        imgEl.style.cursor = 'crosshair';
      }
    }

    function onOut(e) {
      if (currentHovered && (e.target === currentHovered || !currentHovered.contains(e.target))) {
        cleanHover();
      }
    }

    function stopPicker() {
      cleanHover();
      if (badge && badge.parentNode) badge.parentNode.removeChild(badge);
      document.removeEventListener('mouseover', onOver, true);
      document.removeEventListener('mouseout', onOut, true);
      document.removeEventListener('click', onClick, true);
      window.removeEventListener('keydown', onEsc, true);
      if (card) card.style.display = 'block';
      if (backdrop) backdrop.style.display = 'block';
    }

    function onEsc(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        stopPicker();
      }
    }

    function onClick(e) {
      if (badge.contains(e.target)) {
        stopPicker();
        return;
      }
      const el = e.target;
      if (host.contains(el)) return;

      let src = null;
      let alt = '';
      let imgEl = el.closest('img') || (el.tagName === 'IMG' ? el : null);
      if (imgEl) {
        src = imgEl.currentSrc || imgEl.src || imgEl.getAttribute('src');
        alt = imgEl.getAttribute('alt') || imgEl.getAttribute('title') || '';
      } else {
        try {
          const bg = window.getComputedStyle(el).backgroundImage;
          if (bg && bg.startsWith('url(')) {
            src = bg.slice(4, -1).replace(/["']/g, '');
          }
        } catch (_) {}
      }

      if (src) {
        e.preventDefault();
        e.stopPropagation();
        stopPicker();

        // Switch to image kind
        const imgPill = shadow.querySelector('.pill-btn[data-kind="image"]');
        if (imgPill) imgPill.click();

        // Update form inputs
        const inputImg = shadow.getElementById('inputImageSrc');
        if (inputImg) inputImg.value = src;

        const inTitle = shadow.getElementById('inputTitle');
        if (alt && (!inTitle.value || inTitle.value === pageTitle)) {
          inTitle.value = alt;
        }

        // Update preview box
        const pBox = shadow.getElementById('previewBox');
        const pImg = shadow.getElementById('previewImg');
        if (pBox) pBox.style.display = 'flex';
        if (pImg) {
          pImg.src = src;
          pImg.style.display = 'block';
        }
      }
    }

    badge.addEventListener('click', stopPicker);
    document.addEventListener('mouseover', onOver, true);
    document.addEventListener('mouseout', onOut, true);
    document.addEventListener('click', onClick, true);
    window.addEventListener('keydown', onEsc, true);
  }

  const btnPickImage = shadow.getElementById('btnPickImage');
  if (btnPickImage) btnPickImage.addEventListener('click', startImagePicker);
  const btnPickPreview = shadow.getElementById('btnPickPreview');
  if (btnPickPreview) btnPickPreview.addEventListener('click', startImagePicker);

  // Focus tags or quote
  setTimeout(() => {
    if (currentKind === 'quote') {
      shadow.getElementById('inputQuote').focus();
    } else {
      inputTags.focus();
    }
  }, 100);

  // Load collection suggestions
  fetch('http://127.0.0.1:8080/api/collections')
    .then(r => r.json())
    .then(data => {
      if (data && data.collections && Array.isArray(data.collections)) {
        const datalist = shadow.getElementById('collectionSuggestions');
        if (datalist) {
          datalist.innerHTML = data.collections.map(c => `<option value="${escapeHtml(c)}"></option>`).join('');
        }
      }
    })
    .catch(() => {});

  // Check if URL is already in vault (to prefill existing description/tags and allow updating)
  fetch('http://127.0.0.1:8080/api/check?url=' + encodeURIComponent(canonicalUrl))
    .then(r => r.json())
    .then(res => {
      if (res && res.exists && res.atom) {
        const brand = shadow.querySelector('.brand');
        if (brand) {
          brand.innerHTML = '<div class="brand-dot" style="background:#38bdf8; box-shadow:0 0 8px #38bdf8;"></div> WebTack • Existing Atom';
        }
        const btnSave = shadow.getElementById('btnSave');
        if (btnSave) {
          btnSave.textContent = 'Update Atom';
        }
        if (res.atom.description) {
          shadow.getElementById('inputDescription').value = res.atom.description;
        }
        if (res.atom.title) {
          shadow.getElementById('inputTitle').value = res.atom.title;
        }
        if (res.atom.tags && res.atom.tags.length) {
          shadow.getElementById('inputTags').value = res.atom.tags.join(', ');
        }
        if (res.atom.collection) {
          shadow.getElementById('inputCollection').value = res.atom.collection;
        }
        if (res.atom.visibility) {
          shadow.getElementById('selectVisibility').value = res.atom.visibility;
        }
      }
    })
    .catch(() => {});

  // 6. Close Event Handlers
  shadow.getElementById('backdrop').addEventListener('click', closeDrawer);
  shadow.getElementById('closeBtn').addEventListener('click', closeDrawer);
  shadow.getElementById('btnCancel').addEventListener('click', closeDrawer);

  window.addEventListener('keydown', function onKey(e) {
    if (e.key === 'Escape') {
      closeDrawer();
      window.removeEventListener('keydown', onKey);
    }
  });

  // 7. Form Submission to http://127.0.0.1:8080/api/capture
  const form = shadow.getElementById('captureForm');
  const btnSave = shadow.getElementById('btnSave');
  const statusText = shadow.getElementById('statusText');
  const serverWarning = shadow.getElementById('serverWarning');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    serverWarning.style.display = 'none';
    btnSave.disabled = true;
    btnSave.textContent = 'Saving...';
    statusText.className = 'status-text';
    statusText.textContent = 'Writing to vault...';

    const tagsVal = inputTags.value.trim();
    const tags = tagsVal ? tagsVal.split(',').map(t => t.trim().toLowerCase()).filter(Boolean) : [];

    const payload = {
      kind: currentKind,
      title: inputTitle.value.trim() || null,
      collection: shadow.getElementById('inputCollection').value.trim() || null,
      tags: tags,
      description: shadow.getElementById('inputDescription').value.trim() || null,
      visibility: shadow.getElementById('selectVisibility').value,
      author: shadow.getElementById('inputAuthor').value.trim() || null,
      image_url: imageUrl || null
    };

    if (currentKind === 'article' || currentKind === 'bookmark') {
      payload.url = shadow.getElementById('inputUrl').value.trim();
      if (currentKind === 'article') {
        const extractedMd = extractArticleMarkdown();
        if (extractedMd) {
          payload.article_markdown = extractedMd;
        }
      }
    } else if (currentKind === 'video') {
      payload.url = shadow.getElementById('inputUrl').value.trim();
    } else if (currentKind === 'quote') {
      payload.quote = shadow.getElementById('inputQuote').value.trim();
      payload.source = shadow.getElementById('inputUrl').value.trim();
      payload.source_title = pageTitle || null;
    } else if (currentKind === 'note') {
      payload.text = shadow.getElementById('inputNote').value.trim();
    } else if (currentKind === 'image') {
      payload.src = shadow.getElementById('inputImageSrc').value.trim() || imageUrl;
      payload.source = shadow.getElementById('inputUrl').value.trim();
      payload.alt = pageTitle || null;
    }

    try {
      const resp = await fetch('http://127.0.0.1:8080/api/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const res = await resp.json();
      if (res.success && res.atom) {
        statusText.className = 'status-text status-success';
        statusText.textContent = `✨ Saved "${res.atom.title}"!`;
        btnSave.textContent = '✓ Saved';
        setTimeout(() => {
          closeDrawer();
        }, 1200);
      } else {
        throw new Error(res.error || 'Server rejected atom');
      }
    } catch (err) {
      // If direct fetch is blocked by site CSP (e.g. NYTimes connect-src),
      // seamlessly transfer the live tab data to WebTack via postMessage!
      try {
        const win = window.open('http://127.0.0.1:8080/?capture_url=' + encodeURIComponent(payload.url || location.href) + '&capture_title=' + encodeURIComponent(payload.title || document.title) + '&capture_description=' + encodeURIComponent(payload.description || '') + '&capture_collection=' + encodeURIComponent(payload.collection || ''), '_blank');
        if (win) {
          statusText.textContent = 'Transferring to WebTack...';
          const transferPayload = {
            type: 'WEBTACK_DOM_TRANSFER',
            ...payload,
            articleMarkdown: payload.article_markdown
          };
          const timer = setInterval(() => {
            try { win.postMessage(transferPayload, '*'); } catch (_) {}
          }, 400);
          window.addEventListener('message', function h(e) {
            if (e.data && e.data.type === 'WEBTACK_RECEIVED') {
              clearInterval(timer);
              window.removeEventListener('message', h);
              closeDrawer();
            }
          });
          setTimeout(() => clearInterval(timer), 6000);
          return;
        }
      } catch (e) {}

      btnSave.disabled = false;
      btnSave.textContent = 'Save to Vault';
      statusText.className = 'status-text status-error';
      statusText.textContent = 'Connection failed';
      serverWarning.style.display = 'block';
    }
  });
})();
