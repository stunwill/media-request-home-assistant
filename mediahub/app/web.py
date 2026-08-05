from __future__ import annotations


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0b1020">
  <title>MediaHub Setup</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --bg: #080b14;
      --surface: rgba(24, 30, 48, .86);
      --surface-strong: #1b2236;
      --border: rgba(148, 163, 184, .18);
      --text: #f8fafc;
      --muted: #9aa7bd;
      --accent: #8b5cf6;
      --accent-2: #5b8cff;
      --success: #37d487;
      --warning: #f7bd4a;
      --danger: #fb7185;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 15% -5%, rgba(91, 140, 255, .22), transparent 34rem),
        radial-gradient(circle at 100% 10%, rgba(139, 92, 246, .18), transparent 30rem),
        var(--bg);
      color: var(--text);
    }
    button, input { font: inherit; }
    button { cursor: pointer; }
    .shell { max-width: 1160px; margin: 0 auto; padding: 26px 20px 64px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
    .brand { display: flex; align-items: center; gap: 12px; font-weight: 800; letter-spacing: -.02em; }
    .mark {
      display: grid; place-items: center; width: 38px; height: 38px; border-radius: 12px;
      background: linear-gradient(135deg, var(--accent-2), var(--accent));
      box-shadow: 0 12px 36px rgba(91, 140, 255, .28);
    }
    .version { color: var(--muted); font-size: .82rem; }
    .hero { padding: 56px 0 28px; max-width: 760px; }
    .eyebrow { color: #a78bfa; text-transform: uppercase; letter-spacing: .15em; font-size: .75rem; font-weight: 800; }
    h1 { margin: 12px 0; font-size: clamp(2.15rem, 6vw, 4.4rem); line-height: 1; letter-spacing: -.055em; }
    .hero p { margin: 0; color: var(--muted); font-size: 1.06rem; line-height: 1.65; }
    .summary {
      display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 14px; margin: 22px 0 30px;
    }
    .summary-card, .service-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 20px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, .2); backdrop-filter: blur(16px);
    }
    .summary-card { padding: 20px; }
    .summary-card .label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .09em; }
    .summary-card .value { margin-top: 8px; font-weight: 800; font-size: 1.18rem; }
    .progress { height: 7px; background: #101525; border-radius: 99px; overflow: hidden; margin-top: 14px; }
    .progress > span { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--accent-2), var(--accent)); transition: width .3s ease; }
    .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 28px 0 16px; }
    h2 { margin: 0; font-size: 1.35rem; letter-spacing: -.025em; }
    .section-heading p { margin: 5px 0 0; color: var(--muted); font-size: .9rem; }
    .button {
      border: 1px solid var(--border); color: var(--text); background: #20283e; border-radius: 12px;
      padding: 10px 15px; font-weight: 750; transition: transform .15s ease, background .15s ease;
    }
    .button:hover { transform: translateY(-1px); background: #29334f; }
    .button:disabled { cursor: wait; opacity: .62; transform: none; }
    .button.primary { border: 0; background: linear-gradient(135deg, var(--accent-2), var(--accent)); padding: 12px 18px; }
    .services { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .service-card { padding: 20px; }
    .service-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 17px; }
    .service-name { display: flex; align-items: center; gap: 11px; font-size: 1rem; font-weight: 800; }
    .service-icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; background: #252e48; color: #b8c6df; }
    .badge { border-radius: 99px; padding: 5px 9px; font-size: .72rem; font-weight: 800; background: #242c42; color: var(--muted); }
    .badge.connected { background: rgba(55, 212, 135, .12); color: var(--success); }
    .badge.detected { background: rgba(91, 140, 255, .14); color: #8db0ff; }
    .badge.warning { background: rgba(247, 189, 74, .13); color: var(--warning); }
    .badge.error { background: rgba(251, 113, 133, .13); color: var(--danger); }
    .fields { display: grid; gap: 13px; }
    label { display: grid; gap: 7px; color: #c4cede; font-size: .79rem; font-weight: 700; }
    input {
      width: 100%; border: 1px solid var(--border); background: #0e1424; color: var(--text);
      border-radius: 11px; padding: 11px 12px; outline: none;
    }
    input:focus { border-color: rgba(139, 92, 246, .8); box-shadow: 0 0 0 3px rgba(139, 92, 246, .13); }
    input::placeholder { color: #626f87; }
    .hint { color: var(--muted); font-size: .74rem; line-height: 1.45; min-height: 1.1em; }
    .footer-actions {
      position: sticky; bottom: 14px; display: flex; justify-content: space-between; align-items: center; gap: 16px;
      margin-top: 22px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 17px;
      background: rgba(17, 22, 36, .94); box-shadow: 0 18px 55px rgba(0,0,0,.38); backdrop-filter: blur(18px);
    }
    .message { color: var(--muted); font-size: .86rem; }
    .message.success { color: var(--success); }
    .message.error { color: var(--danger); }
    @media (max-width: 760px) {
      .shell { padding: 20px 14px 42px; }
      .hero { padding-top: 42px; }
      .summary { grid-template-columns: 1fr 1fr; }
      .summary-card:first-child { grid-column: 1 / -1; }
      .services { grid-template-columns: 1fr; }
      .section-heading { align-items: flex-start; flex-direction: column; }
      .footer-actions { align-items: stretch; flex-direction: column; }
      .footer-actions .button { width: 100%; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand"><span class="mark">▶</span><span>MediaHub</span></div>
      <span class="version" id="version">0.4.0-dev</span>
    </header>

    <section class="hero">
      <div class="eyebrow">Milestone 1 setup</div>
      <h1>Connect your media stack.</h1>
      <p>MediaHub discovers compatible Home Assistant apps, then validates each connection without exposing credentials to the browser.</p>
    </section>

    <section class="summary" aria-label="Setup summary">
      <article class="summary-card">
        <div class="label">Setup progress</div>
        <div class="value" id="progress-text">Checking services...</div>
        <div class="progress" aria-hidden="true"><span id="progress-bar"></span></div>
      </article>
      <article class="summary-card">
        <div class="label">Apps detected</div>
        <div class="value" id="detected-count">Checking...</div>
      </article>
      <article class="summary-card">
        <div class="label">Connections</div>
        <div class="value" id="connected-count">Checking...</div>
      </article>
    </section>

    <div class="section-heading">
      <div><h2>Service connections</h2><p>Detected addresses are suggested automatically. Add each service's credentials to complete setup.</p></div>
      <button class="button" id="discover-button" type="button">Discover again</button>
    </div>

    <form id="setup-form">
      <section class="services">
        <article class="service-card" data-service="tmdb">
          <div class="service-head"><div class="service-name"><span class="service-icon">TM</span>TMDb</div><span class="badge" data-status>Checking</span></div>
          <div class="fields">
            <label>API key<input id="tmdb_api_key" type="password" autocomplete="new-password" placeholder="Enter TMDb API key"></label>
            <div class="hint" data-hint>Required for posters, metadata and discovery.</div>
          </div>
        </article>

        <article class="service-card" data-service="prowlarr">
          <div class="service-head"><div class="service-name"><span class="service-icon">PR</span>Prowlarr</div><span class="badge" data-status>Checking</span></div>
          <div class="fields">
            <label>Service URL<input id="prowlarr_url" type="url" inputmode="url" placeholder="http://addon-hostname:9696"></label>
            <label>API key<input id="prowlarr_api_key" type="password" autocomplete="new-password" placeholder="Enter Prowlarr API key"></label>
            <div class="hint" data-hint>MediaHub searches indexers only through Prowlarr.</div>
          </div>
        </article>

        <article class="service-card" data-service="radarr">
          <div class="service-head"><div class="service-name"><span class="service-icon">RA</span>Radarr</div><span class="badge" data-status>Checking</span></div>
          <div class="fields">
            <label>Service URL<input id="radarr_url" type="url" inputmode="url" placeholder="http://addon-hostname:7878"></label>
            <label>API key<input id="radarr_api_key" type="password" autocomplete="new-password" placeholder="Enter Radarr API key"></label>
            <div class="hint" data-hint>Handles movie requests and library imports.</div>
          </div>
        </article>

        <article class="service-card" data-service="sonarr">
          <div class="service-head"><div class="service-name"><span class="service-icon">SO</span>Sonarr</div><span class="badge" data-status>Checking</span></div>
          <div class="fields">
            <label>Service URL<input id="sonarr_url" type="url" inputmode="url" placeholder="http://addon-hostname:8989"></label>
            <label>API key<input id="sonarr_api_key" type="password" autocomplete="new-password" placeholder="Enter Sonarr API key"></label>
            <div class="hint" data-hint>Handles television requests and episode monitoring.</div>
          </div>
        </article>

        <article class="service-card" data-service="qbittorrent">
          <div class="service-head"><div class="service-name"><span class="service-icon">QB</span>qBittorrent</div><span class="badge" data-status>Checking</span></div>
          <div class="fields">
            <label>Service URL<input id="qbittorrent_url" type="url" inputmode="url" placeholder="http://addon-hostname:8080"></label>
            <label>Username<input id="qbittorrent_username" autocomplete="username" placeholder="qBittorrent username"></label>
            <label>Password<input id="qbittorrent_password" type="password" autocomplete="new-password" placeholder="Enter qBittorrent password"></label>
            <div class="hint" data-hint>Reports download progress and manages MediaHub transfers.</div>
          </div>
        </article>
      </section>

      <div class="footer-actions">
        <div class="message" id="message" role="status">Credentials are stored only in MediaHub's private data directory.</div>
        <button class="button primary" id="save-button" type="submit">Save and test connections</button>
      </div>
    </form>
  </main>

  <script>
    const services = ['tmdb', 'prowlarr', 'radarr', 'sonarr', 'qbittorrent'];
    const secretFields = ['tmdb_api_key', 'prowlarr_api_key', 'radarr_api_key', 'sonarr_api_key', 'qbittorrent_password'];
    let latest = null;

    function endpoint(path) { return `api/${path}`; }

    async function request(path, options = {}) {
      const response = await fetch(endpoint(path), options);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Request failed');
      return body;
    }

    function statusLabel(status) {
      return ({connected: 'Connected', not_configured: 'Needs details', authentication_failed: 'Check credentials', unavailable: 'Unavailable', invalid_response: 'Invalid response'})[status] || 'Not configured';
    }

    function render(data) {
      latest = data;
      document.getElementById('version').textContent = data.version;
      const discovery = data.discovery.services || [];
      const connections = data.connections.services || [];
      const detected = discovery.filter(item => item.detected).length;
      const connected = connections.filter(item => item.status === 'connected').length;
      document.getElementById('detected-count').textContent = data.discovery.available ? `${detected} of 4` : 'Unavailable';
      document.getElementById('connected-count').textContent = `${connected} of 5`;
      document.getElementById('progress-text').textContent = connected === 5 ? 'Setup complete' : `${connected} of 5 services ready`;
      document.getElementById('progress-bar').style.width = `${connected * 20}%`;

      services.forEach(name => {
        const card = document.querySelector(`[data-service="${name}"]`);
        const badge = card.querySelector('[data-status]');
        const hint = card.querySelector('[data-hint]');
        const connection = connections.find(item => item.name === name) || {};
        const found = discovery.find(item => item.name === name);
        badge.textContent = statusLabel(connection.status);
        badge.className = `badge ${connection.status === 'connected' ? 'connected' : connection.status === 'authentication_failed' ? 'error' : found?.detected ? 'detected' : connection.status === 'unavailable' ? 'warning' : ''}`;
        if (connection.message) hint.textContent = connection.message;

        const settings = data.settings[name] || {};
        if (name !== 'tmdb') {
          const url = document.getElementById(`${name}_url`);
          if (!url.value) url.value = settings.url || found?.suggested_url || '';
        }
        if (name === 'qbittorrent' && !document.getElementById('qbittorrent_username').value) {
          document.getElementById('qbittorrent_username').value = settings.username || '';
        }

        const secretState = name === 'qbittorrent' ? settings.password_set : settings.api_key_set;
        const secretId = name === 'tmdb' ? 'tmdb_api_key' : name === 'qbittorrent' ? 'qbittorrent_password' : `${name}_api_key`;
        if (secretState && !document.getElementById(secretId).value) {
          document.getElementById(secretId).placeholder = 'Saved, enter a new value to replace';
        }
      });
    }

    async function loadSetup(button) {
      if (button) button.disabled = true;
      setMessage('Discovering Home Assistant apps and testing connections...');
      try {
        render(await request('setup'));
        setMessage(latest.discovery.available ? 'Discovery complete. Review the suggested addresses before saving.' : latest.discovery.message);
      } catch (error) {
        setMessage(error.message, 'error');
      } finally {
        if (button) button.disabled = false;
      }
    }

    function setMessage(text, kind = '') {
      const message = document.getElementById('message');
      message.textContent = text;
      message.className = `message ${kind}`;
    }

    document.getElementById('discover-button').addEventListener('click', event => loadSetup(event.currentTarget));
    document.getElementById('setup-form').addEventListener('submit', async event => {
      event.preventDefault();
      const button = document.getElementById('save-button');
      button.disabled = true;
      setMessage('Saving securely and testing all connections...');
      const updates = {};
      ['prowlarr_url', 'radarr_url', 'sonarr_url', 'qbittorrent_url', 'qbittorrent_username'].forEach(id => {
        updates[id] = document.getElementById(id).value;
      });
      secretFields.forEach(id => {
        const value = document.getElementById(id).value;
        if (value) updates[id] = value;
      });
      try {
        const data = await request('setup/integrations', {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({updates, clear_secrets: []}),
        });
        secretFields.forEach(id => { document.getElementById(id).value = ''; });
        render(data);
        setMessage(data.connections.connected === 5 ? 'All services saved and connected.' : 'Settings saved. Review any services that are not connected yet.', data.connections.connected ? 'success' : '');
      } catch (error) {
        setMessage(error.message, 'error');
      } finally {
        button.disabled = false;
      }
    });

    loadSetup();
  </script>
</body>
</html>
"""
