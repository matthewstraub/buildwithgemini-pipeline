/**
 * Job Pipeline Agent — Professional Web Dashboard Client Application Logic
 */

const STAGES = [
  { id: "applied", label: "Applied", color: "#38bdf8" },
  { id: "screen_scheduled", label: "Screen Scheduled", color: "#fbbf24" },
  { id: "screen_done", label: "Screen Done", color: "#c084fc" },
  { id: "onsite_scheduled", label: "Onsite Scheduled", color: "#f472b6" },
  { id: "onsite_done", label: "Onsite Done", color: "#a855f7" },
  { id: "offer", label: "Offer", color: "#34d399" },
  { id: "rejected", label: "Rejected", color: "#f87171" },
  { id: "stale", label: "Stale", color: "#64748b" }
];

let globalApplications = [];
let currentDraftSlug = null;

document.addEventListener("DOMContentLoaded", () => {
  loadDashboardData();
});

function switchTab(tabName) {
  document.querySelectorAll(".nav-item").forEach(tab => tab.classList.remove("active"));
  document.querySelectorAll(".view-panel").forEach(view => {
    view.classList.add("hidden");
    view.classList.remove("active");
  });

  const targetTab = document.getElementById(`tab-${tabName}`);
  const targetView = document.getElementById(`view-${tabName}`);
  if (targetTab && targetView) {
    targetTab.classList.add("active");
    targetView.classList.remove("hidden");
    targetView.classList.add("active");
  }

  if (tabName === "reports") {
    loadReports();
  }
}

async function loadDashboardData() {
  try {
    const res = await fetch("/api/applications");
    const data = await res.json();
    globalApplications = data.applications || [];
    renderStats(globalApplications);
    renderKanbanBoard(globalApplications);
  } catch (err) {
    console.error("Failed to load applications:", err);
  }
}

function renderStats(apps) {
  const total = apps.length;
  const attentionCount = apps.filter(a => a.needs_attention).length;
  const inFlightCount = apps.filter(a => ["screen_scheduled", "screen_done", "onsite_scheduled", "onsite_done"].includes(a.stage)).length;
  const staleCount = apps.filter(a => ["stale", "rejected", "withdrawn"].includes(a.stage)).length;

  document.getElementById("stat-total").innerText = total;
  document.getElementById("stat-attention").innerText = attentionCount;
  document.getElementById("stat-inflight").innerText = inFlightCount;
  document.getElementById("stat-stale").innerText = staleCount;

  const alertBar = document.getElementById("attention-alert-bar");
  if (attentionCount > 0) {
    alertBar.classList.remove("hidden");
    document.getElementById("alert-title").innerText = `${attentionCount} Application${attentionCount > 1 ? 's' : ''} Require Follow-Up Today`;
  } else {
    alertBar.classList.add("hidden");
  }
}

function renderKanbanBoard(apps) {
  const grid = document.getElementById("kanban-grid");
  grid.innerHTML = "";

  STAGES.forEach(stageObj => {
    const stageApps = apps.filter(a => a.stage === stageObj.id);

    const colEl = document.createElement("div");
    colEl.className = "kanban-col";
    colEl.innerHTML = `
      <div class="col-header">
        <span class="col-title" style="color: ${stageObj.color}">
          ● ${stageObj.label}
        </span>
        <span class="col-count">${stageApps.length}</span>
      </div>
      <div class="cards-container" id="col-${stageObj.id}"></div>
    `;

    grid.appendChild(colEl);
    const container = colEl.querySelector(`.cards-container`);

    stageApps.forEach(app => {
      const cardEl = createApplicationCard(app);
      container.appendChild(cardEl);
    });
  });
}

function createApplicationCard(app) {
  const card = document.createElement("div");
  card.className = `app-card ${app.needs_attention ? 'needs-attn' : ''}`;

  const companyUrl = app.url ? `<a href="${app.url}" target="_blank" class="card-company">${app.company} ↗</a>` : `<span class="card-company">${app.company}</span>`;

  let actionHtml = "";
  if (app.needs_attention) {
    actionHtml = `
      <div class="action-inline-bar">
        <span>⚠️ ${app.next_action}</span>
        <button class="btn btn-xs btn-amber" onclick="openDraftModal('${app.slug}', '${app.company}')">Draft</button>
      </div>
    `;
  } else if (app.next_action) {
    actionHtml = `<div class="quiet-tag">${app.next_action}</div>`;
  }

  card.innerHTML = `
    <div>
      ${companyUrl}
      <div class="card-role">${app.role}</div>
    </div>
    <div class="card-meta-row">
      <span class="badge badge-${app.location_type || 'remote'}">${app.location_type || 'remote'}</span>
      <span class="badge badge-source">${app.source}</span>
    </div>
    ${actionHtml}
    <div class="quiet-tag">Quiet: ${app.quiet_bd} business days</div>
  `;
  return card;
}

async function handleVettingSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-vet-submit");
  btn.disabled = true;
  btn.innerHTML = "<span>Analyzing Message...</span>";

  const payload = {
    sender_email: document.getElementById("vet-sender").value || null,
    reply_to_email: document.getElementById("vet-replyto").value || null,
    claimed_company: document.getElementById("vet-company").value || null,
    claimed_role: document.getElementById("vet-role").value || null,
    message_text: document.getElementById("vet-message").value
  };

  try {
    const res = await fetch("/api/vet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    renderVettingResult(result);
  } catch (err) {
    alert("Vetting analysis failed: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg><span>Evaluate Outreach Risk</span>`;
  }
}

function renderVettingResult(res) {
  const card = document.getElementById("vetting-result-card");
  card.classList.remove("hidden");

  const badge = document.getElementById("verdict-badge");
  badge.innerText = res.verdict.toUpperCase().replace("_", " ");
  badge.className = "verdict-tag";

  if (res.verdict === "likely_fraudulent") {
    badge.classList.add("verdict-fraudulent");
  } else if (res.verdict === "needs_verification") {
    badge.classList.add("verdict-verification");
  } else {
    badge.classList.add("verdict-legitimate");
  }

  document.getElementById("legit-status").innerText = res.role_legitimate ? "✅ Genuine Role" : "⚠️ Unverified Role";
  document.getElementById("safety-status").innerText = res.channel_safe ? "✅ Safe Channel" : "🚨 Suspicious Channel";

  const againstList = document.getElementById("signals-against-list");
  againstList.innerHTML = (res.signals_against || []).map(s => `<li>• ${s}</li>`).join("");

  const forList = document.getElementById("signals-for-list");
  forList.innerHTML = (res.signals_for || []).map(s => `<li>• ${s}</li>`).join("");

  const actionsList = document.getElementById("actions-list");
  actionsList.innerHTML = (res.recommended_action || []).map(a => `<li>• ${a}</li>`).join("");
}

async function openDraftModal(slug, companyName) {
  currentDraftSlug = slug;
  document.getElementById("draft-modal-title").innerText = `Follow-Up Email Draft — ${companyName}`;
  const editor = document.getElementById("draft-editor");
  editor.value = "Generating draft via Gemini 2.5 Flash...";
  document.getElementById("draft-modal").classList.remove("hidden");

  try {
    let res = await fetch(`/api/drafts/${slug}`);
    if (!res.ok) {
      res = await fetch(`/api/draft/${slug}`, { method: "POST" });
    }
    const data = await res.json();
    editor.value = data.content || "No draft content found.";
  } catch (err) {
    editor.value = "Error generating draft: " + err;
  }
}

function closeDraftModal() {
  document.getElementById("draft-modal").classList.add("hidden");
}

function copyDraftToClipboard() {
  const text = document.getElementById("draft-editor").value;
  navigator.clipboard.writeText(text);
  alert("Draft copied to clipboard!");
}

function openNewAppModal() {
  document.getElementById("new-app-modal").classList.remove("hidden");
}

function closeNewAppModal() {
  document.getElementById("new-app-modal").classList.add("hidden");
}

async function handleNewAppSubmit(e) {
  e.preventDefault();
  const payload = {
    company: document.getElementById("new-company").value,
    role: document.getElementById("new-role").value,
    url: document.getElementById("new-url").value || null,
    source: document.getElementById("new-source").value,
    location_type: document.getElementById("new-location").value,
    stage: document.getElementById("new-stage").value,
    applied_on: new Date().toISOString().split("T")[0],
    stage_changed_on: new Date().toISOString().split("T")[0]
  };

  try {
    const res = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      closeNewAppModal();
      loadDashboardData();
    }
  } catch (err) {
    alert("Error saving application: " + err);
  }
}

async function loadReports() {
  try {
    const resDigest = await fetch("/api/reports/digest");
    const digestData = await resDigest.json();
    document.getElementById("digest-preview").innerText = digestData.digest || "";

    const resSummary = await fetch("/api/reports/summary");
    const summaryData = await resSummary.json();
    document.getElementById("summary-preview").innerText = summaryData.summary || "";
  } catch (err) {
    console.error("Failed to load reports:", err);
  }
}
