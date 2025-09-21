import json, os, sys
from typing import Any, Dict


def _base_dir() -> str:
    base = os.path.dirname(__file__)
    if getattr(sys, "frozen", False):
        # store alongside prices.json (same user-writable location logic as db.py)
        if os.name == "nt":
            appdata = os.getenv("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
            base = os.path.join(appdata, "Pricer")
        else:
            base = os.path.join(os.path.expanduser("~/.local/share"), "pricer")
        os.makedirs(base, exist_ok=True)
    return base


def config_path() -> str:
    return os.path.join(_base_dir(), "config.json")


DEFAULT_CONFIG: Dict[str, Any] = {
    "title_band": {"x1": 0.24, "y1": 0.06, "x2": 0.92, "y2": 0.18},
}


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return max(0.0, min(1.0, v))


def load_config() -> Dict[str, Any]:
    path = config_path()
    if not os.path.exists(path):
        return DEFAULT_CONFIG.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()
    # validate
    tb = cfg.get("title_band", {})
    cfg["title_band"] = {
        "x1": _clamp01(tb.get("x1", DEFAULT_CONFIG["title_band"]["x1"])),
        "y1": _clamp01(tb.get("y1", DEFAULT_CONFIG["title_band"]["y1"])),
        "x2": _clamp01(tb.get("x2", DEFAULT_CONFIG["title_band"]["x2"])),
        "y2": _clamp01(tb.get("y2", DEFAULT_CONFIG["title_band"]["y2"])),
    }
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    # normalize & save
    out = DEFAULT_CONFIG.copy()
    tb = cfg.get("title_band", {})
    out["title_band"] = {
        "x1": _clamp01(tb.get("x1", out["title_band"]["x1"])),
        "y1": _clamp01(tb.get("y1", out["title_band"]["y1"])),
        "x2": _clamp01(tb.get("x2", out["title_band"]["x2"])),
        "y2": _clamp01(tb.get("y2", out["title_band"]["y2"])),
    }
    path = config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

