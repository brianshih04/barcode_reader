/**
 * Barcode Reader — 前端邏輯
 *
 * 所有檔案讀取統一走 FileReader → base64 → Python scan_base64，
 * 不依賴 pywebview 的 DOMEventHandler / pywebviewFullPath / create_file_dialog。
 */

const $ = (id) => document.getElementById(id);
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

const el = {
  fileInput: $("file-input"),
  dropZone: $("drop-zone"),
  btnChoose: $("btn-choose"),
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

// ===== Init =====
document.addEventListener("pywebviewready", async () => {
  el.btnChoose.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", onFileSelected);
  setupDragDrop();
  try {
    await populateFormats();
  } catch (e) {
    console.error("populateFormats failed:", e);
  }
});

// ===== 拖放 =====
function setupDragDrop() {
  el.dropZone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    el.dropZone.classList.add("drag-over");
  });
  el.dropZone.addEventListener("dragleave", () => {
    el.dropZone.classList.remove("drag-over");
  });
  el.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
  });
  el.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    el.dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      beginScan(files[0]);
    }
  });
}

// ===== 檔案選擇 =====
function onFileSelected() {
  const files = el.fileInput.files;
  if (files && files.length > 0) {
    beginScan(files[0]);
  }
  // 重置 input 以便重複選同一檔案
  el.fileInput.value = "";
}

// ===== 掃描入口：File → base64 → Python =====
async function beginScan(file) {
  if (isScanning) return;

  if (file.size > MAX_FILE_SIZE_BYTES) {
    setStatus("error", "檔案過大，請選擇 50 MB 以下的圖片");
    clearResults();
    return;
  }

  isScanning = true;
  setStatus("scanning", "掃描中...");
  el.btnChoose.disabled = true;
  clearResults();

  try {
    const b64 = await toBase64(file);
    const resultJson = await window.pywebview.api.scan_base64(
      b64,
      file.name,
      el.chkEnhance.checked,
      el.selMode.value,
      el.selFormats.value || null,
    );
    onScanResult(JSON.parse(resultJson));
  } catch (err) {
    isScanning = false;
    el.btnChoose.disabled = false;
    setStatus("error", "處理失敗: " + err.message);
  }
}

function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// ===== 掃描結果 =====
function onScanResult(data) {
  isScanning = false;
  el.btnChoose.disabled = false;

  if (data.status === "error") {
    setStatus("error", data.message);
    return;
  }

  if (data.status === "no_barcode") {
    setStatus("no_barcode", `未偵測到條碼 (${data.total_pages} 頁)`);
    if (data.time_taken_ms) el.statusTime.textContent = `${data.time_taken_ms} ms`;
    return;
  }

  setStatus("success", `偵測到 ${data.results.length} 個條碼 (${data.total_pages} 頁)`);
  el.statusTime.textContent = `${data.time_taken_ms} ms`;
  renderResults(data.results);
}

// ===== 狀態 =====
function setStatus(type, text) {
  el.statusIndicator.className = `status-${type}`;
  el.statusText.textContent = text;
  el.statusTime.textContent = "";
}

// ===== 結果渲染 =====
function renderResults(results) {
  el.resultsBody.innerHTML = "";
  el.resultsPanel.classList.remove("hidden");

  for (const r of results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.page}</td>
      <td>${r.format}</td>
      <td class="result-text">${esc(r.text)}</td>
      <td><button class="btn-copy" data-text="${escAttr(r.text)}">複製</button></td>
    `;
    el.resultsBody.appendChild(tr);
  }

  el.resultsBody.querySelectorAll(".btn-copy").forEach((btn) => {
    btn.addEventListener("click", () => copyText(btn, btn.dataset.text));
  });
}

function clearResults() {
  el.resultsBody.innerHTML = "";
  el.resultsPanel.classList.add("hidden");
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
  const sel = el.selFormats;
  sel.innerHTML = "";
  for (const item of fmtList) {
    const opt = document.createElement("option");
    opt.value = item.value ? JSON.stringify(item.value) : "";
    opt.textContent = item.label;
    sel.appendChild(opt);
  }
}

// ===== 工具 =====
function esc(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function escAttr(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
