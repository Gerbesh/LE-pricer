from __future__ import annotations

from datetime import datetime
import glob
import logging
import os
from typing import Optional, Tuple

import cv2 as cv
import numpy as np
from PIL import Image
from mss import mss

from image_utils import imread_unicode
from log_utils import enforce_logs_quota

logger = logging.getLogger(__name__)

_DEBUG_SAVE_IMAGES = False
_LAST_DETECTION_STATS: dict[str, object] = {}


def set_debug_image_saving(enabled: bool) -> None:
    """Включить или отключить сохранение диагностических кадров."""
    global _DEBUG_SAVE_IMAGES
    _DEBUG_SAVE_IMAGES = bool(enabled)


def _debug_enabled() -> bool:
    if _DEBUG_SAVE_IMAGES:
        return True
    env = os.getenv("PRICER_DEBUG_SAVE", "0").strip().lower()
    return env in ("1", "true", "yes", "on")


def _screen_geom() -> tuple[int, int, int, int]:
    with mss() as sct:
        mon = sct.monitors[0]
        return mon["left"], mon["top"], mon["width"], mon["height"]


def _grab_bbox(left: int, top: int, width: int, height: int) -> Image.Image:
    with mss() as sct:
        raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        return img


def grab_screen() -> Image.Image:
    x, y, w, h = _screen_geom()
    return _grab_bbox(x, y, w, h)


def _template_threshold_default() -> float:
    try:
        value = float(os.getenv("PRICER_TEMPLATE_THRESHOLD", "0.60"))
        if 0.0 < value <= 1.0:
            return value
    except Exception:
        pass
    return 0.60


def get_last_detection_stats() -> dict[str, object]:
    """Вернуть статистику последнего обнаружения рамки."""
    return dict(_LAST_DETECTION_STATS)


_TEMPLATE_STATE = {
    "tl": {"paths": [], "mtimes": {}, "imgs": [], "scaled_cache": {}},
    "br": {"paths": [], "mtimes": {}, "imgs": [], "scaled_cache": {}},
}


def _template_scales() -> tuple[float, ...]:
    env = os.getenv("PRICER_TEMPLATE_SCALES", "").strip()
    if env:
        values: list[float] = []
        for part in env.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                val = float(part)
            except ValueError:
                continue
            if 0.4 <= val <= 2.5:
                values.append(val)
        if values:
            return tuple(values)
    return (0.75, 0.85, 0.95, 1.0, 1.1, 1.25)


def _load_templates() -> tuple[list[np.ndarray], list[np.ndarray]]:
    base_dir = os.path.dirname(__file__)
    tl_paths = sorted(glob.glob(os.path.join(base_dir, "topleft*.png")))
    br_paths = sorted(glob.glob(os.path.join(base_dir, "botright*.png")))

    def _needs_reload(kind: str, paths: list[str]) -> bool:
        state = _TEMPLATE_STATE[kind]
        if state["paths"] != paths:
            return True
        for path in paths:
            try:
                mtime = os.path.getmtime(path)
            except FileNotFoundError:
                return True
            if state["mtimes"].get(path) != mtime:
                return True
        return False

    def _reload(kind: str, paths: list[str]) -> list[np.ndarray]:
        images: list[np.ndarray] = []
        mtimes: dict[str, float] = {}
        for path in paths:
            try:
                tpl = imread_unicode(path, cv.IMREAD_GRAYSCALE)
                if tpl is None:
                    logger.warning("Не удалось прочитать шаблон: %s", path)
                    continue
                if tpl.shape[0] < 6 or tpl.shape[1] < 6:
                    logger.warning("Шаблон слишком мал и пропущен: %s (%dx%d)", path, tpl.shape[1], tpl.shape[0])
                    continue
                images.append(tpl)
                mtimes[path] = os.path.getmtime(path)
                logger.info("Загружен шаблон %s: %s (%dx%d)", kind.upper(), path, tpl.shape[1], tpl.shape[0])
            except Exception as exc:
                logger.warning("Ошибка загрузки шаблона %s: %s", path, exc)
        _TEMPLATE_STATE[kind] = {"paths": paths, "mtimes": mtimes, "imgs": images, "scaled_cache": {}}
        return images

    tl_imgs = _TEMPLATE_STATE["tl"]["imgs"] if not _needs_reload("tl", tl_paths) else _reload("tl", tl_paths)
    br_imgs = _TEMPLATE_STATE["br"]["imgs"] if not _needs_reload("br", br_paths) else _reload("br", br_paths)
    if not tl_imgs or not br_imgs:
        logger.info("Количество шаблонов: TL=%d, BR=%d", len(tl_imgs), len(br_imgs))
    return tl_imgs, br_imgs


def _get_templates_scaled(scales: tuple[float, ...] | None = None) -> tuple[list[np.ndarray], list[np.ndarray]]:
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
                for scale in scales:
                    if abs(scale - 1.0) < 1e-3:
                        tpl_scaled = tpl
                    else:
                        new_w = max(6, int(round(tpl.shape[1] * scale)))
                        new_h = max(6, int(round(tpl.shape[0] * scale)))
                        tpl_scaled = cv.resize(
                            tpl,
                            (new_w, new_h),
                            interpolation=cv.INTER_AREA if scale < 1.0 else cv.INTER_CUBIC,
                        )
                    scaled.append(tpl_scaled)
            cache[key] = scaled
            _TEMPLATE_STATE[kind]["scaled_cache"] = cache
        out.append(cache[key])
    return out[0], out[1]


def _match_best(gray: np.ndarray, templates: list[np.ndarray]) -> Optional[tuple[float, tuple[int, int], tuple[int, int]]]:
    best_val = -1.0
    best_loc = (0, 0)
    best_size = (0, 0)
    for tpl in templates:
        try:
            if tpl.shape[0] >= gray.shape[0] or tpl.shape[1] >= gray.shape[1]:
                continue
            res = cv.matchTemplate(gray, tpl, cv.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_size = (tpl.shape[1], tpl.shape[0])
        except Exception as exc:
            logger.debug("matchTemplate завершился с ошибкой: %s", exc)
            continue
    if best_val < 0:
        return None
    return best_val, best_loc, best_size


def _detect_cropped_region(pil_img: Image.Image, threshold: float = 0.70) -> Optional[tuple[int, int, int, int]]:
    global _LAST_DETECTION_STATS
    scales = _template_scales()
    tl_tpls, br_tpls = _get_templates_scaled(scales)
    rgb = cv.cvtColor(np.array(pil_img.convert("RGB")), cv.COLOR_RGB2BGR)
    gray = cv.cvtColor(rgb, cv.COLOR_BGR2GRAY)
    gray_blur = cv.GaussianBlur(gray, (5, 5), 0)

    min_threshold = min(0.40, threshold)
    used_tl_thr = threshold

    tl = _match_best(gray_blur, tl_tpls)
    if tl is None:
        _LAST_DETECTION_STATS.update({"result": "tl_fail"})
        return None
    tl_val, tl_loc, tl_size = tl
    if tl_val < threshold:
        relaxed = max(min_threshold, threshold - 0.05)
        if tl_val >= relaxed:
            used_tl_thr = relaxed
            logger.debug(
                "Ослаблен порог TL с %.2f до %.2f (score %.3f)",
                threshold,
                used_tl_thr,
                tl_val,
            )
        else:
            _LAST_DETECTION_STATS.update(
                {
                    "result": "tl_fail",
                    "tl_score": float(tl_val),
                    "relaxed_threshold": relaxed,
                }
            )
            logger.info("Совпадение TL=%.3f ниже порога %.2f", tl_val, used_tl_thr)
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
                "Ослаблен порог BR с %.2f до %.2f (score %.3f)",
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
            logger.info("Совпадение TL=%.3f, BR=%.3f ниже порога %.2f", tl_val, br_val, used_tl_thr)
            return None

    br_loc = (rx1 + br_loc_sub[0], ry1 + br_loc_sub[1])
    x1 = tl_loc[0] + max(2, tl_size[0] // 16)
    y1 = tl_loc[1] + max(2, tl_size[1] // 16)
    x2 = br_loc[0] + br_size[0] - max(2, br_size[0] // 16)
    y2 = br_loc[1] + br_size[1] - max(2, br_size[1] // 16)

    if x2 <= x1 or y2 <= y1:
        logger.info("Некорректная геометрия рамки TL(%d,%d) BR(%d,%d)", x1, y1, x2, y2)
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
            out_path = os.path.join("logs", f"ocr_match_{ts}.png")
            cv.imwrite(out_path, cv.cvtColor(dbg, cv.COLOR_RGB2BGR))
            try:
                enforce_logs_quota(300.0, logs_dir="logs")
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Не удалось сохранить диагностическое изображение: %s", exc)
    return rect


def detect_roi(template_threshold: float | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """Найти область подсказки и вернуть (изображение, смещение)."""
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


__all__ = [
    "detect_roi",
    "get_last_detection_stats",
    "grab_screen",
    "set_debug_image_saving",
    "_screen_geom",
    "_grab_bbox",
    "_template_threshold_default",
]
