const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const state = {
  meeting: null,
  roleCards: [],
  roleMeta: { executors: [], domains: [], styles: [] },
  pendingInvited: new Set(),
  editingCardId: "",
  libraryDomain: "all",
  pollTimer: null,
};

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  el.classList.toggle("toast-error", isError);
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 4000);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data.error) throw new Error(data.error);
  return data;
}

function escapeHtml(s) {
  return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function initials(name) {
  return String(name || "G").split(/[-_\s]/).slice(0, 2).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function avatarClass(card) {
  return card?.kind || "arch";
}

function voiceMeter() {
  return '<span class="voice-meter" aria-hidden="true"><span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span></span>';
}

function invitedSet(m) {
  const s = new Set(state.pendingInvited);
  for (const id of m?.invited_cards || []) s.add(id);
  return s;
}

function pendingGuestRows() {
  return [...state.pendingInvited].map((cid) => {
    const card = cardById(cid);
    return {
      id: `pending-${cid}`,
      card_id: cid,
      invited: true,
      card_name: card?.name || cid,
      model: cardModelLabel(card) || card?.model || "",
      role: card?.role || card?.domain || "",
      card_summary: card?.summary || card?.rules || "",
    };
  });
}

function getInvitedRows(m) {
  if (m?.active) {
    return (m.hosting?.guests || []).filter((g) => g.invited);
  }
  return pendingGuestRows();
}

function cardById(id) {
  return state.roleCards.find((c) => c.id === id);
}

function displayName(row, card) {
  return row.card_name || card?.name || row.id;
}

function statusMap(m) {
  return new Map((m?.council_status || []).map((s) => [s.guest, s]));
}

function speakingGuestId(m) {
  for (const s of m?.council_status || []) {
    if (s.status === "running") return s.guest;
  }
  return m?.interactive?.current_speaker || null;
}

function renderInvitedChips(m) {
  const box = $("#invited-chips");
  const invited = invitedSet(m);
  if (!invited.size) {
    box.innerHTML = '<span class="muted">尚未邀请角色</span>';
    return;
  }
  box.innerHTML = [...invited].map((cid) => {
    const card = cardById(cid);
    const name = card?.name || cid;
    return `<span class="chip">${escapeHtml(name)}<button type="button" data-uninvite="${escapeHtml(cid)}" title="移除">×</button></span>`;
  }).join("");
  box.querySelectorAll("[data-uninvite]").forEach((btn) => {
    btn.addEventListener("click", () => uninviteCard(btn.dataset.uninvite));
  });
}

function renderMeetingList() {
  const meetings = state.meeting?.meetings || [];
  const box = $("#meeting-list");
  if (!meetings.length) {
    box.innerHTML = '<p class="muted">发布议题后将显示在这里</p>';
    return;
  }
  box.innerHTML = meetings.map((item) => `
    <button type="button" class="agenda-item ${item.is_current ? "active" : ""}" data-id="${escapeHtml(item.meeting_id)}">
      <strong>${escapeHtml(item.topic || item.meeting_id)}</strong>
      <div class="agenda-meta">
        <span class="tag">${escapeHtml(item.status)}</span>
        <span class="tag">R${item.round || 0}</span>
      </div>
    </button>`).join("");
  box.querySelectorAll(".agenda-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api("/api/meeting/switch", { method: "POST", body: JSON.stringify({ meeting_id: btn.dataset.id }) });
      await refreshAll();
    });
  });
}

const HITL_REASON_LABELS = {
  every_n_rounds: "已达轮次上限，需主持人放行",
  guest_failure: "有嘉宾失败，需主持人决策",
};

const STATUS_CLASS = {
  done: "",
  running: "speaking",
  queued: "queued",
  failed: "failed",
  skipped: "skipped",
  idle: "",
};

function renderHitlBanner(m) {
  const el = $("#hitl-banner");
  if (!m?.active || !m?.owner_required) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const hitl = m.hitl || {};
  const reason = hitl.reason || "owner_required";
  const label = HITL_REASON_LABELS[reason] || `需主持人介入（${reason}）`;
  el.hidden = false;
  el.innerHTML = `<strong>⏸ Owner 闸门</strong><span>${escapeHtml(label)}</span><span class="muted">Round ${hitl.round || m.round || 0}</span>`;
}

function renderPartialBanner(m) {
  const el = $("#partial-banner");
  const warnings = m?.partial_warnings || [];
  if (!m?.active || !warnings.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const latest = warnings[warnings.length - 1];
  const failed = (latest?.failed_guests || []).join(", ");
  el.hidden = false;
  el.innerHTML = `<strong>⚠ 部分成功</strong><span>Round ${latest?.round || "?"} · 失败：${escapeHtml(failed || "—")}</span>`;
}

function renderSpeakers(m) {
  const strip = $("#speaker-strip");
  const online = $("#online-list");
  const rows = getInvitedRows(m);
  const speaking = speakingGuestId(m);
  const sm = statusMap(m);

  if (!rows.length) {
    strip.innerHTML = '<p class="empty-state">点击「邀请已有角色」或「创建智能体角色卡」</p>';
    online.innerHTML = '<p class="muted">暂无在线嘉宾</p>';
    $("#pill-guests").textContent = "0 位 AI 嘉宾在线";
    return;
  }

  $("#pill-guests").textContent = `${rows.length} 位 AI 嘉宾在线`;

  const htmlFor = (row) => {
    const card = cardById(row.card_id || row.id);
    const name = displayName(row, card);
    const model = row.model_label || cardModelLabel(card) || row.model || "";
    const st = sm.get(row.id) || { status: "idle", detail: "待命" };
    const cls = avatarClass(card || { kind: avatarClass({ id: row.id }) });
    const statusCls = row.id === speaking ? "speaking" : (STATUS_CLASS[st.status] || "");
    const phaseTag = st.phase ? `<span class="phase-tag phase-${escapeHtml(st.phase)}">${escapeHtml(st.phase)}</span>` : "";
    const cardActive = row.id === speaking ? "active" : "";
    return {
      strip: `<article class="speaker ${statusCls}">
        <div class="avatar ${cls}">${initials(name)}</div>
        <div><div class="speaker-name">${escapeHtml(name)} ${phaseTag}</div>
        <div class="speaker-role">${escapeHtml(model)} · ${escapeHtml(st.detail)}</div></div></article>`,
      online: `<article class="guest-card ${cardActive}" data-edit-card="${escapeHtml(card?.source === "custom" ? card.id : "")}">
        <div class="avatar ${cls}">${initials(name)}</div>
        <div><div class="speaker-name">${escapeHtml(name)}</div><div class="speaker-role">${escapeHtml(model)}</div></div>
        ${voiceMeter()}</article>`,
    };
  };

  strip.innerHTML = rows.map((r) => htmlFor(r).strip).join("");
  online.innerHTML = rows.map((r) => htmlFor(r).online).join("");
  online.querySelectorAll("[data-edit-card]").forEach((el) => {
    const cid = el.dataset.editCard;
    if (cid) el.addEventListener("dblclick", () => openAgentModal(cid));
  });
}

function renderChat(m) {
  const log = $("#chat-log");
  const chat = m?.chat || [];
  if (!chat.length) {
    log.innerHTML = '<div class="empty-state">还没有讨论。<br>邀请角色后点击「轮流发言」。</div>';
    return;
  }
  log.innerHTML = chat.map((msg) => {
    if (msg.kind === "system") {
      return `<article class="message system"><div class="bubble"><div class="byline"><span>系统</span><span>${escapeHtml(msg.timestamp || "")}</span></div><p>${escapeHtml(msg.content || "")}</p></div></article>`;
    }
    const mine = msg.kind === "owner";
    return `<article class="message ${mine ? "me" : ""}">
      <div class="avatar ${mine ? "owner" : avatarClass({ kind: "arch" })}">${mine ? "我" : initials(msg.author)}</div>
      <div class="bubble"><div class="byline"><span>${escapeHtml(msg.author_label || msg.author)}</span><span>${escapeHtml(msg.timestamp || "")}</span></div>
      <p>${escapeHtml(msg.content || "")}</p></div></article>`;
  }).join("");
  log.scrollTop = log.scrollHeight;
}

function renderSummary(m) {
  const box = $("#summary-list");
  const rows = getInvitedRows(m);
  const positions = m?.guest_positions || [];
  const byGuest = new Map(positions.map((p) => [p.guest, p]));

  if (!rows.length) {
    box.innerHTML = '<p class="muted">邀请角色并跑一轮后显示观点摘要</p>';
    return;
  }

  box.innerHTML = rows.map((row) => {
    const card = cardById(row.card_id || row.id);
    const name = displayName(row, card);
    const p = byGuest.get(row.id);
    const text = p?.position || card?.summary || row.card_summary || row.role || "（等待发言）";
    const model = cardModelLabel(card) || row.model || "";
    return `<article class="summary-card"><div class="summary-title"><span>${escapeHtml(name)}</span><span class="tag">${escapeHtml(model)}</span></div><p>${escapeHtml(text)}</p></article>`;
  }).join("");
}

function renderDecision(m) {
  const box = $("#decision-box");
  const sec = (title, items) => {
    const list = (items || []).filter(Boolean).slice(0, 5);
    if (!list.length) return `<div class="decision-section"><h4>${title}</h4><ul><li>（暂无）</li></ul></div>`;
    return `<div class="decision-section"><h4>${title}</h4><ul>${list.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul></div>`;
  };
  box.innerHTML = sec("已确认", m?.confirmed_points) + sec("分歧", m?.conflicts) + sec("未决", m?.open_questions);
}

function renderRuntimePolicy(m) {
  const panel = $("#runtime-policy-panel");
  if (!panel) return;
  const active = !!m?.active && m?.status !== "stopped";
  panel.querySelectorAll("select, input, button").forEach((el) => {
    el.disabled = !active;
  });
  if (!active) return;
  const select = $("#failure-policy-select");
  if (select && m.failure_policy) select.value = m.failure_policy;
  const chk = $("#require-before-promote");
  if (chk) chk.checked = !!(m.hitl && m.hitl.require_before_promote);
}

function updateHeader(m) {
  const active = !!m?.active;
  ["btn-run-interactive", "btn-run-parallel", "btn-context", "btn-stop"].forEach((id) => {
    $(`#${id}`).disabled = !active || m?.status === "stopped";
  });
  $("#btn-continue").hidden = !m?.owner_required;
  renderHitlBanner(m);
  renderPartialBanner(m);

  if (!active) {
    $("#active-topic").textContent = "选择或发布议题";
    $("#meeting-context").textContent = "邀请角色后点击 + 发布议题，或先在中栏预览嘉宾阵容";
    $("#pill-status").innerHTML = '<span class="dot idle"></span>未开始';
    renderSpeakers(m);
    renderChat(null);
    renderSummary(m);
    renderDecision(null);
  renderInvitedChips(m);
  renderRuntimePolicy(m);
  return;
  }

  const mode = m.meeting_mode === "interactive" ? "投资研讨会（交互话轮）" : "并行研究会议";
  $("#active-topic").textContent = m.topic || m.meeting_id;
  const policy = m.failure_policy ? ` · 策略 ${m.failure_policy}` : "";
  $("#meeting-context").textContent = `${mode} · ${m.current_focus ? "上下文：" + m.current_focus : "上下文未设置"} · Round ${m.round || 0}${policy}`;
  $("#meeting-type-label").textContent = mode;
  const dot = m.task?.running ? "running" : m.status === "stopped" ? "stopped" : "idle";
  $("#pill-status").innerHTML = `<span class="dot ${dot}"></span>${m.status === "stopped" ? "已结束" : m.task?.running ? "进行中" : "会议中"}`;

  renderSpeakers(m);
  renderChat(m);
  renderSummary(m);
  renderDecision(m);
  renderInvitedChips(m);
  renderRuntimePolicy(m);
}

function applyMeeting(m) {
  state.meeting = m;
  if (m?.role_cards) state.roleCards = m.role_cards;
  if (m?.invited_cards) {
    state.pendingInvited = new Set();
  }
  updateHeader(m);
  setTaskIndicator(m?.task);
  renderMeetingList();
}

function setTaskIndicator(task) {
  $("#task-panel").hidden = !task?.running;
  if (task?.running) {
    const labels = { context: "生成上下文…", run_parallel: "并行讨论…", run_interactive: "交互话轮…" };
    $("#task-text").textContent = labels[task.task] || "运行中…";
    startPolling();
  } else if (task?.error) toast(task.error, true);
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(refreshMeeting, 2500);
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function refreshMeeting() {
  const m = await api("/api/meeting/current");
  applyMeeting(m);
}

async function refreshRoleCards() {
  const data = await api("/api/role-cards");
  state.roleCards = data.cards || [];
  state.roleMeta = data.catalog || state.roleMeta;
  fillAgentFormOptions();
}

async function refreshAll() {
  await refreshRoleCards();
  const m = await api("/api/meeting/current");
  m.meetings = (await api("/api/meetings")).meetings;
  applyMeeting(m);
}

function executorLabel(ex) {
  const model = String(ex.model || "").toLowerCase();
  if (model.includes("claude")) return "Claude";
  if (model.includes("codex") || model.includes("gpt")) return "GPT / Codex";
  if (model.includes("grok")) return "Grok";
  if (model.includes("qwen")) return "Qwen";
  if (model.includes("gemini")) return "Gemini";
  if (model.includes("llama") || model.includes("deepseek")) return "Llama";
  if (model.includes("nemotron")) return "Nemotron";
  if (model.includes("cohere") || model.includes("north")) return "North";
  return ex.executor_id || ex.model || "自定义";
}

function cardModelLabel(card) {
  return card?.model_label || executorLabel({ model: card?.model, executor_id: card?.executor_id }) || "模型";
}

function libraryCards() {
  return state.roleCards.filter((c) => c.source === "preset" || c.source === "custom");
}

function matchesLibraryFilter(card, q, domain) {
  if (domain !== "all" && card.domain !== domain) return false;
  if (!q) return true;
  const hay = `${card.name} ${cardModelLabel(card)} ${card.domain} ${card.style} ${card.rules} ${card.summary}`.toLowerCase();
  return hay.includes(q);
}

function renderLibraryCard(card, invited) {
  const inMeeting = invited.has(card.id);
  const editBtn = card.source === "custom"
    ? `<button type="button" class="link-btn" data-edit="${escapeHtml(card.id)}">编辑</button>` : "";
  const badge = card.source === "custom" ? '<span class="tag tag-custom">我的</span>' : "";
  return `<button type="button" class="library-card" data-invite="${escapeHtml(card.id)}" ${inMeeting ? "disabled" : ""}>
    <div class="avatar ${avatarClass(card)}">${initials(card.name)}</div>
    <div class="library-main">
      <div class="library-title">${escapeHtml(card.name)} ${badge}</div>
      <div class="library-desc">调用：${escapeHtml(cardModelLabel(card))} · ${escapeHtml(card.domain || "")}</div>
      <div class="library-desc">${escapeHtml(card.style || "")}</div>
      <div class="library-desc library-rules">${escapeHtml(card.rules || card.summary || "")}</div>
    </div>
    <div class="library-actions"><span class="tag">${inMeeting ? "已在会中" : "邀请"}</span>${editBtn}</div>
  </button>`;
}

function renderDomainFilters() {
  const box = $("#domain-filters");
  if (!box) return;
  const domains = ["all", ...(state.roleMeta.domains || [])];
  const labels = { all: "全部" };
  box.innerHTML = domains.map((d) =>
    `<button type="button" class="filter-chip ${state.libraryDomain === d ? "active" : ""}" data-domain="${escapeHtml(d)}">${escapeHtml(labels[d] || d)}</button>`
  ).join("");
  box.querySelectorAll("[data-domain]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.libraryDomain = btn.dataset.domain;
      renderDomainFilters();
      renderAgentLibrary($("#agent-search").value);
    });
  });
}

function fillAgentFormOptions() {
  const exSel = $("#agent-executor");
  const domSel = $("#agent-domain");
  const styleSel = $("#agent-style");
  const baseSel = $("#agent-base-guest");
  if (!exSel) return;

  exSel.innerHTML = (state.roleMeta.executors || []).map((e) =>
    `<option value="${escapeHtml(e.executor_id)}">${escapeHtml(executorLabel(e))}</option>`).join("");
  domSel.innerHTML = (state.roleMeta.domains || []).map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join("");
  styleSel.innerHTML = (state.roleMeta.styles || []).map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
  baseSel.innerHTML = '<option value="">自动</option>' + libraryCards().map((c) =>
    `<option value="${escapeHtml(c.base_guest || c.id)}">${escapeHtml(c.name)}</option>`).join("");
}

function renderAgentLibrary(filter = "") {
  const box = $("#agent-library-list");
  const q = filter.trim().toLowerCase();
  const invited = invitedSet(state.meeting);
  const cards = libraryCards().filter((card) => matchesLibraryFilter(card, q, state.libraryDomain));
  const presets = cards.filter((c) => c.source === "preset");
  const custom = cards.filter((c) => c.source === "custom");

  if (!cards.length) {
    box.innerHTML = '<p class="muted library-empty">没有匹配的角色，试试换个筛选或创建新角色卡。</p>';
    return;
  }

  const sections = [];
  if (presets.length) {
    sections.push(`<div class="library-section"><div class="library-section-title">预设角色</div>${presets.map((c) => renderLibraryCard(c, invited)).join("")}</div>`);
  }
  if (custom.length) {
    sections.push(`<div class="library-section"><div class="library-section-title">我的角色卡</div>${custom.map((c) => renderLibraryCard(c, invited)).join("")}</div>`);
  }
  box.innerHTML = sections.join("");

  box.querySelectorAll("[data-invite]").forEach((btn) => {
    btn.addEventListener("click", () => inviteCard(btn.dataset.invite));
  });
  box.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openAgentModal(btn.dataset.edit);
    });
  });
}

async function inviteCard(cardId) {
  if (state.meeting?.active) {
    const res = await api("/api/meeting/invite", { method: "POST", body: JSON.stringify({ card_id: cardId }) });
    if (!res.ok) throw new Error(res.error);
    applyMeeting(res.meeting);
    const card = cardById(cardId);
    toast(`${card?.name || cardId} 已加入会议`);
    renderAgentLibrary($("#agent-search").value);
    return;
  }
  state.pendingInvited.add(cardId);
  renderInvitedChips(state.meeting);
  renderSpeakers(state.meeting);
  renderSummary(state.meeting);
  renderAgentLibrary($("#agent-search").value);
  toast(`${cardById(cardId)?.name || cardId} 已加入会议`);
}

async function uninviteCard(cardId) {
  if (state.meeting?.active) {
    const res = await api("/api/meeting/uninvite", { method: "POST", body: JSON.stringify({ card_id: cardId }) });
    if (!res.ok) throw new Error(res.error);
    applyMeeting(res.meeting);
    toast("已移除嘉宾");
    return;
  }
  state.pendingInvited.delete(cardId);
  renderInvitedChips(state.meeting);
  renderSpeakers(state.meeting);
  renderSummary(state.meeting);
  renderAgentLibrary($("#agent-search").value);
}

function openAgentModal(cardId = "") {
  fillAgentFormOptions();
  const card = cardId ? cardById(cardId) : null;
  state.editingCardId = cardId;
  $("#agent-edit-id").value = cardId;
  $("#agent-modal-title").textContent = cardId ? "编辑智能体角色卡" : "创建智能体角色卡";
  $("#delete-agent").hidden = !card || card.source !== "custom";
  $("#save-agent").textContent = cardId ? "保存" : "保存并加入会议";

  if (card) {
    $("#agent-name").value = card.name || "";
    $("#agent-executor").value = card.executor_id || "";
    $("#agent-style").value = card.style || state.roleMeta.styles?.[0] || "";
    $("#agent-domain").value = card.domain || state.roleMeta.domains?.[0] || "";
    $("#agent-model").value = card.model || "";
    $("#agent-base-guest").value = card.base_guest || "";
    $("#agent-rules").value = card.rules || "";
    $("#agent-memory").value = card.memory || "";
  } else {
    $("#agent-name").value = "逆向风险官";
    $("#agent-rules").value = "必须先给判断，再给证据、风险、反证条件和退出信号。禁止给确定性收益承诺。";
    $("#agent-memory").value = "";
    onExecutorChange();
  }
  $("#agent-modal").classList.add("open");
}

function closeAgentModal() {
  $("#agent-modal").classList.remove("open");
  state.editingCardId = "";
}

function onExecutorChange() {
  const eid = $("#agent-executor").value;
  const ex = (state.roleMeta.executors || []).find((e) => e.executor_id === eid);
  if (ex) {
    $("#agent-model").value = ex.model || "";
    if (! $("#agent-base-guest").value && ex.default_guest) {
      $("#agent-base-guest").value = ex.default_guest;
    }
  }
}

function collectAgentForm() {
  return {
    name: $("#agent-name").value.trim(),
    executor_id: $("#agent-executor").value,
    model: $("#agent-model").value.trim(),
    base_guest: $("#agent-base-guest").value,
    style: $("#agent-style").value,
    domain: $("#agent-domain").value,
    rules: $("#agent-rules").value.trim(),
    memory: $("#agent-memory").value.trim(),
  };
}

async function saveAgent(joinMeeting = true) {
  const payload = collectAgentForm();
  if (!payload.name) return toast("请填写角色名称", true);
  const wasEdit = Boolean(state.editingCardId);
  const res = await api("/api/role-cards/save", {
    method: "POST",
    body: JSON.stringify({ id: state.editingCardId, card: payload }),
  });
  if (!res.ok) throw new Error(res.error);
  state.roleCards = res.cards || state.roleCards;
  const card = res.card;
  closeAgentModal();
  toast(wasEdit ? "角色卡已更新" : "角色卡已创建");

  if (joinMeeting && card?.id) {
    await inviteCard(card.id);
  } else {
    renderSpeakers(state.meeting);
    renderSummary(state.meeting);
    renderAgentLibrary($("#agent-search").value);
  }
  await refreshRoleCards();
}

async function deleteAgent() {
  if (!state.editingCardId) return;
  if (!confirm("确定删除此角色卡？")) return;
  const res = await api("/api/role-cards/delete", {
    method: "POST",
    body: JSON.stringify({ id: state.editingCardId }),
  });
  if (!res.ok) throw new Error(res.error);
  closeAgentModal();
  await refreshAll();
  toast("角色卡已删除");
}

async function publishAgenda() {
  const topic = $("#topic-input").value.trim();
  if (!topic) return toast("请输入议题", true);
  const invited = [...invitedSet(state.meeting)];
  if (!invited.length) return toast("请先邀请至少一位角色", true);

  const res = await api("/api/meeting/start", {
    method: "POST",
    body: JSON.stringify({
      topic,
      mode: $("#meeting-mode").value,
      owner_question: topic,
      context_scope: $("#scope-input").value.trim(),
      run_context_after: $("#chk-run-context").checked,
      invited_card_ids: invited,
    }),
  });
  if (!res.ok) throw new Error(res.error);
  state.pendingInvited.clear();
  await refreshAll();
  toast("议题已发布，会议已开始");
  startPolling();
}

$("#btn-add-agenda").addEventListener("click", () => publishAgenda().catch((e) => toast(e.message, true)));
$("#meeting-mode").addEventListener("change", (e) => {
  $("#meeting-type-label").textContent = e.target.selectedOptions[0].textContent;
});

$("#open-invite-modal").addEventListener("click", () => {
  state.libraryDomain = "all";
  renderDomainFilters();
  renderAgentLibrary();
  $("#invite-modal").classList.add("open");
});
$("#close-invite-modal").addEventListener("click", () => $("#invite-modal").classList.remove("open"));
$("#cancel-invite").addEventListener("click", () => $("#invite-modal").classList.remove("open"));
$("#agent-search").addEventListener("input", (e) => renderAgentLibrary(e.target.value));

$("#open-agent-modal").addEventListener("click", () => openAgentModal());
$("#close-agent-modal").addEventListener("click", closeAgentModal);
$("#cancel-agent").addEventListener("click", closeAgentModal);
$("#save-agent").addEventListener("click", () => saveAgent(!state.editingCardId).catch((e) => toast(e.message, true)));
$("#delete-agent").addEventListener("click", () => deleteAgent().catch((e) => toast(e.message, true)));
$("#agent-executor").addEventListener("change", onExecutorChange);

$("#composer-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#message-input").value.trim();
  if (!text) return;
  try {
    const res = await api("/api/meeting/speak", {
      method: "POST",
      body: JSON.stringify({ mode: "ask", text, run_next: false }),
    });
    if (!res.ok) throw new Error(res.error);
    $("#message-input").value = "";
    applyMeeting(res.meeting);
    toast("发言已记录");
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-run-interactive").addEventListener("click", async () => {
  const res = await api("/api/run-interactive", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(res.error);
  toast("轮流发言已开始");
  startPolling();
});
$("#btn-run-parallel").addEventListener("click", async () => {
  const res = await api("/api/run-parallel", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(res.error);
  toast("并行讨论已开始");
  startPolling();
});
$("#btn-context").addEventListener("click", async () => {
  const scope = $("#scope-input").value.trim() || state.meeting?.current_focus || "";
  if (!scope) return toast("请填写上下文范围", true);
  const res = await api("/api/context", { method: "POST", body: JSON.stringify({ scope }) });
  if (!res.ok) throw new Error(res.error);
  toast("正在生成上下文…");
  startPolling();
});
$("#btn-continue").addEventListener("click", async () => {
  const res = await api("/api/owner/continue", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(res.error);
  applyMeeting(res.meeting);
});
$("#btn-stop").addEventListener("click", async () => {
  if (!confirm("确定结束会议？")) return;
  const res = await api("/api/owner/stop", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(res.error);
  stopPolling();
  await refreshAll();
  toast("会议已结束");
});
$("#btn-refresh-board").addEventListener("click", () => refreshMeeting().catch((e) => toast(e.message, true)));
$("#btn-save-runtime-policy").addEventListener("click", async () => {
  try {
    const res = await api("/api/meeting/runtime-policy", {
      method: "POST",
      body: JSON.stringify({
        failure_policy: $("#failure-policy-select").value,
        require_before_promote: $("#require-before-promote").checked,
      }),
    });
    if (!res.ok) throw new Error(res.error);
    applyMeeting(res.meeting);
    toast("运行策略已保存");
  } catch (err) {
    toast(err.message, true);
  }
});

(async function init() {
  try {
    await refreshAll();
    if (state.meeting?.active) startPolling();
  } catch (err) {
    toast("加载失败: " + err.message, true);
  }
})();