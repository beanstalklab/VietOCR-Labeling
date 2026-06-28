# VietOCR Labeling Tool

A full-stack web application for labeling and fine-tuning Vietnamese OCR models. It lets users upload PDF or image documents, automatically detect and recognize text using **PaddleOCR** (detection) + **VietOCR** (recognition), then review, correct, and export training annotations — all from a modern browser UI.

## Features

- **Upload & Preview** — Drag-and-drop PDF or image files; pages render as navigable thumbnails
- **Automatic OCR** — PaddleOCR v5 text detection + VietOCR (VGG-Transformer) recognition, GPU-accelerated
- **Interactive Bounding Boxes** — Boxes on the canvas can be selected/deselected and highlight in real time
- **Inline Text Editing** — Recognized text can be reviewed and corrected in a sidebar editor with auto-resize textareas
- **Dual-output Annotations** — Saves **all** labeled samples and separately saves **only edited** (corrected) samples for targeted fine-tuning
- **Idempotent Save** — Deterministic crop naming (`{stem}_p{page}_{boxId}.jpg`) and upsert-based annotation writes — saving repeatedly never creates duplicates
- **Upload Deduplication** — Rejects files with duplicate names or duplicate content (SHA-256 hash check)
- **Train/Val Split** — Switches between `train` and `val` annotation types per save
- **Batch Processing** — Multiple files can be uploaded and processed in one session
- **One-click Launch** — A single `run.sh` script starts both backend and frontend

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12+ |
| Node.js | 18+ |
| uv | (Python package manager) |
| Poppler | (for `pdf2image`) |
| CUDA | Optional, for GPU acceleration |

### Model Weights

The application requires the following model files:

1. **PaddleOCR** text detection model → `backend/models/paddle/PP-OCRv5_server_det/`
2. **VietOCR** recognition weights → `backend/models/vietocr/weights/vgg_transformer.pth`

> Model paths are configured in `backend/configs/setting.ini`.

## Quick Start

### 1. Clone the repository

The following commands clone the repository:

```bash
git clone https://github.com/beanstalklab/VietOCR-Labeling.git
cd VietOCR-Labeling
```

### 2. Install backend dependencies

The backend uses [uv](https://docs.astral.sh/uv/) for dependency management (`pyproject.toml` + `uv.lock`). On Linux, PyTorch is pulled from the CUDA 12.6 index automatically.

```bash
cd backend
uv sync
cd ..
```

> **Note**: `run.sh` launches the backend with `uv run main.py`, so `uv` must be installed and available on the `PATH`.

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Configure model paths

The model file locations are defined in `backend/configs/setting.ini`:

```ini
[Model-Paddle]
det_model_dir=./models/paddle/PP-OCRv5_server_det

[Model-Vietocr]
base_config=./configs/base.yml
recognize_config=./configs/vgg-transformer.yml
recognize_model_weights=./models/vietocr/weights/vgg_transformer.pth
```

### 5. Launch

```bash
chmod +x run.sh
./run.sh
```

This starts:
- **Backend** at `http://localhost:8005` (FastAPI + Uvicorn with auto-reload)
- **Frontend** at `http://localhost:5175` (Vite dev server)

The UI is then available at `http://localhost:5175`.

## Usage Workflow

```
1. Upload     -  PDF/images are dragged onto the upload area
2. OCR        -  Text is auto-detected and recognized (or per page)
3. Review     -  Bounding boxes are selected and recognized text reviewed
4. Correct    -  Misrecognized text is edited in the sidebar
5. Save       -  "Lưu" exports cropped images + annotations
6. Navigate   -  "Tiếp →" moves to the next page
```

### Output Format

Annotations follow the standard VietOCR training format:

```
img/209_p0_001.jpg	HỢP ĐỒNG DỊCH VỤ CỔNG THANH TOÁN ĐIỆN TỬ
img/209_p0_002.jpg	VÀ DỊCH VỤ HỖ TRỢ THU HỘ, CHI HỘ
img/209_p0_003.jpg	Số: 2742/2025/ECOM
```

- **`output/all/`** - All checked boxes (for the full training set)
- **`output/fix/`** - Only boxes whose text was manually corrected (for targeted fine-tuning)

## Configuration

### Backend port

The port is defined in `run.sh` (line: `--port 8005`) and `frontend/vite.config.ts` (proxy target).

### Python environment

By default `run.sh` runs the backend via `uv run main.py`, which uses the project-managed virtual environment created by `uv sync`.

If Conda or system Python is preferred, `run.sh` can be edited to replace `uv run main.py` with another command (e.g. `python -m uvicorn main:app --reload --port 8005`).

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Upload PDF/image (dedup by name + SHA-256) |
| `POST` | `/api/ocr` | Run OCR on a single page |
| `POST` | `/api/ocr-batch` | Run OCR on multiple pages |
| `POST` | `/api/save` | Save cropped images + annotations |
| `POST` | `/api/cleanup` | Clear temporary data |
| `GET` | `/api/stats` | Get annotation statistics |
| `GET` | `/api/image/pages/{name}` | Serve page image |
| `GET` | `/api/thumbnail/{name}` | Serve page thumbnail |
| `GET` | `/api/image/crops/{name}` | Serve cropped text image |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Uvicorn, Python 3.12+ |
| OCR Detection | PaddleOCR v5 (TextDetection) |
| OCR Recognition | VietOCR (VGG-Transformer) |
| Frontend | Vue 3, TypeScript, Vite 6 |
| Styling | Tailwind CSS 4 |
| State Management | Pinia |
| HTTP Client | Axios |

## License

Released under the [MIT License](LICENSE).
