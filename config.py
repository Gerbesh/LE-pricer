import json, os, sys, copy
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
    "hotkeys": {
        "item_capture": "F1",
        "inventory_scan": "F2",
        "template_capture": "F3",
    },
    "overlay": {
        "duration_ms": 4000,
        "inventory_duration_ms": 4000,
    },
}


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return max(0.0, min(1.0, v))


def _normalize_hotkey(value: Any, default: str) -> str:
    if not value:
        return default
    text = str(value).strip()
    return text.upper() or default


def _coerce_duration(value: Any, default: int) -> int:
    try:
        ivalue = int(value)
    except Exception:
        return default
    return max(500, ivalue)


def _defaults() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def load_config() -> Dict[str, Any]:
    cfg = _defaults()
    path = config_path()
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return cfg

    tb = raw.get("title_band", {}) if isinstance(raw, dict) else {}
    cfg["title_band"] = {
        "x1": _clamp01(tb.get("x1", cfg["title_band"]["x1"])),
        "y1": _clamp01(tb.get("y1", cfg["title_band"]["y1"])),
        "x2": _clamp01(tb.get("x2", cfg["title_band"]["x2"])),
        "y2": _clamp01(tb.get("y2", cfg["title_band"]["y2"])),
    }

    hk = raw.get("hotkeys", {}) if isinstance(raw, dict) else {}
    cfg["hotkeys"] = {
        "item_capture": _normalize_hotkey(hk.get("item_capture"), cfg["hotkeys"]["item_capture"]),
        "inventory_scan": _normalize_hotkey(hk.get("inventory_scan"), cfg["hotkeys"]["inventory_scan"]),
        "template_capture": _normalize_hotkey(hk.get("template_capture"), cfg["hotkeys"]["template_capture"]),
    }

    ov = raw.get("overlay", {}) if isinstance(raw, dict) else {}
    cfg["overlay"] = {
        "duration_ms": _coerce_duration(ov.get("duration_ms"), cfg["overlay"]["duration_ms"]),
        "inventory_duration_ms": _coerce_duration(ov.get("inventory_duration_ms"), cfg["overlay"]["inventory_duration_ms"]),
    }
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    out = _defaults()
    tb = cfg.get("title_band", {}) if isinstance(cfg, dict) else {}
    out["title_band"] = {
        "x1": _clamp01(tb.get("x1", out["title_band"]["x1"])),
        "y1": _clamp01(tb.get("y1", out["title_band"]["y1"])),
        "x2": _clamp01(tb.get("x2", out["title_band"]["x2"])),
        "y2": _clamp01(tb.get("y2", out["title_band"]["y2"])),
    }

    hk = cfg.get("hotkeys", {}) if isinstance(cfg, dict) else {}
    out["hotkeys"] = {
        "item_capture": _normalize_hotkey(hk.get("item_capture"), out["hotkeys"]["item_capture"]),
        "inventory_scan": _normalize_hotkey(hk.get("inventory_scan"), out["hotkeys"]["inventory_scan"]),
        "template_capture": _normalize_hotkey(hk.get("template_capture"), out["hotkeys"]["template_capture"]),
    }

    ov = cfg.get("overlay", {}) if isinstance(cfg, dict) else {}
    out["overlay"] = {
        "duration_ms": _coerce_duration(ov.get("duration_ms"), out["overlay"]["duration_ms"]),
        "inventory_duration_ms": _coerce_duration(ov.get("inventory_duration_ms"), out["overlay"]["inventory_duration_ms"]),
    }

    path = config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
