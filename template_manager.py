import os, json, time, glob
from typing import Optional, Tuple, Dict, List
from PIL import Image
import numpy as np
from image_utils import imread_unicode
import cv2 as cv
import logging

logger = logging.getLogger(__name__)

TEMPLATE_ROOT = os.path.join(os.path.dirname(__file__), "templates")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def sanitize_name(name: str) -> str:
    s = (name or "").strip()
    invalid = '<>:"/\\|?*'
    repl = {ord(ch): '_' for ch in invalid}
    s = s.translate(repl)
    # collapse spaces
    s = " ".join(s.split())
    return s


def item_dir(item_name: str) -> str:
    d = os.path.join(TEMPLATE_ROOT, sanitize_name(item_name))
    _ensure_dir(d)
    return d


def save_samples(image_path: str, item_name: str, name_rect: Tuple[int, int, int, int], lp_rect: Optional[Tuple[int, int, int, int]], potential: int = 0) -> dict:
    """Save cropped samples into templates/<item_name>/.

    name_rect/lp_rect are (x1,y1,x2,y2) in ROI coordinates.
    """
    item_name = sanitize_name(item_name)
    d = item_dir(item_name)
    base_img = Image.open(image_path).convert('RGB')
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = {"item": item_name, "saved": []}

    def _clip(r, w, h):
        x1,y1,x2,y2 = r
        x1 = max(0, min(x1, w-1)); y1 = max(0, min(y1, h-1))
        x2 = max(x1+1, min(x2, w)); y2 = max(y1+1, min(y2, h))
        return (x1,y1,x2,y2)

    W,H = base_img.size
    x1,y1,x2,y2 = _clip(name_rect, W,H)
    name_crop = base_img.crop((x1,y1,x2,y2))
    name_fn = os.path.join(d, f"name_{ts}.png")
    name_crop.save(name_fn)
    out["saved"].append(name_fn)

    lp_fn = None
    if lp_rect is not None:
        x1,y1,x2,y2 = _clip(lp_rect, W,H)
        lp_crop = base_img.crop((x1,y1,x2,y2))
        lp_fn = os.path.join(d, f"lp_{ts}.png")
        lp_crop.save(lp_fn)
        out["saved"].append(lp_fn)

    # Append metadata
    meta_path = os.path.join(d, "meta.json")
    meta = {"samples": []}
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, 'r', encoding='utf-8'))
        except Exception:
            meta = {"samples": []}
    meta["samples"].append({
        "ts": ts,
        "name_file": os.path.basename(name_fn),
        "lp_file": os.path.basename(lp_fn) if lp_fn else None,
        "potential": int(potential or 0),
    })
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    # Invalidate cache after saving
    try:
        invalidate_cache()
    except Exception:
        pass
    return out


def save_lp_sample(image_path: str, item_name: str, lp_rect: Tuple[int, int, int, int], potential: int = 0) -> dict:
    """Save only LP sample and metadata for an existing or new item folder."""
    item_name = sanitize_name(item_name)
    d = item_dir(item_name)
    base_img = Image.open(image_path).convert('RGB')
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = {"item": item_name, "saved": []}

    def _clip(r, w, h):
        x1,y1,x2,y2 = r
        x1 = max(0, min(x1, w-1)); y1 = max(0, min(y1, h-1))
        x2 = max(x1+1, min(x2, w)); y2 = max(y1+1, min(y2, h))
        return (x1,y1,x2,y2)

    W,H = base_img.size
    x1,y1,x2,y2 = _clip(lp_rect, W,H)
    lp_crop = base_img.crop((x1,y1,x2,y2))
    lp_fn = os.path.join(d, f"lp_{ts}.png")
    lp_crop.save(lp_fn)
    out["saved"].append(lp_fn)

    # Append metadata
    meta_path = os.path.join(d, "meta.json")
    meta = {"samples": []}
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, 'r', encoding='utf-8'))
        except Exception:
            meta = {"samples": []}
    meta["samples"].append({
        "ts": ts,
        "name_file": None,
        "lp_file": os.path.basename(lp_fn),
        "potential": int(potential or 0),
    })
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    try:
        invalidate_cache()
    except Exception:
        pass
    return out


def save_inventory_sample(image_path: str, item_name: str, rect: Tuple[int, int, int, int]) -> dict:
    """Save cropped inventory template (item icon) into templates/<item_name>/."""
    item_name = sanitize_name(item_name)
    d = item_dir(item_name)
    base_img = Image.open(image_path).convert('RGB')
    ts = time.strftime("%Y%m%d_%H%M%S")

    def _clip(r, w, h):
        x1, y1, x2, y2 = r
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))
        return (x1, y1, x2, y2)

    W, H = base_img.size
    x1, y1, x2, y2 = _clip(rect, W, H)
    crop = base_img.crop((x1, y1, x2, y2))
    item_fn = os.path.join(d, f"item_{ts}.png")
    crop.save(item_fn)
    try:
        invalidate_cache()
    except Exception:
        pass
    return {"item": item_name, "saved": [item_fn]}




def list_all_items() -> list[str]:
    """Return sorted item directory names (sanitized)."""
    _build_cache_if_needed()
    return sorted(_CACHE.get("items", {}).keys())
def list_items_missing_inventory() -> list[str]:
    """Return sorted item names that do not have inventory templates."""
    _build_cache_if_needed()
    items = _CACHE.get("items", {})
    missing: list[str] = []
    for name, info in items.items():
        inventory_scaled = info.get("inventory_scaled", {}) or {}
        has_templates = False
        for tpl_list in inventory_scaled.values():
            if tpl_list:
                has_templates = True
                break
        if not has_templates:
            missing.append(name)
    missing.sort()
    return missing





def _cv_img(img):
    if isinstance(img, Image.Image):
        arr = np.array(img.convert('RGB'))
        return cv.cvtColor(arr, cv.COLOR_RGB2BGR)
    return img


_CACHE: Dict[str, Dict] = {
    "items": {},
    "last_scan": 0.0,
    "root_mtime": 0.0,
    "scales": (0.75, 0.85, 0.95, 1.0, 1.1, 1.25),
    "lp_global": {},  # pot:int -> {scales_key: [np.ndarray,...], paths:[...], mtimes:[...]}
    "inventory": {},  # item -> {scales_key: [np.ndarray,...], paths:[...]}
}


def _scales_tuple() -> tuple[float, ...]:
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
            vals_tuple = tuple(vals)
            _CACHE["scales"] = vals_tuple
            return vals_tuple
    existing = _CACHE.get("scales")
    if isinstance(existing, tuple) and existing:
        return existing
    default = (0.75, 0.85, 0.95, 1.0, 1.1, 1.25)
    _CACHE["scales"] = default
    return default


def _prepare_gray_roi(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert('RGB'))
    gray = cv.cvtColor(arr, cv.COLOR_RGB2GRAY)
    try:
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    return cv.GaussianBlur(gray, (3, 3), 0)


def _dir_mtime(path: str) -> float:
    latest = 0.0
    for root, dirs, files in os.walk(path):
        for n in files:
            try:
                m = os.path.getmtime(os.path.join(root, n))
                latest = max(latest, m)
            except Exception:
                continue
    return latest


def invalidate_cache() -> None:
    _CACHE["items"] = {}
    _CACHE["inventory"] = {}
    _CACHE["last_scan"] = 0.0
    _CACHE["root_mtime"] = 0.0


def _build_cache_if_needed() -> None:
    if not os.path.exists(TEMPLATE_ROOT):
        return
    # Re-scan at most once per 0.5s
    now = time.time()
    if now - float(_CACHE.get("last_scan", 0.0)) < 0.5:
        return
    root_m = _dir_mtime(TEMPLATE_ROOT)
    if root_m == _CACHE.get("root_mtime") and _CACHE.get("items"):
        _CACHE["last_scan"] = now
        return

    items: Dict[str, Dict] = {}
    inventory_cache: Dict[str, Dict] = {}
    scales = _scales_tuple()
    for d in sorted([p for p in glob.glob(os.path.join(TEMPLATE_ROOT, '*')) if os.path.isdir(p)]):
        item = os.path.basename(d)
        # name templates
        name_paths = sorted(glob.glob(os.path.join(d, 'name_*.png')))
        name_imgs: List[np.ndarray] = []
        name_scaled: Dict[Tuple[float, ...], List[np.ndarray]] = {}
        for nf in name_paths:
            tpl = imread_unicode(nf, cv.IMREAD_GRAYSCALE)
            if tpl is None:
                continue
            name_imgs.append(tpl)
        scaled_list: List[np.ndarray] = []
        for tpl in name_imgs:
            for s in scales:
                if s == 1.0:
                    tpl_s = tpl
                else:
                    tw = max(6, int(round(tpl.shape[1] * s)))
                    th = max(6, int(round(tpl.shape[0] * s)))
                    tpl_s = cv.resize(tpl, (tw, th), interpolation=cv.INTER_AREA if s < 1.0 else cv.INTER_CUBIC)
                scaled_list.append(tpl_s)
        if scaled_list:
            name_scaled[tuple(scales)] = scaled_list

        # lp templates
        lp_paths = sorted(glob.glob(os.path.join(d, 'lp_*.png')))
        lp_imgs: List[np.ndarray] = []
        lp_scaled: Dict[Tuple[float, ...], List[np.ndarray]] = {}
        for lf in lp_paths:
            tpl = imread_unicode(lf, cv.IMREAD_GRAYSCALE)
            if tpl is None:
                continue
            lp_imgs.append(tpl)
        lp_scaled_list: List[np.ndarray] = []
        for tpl in lp_imgs:
            for s in scales:
                if s == 1.0:
                    tpl_s = tpl
                else:
                    tw = max(6, int(round(tpl.shape[1] * s)))
                    th = max(6, int(round(tpl.shape[0] * s)))
                    tpl_s = cv.resize(tpl, (tw, th), interpolation=cv.INTER_AREA if s < 1.0 else cv.INTER_CUBIC)
                lp_scaled_list.append(tpl_s)
        if lp_scaled_list:
            lp_scaled[tuple(scales)] = lp_scaled_list

        # inventory templates (item*.png)
        inv_paths = sorted(glob.glob(os.path.join(d, 'item*.png')))
        inv_imgs: List[np.ndarray] = []
        inv_scaled: Dict[Tuple[float, ...], List[np.ndarray]] = {}
        for itp in inv_paths:
            tpl = imread_unicode(itp, cv.IMREAD_GRAYSCALE)
            if tpl is None:
                continue
            inv_imgs.append(tpl)
        inv_scaled_list: List[np.ndarray] = []
        for tpl in inv_imgs:
            for s in scales:
                if s == 1.0:
                    tpl_s = tpl
                else:
                    tw = max(6, int(round(tpl.shape[1] * s)))
                    th = max(6, int(round(tpl.shape[0] * s)))
                    tpl_s = cv.resize(tpl, (tw, th), interpolation=cv.INTER_AREA if s < 1.0 else cv.INTER_CUBIC)
                inv_scaled_list.append(tpl_s)
        if inv_scaled_list:
            inv_scaled[tuple(scales)] = inv_scaled_list

        items[item] = {
            "name_scaled": name_scaled,
            "lp_scaled": lp_scaled,
            "inventory_scaled": inv_scaled,
            "meta": os.path.join(d, 'meta.json'),
        }
        if inv_paths:
            inventory_cache[item] = {"scaled": inv_scaled, "paths": inv_paths}
    _CACHE["items"] = items
    _CACHE["inventory"] = inventory_cache
    _CACHE["root_mtime"] = root_m
    _CACHE["last_scan"] = now

    # Build global LP templates cache (1lp..4lp under templates/lp or templates)
    lp_dir_pref = [os.path.join(TEMPLATE_ROOT, 'lp'), TEMPLATE_ROOT]
    pot_files: Dict[int, List[str]] = {1: [], 2: [], 3: [], 4: []}
    for pot in (1,2,3,4):
        names = []
        base = f"{pot}lp"
        for d in lp_dir_pref:
            if not os.path.isdir(d):
                continue
            names.extend(glob.glob(os.path.join(d, base + '.*')))
            names.extend(glob.glob(os.path.join(d, base.upper() + '.*')))
        pot_files[pot] = sorted(names)
    lp_global: Dict[int, Dict] = {}
    for pot, files in pot_files.items():
        imgs: List[np.ndarray] = []
        for f in files:
            tpl = imread_unicode(f, cv.IMREAD_GRAYSCALE)
            if tpl is not None:
                imgs.append(tpl)
        scaled_list: List[np.ndarray] = []
        for tpl in imgs:
            for s in scales:
                if s == 1.0:
                    tpl_s = tpl
                else:
                    tw = max(6, int(round(tpl.shape[1]*s)))
                    th = max(6, int(round(tpl.shape[0]*s)))
                    tpl_s = cv.resize(tpl, (tw, th), interpolation=cv.INTER_AREA if s<1.0 else cv.INTER_CUBIC)
                scaled_list.append(tpl_s)
        lp_global[pot] = {"scaled": {tuple(scales): scaled_list}, "paths": files}
    _CACHE["lp_global"] = lp_global


def _best_match_scaled(gray_roi: np.ndarray, scaled_tpls: List[np.ndarray]) -> float:
    best = 0.0
    for tpl_s in scaled_tpls:
        try:
            if tpl_s.shape[0] >= gray_roi.shape[0] or tpl_s.shape[1] >= gray_roi.shape[1]:
                continue
            res = cv.matchTemplate(gray_roi, tpl_s, cv.TM_CCOEFF_NORMED)
            _, mx, _, _ = cv.minMaxLoc(res)
            if mx > best:
                best = mx
        except Exception:
            continue
    return float(best)




def _rect_iou(rect_a: tuple[int, int, int, int], rect_b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = rect_a
    bx1, by1, bx2, by2 = rect_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
    area_a = float(max(0, ax2 - ax1) * max(0, ay2 - ay1))
    area_b = float(max(0, bx2 - bx1) * max(0, by2 - by1))
    denom = area_a + area_b - inter
    if denom <= 0:
        return 0.0
    return inter / denom


def _collect_inventory_matches(
    gray_roi: np.ndarray,
    templates: list[np.ndarray],
    threshold: float,
    max_per_item: int,
    suppress_iou: float = 0.4,
) -> list[tuple[float, int, int, int, int]]:
    raw: list[tuple[float, int, int, int, int]] = []
    for tpl in templates:
        try:
            res = cv.matchTemplate(gray_roi, tpl, cv.TM_CCOEFF_NORMED)
        except Exception:
            continue
        tpl_h, tpl_w = tpl.shape[:2]
        while True:
            _, max_val, _, max_loc = cv.minMaxLoc(res)
            if max_val < threshold:
                break
            x, y = int(max_loc[0]), int(max_loc[1])
            raw.append((float(max_val), x, y, tpl_w, tpl_h))
            cv.rectangle(res, (x, y), (x + tpl_w, y + tpl_h), 0, -1)
    raw.sort(key=lambda item: item[0], reverse=True)
    accepted: list[tuple[float, int, int, int, int]] = []
    for score, x, y, w, h in raw:
        rect = (x, y, x + w, y + h)
        if any(_rect_iou(rect, (ax, ay, ax + aw, ay + ah)) > suppress_iou for _, ax, ay, aw, ah in accepted):
            continue
        accepted.append((score, x, y, w, h))
        if len(accepted) >= max_per_item:
            break
    return accepted


def match_inventory_regions(
    roi_img: Image.Image,
    threshold: float = 0.80,
    max_per_item: int = 3,
    suppress_iou: float = 0.35,
) -> list[dict[str, object]]:
    """Locate inventory item templates within the provided ROI.

    Returns list of dicts with keys: item, score, rect (x1,y1,x2,y2).
    """
    if not os.path.exists(TEMPLATE_ROOT):
        return []
    _build_cache_if_needed()
    gray_roi = _prepare_gray_roi(roi_img)
    items = _CACHE.get("items", {})
    scales = tuple(_scales_tuple())
    matches: list[dict[str, object]] = []
    for item, info in items.items():
        scaled = info.get("inventory_scaled", {}).get(scales, [])
        if not scaled:
            continue
        item_matches = _collect_inventory_matches(gray_roi, scaled, threshold, max_per_item)
        for score, x, y, w, h in item_matches:
            matches.append({
                "item": item,
                "score": float(score),
                "rect": (int(x), int(y), int(x + w), int(y + h)),
            })
    matches.sort(key=lambda m: m["score"], reverse=True)
    filtered: list[dict[str, object]] = []
    for match in matches:
        rect = match["rect"]
        if any(_rect_iou(rect, other["rect"]) > suppress_iou for other in filtered):
            continue
        filtered.append(match)
    return filtered

def match_item_by_templates(roi_img: Image.Image, threshold: float = 0.85) -> Optional[Tuple[str, float]]:
    """Return (item_name, score) if any name_* template matches ROI >= threshold."""
    if not os.path.exists(TEMPLATE_ROOT):
        return None
    gray_roi = _prepare_gray_roi(roi_img)
    _build_cache_if_needed()
    best_name = None
    best_score = 0.0
    items = _CACHE.get("items", {})
    scales_key = tuple(_scales_tuple())
    for item, info in items.items():
        scaled = info.get("name_scaled", {}).get(scales_key, [])
        if not scaled:
            continue
        s = _best_match_scaled(gray_roi, scaled)
        if s > best_score:
            best_score = s
            best_name = item
    if not best_name:
        return None
    relaxed = max(0.72, threshold - 0.07)
    if best_score >= threshold:
        return best_name, best_score
    if best_score >= relaxed:
        logger.info(
            "Template match '%s' accepted at %.3f (relaxed from %.2f)",
            best_name,
            best_score,
            threshold,
        )
        return best_name, best_score
    logger.debug("Best template score %.3f for '%s' below relaxed threshold %.2f", best_score, best_name, relaxed)
    return None



def _lp_threshold_default() -> float:
    try:
        v = float(os.getenv("PRICER_LP_THRESHOLD", "0.90"))
        if 0.0 < v <= 1.0:
            return v
    except Exception:
        pass
    return 0.90


def detect_potential_global(roi_img: Image.Image, threshold: Optional[float] = None) -> Tuple[int, float]:
    """Detect LP globally by matching against 1lp..4lp templates."""
    thr = _lp_threshold_default() if threshold is None else float(threshold)
    _build_cache_if_needed()
    gray_roi = _prepare_gray_roi(roi_img)
    scales_key = tuple(_scales_tuple())
    best_pot = 0
    best = 0.0
    for pot in (1, 2, 3, 4):
        info = _CACHE.get("lp_global", {}).get(pot, {})
        scaled = info.get("scaled", {}).get(scales_key, [])
        if not scaled:
            continue
        s = _best_match_scaled(gray_roi, scaled)
        if s > best:
            best = s
            best_pot = pot
    relaxed = max(0.78, thr - 0.08)
    if best >= thr:
        return best_pot, float(best)
    if best_pot and best >= relaxed:
        logger.info(
            "LP %s detected at %.3f (relaxed from %.2f)",
            best_pot,
            best,
            thr,
        )
        return best_pot, float(best)
    logger.debug("Best LP score %.3f for pot %s below relaxed threshold %.2f", best, best_pot or 0, relaxed)
    return 0, float(best)
