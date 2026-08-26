import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


async def detect_scanned_pages(document_id: str) -> bool:
    """
    Detect if a PDF contains scanned pages (mostly images).
    Uses simple heuristics - in production, use more sophisticated detection.
    """
    try:
        import fitz
        from app.config import settings

        file_path = f"{settings.UPLOAD_DIR}/{document_id}.pdf"
        doc = fitz.open(file_path)

        scanned_count = 0
        for page in doc:
            text = page.get_text().strip()
            if len(text) < 50:
                scanned_count += 1

        doc.close()
        return scanned_count > len(doc) * 0.5

    except Exception:
        return False


async def perform_ocr(document_id: str) -> str:
    """
    Perform OCR using PaddleOCR.
    """
    try:
        from paddleocr import PaddleOCR
        import fitz
        from app.config import settings
        from PIL import Image
        import io

        file_path = f"{settings.UPLOAD_DIR}/{document_id}.pdf"
        doc = fitz.open(file_path)

        ocr = PaddleOCR(use_angle_cls=True, lang="en")
        all_text = []

        for page_num, page in enumerate(doc):
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            result = ocr.ocr(img, cls=True)
            page_text = []
            for line in result[0] if result else []:
                page_text.append(line[1][0])
            all_text.append(f"--- Page {page_num + 1} ---\n" + "\n".join(page_text))

        doc.close()
        return "\n\n".join(all_text)

    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""
