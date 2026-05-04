"""
Barcode Reader — 核心掃描引擎

負責影像讀取、預處理與條碼解碼，不依賴任何 UI 套件。
採用多策略掃描：全圖 + 放大 + 形態學區域偵測 + 多 Binarizer 輪替，最大化條碼辨識率。
"""

import json
import time
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import zxingcpp

SUPPORTED_EXTENSIONS: set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".avif",
}

_PIL_FORMATS: set[str] = {".avif"}

MAX_IMAGE_DIMENSION: int = 2000

ScanMode = Literal["fast", "normal", "deep"]

BINARIZERS = [
    zxingcpp.Binarizer.LocalAverage,
    zxingcpp.Binarizer.GlobalHistogram,
    zxingcpp.Binarizer.FixedThreshold,
]


class ScannerEngine:
    """條碼掃描引擎：讀取圖片 → 預處理 → 多策略解碼。"""

    @staticmethod
    def load_image(file_path: str) -> list[np.ndarray]:
        """讀取圖片檔案，回傳灰度 numpy array 的 list (多頁 TIFF 會有多個元素)。"""
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
        page_count = cv2.imcount(file_path)
        if page_count <= 0:
            raise ValueError(f"無法讀取 TIFF 檔案或檔案為空: {file_path}")

        success, pages = cv2.imreadmulti(file_path, flags=cv2.IMREAD_GRAYSCALE)
        if not success or not pages:
            raise ValueError(f"TIFF 讀取失敗: {file_path}")

        return pages

    @staticmethod
    def _load_via_pillow(file_path: str) -> list[np.ndarray]:
        import pillow_avif  # noqa: F401
        from PIL import Image

        pil_img = Image.open(file_path).convert("L")
        return [np.array(pil_img)]

    @staticmethod
    def preprocess(image: np.ndarray, enable_enhance: bool = False) -> np.ndarray:
        """影像預處理：確保灰度 + 可選增強 + 大圖縮放。"""
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
    def decode(
        image: np.ndarray,
        scan_mode: ScanMode = "deep",
        formats: zxingcpp.BarcodeFormats | None = None,
    ) -> list[dict]:
        """多策略條碼解碼。

        Args:
            image: 灰度 numpy ndarray。
            scan_mode: 掃描深度 — fast (僅全圖)、normal (全圖+放大)、deep (全部策略)。
            formats: 限制搜尋的條碼格式，None 表示搜尋全部。

        Returns:
            去重後的解碼結果列表。
        """
        seen: set[tuple[str, str]] = set()
        all_results: list[dict] = []
        fmt = formats or zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.All)

        # Pass 1: 全圖原圖 + 多 Binarizer 輪替
        for binarizer in BINARIZERS:
            for bc in zxingcpp.read_barcodes(
                image,
                formats=fmt,
                try_rotate=True,
                try_downscale=True,
                try_invert=True,
                binarizer=binarizer,
            ):
                ScannerEngine._add_unique(bc, seen, all_results)

        h, w = image.shape[:2]
        min_dim = min(h, w)

        # Pass 2: 放大掃描 (捕捉微小條碼)
        if scan_mode in ("normal", "deep") and min_dim < 1500:
            scale = 4 if min_dim < 500 else 2
            interpolation = cv2.INTER_CUBIC if scale >= 3 else cv2.INTER_LINEAR
            img_up = cv2.resize(
                image, (w * scale, h * scale), interpolation=interpolation
            )
            for bc in zxingcpp.read_barcodes(
                img_up,
                formats=fmt,
                try_rotate=True,
                try_downscale=False,
                try_invert=True,
            ):
                ScannerEngine._add_unique(bc, seen, all_results)

        if scan_mode != "deep":
            return all_results

        # Pass 3: 形態學區域偵測 → 裁切 + 5x 放大掃描
        ScannerEngine._scan_morphology_regions(image, seen, all_results, fmt)

        # Pass 4: 低解析度 1D 條碼 ROI 掃描
        if 450 <= min_dim < 900 and len(all_results) < 5:
            ScannerEngine._scan_linear_regions(image, seen, all_results, formats)

        # Pass 5: 低解析度圖片 4x 放大 + 多閥值二值化 (破解浮水印 / 低對比)
        if min_dim < 500:
            ScannerEngine._scan_upsampled_thresholds(image, seen, all_results, fmt)

        return all_results

    @staticmethod
    def _scan_upsampled_thresholds(
        image: np.ndarray,
        seen: set[tuple[str, str]],
        results: list[dict],
        formats: zxingcpp.BarcodeFormats,
    ) -> None:
        """低解析度圖片 4x 放大 + 多閥值二值化，用於破解浮水印、低解析度等干擾。"""
        h, w = image.shape[:2]
        img4x = cv2.resize(image, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)

        for t in (120, 140, 160):
            bin_img = cv2.threshold(img4x, t, 255, cv2.THRESH_BINARY)[1]
            for bc in zxingcpp.read_barcodes(
                bin_img,
                formats=formats,
                try_rotate=True,
                try_downscale=False,
                try_invert=True,
            ):
                ScannerEngine._add_unique(bc, seen, results)

    @staticmethod
    def _scan_morphology_regions(
        image: np.ndarray,
        seen: set[tuple[str, str]],
        results: list[dict],
        formats: zxingcpp.BarcodeFormats,
    ) -> None:
        """用形態學方法偵測條碼區域，裁切放大後逐一掃描。"""
        h, w = image.shape[:2]

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
                crop_up,
                formats=formats,
                try_rotate=True,
                try_downscale=False,
                try_invert=True,
            ):
                ScannerEngine._add_unique(bc, seen, results)

    @staticmethod
    def _scan_linear_regions(
        image: np.ndarray,
        seen: set[tuple[str, str]],
        results: list[dict],
        formats: zxingcpp.BarcodeFormats | None,
    ) -> None:
        """針對低解析度 1D 條碼，切出候選區域後多倍率掃描。"""
        h, w = image.shape[:2]
        linear_formats = formats or zxingcpp.BarcodeFormats(
            zxingcpp.BarcodeFormat.AllLinear
        )

        grad_x = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=-1)
        grad_y = cv2.Sobel(image, cv2.CV_32F, 0, 1, ksize=-1)
        grad = cv2.subtract(grad_x, grad_y)
        grad = cv2.convertScaleAbs(grad)
        grad = cv2.GaussianBlur(grad, (3, 3), 0)
        _, binary = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        for kernel_size in ((21, 7), (31, 9)):
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            closed = cv2.erode(closed, None, iterations=1)
            closed = cv2.dilate(closed, None, iterations=1)

            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:80]:
                x, y, cw, ch = cv2.boundingRect(cnt)
                if cw * ch < 500 or cw < 30 or ch < 8 or cw / ch < 1.2:
                    continue

                pad = max(8, int(min(cw, ch) * 0.25))
                x1, y1 = max(0, x - pad), max(0, y - pad)
                x2, y2 = min(w, x + cw + pad), min(h, y + ch + pad)
                crop = image[y1:y2, x1:x2]

                for variant in ScannerEngine._linear_crop_variants(crop):
                    for binarizer in BINARIZERS:
                        for bc in zxingcpp.read_barcodes(
                            variant,
                            formats=linear_formats,
                            try_rotate=True,
                            try_downscale=False,
                            try_invert=True,
                            binarizer=binarizer,
                        ):
                            if ScannerEngine._is_plausible_linear_result(bc):
                                ScannerEngine._add_unique(bc, seen, results)

    @staticmethod
    def _linear_crop_variants(crop: np.ndarray) -> list[np.ndarray]:
        variants: list[np.ndarray] = []
        for sx, sy in ((3, 3), (4, 4), (6, 3)):
            up = cv2.resize(
                crop,
                (crop.shape[1] * sx, crop.shape[0] * sy),
                interpolation=cv2.INTER_CUBIC,
            )
            variants.append(up)
            variants.append(
                cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
            )
            variants.append(cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
            variants.append(cv2.threshold(up, 120, 255, cv2.THRESH_BINARY)[1])
        return variants

    @staticmethod
    def _is_plausible_linear_result(barcode: zxingcpp.Barcode) -> bool:
        fmt = barcode.format.name
        text = barcode.text
        digits = text.isdigit()

        if fmt == "EAN13":
            return len(text) == 13 and digits
        if fmt == "EAN8":
            return len(text) == 8 and digits
        if fmt == "UPCA":
            return len(text) == 12 and digits
        if fmt == "UPCE":
            return len(text) in (6, 8) and digits
        if fmt in ("ITF", "ITF14"):
            return len(text) >= 6 and digits
        if fmt.startswith("DataBar"):
            return len(text) >= 8
        if fmt in ("Code128", "Code39", "Code93", "Codabar"):
            return len(text.strip()) >= 3
        return True

    @staticmethod
    def _add_unique(
        barcode: zxingcpp.Barcode,
        seen: set[tuple[str, str]],
        results: list[dict],
    ) -> None:
        """去重加入解碼結果。"""
        key = (barcode.format.name, barcode.text)
        if key not in seen:
            seen.add(key)
            results.append(ScannerEngine._barcode_to_dict(barcode))

    @staticmethod
    def _barcode_to_dict(barcode: zxingcpp.Barcode) -> dict:
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
        scan_mode: ScanMode = "deep",
        formats: list[str] | None = None,
    ) -> dict:
        """掃描檔案的主入口方法。

        Args:
            file_path: 圖片檔案路徑。
            enable_enhance: 是否啟用影像增強。
            scan_mode: 掃描深度 — fast / normal / deep。
            formats: 限制搜尋的條碼格式名稱列表 (如 ["QRCode", "EAN13"])，None 表示全部。

        Returns:
            標準化的掃描結果 dict。
        """
        start_time = time.perf_counter()
        try:
            zxing_fmts = self._parse_formats(formats)
        except ValueError as e:
            return self._error_result(str(e), file_path, start_time)

        try:
            pages = self.load_image(file_path)
        except ValueError as e:
            return self._error_result(str(e), file_path, start_time)
        except Exception as e:
            return self._error_result(f"圖片讀取失敗: {e}", file_path, start_time)

        all_results: list[dict] = []
        page_errors: list[dict] = []
        seen_results: set[tuple[int, str, str]] = set()
        enhanced_retry_pages: list[int] = []
        for page_idx, page_img in enumerate(pages):
            page_num = page_idx + 1
            page_result_count = len(all_results)
            try:
                processed = self.preprocess(page_img, enable_enhance=enable_enhance)
                decoded = self.decode(processed, scan_mode=scan_mode, formats=zxing_fmts)
            except Exception as e:
                decoded = []
                page_errors.append({"page": page_num, "message": str(e)})

            self._append_page_results(decoded, page_num, seen_results, all_results)
            normal_result_count = len(all_results) - page_result_count

            if self._should_retry_enhanced(
                page_img, normal_result_count, enable_enhance, scan_mode
            ):
                try:
                    enhanced = self.preprocess(page_img, enable_enhance=True)
                    enhanced_decoded = self.decode(
                        enhanced, scan_mode=scan_mode, formats=zxing_fmts
                    )
                except Exception:
                    enhanced_decoded = []

                before_retry_count = len(all_results)
                self._append_page_results(
                    enhanced_decoded, page_num, seen_results, all_results
                )
                if len(all_results) > before_retry_count:
                    enhanced_retry_pages.append(page_num)

            if len(all_results) > page_result_count:
                page_errors = [
                    err for err in page_errors if err.get("page") != page_num
                ]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
        if page_errors and len(page_errors) == len(pages):
            return {
                "status": "error",
                "message": "所有頁面掃描失敗: "
                + "; ".join(
                    f"第 {err['page']} 頁: {err['message']}" for err in page_errors
                ),
                "results": [],
                "file_name": Path(file_path).name,
                "total_pages": len(pages),
                "time_taken_ms": elapsed_ms,
                "page_errors": page_errors,
            }

        result = {
            "status": "success" if all_results else "no_barcode",
            "results": all_results,
            "file_name": Path(file_path).name,
            "total_pages": len(pages),
            "time_taken_ms": elapsed_ms,
        }
        if page_errors:
            result["page_errors"] = page_errors
        if enhanced_retry_pages:
            result["enhanced_retry_pages"] = enhanced_retry_pages
        return result

    @staticmethod
    def _append_page_results(
        decoded: list[dict],
        page_num: int,
        seen: set[tuple[int, str, str]],
        results: list[dict],
    ) -> None:
        """加入單頁結果，合併原圖掃描與強化重試的重複項目。"""
        for item in decoded:
            key = (page_num, item["format"], item["text"])
            if key in seen:
                continue
            seen.add(key)
            item["page"] = page_num
            results.append(item)

    @staticmethod
    def _should_retry_enhanced(
        image: np.ndarray,
        found_count: int,
        enable_enhance: bool,
        scan_mode: ScanMode,
    ) -> bool:
        """決定是否用 CLAHE 強化重試，避免 deep 模式無條件加倍耗時。"""
        if enable_enhance or scan_mode != "deep":
            return False
        if found_count == 0:
            return True

        h, w = image.shape[:2]
        aspect_ratio = max(h, w) / min(h, w)
        return min(h, w) < 500 and aspect_ratio > 2.5 and found_count < 3

    @staticmethod
    def _parse_formats(formats: list[str] | None) -> zxingcpp.BarcodeFormats | None:
        """將格式名稱字串列表轉為 zxingcpp.BarcodeFormats。"""
        if not formats:
            return None
        invalid = [f for f in formats if not hasattr(zxingcpp.BarcodeFormat, f)]
        if invalid:
            raise ValueError(f"不支援的條碼格式: {', '.join(invalid)}")

        fmt_list = [getattr(zxingcpp.BarcodeFormat, f) for f in formats]
        return zxingcpp.BarcodeFormats(fmt_list)

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

    @staticmethod
    def available_formats() -> list[dict]:
        """回傳可用的條碼格式列表，供 UI 下拉選單使用。"""
        format_groups = [
            ("全部", None),
            ("僅一維碼", ["AllLinear"]),
            ("僅二維碼", ["AllMatrix"]),
            ("QR Code", ["QRCode"]),
            ("EAN-13 / UPC-A", ["EAN13", "UPCA"]),
            ("Code 128", ["Code128"]),
            ("Code 39", ["Code39"]),
            ("ITF", ["ITF"]),
            ("Data Matrix", ["DataMatrix"]),
            ("PDF417", ["PDF417"]),
            ("Aztec", ["AztecCode"]),
        ]
        return [{"label": label, "value": ids} for label, ids in format_groups]


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
