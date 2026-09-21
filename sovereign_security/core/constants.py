# Core security constants

DECISION_ALLOW = "ALLOW"
DECISION_BLOCK = "BLOCK"
DECISION_WARN = "WARN"
DECISION_QUARANTINE = "QUARANTINE"
DECISION_REVIEW = "REVIEW"

RISK_HIGH = "HIGH"
RISK_MEDIUM = "MEDIUM"
RISK_LOW = "LOW"
RISK_NONE = "NONE"

# Default maximums
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 89478485 # Approx 4k * 4k * 5
MAX_PDF_PAGES = 100

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".txt", ".md", ".csv"
}

ALLOWED_MIME_TYPES = {
    "application/pdf", "image/png", "image/jpeg", "image/tiff", "image/bmp", "text/plain", "text/markdown", "text/csv"
}
