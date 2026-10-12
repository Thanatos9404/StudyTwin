/* StudyTwin web UI (vanilla JS, no build step). */
"use strict";

const S = { student: null, students: [], topics: [], tree: [], health: null, history: [], quiz: null, qi: 0, mode: "quiz", scope: new Set() };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => (x == null ? "-" : `${Math.round(x * 100)}%`);
const fmtTs = (s) => { s = Math.floor(s || 0); const m = Math.floor(s / 60), ss = String(s % 60).padStart(2, "0"); return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${ss}` : `${m}:${ss}`; };

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.body && !(opts.body instanceof FormData)) { init.body = JSON.stringify(opts.body); init.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(path, init);
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ } throw new Error(msg); }
  return r.json();
}
function toast(msg, ms = 3200) { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms); }

/* ---------- rendering helpers ---------- */
function md(text) {
  let html = window.marked ? window.marked.parse(String(text || ""), { breaks: true }) : `<p>${esc(text)}</p>`;
  return html;
}
function mathify(el) {
  if (window.renderMathInElement) {
    try {
      window.renderMathInElement(el, { delimiters: [{ left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true }, { left: "\\(", right: "\\)", display: false }, { left: "$", right: "$", display: false }], throwOnError: false });
    } catch (e) { /* ignore */ }
  }
}
function citeChips(html, cites) {
  const byTag = Object.fromEntries((cites || []).map((c) => [c.tag, c]));
  return html.replace(/\[(S\d+)\]/g, (m, tag) => byTag[tag] ? `<button class="cite" data-unit="${esc(byTag[tag].unit_id)}" data-q="${esc(byTag[tag].quote || "")}" title="${esc(byTag[tag].label)}">${tag}</button>` : "");
}
function labelChips(html, cites) {
  // explanations cite sources by label: [6.041 L2 slides · slide 5]
  (cites || []).forEach((c) => {
    const lab = esc(c.label);
    html = html.split(`[${lab}]`).join(`<button class="cite" data-unit="${esc(c.unit_id)}">${lab}</button>`);
  });
  return html;
}
function kindBadge(k) { const map = { textbook: "Textbook", slides: "Slides", video: "Video" }; return `<span class="kind ${k}">${map[k] || k}</span>`; }
function locText(c) {
  const l = c.loc || {};
  if (l.start != null) return `${fmtTs(l.start)}-${fmtTs(l.end)}`;
  if (l.slide != null) return `slide ${l.slide}`;
  if (l.page_label != null) return `p. ${l.page_label}`;
  return "";
}
function sourceRows(cites) {
  if (!cites || !cites.length) return "";
  return `<div class="sources">${cites.map((c) => {
    const qs = c.quote_status === "exact" ? `<span class="quote-ok" title="Quote found verbatim in the source">verbatim</span>` : c.quote_status === "approx" ? `<span class="quote-approx" title="Quote closely matches the source">close match</span>` : "";
    const q = c.quote ? ` "${esc(c.quote.slice(0, 140))}" ${qs}` : "";
    return `<div class="source-row" data-unit="${esc(c.unit_id)}" data-q="${esc(c.quote || "")}"><span class="tag">${esc(c.tag || "")}</span>${kindBadge(c.source_kind)}<div><b>${esc(c.label)}</b>${c.section && c.source_kind !== "video" ? ` <span class="muted">· ${esc(c.section)}</span>` : ""}<div class="muted">${q}</div></div></div>`;
  }).join("")}</div>`;
}
function levelCls(p) { return p >= 0.8 ? "strong" : p >= 0.5 ? "mid" : "weak"; }
let mermaidReady = false;
async function drawMermaid(el, code) {
  if (!window.mermaid) { el.innerHTML = `<pre class="small">${esc(code)}</pre>`; return; }
  if (!mermaidReady) { window.mermaid.initialize({ startOnLoad: false, theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default", securityLevel: "strict" }); mermaidReady = true; }
  try { const { svg } = await window.mermaid.render("m" + Math.random().toString(36).slice(2), code); el.innerHTML = svg; } catch (e) { el.innerHTML = `<pre class="small">${esc(code)}</pre>`; }
}

/* ---------- source viewer ---------- */
async function openUnit(unitId, quote = "") {
  const d = $("drawer");
  d.classList.add("open"); d.setAttribute("aria-hidden", "false");
  $("drawerBody").innerHTML = `<div class="placeholder">Opening source...</div>`;
  try {
    const r = await api(`/api/units/${encodeURIComponent(unitId)}?q=${encodeURIComponent(quote || "")}`);
    const u = r.unit, s = r.source, v = r.view;
    $("drawerTitle").textContent = u.label;
    $("drawerSub").innerHTML = `${kindBadge(s.kind)} ${esc(s.title)}${s.license ? ` · ${esc(s.license)}` : ""}`;
    let body = "";
    if (v.type === "textbook") {
      body += `<div class="page-wrap" id="pageWrap"><img src="${v.page_image}" alt="page ${v.page_label}" id="pageImg" /></div>`;
      body += `<div class="actions">${v.pdf_url ? `<a class="btn small" target="_blank" href="${v.pdf_url}">Open PDF at page ${v.page}</a>` : ""}</div>`;
    } else if (v.type === "slides") {
      body += `<div class="page-wrap"><img src="${v.image || v.page_image}" alt="slide ${v.slide}" /></div>`;
      body += `<div class="actions">${v.pdf_url ? `<a class="btn small" target="_blank" href="${v.pdf_url}">Open slide deck</a>` : ""}</div>`;
    } else {
      if (v.youtube_id) body += `<iframe class="yt" height="320" src="https://www.youtube-nocookie.com/embed/${esc(v.youtube_id)}?start=${Math.floor(v.start)}&autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`;
      else if (v.video_url) body += `<video id="vid" controls preload="metadata" src="${esc(v.video_url)}#t=${Math.floor(v.start)}"></video>`;
      body += `<div class="actions"><span class="tagpill topic">Timestamp ${fmtTs(v.start)}-${fmtTs(v.end)}</span></div>`;
    }
    if (u.kind === "figure" && u.image && v.type !== "slides") body += `<h4>Figure</h4><img src="/media/${esc(u.image)}" style="max-width:100%;border:1px solid var(--line);border-radius:6px" />`;
    if (quote) body += `<div class="excerpt"><b>Quoted:</b> "${esc(quote)}"</div>`;
    body += `<div class="excerpt">${esc(u.text)}</div>`;
    $("drawerBody").innerHTML = body;
    const vid = $("vid");
    if (vid) vid.addEventListener("loadedmetadata", () => { vid.currentTime = v.start || 0; vid.play().catch(() => {}); }, { once: true });
    const img = $("pageImg");
    if (img && v.highlights && v.highlights.length) {
      const place = () => {
        const sc = img.clientWidth / v.page_size[0];
        v.highlights.forEach((h) => { const e = document.createElement("div"); e.className = "hl"; Object.assign(e.style, { left: `${h[0] * sc}px`, top: `${h[1] * sc}px`, width: `${h[2] * sc}px`, height: `${h[3] * sc}px` }); $("pageWrap").appendChild(e); });
        const first = $("pageWrap").querySelector(".hl"); if (first) first.scrollIntoView({ block: "center", behavior: "smooth" });
      };
      img.complete ? place() : img.addEventListener("load", place, { once: true });
    }
  } catch (e) { $("drawerBody").innerHTML = `<div class="placeholder">Could not open source: ${esc(e.message)}</div>`; }
}
function closeDrawer() { const d = $("drawer"); d.classList.remove("open"); d.setAttribute("aria-hidden", "true"); const v = $("vid"); if (v) v.pause(); }
document.addEventListener("click", (e) => {
  const c = e.target.closest("[data-unit]");
  if (c && !e.target.closest(".drawer")) { e.preventDefault(); openUnit(c.dataset.unit, c.dataset.q || ""); }
});

/* ---------- tabs ---------- */
function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "progress") loadProgress();
  if (name === "library") loadLibrary();
  if (name === "eval") loadEval();
  if (name === "practice") renderScope();
}
$("tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) showTab(b.dataset.tab); });

/* ---------- students ---------- */
async function loadStudents(selectId) {
  S.students = await api("/api/students");
  const sel = $("studentSelect");
  sel.innerHTML = S.students.length ? S.students.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("") : `<option value="">No student yet</option>`;
  const saved = selectId || localStorage.getItem("st_student");
  const pick = S.students.find((s) => s.id === saved) || S.students[S.students.length - 1];
  S.student = pick ? pick.id : null;
  if (S.student) sel.value = S.student;
}
$("studentSelect").addEventListener("change", (e) => { S.student = e.target.value; try { localStorage.setItem("st_student", S.student); } catch (err) { /* ignore */ } S.history = []; toast(`Switched to ${e.target.selectedOptions[0].text}`); });
$("newStudentBtn").addEventListener("click", () => newStudentFlow());

function newStudentFlow() {
  const m = $("modal"), card = $("modalCard");
  m.classList.remove("hidden");
  card.innerHTML = `<h3>New student</h3><p class="hint">StudyTwin starts with no history. A short intake (self-rating) sets the starting mastery, then a diagnostic quiz (one question per topic) calibrates it.</p>
    <div class="field"><input type="text" id="nsName" placeholder="Your name" style="width:100%" /></div>
    <div class="actions"><button class="btn primary" id="nsCreate">Continue</button><button class="btn ghost" id="nsCancel">Cancel</button></div>`;
  $("nsCancel").onclick = () => m.classList.add("hidden");
  $("nsCreate").onclick = async () => {
    const name = $("nsName").value.trim() || "Student";
    const st = await api("/api/students", { method: "POST", body: { name } });
    await loadStudents(st.id); S.student = st.id; try { localStorage.setItem("st_student", st.id); } catch (e) { /* ignore */ }
    intakeStep(st);
  };
}
function intakeStep(st) {
  const card = $("modalCard");
  const labels = ["Never seen", "Heard of it", "Somewhat", "Comfortable", "Confident"];
  card.innerHTML = `<h3>Hi ${esc(st.name)}, how familiar are you with each topic?</h3>
    ${S.tree.map((t) => `<div class="rating"><div>${esc(t.name)}</div><div class="seg" data-topic="${t.id}">${labels.map((l, i) => `<button data-v="${i + 1}" class="${i === 0 ? "active" : ""}" title="${l}">${i + 1}</button>`).join("")}</div></div>`).join("")}
    <p class="hint">1 = ${labels[0]}, 5 = ${labels[4]}</p>
    <div class="field"><input type="text" id="nsGoal" placeholder="Your goal (e.g. midterm on conditional probability next week)" style="width:100%" /></div>
    <div class="actions"><button class="btn primary" id="nsSave">Save and take the diagnostic</button><button class="btn ghost" id="nsSkip">Skip</button></div>`;
  card.querySelectorAll(".seg").forEach((seg) => seg.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; seg.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b)); }));
  $("nsSkip").onclick = () => { $("modal").classList.add("hidden"); };
  $("nsSave").onclick = async () => {
    const ratings = {};
    card.querySelectorAll(".seg").forEach((seg) => { ratings[seg.dataset.topic] = Number(seg.querySelector("button.active").dataset.v); });
    await api(`/api/students/${st.id}/intake`, { method: "POST", body: { ratings, goals: $("nsGoal").value } });
    $("modal").classList.add("hidden");
    showTab("practice"); setMode("diagnostic"); startQuiz();
  };
}

/* ---------- tutor ---------- */
const SUGGEST = [
  "In the radar example, what is P(airplane present | radar registers)?",
  "What is the difference between independent and mutually exclusive events?",
  "Why does zero probability not mean impossible?",
  "State the total probability theorem and when to use it.",
  "How do I read a contingency table to get P(A|B)?",
  "Explain the central limit theorem.",
];
function renderSuggestions() { $("suggestions").innerHTML = SUGGEST.map((s) => `<button class="chip" type="button">${esc(s)}</button>`).join(""); }
$("suggestions").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (b) { $("chatText").value = b.textContent; sendChat(); } });
function addMsg(role, html) { $("chatEmpty").classList.add("hidden"); const d = document.createElement("div"); d.className = `msg ${role}`; d.innerHTML = `<div class="bubble">${html}</div>`; $("chatThread").appendChild(d); $("chatThread").scrollTop = 1e9; return d; }
async function sendChat() {
  const text = $("chatText").value.trim();
  if (!text) return;
  $("chatText").value = "";
  addMsg("user", esc(text));
  const pending = addMsg("bot", `<span class="typing">Searching your course material...</span>`);
  $("sendBtn").disabled = true;
  try {
    const r = await api("/api/chat", { method: "POST", body: { message: text, student_id: S.student, lang: $("langSelect").value, allow_outside: $("allowOutside").checked, history: S.history } });
    S.history.push({ role: "user", content: text }, { role: "assistant", content: r.answer || "" });
    pending.querySelector(".bubble").innerHTML = renderAnswer(r);
    mathify(pending);
  } catch (e) { pending.querySelector(".bubble").innerHTML = `<span class="status not_covered">Error</span> ${esc(e.message)}`; }
  $("sendBtn").disabled = false;
  $("chatThread").scrollTop = 1e9;
}
function renderAnswer(r) {
  const label = { answered: "Source-backed answer", partial: "Partly covered by your material", not_covered: "Not in your course material" }[r.status] || r.status;
  let h = `<span class="status ${r.status}">${label}</span>`;
  h += `<div class="answer">${citeChips(md(r.answer), r.citations)}</div>`;
  if (r.outside_knowledge) h += `<div class="outside"><b>Outside your course material (general knowledge, not verified against your sources):</b> ${esc(r.outside_knowledge)}</div>`;
  h += sourceRows(r.citations);
  if (r.followups && r.followups.length) h += `<div class="followups">${r.followups.map((f) => `<button class="chip" type="button" onclick="document.getElementById('chatText').value=this.textContent">${esc(f)}</button>`).join("")}</div>`;
  const cs = r.context_stats || {};
  const slim = cs.llmslim ? `<span class="slim">LLMSlim: evidence ${cs.tokens_before} -> ${cs.tokens_after} tokens (-${cs.saved_pct}%), ${cs.citations_preserved} citations kept, ${cs.verbatim_sentences} sentences verbatim</span>` : `<span>Evidence ${cs.tokens_before || 0} tokens (under budget, no compression)</span>`;
  const mu = r.mastery_update ? `<span>Mastery ${esc(topicName(r.mastery_update.topic_id))}: ${pct(r.mastery_update.before)} -> ${pct(r.mastery_update.after)} (${esc(r.mastery_update.signal)})</span>` : "";
  h += `<div class="meta">${slim}<span>retrieval support ${r.support}</span><span>${r.latency_s}s</span>${r.model ? `<span>${esc(r.model)}</span>` : ""}${r.uncited_sentences ? `<span>${r.uncited_sentences} uncited sentence(s)</span>` : ""}${mu}</div>`;
  return h;
}
$("chatForm").addEventListener("submit", (e) => { e.preventDefault(); sendChat(); });
$("chatText").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
function topicName(id) { const t = S.tree.find((x) => x.id === id); return t ? t.name : id || ""; }

/* ---------- practice ---------- */
const MODE_HINT = {
  quiz: "Adaptive: topics are weighted by low mastery and fading memory; difficulty is chosen so you succeed about 70% of the time.",
  mock: "Mock exam: a fixed blueprint across the chosen topics with all question types and difficulties.",
  diagnostic: "Diagnostic: one medium question per topic to calibrate a new learner model.",
};
function setMode(m) { S.mode = m; document.querySelectorAll("#modeSeg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === m)); $("modeHint").textContent = MODE_HINT[m]; }
$("modeSeg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setMode(b.dataset.mode); });
function renderScope() {
  if (!S.scope.size) S.tree.forEach((t) => S.scope.add(t.id));
  $("scopeChips").innerHTML = S.tree.map((t) => `<button class="chip ${S.scope.has(t.id) ? "on" : ""}" data-t="${t.id}" type="button">${esc(t.name)}</button>`).join("");
}
$("scopeChips").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; const id = b.dataset.t; S.scope.has(id) ? S.scope.delete(id) : S.scope.add(id); renderScope(); });
$("startQuizBtn").addEventListener("click", () => startQuiz());
async function startQuiz(topicIds) {
  if (!S.student) { newStudentFlow(); return; }
  const types = [...document.querySelectorAll(".qtype:checked")].map((x) => x.value);
  $("quizReport").classList.add("hidden");
  $("quizRunner").innerHTML = `<div class="placeholder">Selecting questions for your current mastery...</div>`;
  try {
    S.quiz = await api("/api/assessments", { method: "POST", body: { student_id: S.student, kind: S.mode, topic_ids: topicIds || [...S.scope], n: Number($("qCount").value) || 6, types } });
    S.qi = 0; S.quiz.results = [];
    if (!S.quiz.questions.length) { $("quizRunner").innerHTML = `<div class="placeholder">No questions available for this scope yet.</div>`; return; }
    renderQuestion();
  } catch (e) { $("quizRunner").innerHTML = `<div class="placeholder">Could not build the assessment: ${esc(e.message)}</div>`; }
}
function renderQuestion() {
  const q = S.quiz.questions[S.qi], n = S.quiz.questions.length;
  const dots = "&#9679;".repeat(q.difficulty) + "&#9675;".repeat(3 - q.difficulty);
  let input = "";
  if (q.type === "mcq") input = `<div class="options">${q.options.map((o, i) => `<div class="option" data-l="${"ABCD"[i]}"><span class="letter">${"ABCD"[i]}</span><span>${esc(o)}</span></div>`).join("")}</div>`;
  else if (q.type === "numerical") input = `<input class="answer-input" id="ansIn" placeholder="Your answer (decimal, fraction like 3/11, or %)" />`;
  else input = `<textarea class="answer-input" id="ansIn" rows="3" placeholder="Answer in 1-3 sentences"></textarea>`;
  $("quizRunner").innerHTML = `<div class="progress-line"><div style="width:${(S.qi / n) * 100}%"></div></div>
    <div class="q-meta"><span class="tagpill">${S.quiz.kind} · ${S.qi + 1}/${n}</span><span class="tagpill topic">${esc(q.topic)}</span><span class="tagpill">${q.type === "mcq" ? "Multiple choice" : q.type === "numerical" ? "Numerical" : "Short answer"}</span><span class="tagpill" title="difficulty">${dots}</span>${q.sources.map((s) => `<span class="tagpill">${esc(s)}</span>`).join("")}</div>
    <div class="q-stem">${md(q.stem)}</div>${input}
    <div class="actions"><button class="btn primary" id="submitAns">Check answer</button></div><div id="fbBox"></div>`;
  mathify($("quizRunner"));
  $("quizRunner").querySelectorAll(".option").forEach((o) => o.addEventListener("click", () => { if (o.closest(".done")) return; $("quizRunner").querySelectorAll(".option").forEach((x) => x.classList.toggle("sel", x === o)); }));
  $("submitAns").onclick = submitAnswer;
}
async function submitAnswer() {
  const q = S.quiz.questions[S.qi];
  let resp = "";
  if (q.type === "mcq") { const sel = $("quizRunner").querySelector(".option.sel"); if (!sel) { toast("Pick an option"); return; } resp = sel.dataset.l; }
  else resp = $("ansIn").value.trim();
  $("submitAns").disabled = true;
  try {
    const fb = await api(`/api/assessments/${S.quiz.id}/answer`, { method: "POST", body: { question_id: q.id, response: resp } });
    S.quiz.results.push(fb);
    if (q.type === "mcq") {
      const opts = $("quizRunner").querySelector(".options"); opts.classList.add("done");
      opts.querySelectorAll(".option").forEach((o) => { if (o.dataset.l === fb.correct_answer[0]) o.classList.add("right"); else if (o.dataset.l === resp) o.classList.add("wrong"); });
    }
    const cls = fb.score >= 0.75 ? "good" : fb.score > 0 ? "half" : "bad";
    const head = fb.score >= 0.75 ? "Correct" : fb.score > 0 ? "Partly correct" : "Not quite";
    const mu = fb.mastery && fb.mastery.topic_id ? `<div class="meta"><span>Mastery of ${esc(topicName(fb.mastery.topic_id))}: ${pct(fb.mastery.before)} -> <b>${pct(fb.mastery.after)}</b> (BKT update)</span></div>` : "";
    $("fbBox").innerHTML = `<div class="feedback ${cls}"><h4>${head}${q.type !== "mcq" ? ` · answer: ${esc(fb.correct_answer)}` : ""}</h4>
      ${fb.feedback ? `<div>${labelChips(md(fb.feedback), fb.citations)}</div>` : ""}
      ${fb.misconception ? `<div class="mis"><b>Likely misconception:</b> ${esc(fb.misconception)}</div>` : ""}
      <div class="answer">${labelChips(md(fb.explanation), fb.citations)}</div>${sourceRows(fb.citations)}${mu}</div>
      <div class="actions"><button class="btn primary" id="nextQ">${S.qi + 1 < S.quiz.questions.length ? "Next question" : "Finish and see report"}</button></div>`;
    mathify($("fbBox"));
    $("nextQ").onclick = () => { S.qi += 1; S.qi < S.quiz.questions.length ? renderQuestion() : finishQuiz(); };
  } catch (e) { toast(e.message); $("submitAns").disabled = false; }
}
async function finishQuiz() {
  $("quizRunner").innerHTML = `<div class="placeholder">Building your report...</div>`;
  const r = await api(`/api/assessments/${S.quiz.id}/finish`, { method: "POST" });
  $("quizRunner").innerHTML = `<div class="placeholder">Assessment complete: ${r.score}/${r.n} (${pct(r.accuracy)}). See the report below.</div>`;
  const box = $("quizReport"); box.classList.remove("hidden");
  box.innerHTML = `<h3>Post-assessment report</h3>
    <div class="stats-row"><div class="stat"><div class="v">${pct(r.accuracy)}</div><div class="k">Score (${r.score}/${r.n})</div></div>
    <div class="stat"><div class="v">${r.weak_topics.length}</div><div class="k">Weak topics</div></div>
    <div class="stat"><div class="v">${r.misconceptions.length}</div><div class="k">Misconceptions found</div></div>
    <div class="stat"><div class="v">${r.repeats || 0}</div><div class="k">Repeated questions</div></div></div>
    <table class="simple"><tr><th>Topic</th><th>Questions</th><th>Score</th><th>Mastery before -> after</th></tr>
    ${r.topics.map((t) => `<tr><td>${esc(t.name)}</td><td>${t.n}</td><td>${pct(t.accuracy)}</td><td>${pct(t.before)} -> <b>${pct(t.after)}</b></td></tr>`).join("")}</table>
    ${r.misconceptions.length ? `<h4>Likely misconceptions</h4>${r.misconceptions.map((m) => `<div class="day"><b>${esc(m.topic)}:</b> ${esc(m.misconception)}<div class="muted small">${esc(m.question)}</div>${sourceRows(m.citations)}</div>`).join("")}` : ""}
    ${r.recommendations.length ? `<h4>What to review next</h4>${r.recommendations.map((x) => `<div class="day"><b>${esc(x.topic)}</b>: ${esc(x.action)}${sourceRows(x.review)}<div class="actions"><button class="btn small" data-practice="${x.topic_id}">Practice ${esc(x.topic)}</button></div></div>`).join("")}` : `<p>No weak topics in this assessment.</p>`}`;
  box.querySelectorAll("[data-practice]").forEach((b) => b.addEventListener("click", () => { setMode("quiz"); startQuiz([b.dataset.practice]); window.scrollTo({ top: 0, behavior: "smooth" }); }));
  box.scrollIntoView({ behavior: "smooth" });
}

/* ---------- progress ---------- */
async function loadProgress() {
  if (!S.student) { $("masteryList").innerHTML = `<div class="placeholder">Create a student to start tracking mastery.</div>`; return; }
  const d = await api(`/api/students/${S.student}/dashboard`);
  const mastered = d.mastery.filter((m) => m.level === "mastered").length;
  const acc = d.answered ? d.score_sum / d.answered : null;
  $("statsRow").innerHTML = [[d.answered, "Questions answered"], [pct(acc), "Overall accuracy"], [d.questions_asked, "Questions asked to tutor"], [`${mastered}/${d.mastery.length}`, "Topics mastered (P>=0.8)"]]
    .map(([v, k]) => `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
  $("masteryList").innerHTML = d.mastery.map((m) => `<div class="mastery-row"><div><div class="name">${esc(m.name)}</div><div class="sub">${m.n} answers${m.accuracy != null ? ` · ${pct(m.accuracy)} correct` : ""} · retention ${pct(m.retention)}${m.due ? " · <b>review due</b>" : ""}</div></div>
    <div class="bar"><div class="${levelCls(m.p)}" style="width:${m.p * 100}%"></div></div><div><span class="level ${m.level === "needs work" ? "needs" : m.level}">${pct(m.p)} ${m.level}</span></div></div>`).join("")
    + (d.is_new ? `<p class="hint">New learner: take the diagnostic in Practice to calibrate these estimates.</p>` : "");
  drawMermaid($("progressMap"), d.mermaid);
  $("timeline").innerHTML = timelineSvg(d.log, d.mastery);
  $("flashTopic").innerHTML = d.mastery.slice().sort((a, b) => a.p - b.p).map((m) => `<option value="${m.topic_id}">${esc(m.name)} (${pct(m.p)})</option>`).join("");
  if (!$("examDate").value) { const dt = new Date(Date.now() + 7 * 864e5); $("examDate").value = dt.toISOString().slice(0, 10); }
}
function timelineSvg(log, mastery) {
  if (!log.length) return `<div class="placeholder">No evidence yet. Answer questions or chat with the tutor.</div>`;
  const W = 560, H = 220, P = 30;
  const ids = mastery.map((m) => m.topic_id);
  const colors = ["#3b5bdb", "#e8590c", "#2f9e44", "#ae3ec9", "#1098ad", "#f08c00", "#c92a2a", "#5c940d"];
  const series = {};
  log.forEach((e, i) => { (series[e.topic_id] = series[e.topic_id] || []).push([i, e.p_after]); });
  const x = (i) => P + (i / Math.max(1, log.length - 1)) * (W - 2 * P), y = (p) => H - P - p * (H - 2 * P);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}"><line x1="${P}" y1="${y(0.8)}" x2="${W - P}" y2="${y(0.8)}" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="4 4"/><text x="${W - P}" y="${y(0.8) - 4}" font-size="10" text-anchor="end" fill="currentColor" opacity=".6">mastered</text>`;
  [0, 0.5, 1].forEach((t) => { svg += `<text x="4" y="${y(t) + 4}" font-size="10" fill="currentColor" opacity=".6">${t * 100}%</text>`; });
  ids.forEach((id, k) => {
    const pts = series[id]; if (!pts) return;
    svg += `<polyline fill="none" stroke="${colors[k % colors.length]}" stroke-width="2" points="${pts.map(([i, p]) => `${x(i)},${y(p)}`).join(" ")}"/>`;
    const [li, lp] = pts[pts.length - 1];
    svg += `<circle cx="${x(li)}" cy="${y(lp)}" r="3" fill="${colors[k % colors.length]}"/>`;
  });
  svg += `</svg><div class="chips">${ids.map((id, k) => series[id] ? `<span class="small" style="color:${colors[k % colors.length]}">&#9632; ${esc(topicName(id))}</span>` : "").join(" ")}</div>`;
  return svg;
}
$("planBtn").addEventListener("click", async () => {
  if (!S.student) return;
  const r = await api(`/api/students/${S.student}/schedule?exam_date=${$("examDate").value}&minutes=${$("minutesDay").value}`);
  $("planOut").innerHTML = r.days.map((d) => `<div class="day"><div class="d">${d.date}</div>${d.tasks.map((t) => `<div>${esc(t.activity)} <b>${esc(t.topic)}</b> · ${t.minutes} min${t.why ? ` <span class="muted">(${esc(t.why)})</span>` : ""}${t.sources ? `<div class="muted small">Sources: ${t.sources.map(esc).join(", ")}</div>` : ""}</div>`).join("")}</div>`).join("");
});
$("flashBtn").addEventListener("click", async () => {
  const tid = $("flashTopic").value; if (!tid) return;
  $("flashOut").innerHTML = `<div class="placeholder">Writing cited flashcards...</div>`;
  const cards = await api(`/api/topics/${tid}/flashcards`);
  $("flashOut").innerHTML = cards.map((c) => `<div class="flash"><div class="face front">${esc(c.front)}</div><div class="face back">${esc(c.back)}</div>${c.citation ? `<div class="src"><button class="cite" data-unit="${esc(c.citation.unit_id)}">${esc(c.citation.label)}</button></div>` : ""}</div>`).join("") || `<div class="placeholder">No cards.</div>`;
  $("flashOut").querySelectorAll(".flash").forEach((f) => f.addEventListener("click", (e) => { if (!e.target.closest(".cite")) f.classList.toggle("flipped"); }));
  mathify($("flashOut"));
});

/* ---------- library ---------- */
async function loadLibrary() {
  const [srcs, tp] = await Promise.all([api("/api/sources"), api("/api/topics")]);
  S.tree = tp.tree;
  $("sourcesTable").innerHTML = srcs.length ? `<table class="simple"><tr><th>Type</th><th>Title</th><th>Knowledge units</th><th>License</th></tr>${srcs.map((s) => {
    const uc = s.unit_counts || {};
    const parts = Object.entries(uc).map(([k, n]) => `${n} ${k === "text" ? "passages" : k === "transcript" ? "timed segments" : k + "s"}`).join(", ");
    const meta = s.meta || {};
    const extra = meta.transcript === "whisper" ? ` · Whisper ${esc(meta.model)} transcript (${Math.round(meta.duration_s / 60)} min audio)` : meta.transcript ? ` · ${esc(meta.transcript)}` : "";
    return `<tr><td>${kindBadge(s.kind)}</td><td><b>${esc(s.title)}</b><div class="muted small">${esc(s.attribution || "")}${extra}</div></td><td>${parts}</td><td>${esc(s.license || "")}</td></tr>`;
  }).join("")}</table>` : `<div class="placeholder">No sources yet. Upload a PDF, slide deck or lecture video.</div>`;
  $("topicTree").innerHTML = S.tree.map((t) => `<div class="topic-card"><div class="t">${esc(t.id)} · ${esc(t.name)}</div><div class="muted small">${esc(t.description)}</div>
    <div class="cov">Prerequisites: ${(t.prerequisites || []).map(topicName).map(esc).join(", ") || "none"} · Coverage: ${Object.entries(t.coverage || {}).map(([k, n]) => `${n} ${k}`).join(", ")}</div>
    <div class="chips" style="margin-top:6px">${(t.key_concepts || []).map((c) => `<span class="tagpill">${esc(c)}</span>`).join("")}</div>
    <div class="sub-list">${(t.subtopics || []).map((s) => `<div>${esc(s.id)} ${esc(s.name)} <span class="muted small">(${s.units} units)</span></div>`).join("")}</div></div>`).join("");
  drawMermaid($("libraryMap"), tp.mermaid);
}
async function pollJob(jid) {
  const box = $("jobBox");
  for (;;) {
    const j = await api(`/api/jobs/${jid}`);
    box.innerHTML = `<div class="job"><div class="progress-line"><div style="width:${Math.round((j.progress || 0) * 100)}%"></div></div>${esc(j.status)}: ${esc(j.message || "")}</div>`;
    if (j.status === "done" || j.status === "error") { if (j.status === "done") { toast("Ingestion complete"); await refreshTopics(); loadLibrary(); } return; }
    await new Promise((r) => setTimeout(r, 1200));
  }
}
async function uploadFile(file) {
  const fd = new FormData(); fd.append("file", file); fd.append("kind", $("kindSelect").value); fd.append("title", $("titleInput").value);
  $("jobBox").innerHTML = `<div class="job">Uploading ${esc(file.name)}...</div>`;
  try { const r = await api("/api/sources", { method: "POST", body: fd }); pollJob(r.job_id); } catch (e) { $("jobBox").innerHTML = `<div class="job">Upload failed: ${esc(e.message)}</div>`; }
}
$("fileInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadFile(e.target.files[0]); e.target.value = ""; });
const dz = $("dropzone");
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });
$("ytBtn").addEventListener("click", async () => { const url = $("ytInput").value.trim(); if (!url) return; try { const r = await api("/api/sources/youtube", { method: "POST", body: { url } }); pollJob(r.job_id); } catch (e) { toast(e.message); } });

/* ---------- evaluation ---------- */
function metricCards(items) { return `<div class="metric-grid">${items.map(([k, v, sub]) => `<div class="metric"><div class="v">${v}</div><div class="k">${k}</div>${sub ? `<div class="muted small">${sub}</div>` : ""}</div>`).join("")}</div>`; }
const f2 = (x) => (x == null || Number.isNaN(x) ? "-" : Number(x).toFixed(2));
async function loadEval() {
  const r = await api("/api/eval");
  const out = [];
  const rag = r.rag_eval;
  if (rag) {
    const cfgs = rag.configs || {};
    Object.entries(cfgs).forEach(([name, c]) => {
      const m = c.metrics || {};
      out.push(`<div class="card"><h3>RAG evaluation · ${esc(name)}</h3><p class="hint">${esc(c.description || "")}</p>${metricCards([
        ["Faithfulness", f2(m.faithfulness), "RAGAS, LLM judge"], ["Answer relevancy", f2(m.answer_relevancy), "RAGAS"],
        ["Context precision", f2(m.context_precision), "RAGAS (LLM, with reference)"], ["Context recall", f2(m.context_recall), "RAGAS (LLM, with reference)"],
        ["Source-location hit@k", f2(m.hit_at_k), "gold page/slide/timestamp retrieved"], ["Citation accuracy", f2(m.citation_accuracy), "answer cites a gold location"],
        ["Quote verified", f2(m.quote_verified), "quotes found in cited source"], ["Off-material declined", f2(m.refusal_rate), `${m.n_off || 0} off-material queries`],
        ["False refusals", f2(m.false_refusal_rate), "in-scope questions declined"], ["Evidence tokens / query", m.context_tokens ? Math.round(m.context_tokens) : "-", "mean, est."],
        ["Prompt tokens / query", m.prompt_tokens ? Math.round(m.prompt_tokens) : "-", "provider-reported, mean"], ["Latency p50", m.latency_p50 ? `${f2(m.latency_p50)} s` : "-", ""],
      ])}</div>`);
    });
    if (rag.notes) out.push(`<div class="card"><h3>About this evaluation</h3>${rag.notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}</div>`);
  }
  const sim = r.simulation;
  if (sim) {
    out.push(`<div class="card"><h3>Personalization: simulated students</h3><p class="hint">${esc(sim.description || "")}</p>
      <table class="simple"><tr><th>Profile</th><th>Policy</th><th>True mastery start -> end</th><th>Gain</th><th>BKT error (first -> last session)</th><th>Repeat rate</th></tr>
      ${(sim.rows || []).map((x) => `<tr><td>${esc(x.profile)}</td><td>${esc(x.policy)}</td><td>${pct(x.true_start)} -> ${pct(x.true_end)}</td><td><b>${x.gain >= 0 ? "+" : ""}${pct(x.gain)}</b></td><td>${f2(x.bkt_mae_first)} -> ${f2(x.bkt_mae_last)}</td><td>${pct(x.repeat_rate)}</td></tr>`).join("")}</table>
      ${sim.curve ? simChart(sim.curve) : ""}</div>`);
  }
  const bank = r.question_bank;
  if (bank) out.push(`<div class="card"><h3>Question bank quality</h3>${metricCards([["Generated", bank.generated], ["Passed cross-model verification", bank.verified, pct(bank.verified_rate)], ["Rejected", bank.rejected], ["Near-duplicates blocked", bank.duplicates]])}<p class="note">${esc(bank.note || "")}</p></div>`);
  const asr = r.asr;
  if (asr) out.push(`<div class="card"><h3>Video transcription quality</h3>${metricCards([["Word error rate", pct(asr.wer), `vs official captions`], ["Audio", `${Math.round(asr.duration_s / 60)} min`], ["CPU time", `${Math.round(asr.wall_time_s / 60)} min`, esc(asr.model)]])}<p class="note">${esc(asr.note || "")}</p></div>`);
  $("evalOut").innerHTML = out.join("") || `<div class="placeholder">No evaluation results yet. Run: python -m studytwin.eval.run_all</div>`;
}
function simChart(curve) {
  const W = 560, H = 220, P = 34;
  const series = Object.entries(curve);
  const n = Math.max(...series.map(([, v]) => v.length));
  const x = (i) => P + (i / Math.max(1, n - 1)) * (W - 2 * P), y = (p) => H - P - p * (H - 2 * P);
  const colors = ["#3b5bdb", "#e8590c", "#2f9e44", "#ae3ec9"];
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  [0, 0.5, 1].forEach((t) => { svg += `<text x="2" y="${y(t) + 4}" font-size="10" fill="currentColor" opacity=".6">${t * 100}%</text><line x1="${P}" x2="${W - P}" y1="${y(t)}" y2="${y(t)}" stroke="currentColor" stroke-opacity=".1"/>`; });
  series.forEach(([name, v], k) => { svg += `<polyline fill="none" stroke="${colors[k % 4]}" stroke-width="2.2" points="${v.map((p, i) => `${x(i)},${y(p)}`).join(" ")}"/>`; });
  svg += `<text x="${W / 2}" y="${H - 6}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".6">session</text></svg>`;
  return svg + `<div class="chips">${series.map(([name], k) => `<span class="small" style="color:${colors[k % 4]}">&#9632; ${esc(name)}</span>`).join(" ")}</div><p class="note">Mean true mastery (fraction of topics known) after each session, averaged over simulated students.</p>`;
}

/* ---------- boot ---------- */
async function refreshTopics() { const tp = await api("/api/topics"); S.tree = tp.tree; }
async function boot() {
  $("drawerClose").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  renderSuggestions(); setMode("quiz");
  try {
    S.health = await api("/api/health");
    const p = $("statusPill");
    p.textContent = S.health.llm ? `Live · Nebius · ${S.health.counts.units} units` : `Offline mode · ${S.health.counts.units} units`;
    p.classList.toggle("off", !S.health.llm);
    p.title = Object.entries(S.health.models).map(([k, v]) => `${k}: ${v}`).join("\n");
    $("bankNote").textContent = `${S.health.counts.questions} verified questions in the bank; new ones are generated and verified on demand when a scope runs out.`;
  } catch (e) { $("statusPill").textContent = "API unreachable"; }
  await refreshTopics();
  await loadStudents();
  renderScope();
}
window.addEventListener("DOMContentLoaded", boot);
