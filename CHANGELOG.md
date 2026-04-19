# 變更日誌

本專案所有重要變更都會記錄在此文件中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

---

## [1.1.0] - 2026-04-19

### 變更

- **掃描引擎升級** (`engine.py`)
  - Pass 2 放大策略改為自適應倍率：短邊 < 500px 自動 4x 放大（INTER_CUBIC），其餘維持 2x
  - 新增 Pass 4「多閥值二值化掃描」：固定閥值 (127) + OTSU + 自適應二值化
  - 低解析度圖片（短邊 < 500px）額外執行 4x 放大 + 多閥值 (120/140/160) 二值化掃描
  - 有效破解：浮水印干擾、低對比圖片、低解析度一維條碼像素沾黏等 Edge Case

### 測試結果

- `a.jpg`（浮水印 QR Code）：v1.0 失敗 → v1.1 成功解碼
- `3.webp`（低解析度多條碼）：v1.0 僅抓到 1 個 QR Code → v1.1 成功抓到全部 3 個（QRCode + 2x EAN-13）
- `58.jpg`（條碼種類參考圖，28+ 種條碼）：成功辨識 4 個 2D 條碼（DataMatrix、PDF417、QRCode、Aztec），其餘受物理限制（解析度不足 1-2px 線條）或 zxing-cpp 不支援該格式

---

## [1.0.0] - 2026-04-19

### 新增

- **核心掃描引擎** (`engine.py`)
  - `ScannerEngine` 類別：影像讀取 → 預處理 → 多策略解碼
  - 支援圖片格式：JPG、PNG、BMP、TIFF（含多頁）、WebP、AVIF
  - 多頁 TIFF 透過 `cv2.imreadmulti()` 逐頁掃描
  - AVIF 透過 Pillow + pillow-avif-plugin 讀取
  - 三階段掃描策略：全圖原圖 → 全圖 2x 放大 → 形態學區域偵測
  - 大圖自動等比例縮放（上限 2000px）
  - 可選 CLAHE 對比度增強
  - 完整錯誤處理：不會因損毀圖片或不支援格式而 crash
  - CLI 模式：`python engine.py <image_path>` 直接輸出 JSON 結果

- **桌面應用程式** (`app.py`)
  - pywebview 框架，無邊框視窗 + 自訂標題列
  - `Api` 類別：暴露 `scan_file`、`open_file_dialog`、`minimize`、`close` 給前端
  - 拖放支援：透過 `DOMEventHandler` 在 Python 端接收完整檔案路徑
  - 原生檔案選擇對話框，支援所有圖片格式篩選
  - `--debug` 參數開啟 DevTools

- **前端介面** (`ui/`)
  - 深色主題 UI
  - Drop Zone 拖曳上傳區，含 drag-over 視覺回饋
  - 即時狀態指示器：等待輸入 / 掃描中 / 完成 / 無法辨識 / 錯誤
  - 掃描結果表格：顯示頁數、條碼類型、解碼內容
  - 一鍵複製按鈕（`navigator.clipboard`）
  - 可折疊進階設定面板

- **支援的條碼格式**（透過 zxing-cpp）
  - 1D：EAN-8、EAN-13、UPC-A、UPC-E、Code 39、Code 93、Code 128、ITF、ITF-14、Codabar
  - 2D：QR Code、Data Matrix、PDF417、Aztec Code、MaxiCode
  - GS1 DataBar 家族

- **專案基礎建設**
  - `requirements.txt` 依賴清單
  - `CLAUDE.md` 開發規範
  - `.gitignore` 排除 `.venv/`、`__pycache__/`、建置產物
