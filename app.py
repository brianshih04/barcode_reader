"""
Barcode Reader — 應用程式進入點

負責定義 pywebview API 類別、視窗建立與啟動。
"""

import base64
import json
import os
import sys
import tempfile
import time
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
        """掃描指定圖片檔案，回傳 JSON 結果。"""
        fmt_list = json.loads(formats) if formats else None
        result = self._engine.scan_file(
            file_path,
            enable_enhance=enable_enhance,
            scan_mode=scan_mode,
            formats=fmt_list,
        )
        return json.dumps(result, ensure_ascii=False)

    def scan_base64(
        self,
        b64_data: str,
        filename: str,
        enable_enhance: bool = False,
        scan_mode: str = "deep",
        formats: str | None = None,
    ) -> str:
        """接收 base64 圖片資料，存暫存檔後掃描，回傳 JSON 結果。"""
        tmp_path = ""
        start_time = time.perf_counter()
        try:
            raw = base64.b64decode(b64_data)
            suffix = os.path.splitext(filename)[1] or ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(raw)
                tmp_path = f.name

            return self.scan_file(tmp_path, enable_enhance, scan_mode, formats)
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return json.dumps(
                {
                    "status": "error",
                    "message": str(e),
                    "results": [],
                    "file_name": filename,
                    "total_pages": 0,
                    "time_taken_ms": elapsed_ms,
                },
                ensure_ascii=False,
            )
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def get_formats(self) -> str:
        """回傳可用的條碼格式清單 JSON。"""
        return json.dumps(self._engine.available_formats(), ensure_ascii=False)


def main() -> None:
    api = Api()

    window = webview.create_window(
        title="Barcode Reader",
        url="ui/index.html",
        js_api=api,
        width=900,
        height=700,
        min_size=(600, 400),
    )
    api.set_window(window)

    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
