"""OCR Service: PaddleOCR detection + VietOCR recognition."""

import configparser
import logging
import os

import cv2
import numpy as np
import yaml
from paddleocr import TextDetection
from pdf2image import convert_from_path
from PIL import Image
from torch import cuda

from utils.predictor import Predictor

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------
def load_config_from_file(fbase_config: str, fmodel_config: str) -> dict:
    """Merge base.yml + model-specific yml into a single config dict."""
    with open(fbase_config, "r", encoding="utf-8") as f:
        base = yaml.safe_load(f)

    with open(fmodel_config, "r", encoding="utf-8") as f:
        model_cfg = yaml.safe_load(f)

    # model_cfg keys override base
    merged = {**base, **model_cfg}
    return merged


def _load_setting(ini_path: str) -> configparser.ConfigParser:
    """Load setting.ini."""
    cfg = configparser.ConfigParser()
    cfg.read(ini_path, encoding="utf-8")
    return cfg


# ------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------
def margin_pst(point):
    """Expand detected polygon box by a small margin."""
    top_min_y = int(
        min([point[0][1], point[1][1], point[2][1], point[3][1]])
    )
    bot_max_y = int(
        max([point[0][1], point[1][1], point[2][1], point[3][1]])
    )

    margin = int((bot_max_y - top_min_y) / 7)

    point[0][0] = point[0][0] - margin
    point[0][1] = point[0][1] - margin
    point[1][0] = point[1][0] + margin
    point[1][1] = point[1][1] - margin
    point[2][0] = point[2][0] + margin
    point[2][1] = point[2][1] + margin
    point[3][0] = point[3][0] - margin
    point[3][1] = point[3][1] + margin

    return point


# ------------------------------------------------------------------
# OCR Engine
# ------------------------------------------------------------------
class OCREngine:
    """Encapsulates PaddleOCR text detection and VietOCR recognition."""

    def __init__(self, setting_path: str | None = None):
        if setting_path is None:
            setting_path = os.path.join(BASE_DIR, "configs", "setting.ini")

        cfg = _load_setting(setting_path)

        # --- Device ---
        device = "cuda" if cuda.is_available() else "cpu"
        logger.info("Using device: %s", device)

        # --- Detection model (PaddleOCR) ---
        det_model_dir = os.path.join(
            BASE_DIR, cfg.get("Model-Paddle", "det_model_dir"),
        )
        logger.info("Loading PaddleOCR TextDetection from %s", det_model_dir)
        self.detect_model = TextDetection(model_dir=det_model_dir)

        # --- Recognition model (VietOCR) ---
        fbase_config = os.path.join(
            BASE_DIR, cfg.get("Model-Vietocr", "base_config"),
        )
        fmodel_config = os.path.join(
            BASE_DIR, cfg.get("Model-Vietocr", "recognize_config"),
        )
        recognize_model_weights = os.path.join(
            BASE_DIR, cfg.get("Model-Vietocr", "recognize_model_weights"),
        )

        config = load_config_from_file(
            fbase_config=fbase_config, fmodel_config=fmodel_config,
        )
        config["weights"] = recognize_model_weights
        config["device"] = device
        config["cnn"]["pretrained"] = False

        logger.info("Loading VietOCR model (%s)", config.get("backbone"))
        self.recognizer_model = Predictor(config)

        # --- Output dirs ---
        data_folder = os.path.join(
            BASE_DIR, cfg.get("Local-Data", "local_data_folder"),
        )
        self.output_folder = os.path.join(
            BASE_DIR, cfg.get("Local-Data", "local_output_folder"),
        )
        self.img_output_dir = os.path.join(self.output_folder, "img")
        self.upload_dir = os.path.join(data_folder, "uploads")
        self.pages_dir = os.path.join(data_folder, "pages")
        os.makedirs(self.img_output_dir, exist_ok=True)
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.pages_dir, exist_ok=True)

        logger.info("OCREngine initialised successfully.")

    # ------------------------------------------------------------------
    # PDF helpers
    # ------------------------------------------------------------------
    @staticmethod
    def pdf_to_images(pdf_path: str, dpi: int = 200) -> list[Image.Image]:
        """Convert each page of a PDF to a PIL Image."""
        return convert_from_path(pdf_path, dpi=dpi)

    # ------------------------------------------------------------------
    # Detection + Recognition
    # ------------------------------------------------------------------
    def run_ocr(self, image: Image.Image) -> list[dict]:
        """Run detection + recognition on a single PIL image.

        Returns list of dicts: [{id, box:[x,y,w,h], text}, ...]
        """
        # img_np = np.array(image.convert("RGB"))
        img_np = np.array(image)
        print(img_np.shape)
        h_img, w_img = img_np.shape[:2]

        # --- Detection ---
        result_boxes = self.detect_model.predict(input=img_np)[0]["dt_polys"]

        if len(result_boxes) == 0:
            return []

        # Reverse order (as per original code)
        result_boxes = result_boxes[::-1]

        all_segments_to_ocr = []
        box_coords: list[list[int]] = []

        for box in result_boxes:
            box_copy = np.array(box.copy(), dtype=np.float32)

            # Add margin to border box
            box_copy = margin_pst(box_copy)

            # Get bounding rectangle: x, y (top left) and width, height
            x, y, w, h = cv2.boundingRect(box_copy)
            if x < 0:
                x = 0
            if y < 0:
                y = 0

            # Clamp to image boundaries
            # w = min(w, w_img - x)
            # h = min(h, h_img - y)

            if w <= 0 or h <= 0:
                continue

            # Crop image with coord box
            cropped_image = img_np[y:y + h, x:x + w]

            all_segments_to_ocr.append(cropped_image)
            box_coords.append([x, y, w, h])

        if not all_segments_to_ocr:
            return []

        # --- Recognition (batch) ---
        all_ocr_results = self.recognizer_model.predict_batch(
            all_segments_to_ocr,
        )

        results = []
        for i, text in enumerate(all_ocr_results):
            results.append({
                "id": i,
                "box": box_coords[i],
                "text": text,
            })
        return results
