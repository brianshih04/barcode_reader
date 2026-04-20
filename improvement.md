# Barcode Reader 改善計畫

基於對照 zxing-cpp 原始碼架構的 review，以下是分階段的改善計畫。

---

## Phase 1: 高優先級 — 效能提升

### 1.1 移除冗餘手動二值化，改用 zxing-cpp 原生 Binarizer

**問題**：`engine.py` Pass 4 手動做 OTSU / 固定閥值 / 自適應二值化，與 zxing-cpp 內建的 `Binarizer` 管線重複。zxing-cpp 的 `HybridBinarizer`（LocalAverage）已結合局部平均與全域直方圖，且內建 BitMatrix 快取與 invert 機制，手動二值化反而繞過了這些優化。

**做法**：

- 刪除 `_scan_binarized()` 中大部分手動二值化邏輯
- 改為輪替 `binarizer` 參數：`LocalAverage`、`GlobalHistogram`、`FixedThreshold`
- 保留低解析度圖片（短邊 < 500px）的 4x 放大 + 多閥值掃描作為特殊 case

**參考**：`zxing-cpp/core/src/ReadBarcode.cpp:232-241`、`ReaderOptions.h:124-125`

### 1.2 加入 Early Termination

**問題**：`decode()` 無論前面 Pass 是否已找到條碼，都跑完全部 4 個 Pass。對大圖來說非常慢。

**做法**：

- 在每個 Pass 結束後檢查是否已找到條碼
- 加入 `stop_on_found` 參數控制是否提前結束
- 提供 `scan_mode` 選項：`fast`（僅 Pass 1）、`normal`（Pass 1+2）、`deep`（全部）

### 1.3 暴露 `formats` 參數到 UI

**問題**：預設搜尋所有格式，搜尋空間過大。

**做法**：

- UI 新增格式篩選下拉選單（全部、僅一維碼、僅二維碼、僅 QR Code 等）
- 透過 `zxingcpp.read_barcodes(formats=...)` 傳入

**參考**：`zxing-cpp/core/src/BarcodeFormat.h` 的 `AllLinear`、`AllMatrix`、`QRCode` 等

### 1.4 利用 `maxNumberOfSymbols` 提速

> **不可行**：Python binding (`zxing.cpp`) 未暴露 `max_number_of_symbols` 參數，無法從 Python 端設定。

**替代做法**：透過 `scan_mode` 的 early termination 機制達到類似效果。

---

## Phase 2: 中優先級 — 功能增強

### 2.1 修復 `enable_enhance` 未傳遞的 Bug

**問題**：`app.py` 的 `scan_file()` 沒有接收 `enable_enhance` 參數，UI 的 checkbox 狀態無效。

**做法**：

- `Api.scan_file()` 加入 `enable_enhance` 參數
- 前端 `startScan()` 傳遞 checkbox 狀態

### 2.2 加入 `try_denoise` 實驗性選項

> **不可行**：Python binding (`zxing.cpp`) 未暴露 `try_denoise` 參數。

**替代做法**：Pass 3 的形態學區域偵測已覆蓋類似功能，保留現有實作。

### 2.3 加入掃描模式選擇

**問題**：所有圖片都用 4-Pass 全掃描，簡單圖片浪費時間。

**做法**：

- UI 加入掃描模式選項：快速 / 標準 / 深度
- 快速：僅 Pass 1（全圖原圖，含 `try_downscale` + `try_rotate` + `try_invert`）
- 標準：Pass 1 + Pass 2（放大）
- 深度：全部 Pass

---

## Phase 3: 低優先級 — 程式碼品質

### 3.1 修補型別標註

- `_barcode_to_dict(barcode)` → `_barcode_to_dict(barcode: zxingcpp.Barcode)`
- 補齊其他缺少型別標註的地方

### 3.2 位置重疊去重

**問題**：目前用 `(format, text)` 去重，不同 Pass 在相同位置找到相同條碼會重複。

**做法**：

- 利用 zxing-cpp 回傳的 `position`（四邊形座標）
- 兩個結果位置重疊度 > 80% 且 format + text 相同時，保留較早發現的

### 3.3 `try_downscale` 在放大二值圖上的效益評估

**問題**：Pass 4 小圖放大後的 `try_downscale=True` 在已經二值化的放大圖上效益遞減。

**做法**：評估後改為 `try_downscale=False`
