
from PIL import Image
import pytesseract, re, io, os, logging, math, ctypes, sys, glob
import cv2 as cv
from image_utils import imread_unicode
import numpy as np
from datetime import datetime
from mss import mss
# Paddle OCR disabled by request; keep stub to avoid optional import cost
PaddleOCR = None  # type: ignore
from log_utils import enforce_logs_quota

# Heuristics tuned for Russian+English text from LE tooltip
TESS_CONFIG = "--oem 1 --psm 6 -c preserve_interword_spaces=1"

# Default Windows installation path for Tesseract OCR
DEFAULT_TESSERACT_EXE = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

logger = logging.getLogger(__name__)

# App-controlled flag to save debug images (default: off)

_DEBUG_SAVE_IMAGES = False


def _pil_to_gray_np(img: Image.Image) -> np.ndarray:
    """Convert PIL image to grayscale numpy array."""
    arr = np.array(img.convert('RGB'))
    return cv.cvtColor(arr, cv.COLOR_RGB2GRAY)


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Enhance tooltip ROI before feeding it to Tesseract."""
    try:
        gray = _pil_to_gray_np(img)
        # Stretch contrast to cover full dynamic range
        norm = cv.normalize(gray, None, alpha=0, beta=255, norm_type=cv.NORM_MINMAX)
        # Adaptive contrast limited histogram equalization is robust on UI gradients
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        eq = clahe.apply(norm)
        # Gentle denoising helps reduce compression artifacts without blurring text
        denoised = cv.fastNlMeansDenoising(eq, h=18, templateWindowSize=7, searchWindowSize=21)
        # Adaptive threshold emphasises glyph strokes despite glow/gradients
        thresh = cv.adaptiveThreshold(
            denoised,
            255,
            cv.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv.THRESH_BINARY,
            31,
            9,
        )
        inverted = cv.bitwise_not(thresh)
        return Image.fromarray(inverted, mode='L')
    except Exception:
        # Fallback to simple grayscale if advanced pipeline fails
        return img.convert('L')


def _save_debug_image(img: Image.Image, path: str | None) -> None:
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        img.save(path)
        enforce_logs_quota(300.0, logs_dir=os.path.dirname(path) or 'logs')
    except Exception as e:
        logger.debug('Failed to save debug image %s: %s', path, e)


def set_debug_image_saving(enabled: bool) -> None:
    global _DEBUG_SAVE_IMAGES
    _DEBUG_SAVE_IMAGES = bool(enabled)


def _debug_enabled() -> bool:
    # Enable saving images only if the app flag is set or env overrides
    if _DEBUG_SAVE_IMAGES:
        return True
    env = os.getenv("PRICER_DEBUG_SAVE", "0").strip().lower()
    return env in ("1", "true", "yes", "on")

def _template_threshold_default() -> float:
    try:
        v = float(os.getenv("PRICER_TEMPLATE_THRESHOLD", "0.60"))
        if 0.0 < v <= 1.0:
            return v
    except Exception:
        pass
    return 0.60

def _resolve_tesseract_path(bin_path: str | None) -> str | None:
    """Resolve a user-provided path to the tesseract executable.

    Accepts either a direct path to `tesseract.exe` or a directory path
    (in which case `tesseract.exe` is appended). Returns None if not resolvable.
    """
    if not bin_path:
        return None
    path = bin_path.strip().strip('"')
    if not path:
        return None
    if os.path.isdir(path):
        candidate = os.path.join(path, "tesseract.exe")
    else:
        candidate = path
    return candidate


def set_tesseract_path(bin_path: str | None):
    # Prefer provided path; fall back to default Windows path if present
    candidate = _resolve_tesseract_path(bin_path) or DEFAULT_TESSERACT_EXE
    if candidate and os.path.exists(candidate):
        pytesseract.pytesseract.tesseract_cmd = candidate
        logger.info("Using Tesseract at: %s", candidate)
    else:
        # Leave pytesseract to use PATH; log warning for visibility
        logger.warning("Tesseract not found at provided/default path: %s", candidate)

def _screen_geom():
    with mss() as sct:
        mon = sct.monitors[0]
        return mon["left"], mon["top"], mon["width"], mon["height"]


def _get_cursor_pos() -> tuple[int, int] | None:
    if os.name == "nt":
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    return None


def _grab_bbox(left: int, top: int, width: int, height: int) -> Image.Image:
    with mss() as sct:
        raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        return img


def grab_screen() -> Image.Image:
    x, y, w, h = _screen_geom()
    return _grab_bbox(x, y, w, h)



def ocr_full(img: Image.Image, debug_save: str | None = None, allow_soft: bool = True):
    """Run OCR on a tooltip ROI with preprocessing and optional debug dumps."""
    logger.debug("Starting OCR on image size: %s", getattr(img, 'size', None))
    processed = _preprocess_for_ocr(img)
    if debug_save and _debug_enabled():
        root, ext = os.path.splitext(debug_save)
        ext = ext or '.png'
        raw_path = f"{root}_raw{ext}"
        prep_path = f"{root}_prep{ext}"
        _save_debug_image(img.convert('RGB'), raw_path)
        _save_debug_image(processed, prep_path)
    data = pytesseract.image_to_data(
        processed,
        lang="rus+eng",
        config=TESS_CONFIG,
        output_type=pytesseract.Output.DICT,
    )
    return data


## Paddle OCR removed — using Tesseract only

# Title band helpers removed in simplified pipeline

_ALLOWED_RE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё\-\(\)\[\] \+']+")


def _clean_text(s: str) -> str:
    s = _ALLOWED_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def parse_item(data_dict):
    """Parse Tesseract output and extract tooltip name/potential."""
    n = len(data_dict["text"])
    grouped: dict[tuple[int, int, int, int], dict] = {}
    for i in range(n):
        txt_raw = (data_dict["text"][i] or "").strip()
        if not txt_raw:
            continue
        key = (
            data_dict["page_num"][i],
            data_dict["block_num"][i],
            data_dict["par_num"][i],
            data_dict["line_num"][i],
        )
        entry = grouped.setdefault(
            key,
            {"words": [], "lefts": [], "tops": [], "confs": []},
        )
        entry["words"].append(txt_raw)
        entry["lefts"].append(int(data_dict["left"][i]))
        entry["tops"].append(int(data_dict["top"][i]))
        try:
            conf = float(data_dict["conf"][i])
        except Exception:
            conf = 0.0
        entry["confs"].append(conf)

    sorted_line_items: list[tuple[int, int, str]] = []
    candidates: list[tuple[float, int, int, str]] = []
    banned_tokens = ("легендар", "потенциал", "броня")
    for val in grouped.values():
        text = _clean_text(" ".join(val["words"]))
        if not text:
            continue
        top = min(val["tops"]) if val["tops"] else 0
        left = min(val["lefts"]) if val["lefts"] else 0
        avg_conf = sum(val["confs"]) / max(1, len(val["confs"]))
        sorted_line_items.append((top, left, text))

        low = text.lower()
        length_norm = min(len(text), 28) / 28.0
        conf_norm = max(0.0, min(1.0, avg_conf / 100.0))
        alpha_ratio = sum(ch.isalpha() for ch in text) / max(1, len(text))
        digit_ratio = sum(ch.isdigit() for ch in text) / max(1, len(text))
        penalty = 0.0
        if low.startswith('+'):
            penalty += 0.35
        if re.match(r'^\d{1,3}\b', low):
            penalty += 0.25
        if any(tok in low for tok in banned_tokens):
            penalty += 0.6
        if digit_ratio > 0.5:
            penalty += 0.3
        top_bias = 1.0 / (1.0 + (top / 120.0))
        score = (
            conf_norm * 0.45
            + alpha_ratio * 0.30
            + length_norm * 0.15
            + top_bias * 0.10
            - penalty
        )
        candidates.append((score, top, left, text))

    sorted_line_items.sort()
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    name = ""
    name_left = 80
    name_top = 80
    if candidates:
        best_score, best_top, best_left, best_text = candidates[0]
        if best_score > -0.4:
            name = best_text
            name_left = best_left
            name_top = best_top
    if not name and sorted_line_items:
        top, left, text = sorted_line_items[0]
        name = text
        name_left = left
        name_top = top

    potential = None
    pattern_idx = None
    for i in range(n):
        t = (data_dict["text"][i] or "").strip().lower()
        if "легендар" in t:
            pattern_idx = i
            for j in range(max(0, i - 3), min(n, i + 4)):
                tj = (data_dict["text"][j] or "").strip()
                m = re.search(r"\b([1-4])\b", tj)
                if m:
                    potential = int(m.group(1))
                    break
            if potential is not None:
                break

    if potential is None:
        full_text = " ".join((data_dict["text"][i] or "") for i in range(n))
        m = re.search(r"([1-4]).{0,10}ЛЕГЕНДАР", full_text, flags=re.I | re.S)
        if m:
            potential = int(m.group(1))

    line_scores = [
        {"text": text, "score": round(score, 3), "top": top, "left": left}
        for score, top, left, text in candidates
    ]

    return {
        "name": (name or "").strip(),
        "name_bbox": (int(name_left), int(name_top)),
        "potential": potential,
        "lines": [li[2] for li in sorted_line_items],
        "line_scores": line_scores,
    }



def process_screen(tesseract_path: str | None = None, template_threshold: float | None = None, allow_soft_ocr: bool = True, ocr_engine: str = 'tesseract'):
    """Detect tooltip, run OCR with preprocessing, and return parsed fields."""
    set_tesseract_path(tesseract_path)
    screen_left, screen_top, screen_w, screen_h = _screen_geom()
    full_img = _grab_bbox(screen_left, screen_top, screen_w, screen_h)
    thr = _template_threshold_default() if template_threshold is None else float(template_threshold)
    crop = _detect_cropped_region(full_img, threshold=thr)
    detect_stats = get_last_detection_stats()
    if detect_stats:
        logger.debug("ROI detection stats: %s", detect_stats)
    img = None
    roi_offset = (screen_left, screen_top)
    if crop is not None:
        x1, y1, x2, y2 = crop
        try:
            x1 = max(0, min(x1, full_img.width - 1))
            y1 = max(0, min(y1, full_img.height - 1))
            x2 = max(0, min(x2, full_img.width))
            y2 = max(0, min(y2, full_img.height))
            if x2 > x1 + 10 and y2 > y1 + 10:
                img = full_img.crop((x1, y1, x2, y2))
                roi_offset = (screen_left + x1, screen_top + y1)
                logger.info("Corner ROI detected (fullscreen): (%d,%d)-(%d,%d)", x1, y1, x2, y2)
        except Exception as e:
            logger.debug("Corner ROI crop failed (fullscreen): %s", e)
    if img is None:
        img = full_img
        roi_offset = (screen_left, screen_top)
        logger.info("Corner ROI not found; falling back to full screen OCR")
    debug_token: str | None = None
    if _debug_enabled():
        try:
            os.makedirs("logs", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            debug_token = os.path.join("logs", f"ocr_{ts}")
            _save_debug_image(img, f"{debug_token}_roi.png")
            if img is full_img:
                _save_debug_image(full_img, f"{debug_token}_full.png")
        except Exception as e:
            logger.debug("Failed to prepare debug dump: %s", e)
            debug_token = None
    data = ocr_full(img, debug_save=debug_token, allow_soft=allow_soft_ocr)
    parsed = parse_item(data)
    parsed["image_size"] = img.size
    nbx, nby = parsed.get("name_bbox", (0, 0))
    parsed["name_bbox"] = (roi_offset[0] + int(nbx), roi_offset[1] + int(nby))
    parsed["roi"] = {"left": roi_offset[0], "top": roi_offset[1], "size": img.size}
    logger.info(
        "Parsed item: name='%s', potential=%s, at=%s",
        parsed.get("name", ""),
        parsed.get("potential"),
        parsed.get("name_bbox"),
    )
    return parsed



def detect_roi(template_threshold: float | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """Detect tooltip ROI on full screen and return (PIL.Image, (left, top)).

    If detection fails, returns full screen.
    """
    screen_left, screen_top, screen_w, screen_h = _screen_geom()
    full_img = _grab_bbox(screen_left, screen_top, screen_w, screen_h)
    thr = _template_threshold_default() if template_threshold is None else float(template_threshold)
    crop = _detect_cropped_region(full_img, threshold=thr)
    if crop is not None:
        x1, y1, x2, y2 = crop
        try:
            x1 = max(0, min(x1, full_img.width - 1))
            y1 = max(0, min(y1, full_img.height - 1))
            x2 = max(0, min(x2, full_img.width))
            y2 = max(0, min(y2, full_img.height))
            if x2 > x1 + 10 and y2 > y1 + 10:
                img = full_img.crop((x1, y1, x2, y2))
                return img, (screen_left + x1, screen_top + y1)
        except Exception:
            pass
    return full_img, (screen_left, screen_top)

# ------------------------- Template matching helpers -------------------------

def _template_scales() -> tuple[float, ...]:
    env = os.getenv("PRICER_TEMPLATE_SCALES", "").strip()
    if env:
        vals: list[float] = []
        for part in env.replace(';', ',').split(','):
            part = part.strip()
            if not part:
                continue
            try:
                val = float(part)
            except ValueError:
                continue
            if 0.4 <= val <= 2.5:
                vals.append(val)
        if vals:
            return tuple(vals)
    return (0.75, 0.85, 0.95, 1.0, 1.1, 1.25)


_LAST_DETECTION_STATS: dict[str, object] = {}

def get_last_detection_stats() -> dict[str, object]:
    """Return stats from the most recent corner detection attempt."""
    return dict(_LAST_DETECTION_STATS)


_TEMPLATE_STATE = {
    "tl": {"paths": [], "mtimes": {}, "imgs": [], "scaled_cache": {}},
    "br": {"paths": [], "mtimes": {}, "imgs": [], "scaled_cache": {}},
}

def _load_templates() -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Load templates from disk with auto-reload when files change.

    Scans for files named `topleft*.png` and `botright*.png` in the same
    directory as this module. If files are added/modified, reloads them.
    """
    base_dir = os.path.dirname(__file__)
    tl_paths = sorted(glob.glob(os.path.join(base_dir, "topleft*.png")))
    br_paths = sorted(glob.glob(os.path.join(base_dir, "botright*.png")))

    def _needs_reload(kind: str, paths: list[str]) -> bool:
        st = _TEMPLATE_STATE[kind]
        if st["paths"] != paths:
            return True
        for p in paths:
            try:
                m = os.path.getmtime(p)
            except FileNotFoundError:
                return True
            if st["mtimes"].get(p) != m:
                return True
        return False

    def _reload(kind: str, paths: list[str]) -> list[np.ndarray]:
        imgs: list[np.ndarray] = []
        mtimes: dict[str, float] = {}
        for p in paths:
            try:
                tpl = imread_unicode(p, cv.IMREAD_GRAYSCALE)
                if tpl is None:
                    logger.warning("Template read returned None: %s", p)
                    continue
                # skip too small
                if tpl.shape[0] < 6 or tpl.shape[1] < 6:
                    logger.warning("Template too small (skip): %s (%dx%d)", p, tpl.shape[1], tpl.shape[0])
                    continue
                imgs.append(tpl)
                mtimes[p] = os.path.getmtime(p)
                logger.info("Loaded %s template: %s (%dx%d)", kind.upper(), p, tpl.shape[1], tpl.shape[0])
            except Exception as e:
                logger.warning("Failed to load %s template %s: %s", kind, p, e)
        _TEMPLATE_STATE[kind] = {"paths": paths, "mtimes": mtimes, "imgs": imgs, "scaled_cache": {}}
        return imgs

    tl_imgs = _TEMPLATE_STATE["tl"]["imgs"] if not _needs_reload("tl", tl_paths) else _reload("tl", tl_paths)
    br_imgs = _TEMPLATE_STATE["br"]["imgs"] if not _needs_reload("br", br_paths) else _reload("br", br_paths)
    if not tl_imgs or not br_imgs:
        logger.info("Templates present: TL=%d, BR=%d", len(tl_imgs), len(br_imgs))
    return tl_imgs, br_imgs



def _get_templates_scaled(scales: tuple[float, ...] | None = None) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Return cached pre-scaled templates for given scales."""
    if scales is None:
        scales = _template_scales()
    tl_imgs, br_imgs = _load_templates()
    out: list[list[np.ndarray]] = []
    for kind, base in (("tl", tl_imgs), ("br", br_imgs)):
        cache = _TEMPLATE_STATE[kind].get("scaled_cache", {})
        key = tuple(scales)
        if key not in cache:
            scaled: list[np.ndarray] = []
            for tpl in base:
                for s in scales:
                    if abs(s - 1.0) < 1e-3:
                        tpl_s = tpl
                    else:
                        new_w = max(6, int(round(tpl.shape[1] * s)))
                        new_h = max(6, int(round(tpl.shape[0] * s)))
                        tpl_s = cv.resize(
                            tpl,
                            (new_w, new_h),
                            interpolation=cv.INTER_AREA if s < 1.0 else cv.INTER_CUBIC,
                        )
                    scaled.append(tpl_s)
            cache[key] = scaled
            _TEMPLATE_STATE[kind]["scaled_cache"] = cache
        out.append(cache[key])
    return out[0], out[1]

def _match_best(gray: np.ndarray, templates: list[np.ndarray]) -> tuple[float, tuple[int, int], tuple[int, int]] | None:
    """Return best (score, location, (w,h)) over multi-scale template matching.

    NOTE: For speed, prefer calling with pre-scaled templates from _get_templates_scaled().
    """
    best_val = -1.0
    best_loc = (0, 0)
    best_size = (0, 0)
    for tpl_s in templates:
        try:
            if tpl_s.shape[0] >= gray.shape[0] or tpl_s.shape[1] >= gray.shape[1]:
                continue
            res = cv.matchTemplate(gray, tpl_s, cv.TM_CCOEFF_NORMED)
            _, maxVal, _, maxLoc = cv.minMaxLoc(res)
            if maxVal > best_val:
                best_val = maxVal
                best_loc = maxLoc
                best_size = (tpl_s.shape[1], tpl_s.shape[0])
        except Exception as e:
            logger.debug("matchTemplate failed: %s", e)
            continue
    if best_val < 0:
        return None
    return best_val, best_loc, best_size


def _detect_cropped_region(pil_img: Image.Image, threshold: float = 0.70) -> tuple[int, int, int, int] | None:
    """Detect ROI bounded by top-left and bottom-right corner templates."""
    global _LAST_DETECTION_STATS
    scales = _template_scales()
    _LAST_DETECTION_STATS = {
        "threshold": float(threshold),
        "scales": list(scales),
        "result": "init",
    }
    tl_tpls, br_tpls = _get_templates_scaled(scales)
    if not tl_tpls or not br_tpls:
        _LAST_DETECTION_STATS["result"] = "no_templates"
        return None

    rgb = np.array(pil_img.convert("RGB"))
    gray = cv.cvtColor(rgb, cv.COLOR_RGB2GRAY)
    try:
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    gray_blur = cv.GaussianBlur(gray, (3, 3), 0)

    relax_margin = 0.08
    min_threshold = 0.52

    tl = _match_best(gray_blur, tl_tpls)
    if tl is None:
        _LAST_DETECTION_STATS.update({"result": "tl_fail", "tl_score": None})
        return None
    tl_val, tl_loc, tl_size = tl
    used_tl_thr = float(threshold)
    relaxed_tl_thr = max(min_threshold, threshold - relax_margin)
    if tl_val < threshold:
        if tl_val >= relaxed_tl_thr:
            used_tl_thr = relaxed_tl_thr
            logger.debug(
                "Relaxing TL threshold from %.2f to %.2f for score %.3f",
                threshold,
                used_tl_thr,
                tl_val,
            )
        else:
            _LAST_DETECTION_STATS.update(
                {
                    "result": "tl_fail",
                    "tl_score": float(tl_val),
                    "relaxed_threshold": relaxed_tl_thr,
                }
            )
            logger.info("Template scores TL=%.3f (< %.2f) — no crop", tl_val, threshold)
            return None

    rx1 = min(max(0, tl_loc[0] + max(2, tl_size[0] // 2)), gray_blur.shape[1] - 1)
    ry1 = min(max(0, tl_loc[1] + max(2, tl_size[1] // 2)), gray_blur.shape[0] - 1)
    rx2 = gray_blur.shape[1]
    ry2 = gray_blur.shape[0]
    if rx2 - rx1 < 8 or ry2 - ry1 < 8:
        _LAST_DETECTION_STATS.update(
            {
                "result": "br_window_fail",
                "tl_score": float(tl_val),
                "relaxed_threshold": used_tl_thr,
            }
        )
        return None
    sub = gray_blur[ry1:ry2, rx1:rx2]

    br = _match_best(sub, br_tpls)
    if br is None:
        _LAST_DETECTION_STATS.update(
            {
                "result": "br_fail",
                "tl_score": float(tl_val),
                "relaxed_threshold": used_tl_thr,
            }
        )
        return None
    br_val, br_loc_sub, br_size = br
    used_br_thr = used_tl_thr
    relaxed_br_thr = max(min_threshold, used_tl_thr - 0.05)
    if br_val < used_tl_thr:
        if br_val >= relaxed_br_thr:
            used_br_thr = relaxed_br_thr
            logger.debug(
                "Relaxing BR threshold from %.2f to %.2f for score %.3f",
                used_tl_thr,
                used_br_thr,
                br_val,
            )
        else:
            _LAST_DETECTION_STATS.update(
                {
                    "result": "br_fail",
                    "tl_score": float(tl_val),
                    "br_score": float(br_val),
                    "relaxed_threshold": used_tl_thr,
                    "relaxed_br_threshold": relaxed_br_thr,
                }
            )
            logger.info("Template scores TL=%.3f BR=%.3f (< %.2f) — no crop", tl_val, br_val, used_tl_thr)
            return None

    br_loc = (rx1 + br_loc_sub[0], ry1 + br_loc_sub[1])
    x1 = tl_loc[0] + max(2, tl_size[0] // 16)
    y1 = tl_loc[1] + max(2, tl_size[1] // 16)
    x2 = br_loc[0] + br_size[0] - max(2, br_size[0] // 16)
    y2 = br_loc[1] + br_size[1] - max(2, br_size[1] // 16)

    if x2 <= x1 or y2 <= y1:
        logger.info("Corner geometry invalid TL(%d,%d) BR(%d,%d)", x1, y1, x2, y2)
        _LAST_DETECTION_STATS.update(
            {
                "result": "geometry_fail",
                "tl_score": float(tl_val),
                "br_score": float(br_val),
                "tl_threshold_used": used_tl_thr,
                "br_threshold_used": used_br_thr,
            }
        )
        return None
    if x2 <= x1 + 10 or y2 <= y1 + 10:
        _LAST_DETECTION_STATS.update(
            {
                "result": "geometry_fail",
                "tl_score": float(tl_val),
                "br_score": float(br_val),
                "tl_threshold_used": used_tl_thr,
                "br_threshold_used": used_br_thr,
            }
        )
        return None

    rect = (int(x1), int(y1), int(x2), int(y2))
    _LAST_DETECTION_STATS.update(
        {
            "result": "ok",
            "tl_score": float(tl_val),
            "br_score": float(br_val),
            "tl_threshold_used": used_tl_thr,
            "br_threshold_used": used_br_thr,
            "rect": rect,
        }
    )

    try:
        if _debug_enabled():
            os.makedirs("logs", exist_ok=True)
            dbg = rgb.copy()
            cv.rectangle(dbg, (tl_loc[0], tl_loc[1]), (tl_loc[0] + tl_size[0], tl_loc[1] + tl_size[1]), (0, 255, 0), 2)
            cv.rectangle(dbg, (br_loc[0], br_loc[1]), (br_loc[0] + br_size[0], br_loc[1] + br_size[1]), (0, 0, 255), 2)
            cv.rectangle(dbg, (rect[0], rect[1]), (rect[2], rect[3]), (255, 0, 0), 2)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            cv.putText(
                dbg,
                f"TL={tl_val:.3f}/{used_tl_thr:.2f} BR={br_val:.3f}/{used_br_thr:.2f}",
                (10, 20),
                cv.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            outp = os.path.join("logs", f"ocr_match_{ts}.png")
            cv.imwrite(outp, cv.cvtColor(dbg, cv.COLOR_RGB2BGR))
            try:
                enforce_logs_quota(300.0, logs_dir="logs")
            except Exception:
                pass
    except Exception as e:
        logger.debug("Failed to save match debug: %s", e)
    return rect


