/* Ortak yardımcılar + sayfa mantıkları (framework yok). */

function getToken() {
  let t = localStorage.getItem("trs_token");
  if (!t) {
    t = prompt("Sunucu auth token'ı (projects.yaml içindeki auth_token):") || "";
    if (t) localStorage.setItem("trs_token", t);
  }
  return t;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "X-Auth-Token": getToken(), ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    localStorage.removeItem("trs_token");
    alert("Token geçersiz, sayfa yenilenecek.");
    location.reload();
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function fmtDuration(s) {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}sn`;
  return `${Math.floor(s / 60)}dk ${Math.round(s % 60)}sn`;
}

function passRate(run) {
  if (!run || !run.total) return "—";
  return `${Math.round((run.passed / run.total) * 100)}%`;
}

/* ---------------- Dashboard (index.html) ---------------- */

async function initDashboard() {
  getToken();
  await refreshDashboard();
  setInterval(refreshDashboard, 4000);
}

async function refreshDashboard() {
  try {
    const [projects, runs] = await Promise.all([
      api("/api/projects"),
      api("/api/runs?limit=25"),
    ]);
    renderProjects(projects);
    renderRuns(runs);
  } catch (e) {
    console.error(e);
  }
}

function renderProjects(projects) {
  const el = document.getElementById("projects");
  el.innerHTML = projects.map((p) => {
    const running = !!p.active_run_id;
    const last = p.last_run;
    return `<div class="card">
      <div class="name">${esc(p.name)}</div>
      <div class="meta">${esc(p.command)} &nbsp;·&nbsp; ${esc(p.path)}</div>
      <div class="row">
        ${running
          ? `<a href="run.html?id=${encodeURIComponent(p.active_run_id)}"><button>Canlı İzle</button></a>
             <span class="badge running">running</span>`
          : `<button onclick="startRun('${p.id}')">▶ Çalıştır</button>`}
        ${last && !running
          ? `${badge(last.status)} <span class="muted" style="font-size:12px">
               son: ${passRate(last)} geçti (${last.passed}/${last.total})</span>`
          : ""}
      </div>
    </div>`;
  }).join("");
}

async function startRun(projectId) {
  try {
    const { run_id } = await api(`/api/projects/${projectId}/run`, { method: "POST" });
    location.href = `run.html?id=${encodeURIComponent(run_id)}`;
  } catch (e) {
    alert("Koşum başlatılamadı: " + e.message);
  }
}

function renderRuns(runs) {
  const el = document.getElementById("runs");
  if (!runs.length) {
    el.innerHTML = `<tr><td colspan="6" class="muted">Henüz koşum yok</td></tr>`;
    return;
  }
  el.innerHTML = runs.map((r) => `<tr>
    <td><a href="run.html?id=${encodeURIComponent(r.id)}">${esc(r.id)}</a></td>
    <td>${badge(r.status)}</td>
    <td>${r.total
        ? `<span class="pass-cell">${r.passed}✓</span> /
           <span class="fail-cell">${r.failed}✗</span> / ${r.total}
           <span class="muted">(${passRate(r)})</span>`
        : `<span class="muted">—</span>`}</td>
    <td class="muted">${fmtTime(r.started_at)}</td>
    <td class="muted">${fmtDuration(r.duration_s)}</td>
  </tr>`).join("");
}

/* ---------------- Canlı koşum sayfası (run.html) ---------------- */

let ws = null;
let consoleEl = null;
let lineCount = 0;
const MAX_LINES = 5000;

async function initRunPage() {
  getToken();
  const runId = new URLSearchParams(location.search).get("id");
  if (!runId) { location.href = "/"; return; }
  document.getElementById("run-id").textContent = runId;
  consoleEl = document.getElementById("console");

  document.getElementById("stop-btn").onclick = async () => {
    try { await api(`/api/runs/${runId}/stop`, { method: "POST" }); }
    catch (e) { alert("Durdurulamadı: " + e.message); }
  };

  try {
    const run = await api(`/api/runs/${encodeURIComponent(runId)}`);
    setStatus(run.status);
    if (run.live_progress) updateProgress(run.live_progress);
    if (run.status !== "running") {
      showFinal(run.status, { passed: run.passed, failed: run.failed,
                              skipped: run.skipped, total: run.total });
    }
  } catch (e) {
    appendLine("[hata] " + e.message, "err");
  }

  connectWs(runId);
}

function connectWs(runId) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/runs/` +
    `${encodeURIComponent(runId)}/stream?token=${encodeURIComponent(getToken())}`);
  ws.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.type === "backlog") {
      consoleEl.textContent = "";
      lineCount = 0;
      ev.lines.forEach((l) => appendLine(l));
    } else if (ev.type === "log") {
      appendLine(ev.line);
    } else if (ev.type === "progress") {
      updateProgress(ev);
    } else if (ev.type === "finished") {
      showFinal(ev.status, ev.stats);
    } else if (ev.type === "error") {
      appendLine("[hata] " + ev.error, "err");
    }
  };
}

function appendLine(line, cls) {
  const atBottom =
    consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 40;
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = line + "\n";
  consoleEl.appendChild(span);
  if (++lineCount > MAX_LINES) consoleEl.removeChild(consoleEl.firstChild);
  if (atBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
}

function updateProgress(p) {
  const donePct = p.total ? (p.done / p.total) * 100 : 0;
  const passedPct = p.total ? (p.passed / p.total) * 100 : 0;
  const failedPct = p.total ? ((p.failed + p.skipped) / p.total) * 100 : 0;
  document.getElementById("bar-passed").style.width = passedPct + "%";
  document.getElementById("bar-failed").style.width = failedPct + "%";
  const rate = p.done ? Math.round((p.passed / p.done) * 100) : 0;
  document.getElementById("progress-label").textContent =
    `${p.done}/${p.total} senaryo koşuldu (%${Math.round(donePct)}) — ` +
    `geçen: ${p.passed}, kalan hata: ${p.failed}, atlanan: ${p.skipped} — ` +
    `geçme oranı: %${rate}`;
  document.getElementById("stat-passed").textContent = p.passed;
  document.getElementById("stat-failed").textContent = p.failed;
  document.getElementById("stat-total").textContent = p.total;
}

function setStatus(status) {
  document.getElementById("run-status").innerHTML = badge(status);
  document.getElementById("stop-btn").style.display =
    status === "running" ? "" : "none";
}

function showFinal(status, stats) {
  setStatus(status);
  if (stats && stats.total) {
    updateProgress({ ...stats, done: stats.total });
    const rate = Math.round((stats.passed / stats.total) * 100);
    appendLine(`\n══ Koşum bitti: ${status.toUpperCase()} — ` +
      `${stats.passed}/${stats.total} geçti (%${rate}) ══`,
      status === "passed" ? "ok" : "err");
  } else {
    appendLine(`\n══ Koşum bitti: ${status.toUpperCase()} ══`,
      status === "passed" ? "ok" : "err");
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
              '"': "&quot;", "'": "&#39;" }[c]));
}
