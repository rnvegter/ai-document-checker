import { analyze, summarizeForPrompt } from "./heuristics.js";
import { createHistory, titleFor } from "./history.js";

const $ = (id) => document.getElementById(id);
const checks = createHistory(safeLocalStorage());
const state = { id: null, heur: null, claude: null };

const VERDICTS = {
  likely_human: "Likely human-written",
  mixed: "Mixed: partly AI-assisted",
  likely_ai: "Likely AI-generated",
  uncertain: "Uncertain",
};

function safeLocalStorage() {
  try {
    const s = window.localStorage;
    s.getItem("x");
    return s;
  } catch {
    return null;
  }
}

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const colorFor = (pct) => (pct < 35 ? "var(--low)" : pct < 65 ? "var(--mid)" : "var(--high)");
const formatDate = (ms) =>
  new Date(ms).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

function setGauge(el, pct) {
  el.style.setProperty("--pct", pct);
  el.style.setProperty("--col", colorFor(pct));
}

// ---------- Checker view ----------

// Locate a quote from Claude in the text, tolerating whitespace and quote-mark drift.
function findQuote(text, quote) {
  const q = quote.trim();
  if (!q) return null;
  const exact = text.indexOf(q);
  if (exact >= 0) return { start: exact, end: exact + q.length };
  const pattern = q
    .split(/\s+/)
    .map((w) => escapeRegex(w).replace(/["'“”‘’„]/g, "[\"'“”‘’„]"))
    .join("\\s+");
  const m = new RegExp(pattern, "i").exec(text);
  return m ? { start: m.index, end: m.index + m[0].length } : null;
}

function claudeSpans(text) {
  if (!state.claude) return [];
  const spans = [];
  const add = (item, kind, idx) => {
    const loc = findQuote(text, item.quote || "");
    item._found = !!loc;
    if (loc) spans.push({ ...loc, kind, idx, tip: kind === "passage" ? item.reason : item.issue });
  };
  state.claude.passages.forEach((p, i) => add(p, "passage", i));
  state.claude.feedback.forEach((f, i) => add(f, "feedback", i));
  spans.sort((a, b) => a.start - b.start || b.end - a.end);
  const out = [];
  let lastEnd = -1;
  for (const s of spans) if (s.start >= lastEnd) (out.push(s), (lastEnd = s.end));
  return out;
}

function renderRegion(text, start, end, spans) {
  let html = "";
  let pos = start;
  for (const s of spans) {
    const a = Math.max(s.start, start);
    const b = Math.min(s.end, end);
    if (b <= a || a < pos) continue;
    html += escapeHtml(text.slice(pos, a));
    html += `<mark class="m-${s.type}" data-label="${escapeHtml(s.label)}" data-tip="${escapeHtml(s.tip)}">${escapeHtml(text.slice(a, b))}</mark>`;
    pos = b;
  }
  return html + escapeHtml(text.slice(pos, end));
}

function renderView() {
  const text = $("input").value;
  const heurSpans = state.heur ? state.heur.spans : [];
  let html = "";
  let pos = 0;
  for (const c of claudeSpans(text)) {
    html += renderRegion(text, pos, c.start, heurSpans);
    const label = c.kind === "passage" ? "Flagged by Claude" : "Writing feedback";
    html += `<mark class="m-claude" id="c-${c.kind}-${c.idx}" data-label="${label}" data-tip="${escapeHtml(c.tip)}">${renderRegion(text, c.start, c.end, heurSpans)}</mark>`;
    pos = c.end;
  }
  html += renderRegion(text, pos, text.length, heurSpans);
  $("view").innerHTML = html;
  showView(true);
}

function showView(on) {
  $("view").hidden = !on;
  $("input").hidden = on;
  $("legend").hidden = !on;
  $("edit").hidden = !on;
}

function renderHeuristics() {
  const r = state.heur;
  $("empty").hidden = true;
  $("heur").hidden = false;
  $("heurScore").textContent = r.score;
  setGauge($("heurGauge"), r.score);
  const level = r.score < 25 ? "Few AI patterns" : r.score < 50 ? "Some AI patterns" : r.score < 70 ? "Many AI patterns" : "Strong AI patterns";
  $("heurVerdict").textContent = `${level} · ${r.confidence} confidence`;
  $("signals").innerHTML = r.signals
    .map((s) => {
      const pct = s.score === null ? 0 : Math.round(s.score * 100);
      return `<li><div class="row"><span>${escapeHtml(s.name)}</span><span>${s.score === null ? "–" : pct}</span></div>
        <div class="bar"><i style="width:${pct}%;--col:${colorFor(pct)}"></i></div>
        <div class="detail">${escapeHtml(s.detail)}</div></li>`;
    })
    .join("");
  const lang = r.language === "nl" ? "Dutch" : "English";
  $("stats").textContent = `${r.words} words · ${r.sentences} sentences · ${lang} · ${r.spans.length} highlights`;
}

function renderClaude() {
  const c = state.claude;
  $("claude").hidden = !c;
  if (!c) return;
  $("claudeScore").textContent = c.ai_likelihood;
  setGauge($("claudeGauge"), c.ai_likelihood);
  $("claudeVerdict").textContent = VERDICTS[c.verdict] || c.verdict;
  $("claudeSummary").textContent = c.summary;
  $("strengths").innerHTML = c.strengths.length
    ? `<h3>What reads as human</h3><ul>${c.strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
    : "";
  $("claudeModel").textContent = `Reviewed by ${c.model}`;

  $("passages").innerHTML =
    c.passages
      .map(
        (p, i) => `<li>
        <blockquote data-target="c-passage-${i}">${escapeHtml(p.quote)}</blockquote>
        <div>${escapeHtml(p.reason)}</div>
        <blockquote class="rewrite">${escapeHtml(p.rewrite)}</blockquote>
        <div class="actions">${
          p._found
            ? `<button class="btn ghost" data-apply="passage" data-idx="${i}">Apply rewrite</button>`
            : `<span class="notfound">${p._applied ? "Applied" : "Not found in current text"}</span>`
        }</div></li>`,
      )
      .join("") || "<li class='muted'>No passages flagged.</li>";

  $("feedback").innerHTML =
    c.feedback
      .map(
        (f, i) => `<li><span class="tag">${escapeHtml(f.category)}</span>
        ${f.quote ? `<blockquote data-target="c-feedback-${i}">${escapeHtml(f.quote)}</blockquote>` : ""}
        <div>${escapeHtml(f.issue)}</div>
        <div><b>Suggestion:</b> ${escapeHtml(f.suggestion)}</div></li>`,
      )
      .join("") || "<li class='muted'>No feedback.</li>";
}

function runHeuristics({ save = true } = {}) {
  const text = $("input").value;
  if (!text.trim()) return false;
  state.heur = analyze(text, $("lang").value);
  renderHeuristics();
  renderView();
  renderClaude();
  if (save) saveCurrent();
  return true;
}

function showError(msg) {
  $("error").hidden = !msg;
  $("error").textContent = msg || "";
}

function saveCurrent() {
  const text = $("input").value;
  const entry = checks.save({
    id: state.id,
    title: $("title").value.trim() || titleFor(text),
    text,
    lang: $("lang").value,
    language: state.heur.language,
    words: state.heur.words,
    heurScore: state.heur.score,
    claude: state.claude,
  });
  state.id = entry.id;
  $("title").placeholder = entry.title;
  $("savedNote").textContent = `Saved ${formatDate(entry.updated)}`;
  if (location.hash !== `#/check/${entry.id}`) replaceHash(`#/check/${entry.id}`);
  renderNav();
}

// Update the URL without triggering the router.
function replaceHash(hash) {
  window.history.replaceState(null, "", hash);
}

function resetChecker() {
  state.id = null;
  state.heur = null;
  state.claude = null;
  $("input").value = "";
  $("title").value = "";
  $("title").placeholder = "Untitled document";
  $("savedNote").textContent = "";
  $("lang").value = "auto";
  $("stats").textContent = "";
  $("empty").hidden = false;
  $("heur").hidden = true;
  $("claude").hidden = true;
  showError("");
  showView(false);
}

function loadEntry(id) {
  if (state.id === id) return true;
  const entry = checks.get(id);
  if (!entry) return false;
  resetChecker();
  state.id = entry.id;
  state.claude = entry.claude || null;
  $("input").value = entry.text;
  $("lang").value = entry.lang || "auto";
  $("title").value = entry.title;
  $("savedNote").textContent = `Saved ${formatDate(entry.updated)}`;
  runHeuristics({ save: false });
  return true;
}

async function deepCheck() {
  if (!runHeuristics({ save: false })) return;
  showError("");
  const btn = $("deep");
  btn.disabled = true;
  btn.textContent = "Claude is reading…";
  try {
    const res = await fetch("api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("input").value, heuristics: summarizeForPrompt(state.heur) }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    state.claude = data;
    renderView();
    renderClaude();
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = !serverHasClaude;
    btn.textContent = "Deep check with Claude";
    if (state.heur) saveCurrent();
  }
}

function applyRewrite(idx) {
  const p = state.claude.passages[idx];
  const text = $("input").value;
  const loc = findQuote(text, p.quote);
  if (!loc) return;
  $("input").value = text.slice(0, loc.start) + p.rewrite + text.slice(loc.end);
  p._applied = true;
  runHeuristics();
}

async function upload(file) {
  showError("");
  try {
    let text;
    if (/\.(txt|md|markdown)$/i.test(file.name)) {
      text = await file.text();
    } else {
      const res = await fetch("api/extract", { method: "POST", headers: { "X-Filename": file.name }, body: file });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
      text = data.text;
    }
    resetChecker();
    $("input").value = text;
    $("title").value = file.name.replace(/\.[^.]+$/, "");
    runHeuristics();
  } catch (e) {
    showError(`Could not read ${file.name}: ${e.message}`);
  }
}

// ---------- History view ----------

function badge(score, label) {
  return `<span class="badge" style="--col:${colorFor(score)}">${score}<small>${label}</small></span>`;
}

function renderHistory() {
  const q = $("historySearch").value.trim().toLowerCase();
  const all = checks.list();
  const items = q ? all.filter((e) => `${e.title}\n${e.text}`.toLowerCase().includes(q)) : all;
  $("historyEmpty").hidden = all.length > 0;
  $("historyList").innerHTML = items
    .map((e) => {
      const lang = e.language === "nl" ? "Dutch" : "English";
      const snippet = e.text.replace(/\s+/g, " ").slice(0, 160);
      return `<li>
        ${badge(e.heurScore, "instant")}
        ${e.claude ? badge(e.claude.ai_likelihood, "Claude") : ""}
        <div class="info" data-open="${e.id}">
          <b>${escapeHtml(e.title)}</b>
          <span>${formatDate(e.updated)} · ${e.words} words · ${lang}</span>
          <span class="snippet">${escapeHtml(snippet)}</span>
        </div>
        <button class="icon-btn" data-delete="${e.id}" title="Delete" aria-label="Delete">✕</button>
      </li>`;
    })
    .join("");
  if (all.length && !items.length) $("historyList").innerHTML = `<li class="muted">Nothing matches “${escapeHtml(q)}”.</li>`;
}

function exportHistory() {
  const blob = new Blob([checks.exportJson()], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ai-checker-history-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- Navigation ----------

function renderNav(route = currentRoute()) {
  const all = checks.list();
  $("historyCount").textContent = all.length || "";
  $("recent").innerHTML = all
    .slice(0, 6)
    .map((e) => `<li><a href="#/check/${e.id}" class="${state.id === e.id && route === "check" ? "active" : ""}"><span>${escapeHtml(e.title)}</span></a></li>`)
    .join("");
  document.querySelectorAll("[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
}

const currentRoute = () => (location.hash.split("/")[1] || "check");

function route() {
  const [, page = "check", id] = location.hash.split("/");
  if (page === "new") {
    resetChecker();
    replaceHash("#/check");
    return show("check");
  }
  if (page === "check" && id && !loadEntry(id)) {
    replaceHash("#/check");
  }
  show(["check", "history", "about"].includes(page) ? page : "check");
}

function show(page) {
  for (const p of ["check", "history", "about"]) $(`view-${p}`).hidden = p !== page;
  if (page === "history") renderHistory();
  renderNav(page);
  $("sidebar").classList.remove("open");
  $("menuToggle").setAttribute("aria-expanded", "false");
  window.scrollTo(0, 0);
}

// ---------- Events ----------

$("check").addEventListener("click", () => runHeuristics());
$("deep").addEventListener("click", deepCheck);
$("edit").addEventListener("click", () => showView(false));
$("lang").addEventListener("change", () => state.heur && runHeuristics());
$("file").addEventListener("change", (e) => {
  if (e.target.files[0]) upload(e.target.files[0]);
  e.target.value = "";
});
$("title").addEventListener("change", () => state.heur && saveCurrent());
$("historySearch").addEventListener("input", renderHistory);
$("historyExport").addEventListener("click", exportHistory);
$("historyClear").addEventListener("click", () => {
  if (!confirm("Delete all saved checks from this browser?")) return;
  checks.clear();
  state.id = null;
  renderHistory();
  renderNav();
});
$("menuToggle").addEventListener("click", () => {
  const open = $("sidebar").classList.toggle("open");
  $("menuToggle").setAttribute("aria-expanded", String(open));
});
window.addEventListener("hashchange", route);

document.addEventListener("click", (e) => {
  const apply = e.target.closest("[data-apply]");
  if (apply) return applyRewrite(Number(apply.dataset.idx));
  const open = e.target.closest("[data-open]");
  if (open) return (location.hash = `#/check/${open.dataset.open}`);
  const del = e.target.closest("[data-delete]");
  if (del) {
    checks.remove(del.dataset.delete);
    if (state.id === del.dataset.delete) state.id = null;
    renderHistory();
    return renderNav();
  }
  const quote = e.target.closest("blockquote[data-target]");
  const mark = quote && document.getElementById(quote.dataset.target);
  if (mark) {
    showView(true);
    mark.scrollIntoView({ behavior: "smooth", block: "center" });
    mark.classList.add("flash");
    setTimeout(() => mark.classList.remove("flash"), 1500);
  }
});

const tip = $("tip");
document.addEventListener("mouseover", (e) => {
  const m = e.target.closest("mark[data-tip]");
  if (!m) return (tip.hidden = true);
  tip.innerHTML = `<b>${escapeHtml(m.dataset.label)}</b>${escapeHtml(m.dataset.tip)}`;
  tip.hidden = false;
});
document.addEventListener("mousemove", (e) => {
  if (tip.hidden) return;
  tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - 300)}px`;
  tip.style.top = `${e.clientY + 16}px`;
});

// ---------- Start ----------

let serverHasClaude = false;
fetch("api/health")
  .then((r) => r.json())
  .then((h) => {
    serverHasClaude = h.claude;
    $("status").textContent = h.claude ? `Claude: ${h.model}` : "Claude: not configured";
    if (!h.claude) $("deep").title = "Set ANTHROPIC_API_KEY on the server to enable Claude";
  })
  .catch(() => ($("status").textContent = "Server not reachable"))
  .finally(() => ($("deep").disabled = !serverHasClaude));

if (!safeLocalStorage()) $("savedNote").textContent = "History is unavailable in this browser";
route();
