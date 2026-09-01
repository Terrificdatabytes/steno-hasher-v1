const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];

let IDENTITY = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? {} : {'Content-Type': 'application/json'},
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && data.error) || res.statusText);
  return data;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
function fmtDate(iso) { return iso ? new Date(iso).toLocaleString() : '—'; }
function badge(status) {
  const map = {pending:'badge-pending', approved:'badge-approved', rejected:'badge-rejected'};
  return `<span class="badge ${map[status]||''}">${status}</span>`;
}

// ---------------- identity ----------------

async function loadIdentity() {
  IDENTITY = await api('/api/identity');
  renderIdentityBar();
  if (!IDENTITY) {
    $('#identity-gate').classList.remove('hidden');
  } else {
    $('#identity-gate').classList.add('hidden');
    initTabs();
  }
}

function renderIdentityBar() {
  const bar = $('#identity-bar');
  if (!IDENTITY) { bar.innerHTML = ''; return; }
  bar.innerHTML = `
    <div class="flex items-center gap-3">
      <div class="text-right">
        <div class="text-bone font-medium">${escapeHtml(IDENTITY.name)} <span class="text-muted">· ${escapeHtml(IDENTITY.org)}</span></div>
        <div class="text-[11px] uppercase tracking-widest text-amber">${IDENTITY.role}</div>
      </div>
      <button id="switch-identity" class="btn-ghost">Switch</button>
    </div>`;
  $('#switch-identity').onclick = () => $('#identity-gate').classList.remove('hidden');
}

$('#identity-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  try {
    await api('/api/identity', {method: 'POST', body: JSON.stringify(body)});
    await loadIdentity();
  } catch (err) { alert(err.message); }
});

// ---------------- tabs ----------------

function initTabs() {
  $$('.tab-btn').forEach(btn => btn.onclick = () => setActiveTab(btn.dataset.tab));
  setActiveTab(localStorage.getItem('activeTab') || (IDENTITY.role === 'requester' ? 'requester' : 'validator'));
}

function setActiveTab(name) {
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach(p => p.classList.toggle('hidden', p.id !== `tab-${name}`));
  localStorage.setItem('activeTab', name);
  if (name === 'validator') loadValidatorTab();
  if (name === 'requester') loadRequesterTab();
}

// ---------------- validator ----------------

$('#register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const msg = $('#register-msg');
  msg.textContent = 'Uploading & sealing genesis block…';
  msg.className = 'text-sm mt-3 text-muted';
  try {
    await api('/api/files', {method: 'POST', body: fd});
    msg.textContent = 'File protected. Genesis block created.';
    msg.className = 'text-sm mt-3 text-teal';
    e.target.reset();
    loadValidatorTab();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'text-sm mt-3 text-rose';
  }
});

async function loadValidatorTab() {
  if (!IDENTITY || IDENTITY.role !== 'validator') {
    $('#my-files-list').innerHTML = `<p class="text-sm text-muted">Switch to a Validator identity to manage protected files.</p>`;
    $('#incoming-list').innerHTML = '';
    return;
  }
  const [files, incoming] = await Promise.all([api('/api/files/mine'), api('/api/requests/incoming')]);
  renderMyFiles(files);
  renderIncoming(incoming);
}

function renderMyFiles(files) {
  const el = $('#my-files-list');
  if (!files.length) { el.innerHTML = `<p class="text-sm text-muted">No files registered yet.</p>`; return; }
  el.innerHTML = files.map(f => `
    <div class="list-item flex items-center justify-between gap-3">
      <div>
        <div class="font-medium">${escapeHtml(f.filename)}</div>
        <div class="hash">${f.sha256.slice(0,24)}…</div>
        <div class="text-[11px] text-muted mt-1">Registered ${fmtDate(f.created_at)}</div>
      </div>
      <button class="btn-ghost" data-view-chain="${f.file_id}">View Chain</button>
    </div>`).join('');
  $$('[data-view-chain]', el).forEach(btn => btn.onclick = () => viewChain(btn.dataset.viewChain));
}

async function viewChain(fileId) {
  const data = await api(`/api/files/${fileId}/chain`);
  $('#chain-view').classList.remove('hidden');
  $('#chain-content').innerHTML = `
    <div class="mb-3 text-sm text-muted">File: <span class="text-bone">${escapeHtml(data.file.filename)}</span> · Integrity: ${data.valid ? '<span class="text-teal">valid</span>' : '<span class="text-rose">BROKEN</span>'}</div>
    <div class="timeline">${data.chain.map(b => renderBlock(b)).join('')}</div>`;
  $('#chain-view').scrollIntoView({behavior:'smooth', block:'nearest'});
}

function renderBlock(b, highlightId = null) {
  const isGenesis = b.index === 0;
  const cls = isGenesis ? 'genesis' : (highlightId && b.data.watermark_id === highlightId ? 'highlight' : '');
  let body;
  if (isGenesis) {
    const o = b.data.owner;
    body = `<div class="text-sm">Registered by <span class="font-medium">${escapeHtml(o.name)}</span> (${escapeHtml(o.org)})</div>
            <div class="text-[11px] text-muted">${escapeHtml(o.email)} · ${escapeHtml(o.phone||'—')}</div>`;
  } else {
    const h = b.data.holder;
    body = `<div class="text-sm">Approved to <span class="font-medium">${escapeHtml(h.name)}</span> (${escapeHtml(h.org)})</div>
            <div class="text-[11px] text-muted">${escapeHtml(h.email)} · ${escapeHtml(h.phone||'—')}</div>
            <div class="hash mt-1">watermark: ${b.data.watermark_id}</div>`;
  }
  return `
    <div class="timeline-node ${cls}">
      <div class="text-[11px] uppercase tracking-widest text-muted mb-1">Block #${b.index} · ${b.data.event}</div>
      ${body}
      <div class="text-[11px] text-muted mt-1">${fmtDate(b.timestamp)}</div>
      <div class="hash mt-1">${b.block_hash}</div>
    </div>`;
}

function renderIncoming(reqs) {
  const el = $('#incoming-list');
  if (!reqs.length) { el.innerHTML = `<p class="text-sm text-muted">No requests yet.</p>`; return; }
  el.innerHTML = reqs.map(r => `
    <div class="list-item">
      <div class="flex items-center justify-between">
        <div class="font-medium">${escapeHtml(r.filename)}</div>
        ${badge(r.status)}
      </div>
      <div class="text-[11px] text-muted mt-1">${escapeHtml(r.requester.name)} · ${escapeHtml(r.requester.org)} · ${escapeHtml(r.requester.email)}</div>
      <div class="text-[11px] text-muted">${fmtDate(r.created_at)}</div>
      ${r.status === 'pending' ? `
        <div class="flex gap-2 mt-3">
          <button class="btn-primary" data-approve="${r.request_id}">Approve</button>
          <button class="btn-danger" data-reject="${r.request_id}">Reject</button>
        </div>` : ''}
    </div>`).join('');
  $$('[data-approve]', el).forEach(btn => btn.onclick = async () => {
    btn.disabled = true; btn.textContent = 'Approving…';
    try { await api(`/api/requests/${btn.dataset.approve}/approve`, {method:'POST'}); loadValidatorTab(); }
    catch (err) { alert(err.message); btn.disabled = false; btn.textContent = 'Approve'; }
  });
  $$('[data-reject]', el).forEach(btn => btn.onclick = async () => {
    if (!confirm('Reject this request?')) return;
    try { await api(`/api/requests/${btn.dataset.reject}/reject`, {method:'POST', body: JSON.stringify({})}); loadValidatorTab(); }
    catch (err) { alert(err.message); }
  });
}

// ---------------- requester ----------------

async function loadRequesterTab() {
  const files = await api('/api/files');
  renderBrowse(files);
  if (IDENTITY && IDENTITY.role === 'requester') {
    renderMyRequests(await api('/api/requests/mine'));
  } else {
    $('#my-requests-list').innerHTML = `<p class="text-sm text-muted">Switch to a Requester identity to submit and track requests.</p>`;
  }
}

function renderBrowse(files) {
  const el = $('#browse-list');
  if (!files.length) { el.innerHTML = `<p class="text-sm text-muted">No protected files registered yet.</p>`; return; }
  el.innerHTML = files.map(f => `
    <div class="list-item flex items-center justify-between gap-3">
      <div>
        <div class="font-medium">${escapeHtml(f.filename)}</div>
        <div class="text-[11px] text-muted">Owner: ${escapeHtml(f.owner_org)} · ${fmtDate(f.created_at)}</div>
      </div>
      <button class="btn-ghost" data-request="${f.file_id}">Request Access</button>
    </div>`).join('');
  $$('[data-request]', el).forEach(btn => btn.onclick = async () => {
    if (!IDENTITY || IDENTITY.role !== 'requester') { alert('Switch to a Requester identity first.'); return; }
    btn.disabled = true; btn.textContent = 'Requesting…';
    try {
      await api('/api/requests', {method:'POST', body: JSON.stringify({file_id: btn.dataset.request})});
      btn.textContent = 'Requested';
      loadRequesterTab();
    } catch (err) { alert(err.message); btn.disabled = false; btn.textContent = 'Request Access'; }
  });
}

function renderMyRequests(reqs) {
  const el = $('#my-requests-list');
  if (!reqs.length) { el.innerHTML = `<p class="text-sm text-muted">You haven't requested anything yet.</p>`; return; }
  el.innerHTML = reqs.map(r => `
    <div class="list-item">
      <div class="flex items-center justify-between">
        <div class="font-medium">${escapeHtml(r.filename)}</div>
        ${badge(r.status)}
      </div>
      <div class="text-[11px] text-muted mt-1">Requested ${fmtDate(r.created_at)}</div>
      ${r.note ? `<div class="text-[11px] text-rose mt-1">Note: ${escapeHtml(r.note)}</div>` : ''}
      ${r.status === 'approved' ? `<a class="btn-primary inline-block mt-3" href="/api/requests/${r.request_id}/download">Download Watermarked Copy</a>` : ''}
    </div>`).join('');
}

// ---------------- scan ----------------

$('#scan-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const el = $('#scan-result');
  el.innerHTML = `<p class="text-sm text-muted">Scanning…</p>`;
  try {
    const res = await fetch('/api/scan', {method:'POST', body: fd});
    const data = await res.json();
    renderScanResult(data);
  } catch (err) {
    el.innerHTML = `<p class="text-sm text-rose">${err.message}</p>`;
  }
});

function renderScanResult(data) {
  const el = $('#scan-result');
  if (!data.matched) {
    el.innerHTML = `
      <div class="panel-card">
        <h3 class="section-title text-rose">No Match</h3>
        <p class="text-sm text-muted">${escapeHtml(data.message)}</p>
        ${data.payload ? `<div class="hash mt-2">${data.payload}</div>` : ''}
      </div>`;
    return;
  }
  const holder = data.last_holder;
  el.innerHTML = `
    <div class="panel-card mb-6">
      <h3 class="section-title text-teal">Match Found</h3>
      <div class="text-sm mb-3">File: <span class="font-medium">${escapeHtml(data.file.filename)}</span> · Owner: ${escapeHtml(data.file.owner_org)}</div>
      <div class="list-item">
        <div class="text-[11px] uppercase tracking-widest text-amber mb-2">Last Confirmed Holder of This Exact Copy</div>
        <div class="text-lg font-serif">${escapeHtml(holder.name)}</div>
        <div class="text-sm text-muted">${escapeHtml(holder.org)}</div>
        <div class="text-sm text-muted">${escapeHtml(holder.email)} · ${escapeHtml(holder.phone||'—')}</div>
        <div class="text-[11px] text-muted mt-2">Issued at ${fmtDate(data.held_at)}</div>
      </div>
    </div>
    <div class="panel-card">
      <h3 class="section-title">Full Custody Chain</h3>
      <div class="timeline">${data.chain.map(b => renderBlock(b, data.matched_watermark_id)).join('')}</div>
    </div>`;
}

// ---------------- boot ----------------

loadIdentity();
