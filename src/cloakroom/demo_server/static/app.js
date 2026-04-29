const TOKEN_PATTERN = /\[[A-Z][A-Z0-9_]*_\d{3,5}\]/g;

const state = {
  activeScreen: "shield",
  sampleName: "customer_escalation_en.md",
  sampleLanguage: "en",
  originalText: "",
  sampleMarkers: [],
  shield: null,
  trust: null,
  restore: null,
  restoreMode: "clean",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const elements = {
  sampleSelect: $("#sample-select"),
  sourceInput: $("#source-input"),
  pasteButton: $("#paste-button"),
  fileButton: $("#file-button"),
  fileInput: $("#file-input"),
  sourceLanguage: $("#source-language"),
  sourceSubtitle: $("#source-subtitle"),
  shieldButton: $("#shield-button"),
  clearSourceButton: $("#clear-source-button"),
  loadSampleButton: $("#load-sample-button"),
  loadFailureButton: $("#load-failure-button"),
  exportReportButton: $("#export-report-button"),
  resetButton: $("#reset-button"),
  pipelineTitle: $("#pipeline-title"),
  pipelineStatus: $("#pipeline-status"),
  metricReplaced: $("#metric-replaced"),
  metricLeaks: $("#metric-leaks"),
  metricMappings: $("#metric-mappings"),
  safeOutputTitle: $("#safe-output-title"),
  safeOutputSubtitle: $("#safe-output-subtitle"),
  safeOutput: $("#safe-output"),
  safeStatus: $("#safe-status"),
  copySafeButton: $("#copy-safe-button"),
  goRestoreButton: $("#go-restore-button"),
  reviewTableBody: $("#review-table-body"),
  aiSeesList: $("#ai-sees-list"),
  restoreInput: $("#restore-input"),
  restoreButton: $("#restore-button"),
  restoreStatus: $("#restore-status"),
  restoreOutputTitle: $("#restore-output-title"),
  restoreOutputSubtitle: $("#restore-output-subtitle"),
  restoreOutput: $("#restore-output"),
  restoreError: $("#restore-error"),
  restoreModeBadge: $("#restore-mode-badge"),
  useCleanResponseButton: $("#use-clean-response-button"),
  useMutatedResponseButton: $("#use-mutated-response-button"),
  knownTokensFound: $("#known-tokens-found"),
  verifiedTokens: $("#verified-tokens"),
  changedTokens: $("#changed-tokens"),
  vaultStatus: $("#vault-status"),
  ttlStatus: $("#ttl-status"),
  trustWorkspace: $("#trust-workspace"),
  trustVault: $("#trust-vault"),
  trustTtl: $("#trust-ttl"),
  trustMappings: $("#trust-mappings"),
  trustShields: $("#trust-shields"),
  trustRestores: $("#trust-restores"),
  localProofList: $("#local-proof-list"),
  auditTableBody: $("#audit-table-body"),
  policyList: $("#policy-list"),
  toast: $("#toast"),
};

function iconToken(token) {
  return `<span>${escapeHtml(token)}</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail || payload.error?.message || response.statusText;
    throw new Error(detail);
  }
  return payload;
}

function setActiveScreen(screenName) {
  state.activeScreen = screenName;
  $$(".screen").forEach((screen) => {
    const isActive = screen.dataset.screen === screenName;
    screen.hidden = !isActive;
    screen.classList.toggle("is-active", isActive);
  });
  $$(".tab-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.screenTarget === screenName);
  });
  if (screenName === "trust") {
    refreshTrustCenter();
  }
}

function setPipeline(mode) {
  const steps = ["read", "detect", "replace", "vault", "check"];
  const doneThrough = {
    idle: 0,
    reading: 1,
    detecting: 2,
    replacing: 3,
    vault: 4,
    done: 5,
  }[mode] || 0;

  steps.forEach((step, index) => {
    const item = document.querySelector(`[data-step="${step}"]`);
    item.classList.toggle("is-done", index < doneThrough);
    item.classList.toggle("is-active", index === doneThrough && mode !== "done");
  });

  const labels = {
    idle: ["Ready", "Local workflow"],
    reading: ["Reading", "Original stays local"],
    detecting: ["Detecting", "Personal and confidential data"],
    replacing: ["Tokenizing", "Reversible placeholders"],
    vault: ["Locking vault", "Restore map saved locally"],
    done: ["Ready for AI", "Safe to paste into AI"],
  };
  const [title, status] = labels[mode] || labels.idle;
  elements.pipelineTitle.textContent = title;
  elements.pipelineStatus.textContent = status;
}

async function runShieldAnimation(operation) {
  const modes = ["reading", "detecting", "replacing", "vault"];
  const started = Date.now();
  const resultPromise = operation();
  for (const mode of modes) {
    setPipeline(mode);
    await delay(140);
  }
  const result = await resultPromise;
  const elapsed = Date.now() - started;
  if (elapsed < 760) {
    await delay(760 - elapsed);
  }
  setPipeline("done");
  return result;
}

async function loadSample(name = elements.sampleSelect.value) {
  setBusy(true);
  try {
    const payload = await api("/api/demo/load-sample", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    state.sampleName = payload.sample_name;
    state.sampleLanguage = payload.language;
    state.originalText = payload.original_text;
    state.sampleMarkers = payload.sensitive_markers || [];
    elements.sampleSelect.value = payload.sample_name;
    elements.sourceInput.value = payload.original_text;
    elements.sourceInput.dir = directionFor(payload.original_text);
    elements.sourceLanguage.textContent = languageLabel(payload.language);
    elements.sourceSubtitle.textContent = "Original content is visible locally before shielding.";
    clearShieldOutput();
    setPipeline("idle");
    showToast("Demo sample loaded");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function shieldCurrentText() {
  const text = elements.sourceInput.value.trim();
  if (!text) {
    showToast("Add content before creating an AI-safe version.", true);
    return;
  }

  setBusy(true);
  elements.shieldButton.disabled = true;
  try {
    const payload = await runShieldAnimation(() =>
      api("/api/shield", {
        method: "POST",
        body: JSON.stringify({
          text,
          sample_name: state.sampleName,
          language: state.sampleLanguage,
        }),
      }),
    );
    state.shield = payload;
    state.trust = payload.trust_center;
    state.restore = null;
    renderShield(payload);
    renderTrust(payload.trust_center);
    useCleanResponse();
    showToast("AI-safe version created");
  } catch (error) {
    setPipeline("idle");
    showToast(error.message, true);
  } finally {
    setBusy(false);
    elements.shieldButton.disabled = false;
  }
}

function renderShield(payload) {
  elements.safeOutput.textContent = payload.ai_safe_text || "";
  elements.safeOutput.classList.remove("empty");
  elements.safeOutput.dir = directionFor(payload.ai_safe_text || "");
  elements.safeOutputTitle.textContent = "AI-safe version - safe to paste";
  elements.safeOutputSubtitle.textContent = "Only reversible Cloakroom tokens remain in sensitive positions.";
  setBadge(elements.safeStatus, "Safe to paste into AI", "good");

  elements.metricReplaced.textContent = payload.tokens_applied ?? 0;
  elements.metricLeaks.textContent = payload.leak_check?.leaked_items ?? 0;
  elements.metricMappings.textContent = payload.trust_center?.vault?.mappings_count ?? 0;

  elements.copySafeButton.disabled = !payload.ai_safe_text;
  elements.goRestoreButton.disabled = !payload.simulated_ai_response;
  elements.loadFailureButton.disabled = !payload.mutated_ai_response;
  elements.exportReportButton.disabled = !payload.trust_center;
  elements.restoreButton.disabled = false;
  elements.useCleanResponseButton.disabled = false;
  elements.useMutatedResponseButton.disabled = false;

  renderReviewTable(payload.review_items || []);
  renderAiSeesTokens(payload.review_items || [], payload.ai_safe_text || "");
  updateTopStatus(payload.trust_center);
}

function clearShieldOutput() {
  state.shield = null;
  state.restore = null;
  elements.safeOutput.textContent = "AI-safe text will appear here.";
  elements.safeOutput.classList.add("empty");
  elements.safeOutputTitle.textContent = "AI-safe version";
  elements.safeOutputSubtitle.textContent = "Tokens preserve context without exposing the originals.";
  setBadge(elements.safeStatus, "Not created", "neutral");
  elements.metricReplaced.textContent = "0";
  elements.metricLeaks.textContent = "0";
  elements.metricMappings.textContent = state.trust?.vault?.mappings_count ?? "0";
  elements.copySafeButton.disabled = true;
  elements.goRestoreButton.disabled = true;
  elements.loadFailureButton.disabled = true;
  elements.exportReportButton.disabled = !state.trust;
  elements.restoreButton.disabled = true;
  elements.useCleanResponseButton.disabled = true;
  elements.useMutatedResponseButton.disabled = true;
  elements.restoreInput.value = "";
  elements.restoreOutput.textContent = "Restored text will appear here.";
  elements.restoreOutput.classList.add("empty");
  elements.restoreError.hidden = true;
  renderReviewTable([]);
}

function setCustomSource(text, label = "Custom text loaded locally") {
  state.originalText = text;
  state.sampleLanguage = "auto";
  state.sampleMarkers = [];
  elements.sourceInput.value = text;
  elements.sourceInput.dir = directionFor(text);
  elements.sourceLanguage.textContent = "CUSTOM";
  elements.sourceSubtitle.textContent = label;
  clearShieldOutput();
  setPipeline("idle");
}

function renderReviewTable(items) {
  if (!items.length) {
    elements.reviewTableBody.innerHTML =
      '<tr><td colspan="5">Create an AI-safe version to review detected items.</td></tr>';
    return;
  }
  elements.reviewTableBody.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.risk_type || "Sensitive data")}</td>
          <td><span class="masked-value">${escapeHtml(item.masked_value || "***")}</span></td>
          <td><code>${escapeHtml(item.token || "")}</code></td>
          <td>${escapeHtml(item.confidence || "High")}</td>
          <td>${escapeHtml(item.action || "Shielded")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderAiSeesTokens(items, safeText) {
  const tokens = items.map((item) => item.token).filter(Boolean).slice(0, 7);
  const fallbackTokens = Array.from(new Set(safeText.match(TOKEN_PATTERN) || [])).slice(0, 7);
  const visibleTokens = tokens.length ? tokens : fallbackTokens;
  elements.aiSeesList.innerHTML = visibleTokens.length
    ? visibleTokens.map(iconToken).join("")
    : iconToken("[TOKEN_00001]");
}

function useCleanResponse() {
  if (!state.shield?.simulated_ai_response) {
    return;
  }
  state.restoreMode = "clean";
  elements.restoreInput.value = state.shield.simulated_ai_response;
  elements.restoreInput.dir = directionFor(state.shield.simulated_ai_response);
  setBadge(elements.restoreModeBadge, "Clean", "good");
  renderTokenSummary();
}

function useMutatedResponse() {
  if (!state.shield?.mutated_ai_response) {
    return;
  }
  state.restoreMode = "mutated";
  elements.restoreInput.value = state.shield.mutated_ai_response;
  elements.restoreInput.dir = directionFor(state.shield.mutated_ai_response);
  setBadge(elements.restoreModeBadge, "Mutated", "warn");
  renderTokenSummary();
}

async function restoreCurrentText() {
  const text = elements.restoreInput.value.trim();
  if (!text) {
    showToast("Add an AI response before restoring.", true);
    return;
  }
  setBusy(true);
  elements.restoreButton.disabled = true;
  elements.restoreError.hidden = true;
  try {
    const payload = await api("/api/restore", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    state.restore = payload;
    state.trust = payload.trust_center;
    renderRestore(payload);
    renderTrust(payload.trust_center);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
    elements.restoreButton.disabled = false;
  }
}

function renderRestore(payload) {
  if (payload.ok) {
    elements.restoreOutput.textContent = payload.restored_text || "";
    elements.restoreOutput.classList.remove("empty");
    elements.restoreOutput.dir = directionFor(payload.restored_text || "");
    elements.restoreOutputTitle.textContent = "Restored locally";
    elements.restoreOutputSubtitle.textContent = "Token integrity passed before original values were restored.";
    setBadge(elements.restoreStatus, "Restored locally", "good");
    elements.restoreError.hidden = true;
    showToast("Original values restored locally");
  } else {
    const summary = getTokenSummary();
    const mismatch = summary.firstMismatch
      ? `<br>Expected: <code>${escapeHtml(summary.firstMismatch.expected)}</code><br>Found: <code>${escapeHtml(summary.firstMismatch.found)}</code>`
      : "";
    elements.restoreOutput.textContent = "";
    elements.restoreOutput.classList.add("empty");
    elements.restoreOutputTitle.textContent = "Restore blocked";
    elements.restoreOutputSubtitle.textContent = "Cloakroom refused to guess.";
    setBadge(elements.restoreStatus, "Blocked", "danger");
    elements.restoreError.innerHTML = `
      <strong>Restore blocked</strong>
      ${escapeHtml(payload.error?.message || "A protected token was changed or invented.")}
      ${mismatch}
      <br>No partial restore was created.
    `;
    elements.restoreError.hidden = false;
    showToast("Restore blocked. No partial output was created.", true);
  }
  updateTopStatus(payload.trust_center);
}

async function refreshTrustCenter() {
  try {
    const payload = await api("/api/trust-center");
    state.trust = payload;
    renderTrust(payload);
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderTrust(payload) {
  if (!payload) {
    return;
  }
  const workspace = payload.workspace || {};
  const vault = payload.vault || {};
  const activity = payload.activity || {};
  elements.trustWorkspace.textContent = workspace.workspace_name || "Demo Workspace";
  elements.trustVault.textContent = vault.encrypted ? "Encrypted local vault" : "Vault not created";
  elements.trustTtl.textContent = `${workspace.ttl_hours ?? 24} hours`;
  elements.trustMappings.textContent = vault.mappings_count ?? 0;
  elements.trustShields.textContent = activity.anonymize_count ?? 0;
  elements.trustRestores.textContent = activity.restore_count ?? 0;

  const proof = payload.local_only_proof || {};
  const proofRows = [
    `Bind host: ${proof.bind_host || "127.0.0.1"}`,
    `External AI calls: ${proof.external_ai_calls ?? 0}`,
    "Original values stored locally",
    vault.encrypted ? "Vault encrypted" : "Vault waiting",
    proof.original_values_in_reports === false
      ? "Reports exclude original values"
      : "Reports require review",
  ];
  elements.localProofList.innerHTML = proofRows.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  elements.policyList.innerHTML = (payload.policy || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  renderAuditTable(payload.reports || []);
  updateTopStatus(payload);
}

function renderAuditTable(reports) {
  if (!reports.length) {
    elements.auditTableBody.innerHTML = '<tr><td colspan="5">No audit-safe reports yet.</td></tr>';
    return;
  }
  elements.auditTableBody.innerHTML = reports
    .slice()
    .reverse()
    .map((report) => {
      const counts = Object.entries(report.entity_counts || {})
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ");
      return `
        <tr>
          <td>${escapeHtml(formatDate(report.timestamp || report.created_at || ""))}</td>
          <td>${escapeHtml(report.operation || "anonymize")}</td>
          <td><code>${escapeHtml(report.file_label_safe || report.file_hash || "hash-only")}</code></td>
          <td>${escapeHtml(counts || "0")}</td>
          <td>${report.chain_verified ? "Verified" : "Review"}</td>
        </tr>
      `;
    })
    .join("");
}

function renderTokenSummary() {
  const summary = getTokenSummary();
  elements.knownTokensFound.textContent = summary.knownFound;
  elements.verifiedTokens.textContent = summary.verified;
  elements.changedTokens.textContent = summary.unknown.length;
  elements.restoreButton.disabled = !elements.restoreInput.value.trim() || !state.shield;
}

function getTokenSummary() {
  const known = new Set((state.shield?.review_items || []).map((item) => item.token).filter(Boolean));
  const text = elements.restoreInput.value || "";
  const found = Array.from(new Set(text.match(TOKEN_PATTERN) || []));
  const knownFound = found.filter((token) => known.has(token));
  const unknown = found.filter((token) => !known.has(token));
  const firstMismatch = unknown.length
    ? {
        found: unknown[0],
        expected: closestKnownToken(unknown[0], Array.from(known)),
      }
    : null;
  return {
    found,
    knownFound: knownFound.length,
    verified: knownFound.length,
    unknown,
    firstMismatch,
  };
}

function closestKnownToken(token, knownTokens) {
  const prefix = token.replace(/_\d{3,5}\]$/, "_");
  return knownTokens.find((known) => known.startsWith(prefix)) || knownTokens[0] || "[TOKEN_00001]";
}

async function copySafeText() {
  if (!state.shield?.ai_safe_text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(state.shield.ai_safe_text);
    showToast("AI-safe text copied");
  } catch (_error) {
    showToast("Clipboard permission was not available.", true);
  }
}

async function pasteLocalText() {
  try {
    const text = await navigator.clipboard.readText();
    if (!text.trim()) {
      showToast("Clipboard did not contain text.", true);
      return;
    }
    setCustomSource(text, "Clipboard text is visible locally before shielding.");
    showToast("Text pasted locally");
  } catch (_error) {
    showToast("Clipboard permission was not available.", true);
  }
}

async function loadLocalFile(file) {
  if (!file) {
    return;
  }
  const allowed = /\.(txt|md)$/i.test(file.name) || /^text\//.test(file.type || "");
  if (!allowed) {
    showToast("This demo reads .txt and .md files locally.", true);
    return;
  }
  const text = await file.text();
  setCustomSource(text, `${file.name} loaded locally. File contents were not uploaded.`);
  showToast("File loaded locally");
}

async function resetDemo() {
  setBusy(true);
  try {
    const payload = await api("/api/demo/reset", { method: "POST" });
    state.trust = payload.trust_center;
    renderTrust(payload.trust_center);
    await loadSample(state.sampleName);
    showToast("Demo workspace reset");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function exportAuditJson() {
  const payload = state.trust || state.shield?.trust_center;
  if (!payload) {
    return;
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "cloakroom-audit-safe-report.json";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("Audit-safe JSON exported");
}

function updateTopStatus(payload) {
  const vault = payload?.vault || {};
  const workspace = payload?.workspace || {};
  elements.vaultStatus.textContent = vault.encrypted ? "Local vault active" : "Vault waiting";
  elements.vaultStatus.classList.toggle("good", Boolean(vault.encrypted));
  elements.ttlStatus.textContent = `Expires in ${workspace.ttl_hours ?? 24}h`;
}

function setBadge(element, text, mode) {
  element.textContent = text;
  element.classList.remove("good", "warn", "danger", "neutral");
  element.classList.add(mode);
}

function setBusy(isBusy) {
  document.body.classList.toggle("is-busy", isBusy);
}

function directionFor(text) {
  return /[\u0590-\u05ff]/.test(text) ? "auto" : "ltr";
}

function languageLabel(language) {
  if (language === "he") {
    return "HE-IL";
  }
  if (language === "auto") {
    return "MIXED";
  }
  return "EN";
}

function formatDate(value) {
  if (!value) {
    return "Current session";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

let toastTimer = null;

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 2600);
}

function wireEvents() {
  $$(".tab-button").forEach((button) => {
    button.addEventListener("click", () => setActiveScreen(button.dataset.screenTarget));
  });
  elements.sampleSelect.addEventListener("change", () => loadSample(elements.sampleSelect.value));
  elements.loadSampleButton.addEventListener("click", () => loadSample(elements.sampleSelect.value));
  elements.shieldButton.addEventListener("click", shieldCurrentText);
  elements.pasteButton.addEventListener("click", pasteLocalText);
  elements.fileButton.addEventListener("click", () => elements.fileInput.click());
  elements.fileInput.addEventListener("change", () => {
    loadLocalFile(elements.fileInput.files?.[0]);
    elements.fileInput.value = "";
  });
  elements.sourceInput.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.sourceInput.classList.add("is-drop-ready");
  });
  elements.sourceInput.addEventListener("dragleave", () => {
    elements.sourceInput.classList.remove("is-drop-ready");
  });
  elements.sourceInput.addEventListener("drop", (event) => {
    event.preventDefault();
    elements.sourceInput.classList.remove("is-drop-ready");
    loadLocalFile(event.dataTransfer?.files?.[0]);
  });
  elements.clearSourceButton.addEventListener("click", () => {
    elements.sourceInput.value = "";
    elements.sourceSubtitle.textContent = "Drop a file or paste text to prepare it for AI.";
    clearShieldOutput();
    setPipeline("idle");
  });
  elements.copySafeButton.addEventListener("click", copySafeText);
  elements.goRestoreButton.addEventListener("click", () => setActiveScreen("restore"));
  elements.loadFailureButton.addEventListener("click", () => {
    useMutatedResponse();
    setActiveScreen("restore");
  });
  elements.useCleanResponseButton.addEventListener("click", useCleanResponse);
  elements.useMutatedResponseButton.addEventListener("click", useMutatedResponse);
  elements.restoreInput.addEventListener("input", renderTokenSummary);
  elements.restoreButton.addEventListener("click", restoreCurrentText);
  elements.resetButton.addEventListener("click", resetDemo);
  elements.exportReportButton.addEventListener("click", exportAuditJson);
}

async function boot() {
  wireEvents();
  setPipeline("idle");
  await refreshTrustCenter();
  await loadSample(state.sampleName);
}

boot();
