/* NovaDL — Web UI (vanilla SPA, no build step) */
(function () {
  const root = document.getElementById('root');
  const state = { info: null, selected: null, downloading: false };

  function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, pts = [];
    function resize() { w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight; }
    resize(); window.addEventListener('resize', resize);
    const N = Math.min(60, Math.floor(w / 26));
    for (let i = 0; i < N; i++) {
      pts.push({
        x: Math.random() * w, y: Math.random() * h,
        r: Math.random() * 1.7 + 0.4,
        vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
        hue: Math.random() < 0.5 ? 340 : 30,
      });
    }
    function frame() {
      ctx.clearRect(0, 0, w, h);
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 90%, 65%, 0.5)`; ctx.fill();
      }
      requestAnimationFrame(frame);
    }
    frame();
  }

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function api(path, opts = {}) {
    try {
      const res = await fetch(path, opts);
      let data; try { data = await res.json(); } catch { data = {}; }
      return data;
    } catch { return { ok: false, error: 'Network error' }; }
  }

  function toast(msg, err = false) {
    const t = document.createElement('div');
    t.className = 'toast' + (err ? ' err' : '');
    t.textContent = msg; document.body.appendChild(t);
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, 3200);
  }

  function header() {
    return `
      <header>
        <div class="brand">
          <div class="mark">🎬</div>
          <div>
            <h1>Nova<span>DL</span></h1>
            <div class="tag">All-in-One Video Downloader</div>
          </div>
        </div>
        <div class="status-pill"><span class="dot"></span> <span id="verLabel">yt-dlp …</span></div>
      </header>`;
  }

  function hero() {
    return `
      <section class="hero">
        <h2>Download any video, <span class="grad">in seconds</span></h2>
        <p>Paste a link from YouTube, Instagram, TikTok, X, Facebook & more — pick a quality and save it. No ads, no limits.</p>
      </section>`;
  }

  function searchCard() {
    return `
      <div class="card">
        <div class="search-row">
          <input id="url" placeholder="Paste a video URL…  https://" />
          <button class="btn" id="go">🔍 Fetch</button>
        </div>
        <div class="sites">
          <span>YouTube</span><span>Instagram</span><span>TikTok</span><span>X</span><span>Facebook</span><span>Vimeo</span><span>and more…</span>
        </div>
        <div id="searchMsg"></div>
      </div>`;
  }

  function resultCard() {
    if (!state.info) return '';
    const i = state.info;
    const dur = i.duration ? `${Math.floor(i.duration/60)}:${String(i.duration%60).padStart(2,'0')}` : '';
    const meta = [dur && `⏱ ${dur}`, i.uploader && `👤 ${esc(i.uploader)}`].filter(Boolean).join(' · ');
    const qbtns = (i.formats || []).map((f, idx) => {
      const label = f.kind === 'audio' ? `🎵 ${esc(f.label)}` : `▶️ ${esc(f.label)}`;
      const active = state.selected === idx ? ' active' : '';
      return `<button class="q-btn${active}" data-q="${idx}">${label}</button>`;
    }).join('');
    return `
      <div class="card" style="animation-delay:.05s">
        <div class="result">
          ${(i.thumbnail && i.thumbnail.startsWith('http')) ? `<img class="thumb" src="${esc(i.thumbnail)}" alt="thumbnail" />` : ''}
          <div class="result-info">
            <h3>${esc(i.title)}</h3>
            <div class="meta">${meta}</div>
            <div class="quality-grid">${qbtns}</div>
          </div>
        </div>
        <div class="download-bar">
          <button class="btn download-btn" id="download" disabled>⬇️ Select a quality</button>
          <div class="progress" id="prog"><i id="progBar"></i></div>
        </div>
      </div>`;
  }

  function render() {
    root.innerHTML = `
      <div class="container">
        ${header()}
        ${hero()}
        ${searchCard()}
        ${resultCard()}
        <div class="footer">Built with <span class="heart">♥</span> by <b>NovaDL</b></div>
      </div>`;

    const go = document.getElementById('go');
    const urlInput = document.getElementById('url');
    if (go) go.onclick = () => fetchInfo(urlInput.value);
    if (urlInput) urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchInfo(urlInput.value); });

    document.querySelectorAll('.q-btn').forEach((b) => {
      b.onclick = () => {
        state.selected = parseInt(b.dataset.q, 10);
        document.querySelectorAll('.q-btn').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
        const dl = document.getElementById('download');
        dl.disabled = false;
        dl.textContent = '⬇️ Download';
      };
    });

    const dl = document.getElementById('download');
    if (dl) dl.onclick = () => doDownload();

    loadStatus();
  }

  async function loadStatus() {
    const r = await api('/api/status');
    const label = document.getElementById('verLabel');
    if (label && r.ytdlp_version) label.textContent = 'yt-dlp ' + r.ytdlp_version;
  }

  async function fetchInfo(url) {
    if (!url || !/^https?:\/\//.test(url.trim())) {
      toast('⚠️ Enter a valid http(s) URL', true);
      return;
    }
    const go = document.getElementById('go');
    const msg = document.getElementById('searchMsg');
    if (go) { go.disabled = true; go.textContent = '⏳ Fetching…'; }
    if (msg) msg.innerHTML = '';

    const r = await api('/api/info?url=' + encodeURIComponent(url.trim()));
    if (go) { go.disabled = false; go.textContent = '🔍 Fetch'; }

    if (!r.ok) {
      toast('❌ ' + (r.error || 'Failed to fetch'), true);
      if (msg) msg.innerHTML = `<p class="meta" style="margin-top:14px;color:var(--danger)">${esc(r.error || '')}</p>`;
      return;
    }
    state.info = r;
    state.selected = null;
    render();
  }

  async function doDownload() {
    if (state.downloading) return;
    if (state.selected == null) { toast('⚠️ Pick a quality first', true); return; }
    const f = state.info.formats[state.selected];
    const url = state.info.webpage_url || document.getElementById('url').value;

    const dl = document.getElementById('download');
    const prog = document.getElementById('prog');
    const bar = document.getElementById('progBar');

    state.downloading = true;
    if (dl) { dl.disabled = true; dl.textContent = '⬇️ Downloading…'; }
    if (prog) prog.classList.add('active');

    let pct = 0;
    const sim = setInterval(() => {
      pct = Math.min(pct + Math.random() * 12, 92);
      if (bar) bar.style.width = pct + '%';
    }, 400);

    const r = await api('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, format_id: f.format_id, kind: f.kind }),
    });

    clearInterval(sim);
    if (bar) bar.style.width = '100%';

    if (r.ok && r.job_id) {
      toast('✅ Ready! Starting download…');
      window.location.href = '/api/file/' + r.job_id;
    } else {
      toast('❌ ' + (r.error || 'Download failed'), true);
    }

    setTimeout(() => {
      state.downloading = false;
      if (dl) { dl.disabled = false; dl.textContent = '⬇️ Download'; }
      if (prog) prog.classList.remove('active');
      if (bar) bar.style.width = '0';
    }, 1200);
  }

  initParticles();
  render();
})();
