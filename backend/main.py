"""FastAPI backend for VietOCR Labeling Tool."""

from pydantic import BaseModel
from PIL import Image
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, HTTPException, UploadFile
import numpy as np
import asyncio
import hashlib
import logging
import os
import re
import shutil
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from contextlib import asynccontextmanager

# Suppress noisy third-party warnings
warnings.filterwarnings("ignore", message=".*ccache.*")
warnings.filterwarnings("ignore", message=".*enable_nested_tensor.*")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_engine, UPLOAD_DIR, PAGES_DIR, OUTPUT_DIR
    global ALL_DIR, FIX_DIR, ALL_IMG_DIR, FIX_IMG_DIR
    from ocr_service import OCREngine
    ocr_engine = OCREngine()
    UPLOAD_DIR = ocr_engine.upload_dir
    PAGES_DIR = ocr_engine.pages_dir
    OUTPUT_DIR = ocr_engine.output_folder
    ALL_DIR = os.path.join(OUTPUT_DIR, "all")
    FIX_DIR = os.path.join(OUTPUT_DIR, "fix")
    ALL_IMG_DIR = os.path.join(ALL_DIR, "img")
    FIX_IMG_DIR = os.path.join(FIX_DIR, "img")
    os.makedirs(ALL_IMG_DIR, exist_ok=True)
    os.makedirs(FIX_IMG_DIR, exist_ok=True)
    # Clean leftover page images from previous sessions (keep uploads)
    _cleanup_pages()
    logger.info("OCR Engine loaded successfully.")
    yield

app = FastAPI(title="VietOCR Labeling API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
ocr_engine = None  # Initialized on startup

# Directories (will be set from OCREngine after init)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
PAGES_DIR = os.path.join(BASE_DIR, "data", "pages")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ALL_DIR = os.path.join(OUTPUT_DIR, "all")
FIX_DIR = os.path.join(OUTPUT_DIR, "fix")
ALL_IMG_DIR = os.path.join(ALL_DIR, "img")
FIX_IMG_DIR = os.path.join(FIX_DIR, "img")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PAGES_DIR, exist_ok=True)
os.makedirs(ALL_IMG_DIR, exist_ok=True)
os.makedirs(FIX_IMG_DIR, exist_ok=True)


def _sanitize_stem(filename: str) -> str:
    """Extract filename stem and sanitize for use in crop naming."""
    stem = os.path.splitext(filename)[0]
    # Replace spaces/special chars with underscore, keep only safe chars
    stem = re.sub(r"[^\w\-]", "_", stem)
    # Collapse multiple underscores
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem or "file"


def _page_id_from_path(page_path: str) -> str:
    """Extract the page number from the page filename.

    Page filenames look like: {uuid}_page_{N}.ext
    We extract N and return 'p{N}' so crop names become:
      {stem}_p{N}_{boxId}.jpg — fully deterministic across sessions.
    """
    basename = os.path.splitext(os.path.basename(page_path))[0]
    # Try to extract the page number after '_page_'
    match = re.search(r"_page_(\d+)$", basename)
    if match:
        return f"p{match.group(1)}"
    # Fallback: use last 8 chars of basename
    return basename[-8:]


def _upsert_annotation_lines(
    ann_file: str, new_lines: list[str], crop_names: list[str]
):
    """Write *new_lines* into *ann_file*, replacing any existing lines
    whose image path (first column) matches one of *crop_names*.

    This ensures that re-saving the same page overwrites old entries
    instead of appending duplicates.
    """
    # Build set of image paths that will be (re-)written
    new_img_paths = {f"img/{cn}" for cn in crop_names}

    existing_lines: list[str] = []
    if os.path.exists(ann_file):
        with open(ann_file, "r", encoding="utf-8") as f:
            existing_lines = [l.rstrip("\n") for l in f if l.strip()]

    # Keep lines whose image path is NOT in the new batch
    kept = [
        line for line in existing_lines
        if line.split("\t")[0] not in new_img_paths
    ]

    # Append new lines
    kept.extend(new_lines)

    # Rewrite the file
    with open(ann_file, "w", encoding="utf-8") as f:
        for line in kept:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
# Single-thread executor: OCR runs off the event loop so image serving
# is never blocked, but only one OCR job at a time (GPU/model safety).
_ocr_executor = ThreadPoolExecutor(max_workers=1)


def _cleanup_dir(directory: str):
    """Remove all files and sub-directories inside *directory*."""
    if not os.path.isdir(directory):
        return
    for entry in os.listdir(directory):
        entry_path = os.path.join(directory, entry)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)
        except OSError:
            pass


def _cleanup_pages():
    """Clean only the pages directory (used on startup)."""
    _cleanup_dir(PAGES_DIR)
    logger.info("Cleaned up temp dir: pages")


def _cleanup_all():
    """Clean both pages and uploads (used on 'new session')."""
    _cleanup_dir(PAGES_DIR)
    _cleanup_dir(UPLOAD_DIR)
    logger.info("Cleaned up temp dirs: pages + uploads")


def _run_ocr_sync(page_path: str) -> list[dict]:
    """Run OCR synchronously (called from thread pool)."""
    pil_img = Image.open(page_path).convert("RGB")
    return ocr_engine.run_ocr(pil_img)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class OCRRequest(BaseModel):
    page_path: str


class OCRBatchRequest(BaseModel):
    page_paths: List[str]


class BoxData(BaseModel):
    id: int
    box: List[int]  # [x, y, w, h]
    text: str
    original_text: str = ""  # OCR original text (to detect edits)


class SaveRequest(BaseModel):
    page_path: str
    boxes: List[BoxData]
    annotation_type: str = "train"  # "train" or "val"
    source_filename: Optional[str] = None  # original filename for naming
    save_mode: str = "dual"  # "dual" = all + fix, "fix_only" = only fix


# ---------------------------------------------------------------------------
# API: Upload (single file, can be called multiple times)
# ---------------------------------------------------------------------------
def _file_sha256(data: bytes) -> str:
    """Return hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _existing_file_hashes() -> dict[str, str]:
    """Return {sha256_hex: filename} for every file in UPLOAD_DIR."""
    hashes: dict[str, str] = {}
    if not os.path.isdir(UPLOAD_DIR):
        return hashes
    for fname in os.listdir(UPLOAD_DIR):
        fpath = os.path.join(UPLOAD_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        hashes[h] = fname
    return hashes


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an image or PDF. Returns file info + list of page paths.

    Deduplication rules (checked in order):
    1. **Name check** – if a file with the same name exists → HTTP 409
    2. **Hash check** – if any file in uploads has the same SHA-256 → HTTP 409
    """
    original_filename = file.filename or "unknown"
    ext = original_filename.rsplit(
        ".", 1)[-1].lower() if "." in original_filename else "bin"

    # Read file content into memory for hashing
    content = await file.read()

    # --- Check 1: duplicate filename ---
    if os.path.exists(os.path.join(UPLOAD_DIR, original_filename)):
        raise HTTPException(
            status_code=409,
            detail=f"File '{original_filename}' đã tồn tại trong thư mục uploads.",
        )

    # --- Check 2: duplicate content (hash) ---
    upload_hash = _file_sha256(content)
    existing_hashes = _existing_file_hashes()
    if upload_hash in existing_hashes:
        existing_name = existing_hashes[upload_hash]
        raise HTTPException(
            status_code=409,
            detail=(
                f"File có nội dung trùng với '{existing_name}' "
                f"đã upload trước đó."
            ),
        )

    # --- All checks passed → save ---
    file_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, original_filename)

    with open(saved_path, "wb") as buf:
        buf.write(content)

    pages: list[dict] = []

    if ext == "pdf":
        from ocr_service import OCREngine
        pil_pages = OCREngine.pdf_to_images(saved_path, dpi=144)

        for idx, pil_img in enumerate(pil_pages):
            page_name = f"{file_id}_page_{idx}.jpg"
            page_path = os.path.join(PAGES_DIR, page_name)
            pil_img.save(page_path, "JPEG", quality=95)
            pages.append({
                "page_index": idx,
                "page_path": page_path,
                "page_url": f"/api/image/pages/{page_name}",
                "thumbnail_url": f"/api/thumbnail/{page_name}",
                "source_filename": original_filename,
            })
    else:
        page_name = f"{file_id}_page_0.{ext}"
        page_path = os.path.join(PAGES_DIR, page_name)
        with open(page_path, "wb") as f:
            f.write(content)
        pages.append({
            "page_index": 0,
            "page_path": page_path,
            "page_url": f"/api/image/pages/{page_name}",
            "thumbnail_url": f"/api/thumbnail/{page_name}",
            "source_filename": original_filename,
        })

    return {
        "file_id": file_id,
        "filename": original_filename,
        "total_pages": len(pages),
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# API: Serve images
# ---------------------------------------------------------------------------
@app.get("/api/image/pages/{filename}")
async def get_page_image(filename: str):
    path = os.path.join(PAGES_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Page image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/thumbnail/{filename}")
async def get_thumbnail(filename: str):
    """Return a small thumbnail for the page selector bar."""
    path = os.path.join(PAGES_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Page image not found")

    thumb_dir = os.path.join(PAGES_DIR, "thumbs")
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, filename)

    if not os.path.exists(thumb_path):
        img = Image.open(path)
        img.thumbnail((200, 200))
        img.save(thumb_path, "JPEG", quality=80)

    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/api/image/crops/{filename}")
async def get_crop_image(filename: str):
    path = os.path.join(IMG_OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Crop image not found")
    return FileResponse(path, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# API: Run OCR on a single page
# ---------------------------------------------------------------------------
@app.post("/api/ocr")
async def run_ocr(request: OCRRequest):
    """Run detection + recognition on a single page image.

    OCR runs in a thread pool so the event loop stays free to serve images.
    """
    page_path = request.page_path
    if not os.path.exists(page_path):
        raise HTTPException(404, "Page image not found")

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _ocr_executor, _run_ocr_sync, page_path,
        )
        return {"page_path": page_path, "boxes": results}
    except Exception as exc:
        logger.exception("OCR failed")
        raise HTTPException(500, f"OCR processing failed: {exc}")


# ---------------------------------------------------------------------------
# API: Run OCR on multiple pages at once
# ---------------------------------------------------------------------------
@app.post("/api/ocr-batch")
async def run_ocr_batch(request: OCRBatchRequest):
    """Run detection + recognition on multiple pages sequentially.

    Each page runs in the thread pool so the event loop stays free.
    """
    loop = asyncio.get_event_loop()
    results: dict[str, list[dict]] = {}

    for i, page_path in enumerate(request.page_paths):
        if not os.path.exists(page_path):
            logger.warning("Page not found, skipping: %s", page_path)
            results[page_path] = []
            continue

        try:
            logger.info(
                "OCR batch [%d/%d]: %s",
                i + 1, len(request.page_paths),
                os.path.basename(page_path),
            )
            boxes = await loop.run_in_executor(
                _ocr_executor, _run_ocr_sync, page_path,
            )
            results[page_path] = boxes
        except Exception as exc:
            logger.exception("OCR failed for %s", page_path)
            results[page_path] = []

    return {"results": results}


# ---------------------------------------------------------------------------
# API: Save annotations  (naming: {stem}_{pageId}_{boxId}.jpg)
# Deterministic names → re-saving the same page overwrites, never duplicates.
# ---------------------------------------------------------------------------
@app.post("/api/save")
async def save_annotations(request: SaveRequest):
    """Crop each box from the page image and dual-write:

    - ``output/all/`` ← every checked box
    - ``output/fix/`` ← only boxes whose text was edited

    Crop images are named deterministically:
    ``{source_stem}_{page_id}_{box_id}.jpg``
    so clicking Save multiple times on the same page **overwrites**
    existing crops and replaces annotation lines (no duplicates).
    """
    page_path = request.page_path
    if not os.path.exists(page_path):
        raise HTTPException(404, "Page image not found")

    try:
        img = Image.open(page_path).convert("RGB")
    except Exception as exc:
        raise HTTPException(500, f"Cannot open image: {exc}")

    img_np = np.array(img)
    h_img, w_img = img_np.shape[:2]

    ann_name = (
        "train_annotation.txt"
        if request.annotation_type == "train"
        else "val_annotation.txt"
    )
    all_ann_file = os.path.join(ALL_DIR, ann_name)
    fix_ann_file = os.path.join(FIX_DIR, ann_name)

    # Deterministic prefix: stem + page_id
    source = request.source_filename or "unknown"
    stem = _sanitize_stem(source)
    page_id = _page_id_from_path(page_path)

    fix_only = request.save_mode == "fix_only"

    all_lines: list[str] = []
    fix_lines: list[str] = []
    all_crop_names: list[str] = []   # for upsert dedup
    fix_crop_names: list[str] = []

    for box_data in request.boxes:
        x, y, w, h = box_data.box
        text = box_data.text.strip()
        if not text:
            continue

        orig = box_data.original_text.strip() if box_data.original_text else ""
        is_edited = bool(orig) and text != orig
        if box_data.id < 3:  # debug first few boxes
            logger.info(
                "Box #%d | text=%r | orig=%r | edited=%s",
                box_data.id, text[:40], orig[:40], is_edited,
            )

        # In fix_only mode, skip boxes that were NOT edited
        if fix_only and not is_edited:
            continue

        x = max(0, int(x))
        y = max(0, int(y))
        w = min(int(w), w_img - x)
        h = min(int(h), h_img - y)
        if w <= 0 or h <= 0:
            continue

        crop = img.crop((x, y, x + w, y + h))
        # Deterministic name: same page + same box_id → same filename
        crop_name = f"{stem}_{page_id}_{box_data.id:03d}.jpg"
        line = f"img/{crop_name}\t{text}"

        if fix_only:
            os.makedirs(FIX_IMG_DIR, exist_ok=True)
            fix_crop_path = os.path.join(FIX_IMG_DIR, crop_name)
            crop.save(fix_crop_path, "JPEG", quality=95)
            fix_lines.append(line)
            fix_crop_names.append(crop_name)
        else:
            all_crop_path = os.path.join(ALL_IMG_DIR, crop_name)
            crop.save(all_crop_path, "JPEG", quality=95)
            all_lines.append(line)
            all_crop_names.append(crop_name)

            if is_edited:
                os.makedirs(FIX_IMG_DIR, exist_ok=True)
                fix_crop_path = os.path.join(FIX_IMG_DIR, crop_name)
                shutil.copy2(all_crop_path, fix_crop_path)
                fix_lines.append(line)
                fix_crop_names.append(crop_name)

    # Upsert annotation files (replace existing lines for same crops)
    if all_lines:
        _upsert_annotation_lines(all_ann_file, all_lines, all_crop_names)

    if fix_lines:
        _upsert_annotation_lines(fix_ann_file, fix_lines, fix_crop_names)

    saved_count = len(fix_lines) if fix_only else len(all_lines)

    return {
        "status": "success",
        "saved_count": saved_count,
        "fix_count": len(fix_lines),
        "annotation_file": ann_name,
    }


# ---------------------------------------------------------------------------
# API: Cleanup temp files (called on "new session")
# ---------------------------------------------------------------------------
@app.post("/api/cleanup")
async def cleanup():
    """Remove temp page images (new session). Uploads are kept."""
    _cleanup_pages()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API: Stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
async def get_stats():
    """Return counts for train/val annotations (all + fix)."""

    def _count_lines(path: str) -> int:
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    return {
        "train_count": _count_lines(os.path.join(ALL_DIR, "train_annotation.txt")),
        "val_count": _count_lines(os.path.join(ALL_DIR, "val_annotation.txt")),
        "train_fix_count": _count_lines(
            os.path.join(FIX_DIR, "train_annotation.txt")
        ),
        "val_fix_count": _count_lines(
            os.path.join(FIX_DIR, "val_annotation.txt")
        ),
    }


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
