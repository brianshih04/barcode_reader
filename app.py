"""
Barcode Reader — 應用程式進入點

負責定義 pywebview API 類別、視窗建立與啟動。
"""

import json
import sys
import webview

from engine import ScannerEngine


class Api:
    """暴露給前端 JavaScript 呼叫的 API 類別。"""

    def __init__(self) -> None:
        self._engine = ScannerEngine()
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def scan_file(
        self,
        file_path: str,
        enable_enhance: bool = False,
        scan_mode: str = "deep",
        formats: str | None = None,
    ) -> str:
        """掃描指定圖片檔案，回傳 JSON 結果。自動在背景執行緒中執行。"""
        fmt_list = json.loads(formats) if formats else None
        result = self._engine.scan_file(
            file_path,
            enable_enhance=enable_enhance,
            scan_mode=scan_mode,
            formats=fmt_list,
        )
        return json.dumps(result, ensure_ascii=False)

    def get_formats(self) -> str:
        """回傳可用的條碼格式清單 JSON。"""
        return json.dumps(self._engine.available_formats(), ensure_ascii=False)

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

    def close_window(self) -> None:
        if self._window:
            self._window.destroy()


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
    api.set_window(window)

    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
