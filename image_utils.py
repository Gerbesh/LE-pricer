"""Utility helpers for OpenCV image IO."""
from __future__ import annotations

from typing import Optional

import numpy as np
import cv2 as cv


def imread_unicode(path: str, flags: int = cv.IMREAD_COLOR) -> Optional[np.ndarray]:
    """Read image from *path*, handling Windows Unicode paths gracefully.

    On some OpenCV builds, ``cv.imread`` fails to open files whose paths
    contain non-ASCII characters (common for Cyrillic item names). We first
    try the regular loader and, if it fails, fall back to decoding raw bytes
    via ``cv.imdecode``.
    """
    img = cv.imread(path, flags)
    if img is not None:
        return img

    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None

    if data.size == 0:
        return None

    return cv.imdecode(data, flags)
