# 變更日誌

本專案所有重要變更都會記錄在此文件中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

---

## [1.3.0] - 2026-05-04

### 新增

- **條件式影像強化重試** (`engine.py`)
  - 深度掃描模式下，若未偵測到條碼，或低解析度寬圖只找到少量結果，會自動以 CLAHE 強化後重掃
  - 新增跨輪去重邏輯，合併原圖掃描與強化重試的新結果
  - 回傳 `enhanced_retry_pages`，標示哪些頁面靠影像強化補到新結果

- **低解析度 1D ROI 補救掃描** (`engine.py`)
  - 針對中低解析度且結果較少的圖片，使用 OpenCV Sobel 梯度與形態學閉運算找出水平條碼候選區
  - 對候選區裁切後執行多倍率放大、CLAHE、OTSU 與固定閥值重掃
  - 加入 1D 條碼合理性檢查，降低過短 ITF 等假陽性

- **前端相容性調整** (`ui/`, `app.py`)
  - 前端統一使用 HTML File API / FileReader 將圖片轉為 base64，再由 Python 暫存掃描
  - 新增 50 MB 檔案大小保護，避免大檔 base64 造成過高記憶體壓力
  - `scan_base64()` 錯誤回傳補齊 `results`、`file_name`、`total_pages`、`time_taken_ms`

### 修正

- 修正預設「全部格式」使用 `zxingcpp.BarcodeFormats()` 空建構子導致掃描失敗的問題，改為 `BarcodeFormats(BarcodeFormat.All)`
- 修正逐頁掃描例外被吞掉後誤報 `no_barcode` 的問題；現在會回傳 `page_errors`，若所有頁面失敗則回傳 `error`
- 修正無效格式篩選靜默退回全部格式的問題；現在會回傳明確錯誤
- README 同步目前非無邊框視窗與新掃描策略描述

### 測試結果

- `3.webp`：深度模式由 2 個提升為 3 個，補到右側 `EAN13: 8690123456789`
- `58.jpg`：深度模式由 4 個提升為 6 個，新增 `EAN13: 9771473968012` 與 `DataBarStk: (01)24012345678905`
- `barcode-and-qr-code-collection-vector-6406064.avif`：維持 11 個
- `barcode-sample-printing-sevice.jpg`：維持 9 個
- `_debug_crop.png`：仍無法辨識，裁切過小且條碼資訊不足

---

## [1.2.0] - 2026-04-20

### 變更

- **掃描引擎重構** (`engine.py`)
  - Pass 1 改為多 Binarizer 輪替（LocalAverage → GlobalHistogram → FixedThreshold），取代手動二值化
  - 新增 `scan_mode` 參數：`fast`（僅全圖）、`normal`（全圖+放大）、`deep`（全部策略）
  - 新增 `formats` 參數：限制搜尋的條碼格式（如 QRCode、EAN13），縮小搜尋空間
  - 新增 `available_formats()` 方法：回傳可用的格式清單供 UI 使用
  - 新增 `_parse_formats()` 輔助方法：字串列表 → `zxingcpp.BarcodeFormats`
  - 補齊型別標註（`barcode: zxingcpp.Barcode` 等）

- **API 層** (`app.py`)
  - `scan_file()` 新增 `enable_enhance`、`scan_mode`、`formats` 參數傳遞
  - 修復 `enable_enhance` checkbox 狀態未傳遞到引擎的 bug
  - 新增 `get_formats()` API：供前端取得條碼格式清單
  - 拖放事件現在會讀取目前 UI 設定（掃描模式、格式篩選、影像強化）

- **前端介面** (`ui/`)
  - 進階設定面板新增「掃描模式」下拉選單（快速 / 標準 / 深度）
  - 進階設定面板新增「條碼格式」下拉選單（動態從後端載入）
  - 新增 `<select>` 元件的深色主題樣式

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
