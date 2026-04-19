"""
Barcode Reader — 核心掃描引擎

負責影像讀取、預處理與條碼解碼，不依賴任何 UI 套件。
採用多策略掃描：全圖 + 放大 + 形態學區域偵測，最大化條碼辨識率。
"""

import json
import time
from pathlib import Path

import cv2
import numpy as np
import zxingcpp

# 支援的圖片副檔名
SUPPORTED_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
    ".webp", ".avif",
}

# 需要透過 Pillow 讀取的格式 (OpenCV 不原生支援)
_PIL_FORMATS: set[str] = {".avif"}

# 大圖自動縮放的上限 (px)
MAX_IMAGE_DIMENSION: int = 2000


class ScannerEngine:
    """條碼掃描引擎：讀取圖片 → 預處理 → 多策略解碼。"""

    @staticmethod
    def load_image(file_path: str) -> list[np.ndarray]:
        """讀取圖片檔案，回傳灰度 numpy array 的 list (多頁 TIFF 會有多個元素)。

        Args:
            file_path: 圖片檔案的絕對路徑。

        Returns:
            灰度影像列表，每個元素為一頁的 numpy ndarray。

        Raises:
            ValueError: 檔案不存在、格式不支援或讀取失敗。
        """
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"檔案不存在: {file_path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"不支援的格式 '{ext}'，僅支援: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        if ext in (".tiff", ".tif"):
            return ScannerEngine._load_tiff(file_path)

        if ext in _PIL_FORMATS:
            return ScannerEngine._load_via_pillow(file_path)

        img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"無法讀取圖片: {file_path}")
        return [img]

    @staticmethod
    def _load_tiff(file_path: str) -> list[np.ndarray]:
        """讀取多頁 TIFF，回傳所有頁面的灰度影像列表。"""
        page_count = cv2.imcount(file_path)
        if page_count <= 0:
            raise ValueError(f"無法讀取 TIFF 檔案或檔案為空: {file_path}")

        success, pages = cv2.imreadmulti(file_path, flags=cv2.IMREAD_GRAYSCALE)
        if not success or not pages:
            raise ValueError(f"TIFF 讀取失敗: {file_path}")

        return pages

    @staticmethod
    def _load_via_pillow(file_path: str) -> list[np.ndarray]:
        """透過 Pillow 讀取 OpenCV 不支援的格式 (如 AVIF)，轉為灰度 numpy array。"""
        import pillow_avif  # noqa: F401 — 註冊 AVIF codec
        from PIL import Image

        pil_img = Image.open(file_path).convert("L")
        return [np.array(pil_img)]

    @staticmethod
    def preprocess(image: np.ndarray, enable_enhance: bool = False) -> np.ndarray:
        """影像預處理：確保灰度 + 可選增強 + 大圖縮放。

        Args:
            image: 輸入影像 (灰度或彩色)。
            enable_enhance: 是否啟用 CLAHE 對比度增強。

        Returns:
            處理後的灰度影像。
        """
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        h, w = image.shape[:2]
        if max(h, w) > MAX_IMAGE_DIMENSION:
            ratio = MAX_IMAGE_DIMENSION / max(h, w)
            new_w, new_h = int(w * ratio), int(h * ratio)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        if enable_enhance:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            image = clahe.apply(image)

        return image

    @staticmethod
    def decode(image: np.ndarray) -> list[dict]:
        """多策略條碼解碼：全圖掃描 + 放大掃描 + 形態學區域偵測。

        Args:
            image: 灰度 numpy ndarray。

        Returns:
            去重後的解碼結果列表。
        """
        seen: set[tuple[str, str]] = set()
        all_results: list[dict] = []

        # Pass 1: 全圖原圖掃描
        for bc in zxingcpp.read_barcodes(
            image, try_rotate=True, try_downscale=True, try_invert=True
        ):
            ScannerEngine._add_unique(bc, seen, all_results)

        # Pass 2: 全圖 2x 放大掃描 (捕捉微小條碼)
        h, w = image.shape[:2]
        if min(h, w) < 1500:
            img2x = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
            for bc in zxingcpp.read_barcodes(
                img2x, try_rotate=True, try_downscale=False, try_invert=True
            ):
                ScannerEngine._add_unique(bc, seen, all_results)

        # Pass 3: 形態學區域偵測 → 裁切 + 5x 放大掃描
        ScannerEngine._scan_morphology_regions(image, seen, all_results)

        return all_results

    @staticmethod
    def _scan_morphology_regions(
        image: np.ndarray,
        seen: set[tuple[str, str]],
        results: list[dict],
    ) -> None:
        """用形態學方法偵測條碼區域，裁切放大後逐一掃描。"""
        h, w = image.shape[:2]

        # Sobel 水平梯度 → 二值化 → 閉運算 → 找輪廓
        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
        sq_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

        grad_x = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=-1)
        grad_x = cv2.convertScaleAbs(grad_x)
        _, binary = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, rect_kernel)
        closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, sq_kernel)

        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw * ch < 300 or cw < 20 or ch < 10:
                continue

            pad = 8
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(w, x + cw + pad), min(h, y + ch + pad)
            crop = image[y1:y2, x1:x2]

            crop_h, crop_w = crop.shape
            crop_up = cv2.resize(
                crop, (crop_w * 5, crop_h * 5), interpolation=cv2.INTER_LINEAR
            )

            for bc in zxingcpp.read_barcodes(
                crop_up, try_rotate=True, try_downscale=False, try_invert=True
            ):
                ScannerEngine._add_unique(bc, seen, results)

    @staticmethod
    def _add_unique(
        barcode,
        seen: set[tuple[str, str]],
        results: list[dict],
    ) -> None:
        """去重加入解碼結果。"""
        key = (barcode.format.name, barcode.text)
        if key not in seen:
            seen.add(key)
            results.append(ScannerEngine._barcode_to_dict(barcode))

    @staticmethod
    def _barcode_to_dict(barcode) -> dict:
        """將 zxing-cpp Barcode 物件轉為 dict。"""
        pos = barcode.position
        return {
            "format": barcode.format.name,
            "text": barcode.text,
            "bytes_hex": barcode.bytes.hex() if barcode.bytes else "",
            "position": {
                "top_left": [pos.top_left.x, pos.top_left.y],
                "top_right": [pos.top_right.x, pos.top_right.y],
                "bottom_right": [pos.bottom_right.x, pos.bottom_right.y],
                "bottom_left": [pos.bottom_left.x, pos.bottom_left.y],
            },
            "orientation": barcode.orientation,
        }

    def scan_file(
        self,
        file_path: str,
        enable_enhance: bool = False,
    ) -> dict:
        """掃描檔案的主入口方法。

        Args:
            file_path: 圖片檔案路徑。
            enable_enhance: 是否啟用影像增強。

        Returns:
            標準化的掃描結果 dict，包含 status, results, time_taken_ms 等欄位。
        """
        start_time = time.perf_counter()

        try:
            pages = self.load_image(file_path)
        except ValueError as e:
            return self._error_result(str(e), file_path, start_time)
        except Exception as e:
            return self._error_result(f"圖片讀取失敗: {e}", file_path, start_time)

        all_results: list[dict] = []
        for page_idx, page_img in enumerate(pages):
            try:
                processed = self.preprocess(page_img, enable_enhance=enable_enhance)
                decoded = self.decode(processed)
            except Exception:
                continue

            for item in decoded:
                item["page"] = page_idx + 1
                all_results.append(item)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

        return {
            "status": "success" if all_results else "no_barcode",
            "results": all_results,
            "file_name": Path(file_path).name,
            "total_pages": len(pages),
            "time_taken_ms": elapsed_ms,
        }

    @staticmethod
    def _error_result(message: str, file_path: str, start_time: float) -> dict:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "status": "error",
            "message": message,
            "results": [],
            "file_name": Path(file_path).name,
            "total_pages": 0,
            "time_taken_ms": elapsed_ms,
        }


if __name__ == "__main__":
    """CLI 驗證：python engine.py <image_path>"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python engine.py <image_path>")
        sys.exit(1)

    engine = ScannerEngine()
    for path in sys.argv[1:]:
        print(f"\n掃描: {path}")
        result = engine.scan_file(path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
