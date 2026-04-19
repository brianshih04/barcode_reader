\# 專案開發指南 (Project Context for Claude)



\## 1. 專案概述 (Project Overview)

這是一個跨平台 (Windows / macOS) 的桌面端條碼與 QR Code 掃描應用程式。

目標是讓使用者能匯入高品質或低品質的圖片 (JPG, PNG, BMP, 多頁 TIFF)，並快速、準確地解析出條碼內容。



\## 2. 技術選型 (Tech Stack)

絕對遵守以下技術選型，不要引入未經允許的第三方大型框架 (如 PyQt, Tkinter, React, Vue 等)：

\- \*\*前端 UI\*\*: HTML5, Vanilla JavaScript, Tailwind CSS (透過 CDN)。

\- \*\*桌面端橋接\*\*: `pywebview`。

\- \*\*後端邏輯\*\*: Python 3.10+。

\- \*\*影像處理\*\*: `opencv-python` (主要用於讀取檔案與預處理)。

\- \*\*核心解碼\*\*: `zxing-cpp` (Python binding)。



\## 3. 架構規範 (Architecture Rules)

專案採 MVC 概念分離，嚴格遵守以下職責劃分：

\- `/ui` 目錄：只放前端資源 (`index.html`, `style.css`, `script.js`)。絕對不能在這裡寫 Python。

\- `engine.py`：純粹的影像處理與解碼邏輯，不依賴任何 UI 套件。必須處理 OpenCV 讀取錯誤與 zxing-cpp 的例外狀況。

\- `app.py`：程式進入點。負責定義給 JavaScript 呼叫的 API 類別，並啟動 `pywebview` 視窗。



\## 4. 程式碼風格與鐵律 (Coding Conventions)

\- \*\*Python\*\*: 

&#x20; - 必須加上 Type Hints (型別提示)。

&#x20; - 變數與函式命名使用 `snake\_case`，類別使用 `PascalCase`。

&#x20; - 遇到圖片讀取失敗或解碼失敗時，\*\*絕對不能讓程式 Crash\*\*，必須透過 `pywebview` 回傳明確的錯誤訊息 (JSON 格式) 給前端。

\- \*\*JavaScript\*\*:

&#x20; - 呼叫後端 API 必須使用 `async/await` 處理 `window.pywebview.api` 的非同步請求。

&#x20; - 在等待 Python 處理影像時，UI 必須有明確的 Loading 狀態。

\- \*\*影像處理特例 (重要)\*\*:

&#x20; - 使用 OpenCV 讀取圖片時，請預設使用 `cv2.IMREAD\_GRAYSCALE` 以提升效能。

&#x20; - 呼叫 `zxingcpp.read\_barcodes` 時，請務必開啟 `TryHarder=True` 屬性。



\## 5. 開發步驟 (Current Phase)

(可以在此處更新你目前希望 Claude 專注的任務，例如：目前正在開發多頁 TIFF 支援，請專注於 engine.py 的優化。)

