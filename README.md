# Barcode Reader

跨平台桌面端條碼 / QR Code 掃描工具。支援多種圖片格式，採用多策略掃描引擎，最大化條碼辨識率。

## 功能特色

- **多格式圖片支援**：JPG、PNG、BMP、TIFF（含多頁）、WebP、AVIF
- **多策略掃描引擎**：全圖掃描 + 自適應放大掃描 + 形態學區域偵測 + 多閥值二值化，自動合併去重
- **廣泛條碼格式支援**（基於 zxing-cpp）：
  - 1D：EAN-8/13、UPC-A/E、Code 39/93/128、ITF/ITF-14、Codabar
  - 2D：QR Code、Data Matrix、PDF417、Aztec Code、MaxiCode
  - GS1 DataBar 家族（Omni、Limited、Expanded、Stacked）
  - 不支援：Code 11、Pharmacode、MSI、Plessey、JapanPost、OneCode、Postnet、Royal Mail、KIX、AusPost 等
- **現代化深色主題 UI**：無邊框視窗、拖曳上傳、即時狀態指示
- **一鍵複製**：掃描結果直接複製到剪貼簿
- **多頁 TIFF**：自動逐頁掃描，每頁獨立標註頁碼

## 系統需求

- Python 3.10+
- Windows 10/11（macOS 理論支援，尚未測試）
- Windows 需安裝 [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)（Windows 11 已內建）

## 安裝

```bash
git clone https://github.com/brianshih04/barcode_reader.git
cd barcode_reader

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 使用方式

### 啟動應用程式

```bash
python app.py
```

加上 `--debug` 可開啟 DevTools：

```bash
python app.py --debug
```

### 操作方式

1. **拖曳上傳**：將圖片檔案直接拖入視窗的 Drop Zone
2. **點擊選擇**：點擊「點擊選擇檔案」按鈕，從檔案對話框選擇圖片
3. **查看結果**：掃描完成後，結果表格會顯示條碼類型與解碼內容
4. **複製內容**：點擊結果列的「複製」按鈕，一鍵複製解碼文字

### 進階設定

展開「進階設定」面板可啟用**自動影像強化**（CLAHE 對比度增強），適用於低對比度或模糊的圖片。

### CLI 模式（終端機測試）

```bash
python engine.py <image_path> [image_path2 ...]
```

輸出 JSON 格式的掃描結果。

## 專案架構

```
barcode_reader/
├── app.py              # 應用程式進入點，pywebview 橋接層
├── engine.py           # 核心掃描引擎，影像處理與解碼邏輯
├── requirements.txt    # Python 依賴套件
├── ui/
│   ├── index.html      # 前端頁面結構
│   ├── style.css       # 深色主題樣式
│   └── script.js       # 前端互動邏輯
├── CLAUDE.md           # 開發規範
└── README.md
```

### 職責劃分

| 檔案 | 職責 |
|------|------|
| `engine.py` | 影像讀取、預處理、條碼解碼，不依賴任何 UI 套件 |
| `app.py` | pywebview API 類別、拖放事件處理、視窗管理 |
| `ui/` | 前端介面，僅包含 HTML / CSS / JavaScript |

## 掃描引擎策略

引擎採用四階段掃描，自動合併去重結果：

1. **全圖原圖掃描**：以原始解析度直接解碼
2. **自適應放大掃描**：短邊 < 500px 放大 4x（INTER_CUBIC），500–1500px 放大 2x，捕捉微小條碼
3. **形態學區域偵測**：透過 Sobel 梯度 + 閉運算偵測條碼紋理區域，裁切後 5x 放大逐一掃描
4. **多閥值二值化掃描**：固定閥值 + OTSU + 自適應二值化；低解析度圖片額外 4x 放大 + 多閥值掃描，破解浮水印、低對比、像素沾黏等干擾

## 依賴套件

| 套件 | 用途 |
|------|------|
| [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) | 核心條碼解碼引擎 |
| [opencv-python](https://github.com/opencv/opencv-python) | 影像讀取與預處理 |
| [pywebview](https://github.com/r0x0r/pywebview) | 桌面端 Web UI 橋接 |
| [pillow](https://python-pillow.org/) | AVIF 格式讀取支援 |
| [pillow-avif-plugin](https://github.com/nicedouble/pillow-avif-plugin) | Pillow 的 AVIF codec |

## 已知限制

- **低解析度圖片的 1D 條碼**：當圖片短邊 < 500px 且包含多個條碼（如條碼種類參考圖），1D 條碼的最細線條可能只有 1-2 像素，經 JPEG 壓縮後無法重建，此為物理限制
- **不支援的條碼格式**：Code 11、Pharmacode、MSI、Plessey、JapanPost、Intelligent Mail (OneCode)、Postnet、Royal Mail、KIX、AusPost 等格式不在 zxing-cpp 支援範圍內

## 授權

MIT License
