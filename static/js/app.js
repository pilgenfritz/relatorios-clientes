// ===== Relatórios Meta Ads — Frontend =====

// job_id → intervalId
const pollingIntervals = {};

// ─── Toast ──────────────────────────────────────────────────
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ─── Progress update ─────────────────────────────────────────
function updateRow(accountId, jobId, progress) {
  const row = document.querySelector(`tr[data-account-id="${accountId}"]`);
  if (!row) return;

  const fill  = row.querySelector(".progress-bar-fill");
  const label = row.querySelector(".progress-label");
  const runBtn = row.querySelector(".btn-run");
  const dlCell = row.querySelector(".download-area");

  const pct = progress.steps_total > 0
    ? Math.round((progress.steps_done / progress.steps_total) * 100)
    : 0;

  fill.style.width = pct + "%";
  fill.classList.remove("done", "error");
  label.classList.remove("done", "error");

  if (progress.status === "done") {
    fill.style.width = "100%";
    fill.classList.add("done");
    label.classList.add("done");
    label.textContent = "✓ Concluído";
    if (runBtn) runBtn.disabled = false;
    if (dlCell && progress.pdf_filename) {
      dlCell.innerHTML = `
        <a class="btn btn-outline btn-sm" href="/download/${progress.pdf_filename}" target="_blank">
          ⬇ PDF
        </a>`;
    }
    stopPolling(jobId);
    showToast(`Relatório de ${progress.client_name} concluído!`, "success");

  } else if (progress.status === "error") {
    fill.classList.add("error");
    label.classList.add("error");
    label.textContent = "✗ Erro: " + (progress.error_message || "desconhecido");
    if (runBtn) runBtn.disabled = false;
    stopPolling(jobId);
    showToast(`Erro em ${progress.client_name}: ${progress.error_message}`, "error");

  } else {
    label.textContent = progress.current_step || "Processando...";
    fill.style.width = pct + "%";
    if (runBtn) runBtn.disabled = true;
  }
}

// ─── Polling ─────────────────────────────────────────────────
function startPolling(accountId, jobId) {
  if (pollingIntervals[jobId]) return;

  pollingIntervals[jobId] = setInterval(async () => {
    try {
      const resp = await fetch(`/progress/${jobId}`);
      const data = await resp.json();
      updateRow(accountId, jobId, data);
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, 2000);
}

function stopPolling(jobId) {
  clearInterval(pollingIntervals[jobId]);
  delete pollingIntervals[jobId];
}

// ─── Run single account ───────────────────────────────────────
async function runAccount(accountId) {
  const row = document.querySelector(`tr[data-account-id="${accountId}"]`);
  const runBtn = row?.querySelector(".btn-run");
  if (runBtn) runBtn.disabled = true;

  // Reset visual
  const fill  = row?.querySelector(".progress-bar-fill");
  const label = row?.querySelector(".progress-label");
  if (fill)  { fill.style.width = "5%"; fill.classList.remove("done","error"); }
  if (label) { label.textContent = "Iniciando..."; label.classList.remove("done","error"); }

  try {
    const resp = await fetch(`/run/${accountId}`, { method: "POST" });
    const data = await resp.json();
    if (data.error) {
      showToast("Erro: " + data.error, "error");
      if (runBtn) runBtn.disabled = false;
      return;
    }
    startPolling(accountId, data.job_id);
  } catch (e) {
    showToast("Falha ao iniciar job: " + e.message, "error");
    if (runBtn) runBtn.disabled = false;
  }
}

// ─── Run all accounts ─────────────────────────────────────────
async function runAll() {
  const btn = document.getElementById("btn-run-all");
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch("/run/all", { method: "POST" });
    const data = await resp.json();
    if (data.error) {
      showToast("Erro: " + data.error, "error");
      if (btn) btn.disabled = false;
      return;
    }

    showToast(`${data.job_ids.length} jobs iniciados!`, "success");

    // job_ids vêm no formato "{account_id}_{timestamp}"
    data.job_ids.forEach(jobId => {
      // extrai account_id: tudo antes do último _timestamp
      const parts = jobId.split("_");
      // account_id pode conter underscores (act_XXXXXXX), timestamp é só dígitos
      // Formato: act_ACCOUNTID_TIMESTAMP → pegar até o último segmento numérico grande
      const tsIdx = parts.findLastIndex(p => /^\d{10,}$/.test(p));
      const accountId = parts.slice(0, tsIdx).join("_");
      startPolling(accountId, jobId);
    });
  } catch (e) {
    showToast("Falha ao iniciar jobs: " + e.message, "error");
    if (btn) btn.disabled = false;
  }
}
