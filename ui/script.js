/**
 * Barcode Reader — 前端邏輯
 *
 * 負責處理 UI 事件、呼叫 Python 後端 API、渲染掃描結果。
 */

// DOM 元素快取
const $ = (id) => document.getElementById(id);

const elements = {
  dropZone: $("drop-zone"),
  btnChoose: $("btn-choose"),
  btnMinimize: $("btn-minimize"),
  btnClose: $("btn-close"),
  chkEnhance: $("chk-enhance"),
  selMode: $("sel-mode"),
  selFormats: $("sel-formats"),
  statusIndicator: $("status-indicator"),
  statusText: $("status-text"),
  statusTime: $("status-time"),
  resultsPanel: $("results-panel"),
  resultsBody: $("results-body"),
};

let isScanning = false;

// ===== pywebview 就緒 =====
document.addEventListener("pywebviewready", async () => {
  elements.btnChoose.addEventListener("click", onChooseFile);
  elements.btnMinimize.addEventListener("click", () =>
    window.pywebview.api.minimize(),
  );
  elements.btnClose.addEventListener("click", () =>
    window.pywebview.api.close_window(),
  );
  setupDragDrop();
  try {
    await populateFormats();
  } catch (e) {
    console.error("populateFormats failed:", e);
  }
});

// ===== 拖放 (前端視覺回饋，實際路徑由 Python DOMEventHandler 處理) =====
function setupDragDrop() {
  elements.dropZone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    elements.dropZone.classList.add("drag-over");
  });
  elements.dropZone.addEventListener("dragleave", () => {
    elements.dropZone.classList.remove("drag-over");
  });
  elements.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
  });
  elements.dropZone.addEventListener("drop", async (e) => {
    e.preventDefault();
    elements.dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;
    const path = files[0].pywebviewFullPath;
    if (path) {
      await startScan(path);
    }
  });
}

// ===== 點擊選擇檔案 =====
async function onChooseFile() {
  if (isScanning) return;
  const resultJson = await window.pywebview.api.open_file_dialog();
  const paths = JSON.parse(resultJson);
  if (!paths || paths.length === 0) return;
  await startScan(paths[0]);
}

// ===== 掃描流程 =====
async function startScan(filePath) {
  if (isScanning) return;
  isScanning = true;

  setStatus("scanning", "掃描中...");
  elements.btnChoose.disabled = true;
  clearResults();

  const enhance = elements.chkEnhance.checked;
  const mode = elements.selMode.value;
  const formatsVal = elements.selFormats.value;
  const formatsJson = formatsVal || null;

  const resultJson = await window.pywebview.api.scan_file(
    filePath,
    enhance,
    mode,
    formatsJson,
  );
  onScanResult(JSON.parse(resultJson));
}

/**
 * Python 端掃描完成後的回呼 (由 evaluate_js 或 JS 端直接呼叫)。
 * @param {Object} data - 掃描結果 JSON 物件
 */
function onScanResult(data) {
  isScanning = false;
  elements.btnChoose.disabled = false;

  if (data.status === "error") {
    setStatus("error", data.message);
    return;
  }

  if (data.status === "no_barcode") {
    setStatus("no_barcode", `未偵測到條碼 (${data.total_pages} 頁)`);
    if (data.time_taken_ms) {
      elements.statusTime.textContent = `${data.time_taken_ms} ms`;
    }
    return;
  }

  // 成功
  const count = data.results.length;
  setStatus("success", `偵測到 ${count} 個條碼 (${data.total_pages} 頁)`);
  elements.statusTime.textContent = `${data.time_taken_ms} ms`;
  renderResults(data.results);
}

// ===== 狀態管理 =====
function setStatus(type, text) {
  const indicator = elements.statusIndicator;
  indicator.className = `status-${type}`;
  elements.statusText.textContent = text;
  elements.statusTime.textContent = "";
}

// ===== 結果渲染 =====
function renderResults(results) {
  elements.resultsBody.innerHTML = "";
  elements.resultsPanel.classList.remove("hidden");

  for (const r of results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
            <td>${r.page}</td>
            <td>${r.format}</td>
            <td class="result-text">${escapeHtml(r.text)}</td>
            <td><button class="btn-copy" data-text="${escapeAttr(r.text)}">複製</button></td>
        `;
    elements.resultsBody.appendChild(tr);
  }

  // 綁定複製按鈕
  elements.resultsBody.querySelectorAll(".btn-copy").forEach((btn) => {
    btn.addEventListener("click", () => copyText(btn, btn.dataset.text));
  });
}

function clearResults() {
  elements.resultsBody.innerHTML = "";
  elements.resultsPanel.classList.add("hidden");
}

async function copyText(btn, text) {
  await navigator.clipboard.writeText(text);
  btn.textContent = "已複製";
  btn.classList.add("copied");
  setTimeout(() => {
    btn.textContent = "複製";
    btn.classList.remove("copied");
  }, 1500);
}

async function populateFormats() {
  const raw = await window.pywebview.api.get_formats();
  const fmtList = JSON.parse(raw);
  const sel = elements.selFormats;
  sel.innerHTML = "";
  for (const item of fmtList) {
    const opt = document.createElement("option");
    opt.value = item.value ? JSON.stringify(item.value) : "";
    opt.textContent = item.label;
    sel.appendChild(opt);
  }
}

// ===== 工具函式 =====
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function escapeAttr(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
