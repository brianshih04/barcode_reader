"""
Barcode Reader — 應用程式進入點

負責定義 pywebview API 類別、拖放事件處理、視窗建立與啟動。
"""

import json
import sys
import webview
from webview.dom import DOMEventHandler

from engine import ScannerEngine


class Api:
    """暴露給前端 JavaScript 呼叫的 API 類別。"""

    def __init__(self) -> None:
        self._engine = ScannerEngine()
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def scan_file(self, file_path: str) -> str:
        """掃描指定圖片檔案，回傳 JSON 結果。自動在背景執行緒中執行。"""
        result = self._engine.scan_file(file_path)
        return json.dumps(result, ensure_ascii=False)

    def open_file_dialog(self) -> str:
        """開啟原生檔案選擇對話框，回傳選取的路徑 JSON。"""
        if self._window is None:
            return json.dumps(None)
        result = self._window.create_file_dialog(
            webview.OPEN,
            file_types=("Images (*.jpg;*.jpeg;*.png;*.bmp;*.tiff;*.tif;*.webp;*.avif)",),
        )
        return json.dumps(result)

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def close(self) -> None:
        if self._window:
            self._window.destroy()


def _on_drop(api: Api, event: dict) -> None:
    """Python 端處理拖放事件，取得完整檔案路徑後觸發掃描。"""
    files = event.get("dataTransfer", {}).get("files", [])
    if not files:
        return

    file_path = files[0].get("pywebviewFullPath")
    if not file_path:
        return

    result_json = api.scan_file(file_path)
    if api._window:
        api._window.evaluate_js(f"onScanResult({result_json})")


def _on_drag_over(event: dict) -> None:
    """攔截 dragover 避免瀏覽器預設行為。"""
    pass


def bind(window: webview.Window, api: Api) -> None:
    """視窗載入後的綁定回呼：注入 API 並註冊拖放事件。"""
    api.set_window(window)

    window.dom.document.events.dragover += DOMEventHandler(
        _on_drag_over, True, True
    )
    window.dom.document.events.drop += DOMEventHandler(
        lambda e: _on_drop(api, e), True, True
    )


def main() -> None:
    api = Api()

    window = webview.create_window(
        title="Barcode Reader",
        url="ui/index.html",
        js_api=api,
        width=900,
        height=700,
        min_size=(600, 400),
        frameless=True,
        easy_drag=True,
    )

    webview.start(bind, (window, api), debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
