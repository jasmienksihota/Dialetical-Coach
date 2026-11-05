/* Source-Grounded Tutor — vanilla JS. All untrusted text is inserted with textContent (via h()). */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'hidden') el[k] = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.json !== undefined) {
    o.body = JSON.stringify(o.json);
    o.headers['Content-Type'] = 'application/json';
    o.method = o.method || 'POST';
    delete o.json;
  }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch (e) { /* not json */ }
  if (!r.ok) {
    let d = data && data.detail;
    if (Array.isArray(d)) d = d.map(x => x.msg).join('; ');
    throw new Error(d || `Request failed (${r.status})`);
  }
  return data;
}

let toastTimer = null;
function toast(msg, ok = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = ok ? 'okay' : '';
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ok ? 3500 : 9000);
}
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message); } };

const state = { status: null, docs: [], convs: [], current: null };

const TYPE_LABEL = {
  quote: 'Direct quotation', interpretation: 'Interpretation',
  synthesis: 'Synthesis across texts', fiction: 'Fictional exercise material',
  coaching: 'Coaching (app/tutor instructions)', limits: 'What the library does not establish',
  withheld: 'Withheld',
};
const PURPOSE_LABEL = {
  source_basis: 'source basis', objective: 'objective', scenario: 'scenario', question: 'question',
  feedback: 'feedback', complication: 'new fact', hint: 'hint', clarification: 'clarification',
  analysis: 'analysis', reflection: 'reflection', next_steps: 'next steps', limits: 'limitation',
};
const PHASE_LABEL = {
  attempt: 'Waiting for your first attempt', probe: 'Waiting for your answer to the follow-up',
  revision: 'Waiting for your revision', review: 'Review — revise again or finish',
  paused: 'Paused', done: 'Finished',
};

/* ------------------------------------------------------------------ navigation */
function show(view) {
  for (const b of document.querySelectorAll('#nav button')) b.classList.toggle('active', b.dataset.view === view);
  for (const s of document.querySelectorAll('main > section')) s.hidden = s.id !== `view-${view}`;
  if (view === 'library') loadDocs();
  if (view === 'search') renderSearchScope();
  if (view === 'sessions') loadConvs();
}
$('#nav').addEventListener('click', e => { const b = e.target.closest('button'); if (b) show(b.dataset.view); });

/* ------------------------------------------------------------------ modal */
const modal = $('#modal');
// replaceChildren() stringifies null/undefined/false; drop them first.
function put(el, ...nodes) { el.replaceChildren(...nodes.filter(n => n !== null && n !== undefined && n !== false)); }
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
let modalReturnFocus = null;
function openModal(...nodes) {
  const b = $('#modal-body'); put(b, ...nodes);
  modalReturnFocus = document.activeElement;
  const dlg = modal.querySelector('[role=dialog]');
  const title = b.querySelector('h2');
  if (title) { title.id = 'modal-title'; dlg.setAttribute('aria-labelledby', 'modal-title'); dlg.removeAttribute('aria-label'); }
  else { dlg.removeAttribute('aria-labelledby'); dlg.setAttribute('aria-label', 'Passage view'); }
  modal.hidden = false;
  $('#modal-close').focus();
}
function closeModal() {
  modal.hidden = true;
  if (modalReturnFocus && document.contains(modalReturnFocus)) modalReturnFocus.focus();
  modalReturnFocus = null;
}
document.addEventListener('keydown', e => {
  if (modal.hidden) return;
  if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
  if (e.key !== 'Tab') return;
  const items = [...modal.querySelectorAll(FOCUSABLE)].filter(x => x.offsetParent !== null);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (!modal.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});
$('#modal-close').addEventListener('click', closeModal);
modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

/* ------------------------------------------------------------------ helpers */
const shortLoc = loc => (loc || '').includes(' > ') ? '§ ' + loc.split(' > ').pop() : (loc || '');
function tagBoxes(selected = [], name = 'tag') {
  return state.status.tags.map(t => h('label', {},
    h('input', { type: 'checkbox', name, value: t.slug, checked: selected.includes(t.slug) }), t.label));
}
const checkedValues = (root, name) => [...root.querySelectorAll(`input[name="${name}"]:checked`)].map(i => i.value);

function scopePicker(initial = {}) {
  const docs = state.docs.filter(d => d.approved);
  const root = h('div', { class: 'scope-picker' },
    h('p', { class: 'small muted' }, 'Rule: UNION. A document is included if you check it OR it has ANY checked tag. Nothing checked = all approved primary documents. The list below shows exactly what your choice resolves to.'),
    h('strong', { class: 'small' }, 'Documents (approved only)'),
    h('div', { class: 'taglist' }, docs.length ? docs.map(d => h('label', {},
      h('input', { type: 'checkbox', name: 'doc', value: d.id, checked: (initial.doc_ids || []).includes(d.id) }),
      d.title + (d.kind === 'secondary_notes' ? ' (secondary notes)' : ''))) : h('span', { class: 'muted small' }, 'No approved documents yet.')),
    h('strong', { class: 'small' }, 'Topic tags'),
    h('div', { class: 'taglist' }, tagBoxes(initial.tags || [], 'tag')),
    h('label', { class: 'check' }, h('input', { type: 'checkbox', name: 'sec', checked: !!initial.include_secondary }),
      'Include secondary study notes (not primary sources)'));
  root.value = () => ({ doc_ids: checkedValues(root, 'doc'), tags: checkedValues(root, 'tag'),
                        include_secondary: !!root.querySelector('input[name="sec"]').checked });
  const preview = h('div', { class: 'scope-preview notice ok small', 'aria-live': 'polite' }, 'Resolving…');
  root.append(preview);
  let timer = null;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(guard(async () => renderScopeResolution(preview, await api('/api/scope/resolve', { json: root.value() }))), 120);
  };
  root.addEventListener('change', refresh);
  refresh();
  return root;
}

function renderScopeResolution(el, r) {
  const items = r.included.map(d => h('li', {}, `${d.title}${d.kind === 'secondary_notes' ? ' (secondary notes)' : ''} — ${d.reasons.join(' + ')}`));
  const out = r.excluded.map(d => h('li', { class: 'muted' }, `${d.title}: NOT included (${d.why_excluded})`));
  el.className = 'scope-preview notice small ' + (r.included.length ? 'ok' : 'warn');
  put(el, 
    h('strong', {}, `Resolves to ${r.included.length} document(s)`),
    r.included.length ? h('ul', {}, items) : h('div', {}, 'No eligible documents: nothing can be retrieved with this selection. It will NOT fall back to all documents.'),
    out.length ? h('div', { class: 'small' }, 'Selected but not eligible:', h('ul', {}, out)) : null,
    h('div', { class: 'tiny' }, r.semantics));
}

function describeScope(scope) {
  const parts = [];
  if (scope.doc_ids && scope.doc_ids.length) {
    parts.push('documents: ' + scope.doc_ids.map(id => (state.docs.find(d => d.id === id) || { title: id }).title).join('; '));
  }
  if (scope.tags && scope.tags.length) {
    parts.push('tags: ' + scope.tags.map(s => (state.status.tags.find(t => t.slug === s) || { label: s }).label).join('; '));
  }
  if (!parts.length) parts.push('all approved documents');
  if (scope.include_secondary) parts.push('including secondary study notes');
  return parts.join(' | ');
}

/* ------------------------------------------------------------------ status */
async function loadStatus() {
  state.status = await api('/api/status');
  const s = state.status;
  const chip = $('#status-chip');
  const u = s.live_usage;
  const STAGE = {
    none: 'Live configured · API not yet reached',
    api_reachable: 'Live: API reachable — structured output not yet seen',
    structured_output: 'Live: structured output seen — citation checks not yet passed',
    citation_checks_passed: u.last_citation_checks_passed ? `Live: citation checks passed (${u.last_citation_checks_passed.slice(0, 10)}; mechanical only)` : 'Live: citation checks passed (mechanical only)',
  };
  chip.textContent = !s.live_configured ? 'Demo mode only — live not configured'
    : `${STAGE[u.stage]} · ${u.requests_today}/${u.cap_per_day} requests today`;
  chip.title = `Model: ${s.model || 'not set'}. Tokens reported today: ${u.input_tokens_today} in / ${u.output_tokens_today} out. `
    + '"Citation checks passed" means one reply parsed and every citation passed the app\'s mechanical checks (passage supplied, document approved and in scope, quotation present). '
    + 'It does not measure tutoring quality or whether the passages support the claims. An API success alone does not count. ' + u.note;
  chip.className = 'chip ' + (s.live_configured ? 'live' : 'demo');
  $('#retrieval-note').textContent = `Retrieval: ${s.retrieval_mode}. ${s.retrieval_note}`;
  put($('#up-tags'), ...tagBoxes([], 'uptag'));
}

/* ------------------------------------------------------------------ library */
async function loadDocs() {
  state.docs = await api('/api/documents');
  renderDocs();
}

function docMeta(d) {
  const bits = [d.author && `by ${d.author}`, d.date, d.edition].filter(Boolean);
  return bits.length ? bits.join(' · ') : 'Author/date/edition: not recorded';
}

function renderDocs() {
  const list = $('#doc-list');
  $('#lib-count').textContent = `(${state.docs.length} documents, ${state.docs.filter(d => d.approved).length} approved)`;
  if (!state.docs.length) { put(list, h('div', { class: 'empty' }, h('span', { class: 'star', 'aria-hidden': 'true' }), h('p', { class: 'muted' }, 'No documents yet. Import a file, or load the synthetic demo documents.'))); return; }
  put(list, ...state.docs.map(docCard));
}

function docCard(d) {
  const statusBadge = d.status === 'ok' ? h('span', { class: 'badge ok' }, 'text extracted')
    : d.status === 'warning' ? h('span', { class: 'badge warn' }, 'extracted with warnings')
    : h('span', { class: 'badge bad' }, 'no text extracted');
  const edit = h('details', {}, h('summary', {}, 'Edit metadata & tags'));
  const f = {
    title: h('input', { type: 'text', value: d.title }), author: h('input', { type: 'text', value: d.author || '' }),
    date: h('input', { type: 'text', value: d.date || '' }), edition: h('input', { type: 'text', value: d.edition || '' }),
    off: h('input', { type: 'number', value: d.printed_page_offset === null ? '' : d.printed_page_offset, placeholder: 'e.g. -4' }),
    kind: h('select', {}, h('option', { value: 'primary', selected: d.kind === 'primary' }, 'Primary source'),
      h('option', { value: 'secondary_notes', selected: d.kind === 'secondary_notes' }, 'Secondary study notes')),
  };
  const tagsBox = h('div', { class: 'taglist' }, tagBoxes(d.tags, 'dtag'));
  edit.append(h('div', { class: 'grid' },
    h('label', {}, 'Title', f.title), h('label', {}, 'Author', f.author), h('label', {}, 'Date', f.date),
    h('label', {}, 'Edition / translation', f.edition), h('label', {}, 'Kind', f.kind),
    d.file_type === 'pdf' ? h('label', {}, 'Printed page = PDF page + offset (leave empty if unknown)', f.off) : null),
    h('strong', { class: 'small' }, 'Topic tags'), tagsBox,
    h('button', { class: 'save-meta', onclick: guard(async () => {
      await api(`/api/documents/${d.id}`, { method: 'PATCH', json: {
        title: f.title.value, author: f.author.value, date: f.date.value, edition: f.edition.value,
        kind: f.kind.value, printed_page_offset: f.off.value, tags: checkedValues(tagsBox, 'dtag') } });
      toast('Saved', true); loadDocs();
    }) }, 'Save'));
  return h('div', { class: 'card doc-card', dataset: { id: d.id } },
    h('h3', {}, d.title),
    h('div', {}, h('span', { class: 'badge ' + (d.approved ? 'ok' : 'warn') }, d.approved ? 'approved' : 'unapproved'),
      statusBadge, h('span', { class: 'badge' }, d.file_type.toUpperCase()),
      d.kind === 'secondary_notes' ? h('span', { class: 'badge warn' }, 'secondary study notes') : null,
      d.tags.map(t => h('span', { class: 'tagchip' }, (state.status.tags.find(x => x.slug === t) || { label: t }).label))),
    h('div', { class: 'small muted' }, docMeta(d)),
    h('div', { class: 'small muted' }, `${d.original_filename} · ${d.chunk_count} passages` + (d.page_count ? ` · ${d.page_count} PDF pages` : '') + ` · id ${d.id}`),
    d.warnings.map(w => h('div', { class: 'notice warn' }, w)),
    h('div', { class: 'actions' },
      h('button', { class: 'primary approve-btn', disabled: !d.approved && d.chunk_count === 0, onclick: guard(async () => {
        await api(`/api/documents/${d.id}/approval`, { json: { approved: !d.approved } });
        toast(d.approved ? 'Unapproved' : 'Approved', true); loadDocs(); loadStatus();
      }) }, d.approved ? 'Unapprove' : 'Approve for use'),
      h('button', { class: 'view-btn', disabled: d.chunk_count === 0, onclick: guard(() => viewDocument(d.id)) }, 'View extracted text'),
      h('button', { onclick: guard(async () => {
        if (!confirm(`Remove “${d.title}” from the library? Saved sessions keep their quoted evidence.`)) return;
        await api(`/api/documents/${d.id}`, { method: 'DELETE' }); loadDocs(); loadStatus();
      }) }, 'Remove')),
    edit);
}

async function viewDocument(id, offset = 0, focus = null) {
  const r = await api(`/api/documents/${id}/chunks?offset=${offset}&limit=30`);
  const d = r.document;
  const body = h('div', {},
    h('h2', {}, d.title), h('div', { class: 'small muted' }, docMeta(d)),
    d.file_type === 'pdf' ? h('div', { class: 'small muted' }, 'Locations are physical PDF pages. Printed page numbers are not guessed' + (d.printed_page_offset === null ? ' (unknown for this file).' : ` (offset ${d.printed_page_offset} set by you).`)) : null,
    ...r.chunks.map(c => h('div', { class: 'chunk' }, h('div', { class: 'loc' }, `${c.location} · ${c.id}`),
      h('div', { class: 'body' }, c.text))),
    offset + r.chunks.length < r.total ? h('button', { onclick: guard(() => viewDocument(id, offset + 30)) }, 'Next passages…') : null);
  openModal(body);
}

$('#upload-form').addEventListener('submit', guard(async e => {
  e.preventDefault();
  const file = $('#file-input').files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('title', $('#up-title').value); fd.append('author', $('#up-author').value);
  fd.append('date', $('#up-date').value); fd.append('edition', $('#up-edition').value);
  fd.append('kind', $('#up-secondary').checked ? 'secondary_notes' : 'primary');
  fd.append('tags', checkedValues($('#up-tags'), 'uptag').join(','));
  $('#upload-btn').disabled = true;
  try {
    const r = await api('/api/documents', { method: 'POST', body: fd });
    const msg = $('#upload-msg');
    msg.textContent = r.duplicate ? `Already in the library (exact duplicate of “${r.document.title}”). Nothing was added.`
      : `Imported “${r.document.title}” — unapproved. Review it below, then approve it.`;
    $('#upload-form').reset();
    await loadDocs(); loadStatus();
  } finally { $('#upload-btn').disabled = false; }
}));

$('#fixtures-btn').addEventListener('click', guard(async () => {
  const r = await api('/api/demo/fixtures', { method: 'POST' });
  $('#upload-msg').textContent = r.message;
  await loadDocs(); loadStatus();
}));

/* ------------------------------------------------------------------ passage inspector */
async function openPassage(id) {
  const r = await api(`/api/passages/${id}?context=2`);
  const p = r.passage, d = r.document;
  const nodes = r.neighbours.map(n => n.id === p.id
    ? h('div', { class: 'target passage-text', dataset: { id: n.id } }, n.text)
    : h('div', { class: 'ctx' }, `[${n.location}]\n${n.text}`));
  openModal(
    h('h2', {}, d.title),
    h('div', { class: 'small muted' }, docMeta(d) + ` · file ${d.original_filename}`),
    h('div', {}, h('span', { class: 'badge' }, p.location), h('span', { class: 'badge' }, `passage ${p.id}`),
      d.kind === 'secondary_notes' ? h('span', { class: 'badge warn' }, 'secondary study notes — not a primary source') : h('span', { class: 'badge ok' }, 'primary source'),
      h('span', { class: 'badge ' + (d.approved ? 'ok' : 'bad') }, d.approved ? 'approved' : 'NOT approved')),
    d.file_type === 'pdf' ? h('p', { class: 'tiny' }, 'Physical PDF page shown. A printed page number appears only if you set an offset for this document.') : h('p', { class: 'tiny' }, 'Line numbers refer to the lines of the paragraph(s) this passage was built from.'),
    h('p', { class: 'tiny' }, 'Highlighted = the cited passage. Greyed text is neighbouring context.'),
    ...nodes,
    h('div', { class: 'actions' }, h('button', { onclick: guard(() => viewDocument(d.id, Math.max(0, p.ordinal - 3))) }, 'Open in document view')));
}

/* ------------------------------------------------------------------ search */
function renderSearchScope() {
  put($('#search-scope'), scopePicker({}));
  if (!state.docs.length) loadDocs().then(() => put($('#search-scope'), scopePicker({})));
}
$('#search-form').addEventListener('submit', guard(async e => {
  e.preventDefault();
  const sc = $('#search-scope .scope-picker').value();
  const q = new URLSearchParams({ q: $('#search-q').value, doc_ids: sc.doc_ids.join(','), tags: sc.tags.join(','),
                                   include_secondary: sc.include_secondary, limit: 10 });
  const r = await api('/api/search?' + q);
  const out = $('#search-results');
  const head = h('p', { class: 'muted small' }, `${r.hits.length} passage(s) · evidence: ${r.strength} · ${r.distinct_docs} document(s) with relevant passages · terms: ${r.terms.join(', ') || '—'}`);
  const notes = r.notes.map(n => h('div', { class: 'notice warn' }, n));
  put(out, head, ...notes, ...r.hits.map(hit => h('div', { class: 'hit' },
    h('div', { class: 'meta' }, `${hit.doc_title} · ${hit.location} · term coverage ${Math.round(hit.coverage * 100)}%`),
    h('div', { class: 'body' }, hit.text.length > 420 ? hit.text.slice(0, 420) + '…' : hit.text),
    h('div', { class: 'actions' }, h('button', { class: 'inspect-btn', onclick: guard(() => openPassage(hit.id)) }, 'Inspect passage')))));
}));

/* ------------------------------------------------------------------ sessions */
async function loadConvs() {
  if (!state.docs.length) state.docs = await api('/api/documents');
  state.convs = await api('/api/conversations');
  const list = $('#conv-list');
  put(list, ...state.convs.map(c => h('button', { class: 'conv' + (state.current && state.current.id === c.id ? ' active' : ''),
    onclick: guard(() => openConversation(c.id)) },
    h('span', { class: 't' }, c.title),
    h('span', { class: 'tiny' }, `${c.mode} · ${c.provider === 'demo' ? 'demo' : 'live'} · ${c.message_count} msgs`))));
  if (!state.convs.length) put(list, h('div', { class: 'empty' }, h('span', { class: 'star', 'aria-hidden': 'true' }), h('p', { class: 'muted small' }, 'No saved sessions yet.')));
}

async function openConversation(id) {
  $('#new-panel').hidden = true;
  state.current = await api(`/api/conversations/${id}`);
  renderConversation();
  loadConvs();
}

function providerPicker() {
  const live = state.status.live_configured;
  const root = h('div', {},
    h('label', { class: 'check' }, h('input', { type: 'radio', name: 'prov', value: 'demo', checked: true }),
      'Demo — "Demo: scripted responses, not live tutoring." (offline, nothing leaves your machine)'),
    h('label', { class: 'check' }, h('input', { type: 'radio', name: 'prov', value: 'live', disabled: !live }),
      `Live model (${state.status.model || 'model not set'}) — sends the selected passages and conversation context to Anthropic using your API key. Limits: ${state.status.live_limits.max_requests_per_day} requests/day, ${state.status.live_limits.max_output_tokens} output tokens/request. These are not a dollar cap.`),
    live ? null : h('div', { class: 'notice warn small' }, state.status.live_setup_message));
  root.value = () => root.querySelector('input[name="prov"]:checked').value;
  return root;
}

function confirmLive(provider) {
  return provider !== 'live' || confirm('Live mode sends the selected passages and this conversation to Anthropic using your own API key, and uses your API balance. Continue?');
}

$('#new-chat-btn').addEventListener('click', () => {
  const panel = $('#new-panel');
  const title = h('input', { type: 'text', id: 'nc-title', placeholder: 'Session title (optional)' });
  const scope = scopePicker({}), prov = providerPicker();
  put(panel, h('h2', {}, 'New study chat'), h('label', {}, 'Title', title), h('h3', {}, 'Source scope'), scope,
    h('h3', {}, 'Tutor'), prov,
    h('button', { class: 'primary', id: 'nc-start', onclick: guard(async () => {
      if (!confirmLive(prov.value())) return;
      const c = await api('/api/conversations', { json: { title: title.value, provider: prov.value(), acknowledge_live: prov.value() === 'live', scope: scope.value() } });
      await openConversation(c.id);
    }) }, 'Start chat'));
  panel.hidden = false;
});

$('#new-exercise-btn').addEventListener('click', () => {
  const panel = $('#new-panel');
  const sel = (id, opts) => h('select', { id }, opts.map(([v, l]) => h('option', { value: v }, l)));
  const mode = sel('ex-mode', state.status.modes.map(m => [m.key, m.title]));
  const level = sel('ex-level', state.status.levels.map(l => [l, l]));
  const kind = sel('ex-kind', [['fictional', 'Fictional, non-political scenario (default)'], ['historical', 'Historical case (only if documented in the library)']]);
  const focus = h('input', { type: 'text', id: 'ex-focus', placeholder: 'optional: a term that appears in your texts' });
  const topic = h('input', { type: 'text', id: 'ex-topic', placeholder: 'case to look for in the selected library' });
  const topicRow = h('label', { hidden: true }, 'Historical case topic', topic);
  kind.addEventListener('change', () => { topicRow.hidden = kind.value !== 'historical'; });
  const multi = h('input', { type: 'checkbox', id: 'ex-multi', checked: true });
  const scope = scopePicker({}), prov = providerPicker();
  const msg = h('div', { id: 'ex-msg' });
  const start = async (allowSingle = false) => {
    if (!confirmLive(prov.value())) return;
    const r = await api('/api/exercises', { json: { mode: mode.value, level: level.value, scenario_kind: kind.value,
      multi_source: multi.checked, focus: focus.value, historical_topic: topic.value, provider: prov.value(), acknowledge_live: prov.value() === 'live',
      scope: scope.value(), allow_single_source: allowSingle } });
    if (r.status === 'blocked') { put(msg, h('div', { class: 'notice bad' }, r.message)); return; }
    if (r.status === 'needs_confirmation') {
      put(msg, h('div', { class: 'notice warn' }, r.message),
        h('button', { id: 'ex-single', onclick: guard(() => start(true)) }, 'Continue with a single-source exercise'));
      return;
    }
    state.current = r.conversation; $('#new-panel').hidden = true; renderConversation(); loadConvs();
  };
  put(panel, h('h2', {}, 'New exercise'),
    h('p', { class: 'small muted' }, 'The tutor asks one question at a time and waits for you. The rubric is an app-created learning aid, not a canonical standard; feedback is qualitative.'),
    h('div', { class: 'grid' }, h('label', {}, 'Mode', mode), h('label', {}, 'Level', level), h('label', {}, 'Scenario', kind),
      h('label', {}, 'Focus (optional)', focus), topicRow,
      h('label', { class: 'check' }, multi, 'Require sources from at least two documents (otherwise I will tell you and offer single-source)')),
    h('h3', {}, 'Source scope'), scope, h('h3', {}, 'Tutor'), prov, msg,
    h('button', { class: 'primary', id: 'ex-start', onclick: guard(() => start(false)) }, 'Start exercise'));
  panel.hidden = false;
});

/* ------------------------------------------------------------------ conversation rendering */
function citationChips(msg, block, bi) {
  const chips = (block.citations || []).map(c => h('button', {
    class: 'cite-chip' + (c.doc_kind === 'secondary_notes' ? ' sec' : ''), title: `${c.doc_title} — ${c.location}\nPassage ${c.passage_id}` + (c.quote ? '\nQuoted text found in passage ✓' : ''),
    onclick: guard(() => openPassage(c.passage_id)) }, `${c.doc_title} · ${shortLoc(c.location)}`));
  if (!chips.length) return null;
  const flagged = (msg.flags || []).filter(f => f.block_index === bi);
  return h('div', { class: 'cites' }, chips,
    h('button', { class: 'flag-btn', title: 'Mark this reading as unsupported by the passage', onclick: guard(async () => {
      const note = prompt('Why do you think the passage does not support this? (optional)');
      if (note === null) return;
      await api(`/api/messages/${msg.id}/flags`, { json: { block_index: bi, chunk_id: block.citations[0].passage_id, note } });
      toast('Flagged for review (included in the export)', true); openConversation(state.current.id);
    }) }, flagged.length ? `⚑ Flagged (${flagged.length})` : '⚑ Flag as unsupported'),
    h('span', { class: 'tiny' }, 'Mechanical check passed (passage supplied, approved, in scope' + (block.citations.some(c => c.quote) ? ', quote present' : '') + '). Whether it supports the claim is for you to judge.'));
}

function renderBlock(msg, block, bi) {
  if (block.type === 'withheld') {
    return h('div', { class: 'block withheld' }, h('div', { class: 'lbl' }, 'Withheld'), h('div', { class: 'body' }, block.reason));
  }
  const purpose = block.purpose && PURPOSE_LABEL[block.purpose];
  return h('div', { class: `block ${block.type}` + (block.purpose === 'question' ? ' question' : ''), dataset: { type: block.type, purpose: block.purpose || '' } },
    h('div', { class: 'lbl', title: block.status === 'uncited' ? 'No sources cited. The app only pattern-checks such blocks for obvious claims about what the sources say; it can miss paraphrase.' : null },
      TYPE_LABEL[block.type] || block.type, purpose ? ` · ${purpose}` : '', block.app ? ' · app-authored' : '',
      block.status === 'uncited' && !block.app ? ' · no sources cited' : ''),
    h('div', { class: 'body' }, block.text), citationChips(msg, block, bi));
}

function renderMessage(msg) {
  if (msg.role === 'user') {
    return h('div', { class: 'msg user' }, h('div', { class: 'who' }, 'You'), h('div', { class: 'body' }, msg.text));
  }
  const ev = msg.evidence || [];
  const cited = ev.filter(e => e.cited).length;
  const rep = msg.report || {};
  const titleOf = id => (state.docs.find(d => d.id === id) || { title: id }).title;
  const evidence = ev.length ? h('details', { class: 'evidence' },
    h('summary', {}, `Evidence supplied for this turn: ${ev.length} passage(s), ${cited} cited`),
    rep.retrieval ? h('div', { class: 'tiny' }, 'Search used: ' + rep.retrieval.query
      + (rep.retrieval.followup ? ' — short follow-up: the earlier question was added to the search (still inside your scope).' : '')
      + (rep.retrieval.seeks_new ? ' Passages already used last turn were excluded.' : '')) : null,
    rep.scope ? h('div', { class: 'tiny' }, 'Documents in scope this turn: ' + (rep.scope.doc_ids.map(titleOf).join('; ') || 'none')) : null,
    ...ev.map(e => h('div', { class: 'hit' }, h('div', { class: 'meta' }, `${e.doc_title} · ${e.location} · ${e.cited ? 'cited' : 'not cited'}` + (e.doc_kind === 'secondary_notes' ? ' · secondary notes' : '')),
      h('div', { class: 'body' }, e.text.length > 300 ? e.text.slice(0, 300) + '…' : e.text),
      h('button', { class: 'link', onclick: guard(() => openPassage(e.id)) }, 'Inspect')))) : null;
  const repaired = msg.report && msg.report.repair_attempted;
  return h('div', { class: 'msg assistant' },
    h('div', { class: 'who' }, 'Tutor · ' + (msg.provider_label || '')),
    ...(msg.blocks || []).map((b, i) => renderBlock(msg, b, i)),
    repaired ? h('div', { class: 'tiny' }, 'Some citations failed validation; one automatic repair was attempted. Anything still unverifiable is withheld above.') : null,
    evidence);
}

function renderConversation() {
  const c = state.current;
  const view = $('#conv-view');
  if (!c) return;
  const banner = c.provider === 'demo'
    ? h('div', { class: 'banner demo' }, state.status.demo_label)
    : h('div', { class: 'banner live' }, 'Live model: selected passages and conversation context are sent to Anthropic.');
  const scopeLine = h('div', { class: 'small muted', id: 'scope-line' }, 'Source scope (in force for the whole session): ' + describeScope(c.scope));
  const scopeBox = h('div', { class: 'scope-preview notice small ok', id: 'scope-resolved' }, 'Resolving…');
  const scopeDetails = h('details', { id: 'scope-details' }, h('summary', {}, 'Documents in scope right now'), scopeBox);
  api('/api/scope/resolve', { json: c.scope }).then(r => {
    renderScopeResolution(scopeBox, r);
    scopeDetails.querySelector('summary').textContent = `Documents in scope right now: ${r.included.length}`;
  }).catch(() => {});
  const header = h('div', { class: 'row wrap' },
    h('h2', { id: 'conv-title' }, c.title),
    h('button', { onclick: guard(async () => {
      const t = prompt('Rename session', c.title); if (!t) return;
      await api(`/api/conversations/${c.id}`, { method: 'PATCH', json: { title: t } }); openConversation(c.id);
    }) }, 'Rename'),
    h('a', { id: 'export-btn', class: 'btn', href: `/api/conversations/${c.id}/export.md`, download: '' }, h('button', { type: 'button' }, 'Export Markdown')),
    h('a', { href: `/api/conversations/${c.id}/export.md?transcript=true`, download: '' }, h('button', { type: 'button' }, 'Export with transcript')),
    h('button', { onclick: guard(async () => {
      if (!confirm('Delete this saved session?')) return;
      await api(`/api/conversations/${c.id}`, { method: 'DELETE' }); state.current = null;
      put($('#conv-view'), h('p', { class: 'muted' }, 'Session deleted.')); loadConvs();
    }) }, 'Delete'));
  const handoff = h('div', { class: 'tiny' }, 'Export is a manual handoff for NotebookLM or another notes tool — a one-time Markdown snapshot, not synchronization.');
  const summary = c.summary ? h('details', {}, h('summary', {}, 'Earlier turns condensed (app-generated)'), h('div', { class: 'ctx' }, c.summary), h('div', { class: 'tiny' }, c.summary_note)) : null;
  const thread = h('div', { class: 'thread', id: 'thread' }, ...c.messages.map(renderMessage));
  put(view, ...[header, banner, scopeLine, scopeDetails, handoff, summary, thread,
    c.mode === 'exercise' ? exercisePanel(c) : chatComposer(c)].filter(Boolean));
  const last = thread.lastElementChild;
  if (last) last.scrollIntoView({ block: 'nearest' });
}

function chatComposer(c) {
  const ta = h('textarea', { id: 'chat-input', placeholder: 'Ask about the selected texts…' });
  const intent = h('select', { id: 'chat-intent' },
    [['ask', 'Ask'], ['explain', 'Explain a passage'], ['compare', 'Compare across texts'], ['challenge', 'Challenge my interpretation'], ['disagreements', 'Find disagreements & limits']]
      .map(([v, l]) => h('option', { value: v }, l)));
  const send = h('button', { class: 'primary', id: 'chat-send' }, 'Send');
  send.addEventListener('click', guard(async () => {
    const text = ta.value.trim(); if (!text) return;
    send.disabled = true; send.textContent = 'Thinking…';
    try {
      await api(`/api/conversations/${c.id}/messages`, { json: { text, intent: intent.value } });
      await openConversation(c.id);
      loadStatus();
    } finally { send.disabled = false; send.textContent = 'Send'; }
  }));
  return h('div', { class: 'panel' }, ta, h('div', { class: 'row wrap actions' }, intent, send,
    h('span', { class: 'tiny' }, 'To practise, use “New exercise”.')));
}

function exercisePanel(c) {
  const ex = c.exercise;
  const acts = ex.available_actions;
  const ta = h('textarea', { id: 'answer-text', placeholder: ex.phase === 'revision' || ex.phase === 'review' ? 'Your revision…' : 'Your answer…', disabled: !acts.includes('answer') });
  const run = (action, extra = {}) => guard(async () => {
    let r = await api(`/api/conversations/${c.id}/exercise`, { json: { action, text: extra.text ?? ta.value, confirm: !!extra.confirm } });
    if (r.status === 'needs_confirmation') {
      if (!confirm(r.message)) return;
      r = await api(`/api/conversations/${c.id}/exercise`, { json: { action, text: '', confirm: true } });
    }
    state.current = r.conversation; renderConversation(); loadConvs(); loadStatus();
  });
  const btn = (id, label, action, cls = '') => acts.includes(action) ? h('button', { id, class: cls, onclick: run(action) }, label) : null;
  const clarifyBox = h('div', { hidden: true, class: 'row' }, h('input', { type: 'text', id: 'clarify-text', placeholder: 'Ask a clarifying question about the scenario' }),
    h('button', { id: 'clarify-send', onclick: guard(async () => { const t = $('#clarify-text').value; await run('clarify', { text: t })(); }) }, 'Ask'));
  const q = ex.current_question;
  return h('div', { class: 'ex-panel', id: 'ex-panel' },
    h('div', { class: 'phase', id: 'ex-phase' }, `${ex.mode_title} · ${ex.level} · ${PHASE_LABEL[ex.phase] || ex.phase}`),
    ex.limitation ? h('div', { class: 'notice warn' }, ex.limitation) : null,
    q && ex.phase !== 'done' ? h('div', { class: 'small' }, h('strong', {}, 'Current question: '), q) : null,
    acts.includes('answer') ? ta : null,
    h('div', { class: 'actions' },
      btn('submit-answer', ex.phase === 'revision' || ex.phase === 'review' ? 'Submit revision' : 'Submit answer', 'answer', 'primary'),
      btn('hint-btn', 'Hint', 'hint'),
      acts.includes('clarify') ? h('button', { id: 'clarify-btn', onclick: () => { clarifyBox.hidden = !clarifyBox.hidden; } }, 'Ask a clarifying question') : null,
      btn('pause-btn', 'Pause', 'pause'), btn('resume-btn', 'Resume', 'resume', 'primary'),
      btn('analysis-btn', 'Show analysis', 'show_analysis'),
      btn('finish-btn', 'Finish & reflect', 'finish')),
    clarifyBox,
    h('div', { class: 'tiny' }, ex.rubric_note + ' Rubric dimensions: ' + ex.rubric.map(r => r.label).join('; ') + '.'));
}

/* ------------------------------------------------------------------ boot */
guard(async () => {
  await loadStatus();
  await loadDocs();
})();
