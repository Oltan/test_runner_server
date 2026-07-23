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
                              skipped: run.skipped, total: run.total },
                run.retry_run_id);
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
      showFinal(ev.status, ev.stats, ev.retry_run_id);
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

function showFinal(status, stats, retryRunId) {
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
  if (retryRunId) {
    const banner = document.getElementById("retry-banner");
    banner.style.display = "";
    banner.innerHTML = `↻ Kalan senaryolar için otomatik retry koşumu başladı
      (flaky ayrımı için): <a href="run.html?id=${encodeURIComponent(retryRunId)}">
      ${esc(retryRunId)}</a>`;
  }
  loadScenarios();
}

async function loadScenarios() {
  const runId = new URLSearchParams(location.search).get("id");
  let run;
  try { run = await api(`/api/runs/${encodeURIComponent(runId)}`); }
  catch (e) { return; }
  if (!run.scenarios || !run.scenarios.length) return;

  if (run.retry_run_id) {
    const banner = document.getElementById("retry-banner");
    banner.style.display = "";
    banner.innerHTML = `↻ Bu koşumun retry koşumu:
      <a href="run.html?id=${encodeURIComponent(run.retry_run_id)}">
      ${esc(run.retry_run_id)}</a>`;
  }

  document.getElementById("scenarios-section").style.display = "";
  const healByScenario = {};
  (run.heals || []).forEach((h) => { healByScenario[h.scenario] = h; });

  document.getElementById("scenarios").innerHTML = run.scenarios.map((s) => {
    const flaky = s.passed_on_retry
      ? ` <span class="badge flaky">flaky şüphesi</span>` : "";
    let action = "";
    const heal = healByScenario[s.scenario];
    if (heal) {
      action = `<a href="heal.html?id=${encodeURIComponent(heal.id)}">
        <span class="badge ${heal.status}">heal: ${heal.status}</span></a>`;
    } else if (s.status === "failed" && !s.passed_on_retry && run.agent_enabled) {
      action = `<button class="heal-btn"
        onclick="startHeal('${esc(s.scenario).replace(/'/g, "\\'")}')">
        🩹 AI ile düzelt</button>`;
    }
    const err = s.error_message
      ? `<span class="err-excerpt" title="${esc(s.error_message)}">
           ${esc(s.error_message.split("\n")[0])}</span>` : "";
    return `<tr>
      <td class="muted">${esc(s.feature || "")}</td>
      <td>${esc(s.scenario)}${err}</td>
      <td>${badge(s.status)}${flaky}</td>
      <td class="muted">${fmtDuration(s.duration_s)}</td>
      <td>${action}</td>
    </tr>`;
  }).join("");
}

async function startHeal(scenario) {
  const runId = new URLSearchParams(location.search).get("id");
  try {
    const { heal_id } = await api(`/api/runs/${encodeURIComponent(runId)}/heal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario, mode: "auto" }),
    });
    location.href = `heal.html?id=${encodeURIComponent(heal_id)}`;
  } catch (e) {
    alert("Heal başlatılamadı: " + e.message);
  }
}

/* ---------------- Heal sayfası (heal.html) ---------------- */

async function initHealPage() {
  getToken();
  const healId = new URLSearchParams(location.search).get("id");
  if (!healId) { location.href = "/"; return; }

  document.getElementById("approve-btn").onclick = () => resolveHeal(healId, "approve");
  document.getElementById("reject-btn").onclick = () => resolveHeal(healId, "reject");

  await refreshHeal(healId);
  const timer = setInterval(async () => {
    const status = await refreshHeal(healId);
    if (status !== "running") clearInterval(timer);
  }, 2000);
}

async function refreshHeal(healId) {
  let heal;
  try { heal = await api(`/api/heals/${encodeURIComponent(healId)}`); }
  catch (e) { return "error"; }

  // canlı çıktı: agent + LLM + doğrulama komutlarının akan logu
  try {
    const res = await fetch(`/api/heals/${encodeURIComponent(healId)}/log`,
                            { headers: { "X-Auth-Token": getToken() } });
    if (res.ok) {
      const text = await res.text();
      if (text) {
        document.getElementById("log-section").style.display = "";
        const box = document.getElementById("heal-log");
        if (box.textContent !== text) {
          const atBottom =
            box.scrollHeight - box.scrollTop - box.clientHeight < 60;
          box.textContent = text;
          if (atBottom) box.scrollTop = box.scrollHeight;
        }
      }
    }
  } catch (e) { /* log alınamazsa sayfa yine çalışsın */ }

  document.getElementById("heal-title").textContent = heal.scenario;
  document.getElementById("heal-status").innerHTML = badge(heal.status);
  document.getElementById("heal-meta").innerHTML =
    `sınıf: <b>${esc(heal.failure_class || "-")}</b>&nbsp; agent:
     <b>${esc(heal.mode || "-")}</b>${heal.model ? `&nbsp; model:
     <b>${esc(heal.model)}</b>` : ""}&nbsp; branch: <b>${esc(heal.branch || "-")}</b>`;

  document.getElementById("stages").innerHTML = (heal.stages || []).map((s) => `
    <tr>
      <td>${esc(s.stage)}</td>
      <td>${s.ok ? '<span class="ok">✓</span>' : '<span class="err">✗</span>'}</td>
      <td class="muted" style="font-family:monospace; font-size:12.5px;
          word-break:break-all">${esc(s.detail || "")}</td>
    </tr>`).join("") ||
    `<tr><td colspan="3" class="muted">Başlatılıyor…</td></tr>`;

  if (heal.diff) {
    document.getElementById("diff-section").style.display = "";
    document.getElementById("diff").innerHTML = heal.diff.split("\n").map((l) => {
      let cls = "";
      if (l.startsWith("+") && !l.startsWith("+++")) cls = "diff-add";
      else if (l.startsWith("-") && !l.startsWith("---")) cls = "diff-del";
      else if (l.startsWith("@@")) cls = "diff-hunk";
      return `<span class="${cls}">${esc(l)}</span>`;
    }).join("\n");
  }

  document.getElementById("heal-actions").style.display =
    heal.status === "proposed" ? "" : "none";

  const banner = document.getElementById("result-banner");
  if (heal.status === "approved") {
    banner.style.display = "";
    banner.innerHTML = `✓ Onaylandı — düzeltme <b>${esc(heal.branch)}</b>
      branch'inde. Projede inceleyip merge/push edebilirsiniz.`;
  } else if (heal.status === "needs_human") {
    banner.style.display = "";
    banner.textContent = "Bu hata otomatik patch için güvenli değil — " +
      "aşama detayındaki gerekçeyle birlikte insan incelemesi gerekiyor.";
  }
  return heal.status;
}

async function resolveHeal(healId, action) {
  try {
    await api(`/api/heals/${encodeURIComponent(healId)}/${action}`,
              { method: "POST" });
    await refreshHeal(healId);
  } catch (e) {
    alert("İşlem başarısız: " + e.message);
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;",
              '"': "&quot;", "'": "&#39;" }[c]));
}
