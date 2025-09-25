import json, threading, os, sys, re, uuid
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from rapidfuzz import fuzz


def _default_db_path() -> str:
    base_dir = os.path.dirname(__file__)
    # When frozen into an executable, store data in a user-writable location
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            appdata = os.getenv("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
            base_dir = os.path.join(appdata, "Pricer")
        else:
            base_dir = os.path.join(os.path.expanduser("~/.local/share"), "pricer")
        os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "prices.json")


DB_PATH = _default_db_path()

_lock = threading.RLock()

LP_MIN = 0
LP_MAX = 4
LP_RANGE = range(LP_MIN, LP_MAX + 1)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(name: str) -> str:
    return (name or "").strip().lower()


_SHAPE_MAP = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "Т": "T", "Х": "X", "У": "Y", "Ш": "W", "Щ": "W", "Ь": "b", "Я": "R", "Л": "A",
    "а": "a", "в": "b", "с": "c", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "т": "t", "х": "x", "у": "y", "ш": "w", "щ": "w", "ь": "b", "я": "r", "л": "a",
    "A": "A", "B": "B", "C": "C", "E": "E", "H": "H", "K": "K", "M": "M", "O": "O", "P": "P", "T": "T", "X": "X", "Y": "Y", "W": "W",
    "a": "a", "b": "b", "c": "c", "e": "e", "h": "h", "k": "k", "m": "m", "o": "o", "p": "p", "t": "t", "x": "x", "y": "y", "w": "w",
    "0": "o", "3": "e", "4": "a", "6": "b", "8": "b"
})


def _shape_fold(s: str) -> str:
    s = (s or "").strip()
    return s.translate(_SHAPE_MAP).lower()


def _clean_for_match(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ё", "е")
    s = re.sub(r"[^0-9a-zа-я ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_RU2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ы": "y", "э": "e", "ю": "yu", "я": "ya"
}


def _translit_ru_to_lat(s: str) -> str:
    out = []
    for ch in (s or "").lower():
        out.append(_RU2LAT.get(ch, ch))
    return "".join(out)


def _normalize_comment(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_price_text(value: Any) -> Tuple[Optional[float], Optional[str]]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    if not text:
        return None, None
    try:
        return float(text.replace(',', '.')), None
    except Exception:
        return None, text


def _price_field(pot: int) -> str:
    return f"price_lp{pot}"


def _comment_field(pot: int) -> str:
    return f"comment_lp{pot}"


def _empty_state() -> Dict[str, Any]:
    return {"known": {}, "known_order": [], "pending": []}


def _entry_has_lp(entry: Dict[str, Any], pot: int) -> bool:
    price = entry.get(_price_field(pot))
    comment = entry.get(_comment_field(pot))
    if price is not None:
        return True
    if isinstance(comment, str) and comment.strip():
        return True
    return False


def _lp_display_value(entry: Dict[str, Any], pot: int) -> Optional[Any]:
    comment = entry.get(_comment_field(pot))
    if isinstance(comment, str) and comment.strip():
        return comment
    return entry.get(_price_field(pot))


class PriceDB:
    """Price storage with LP-specific columns."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        if not os.path.exists(self.path):
            raw_state = _empty_state()
            self._write_state(raw_state)
        with open(self.path, "r", encoding="utf-8") as fh:
            raw_state = json.load(fh)
        if self._is_legacy(raw_state):
            raise RuntimeError(
                "Detected legacy price schema. Run scripts/migrate_prices_lp.py before using this version."
            )
        self._state = self._coerce_state(raw_state)
        raw_serialized = json.dumps(raw_state, sort_keys=True, ensure_ascii=False)
        new_serialized = json.dumps(self._state, sort_keys=True, ensure_ascii=False)
        if raw_serialized != new_serialized:
            self._write_state(self._state)

    def _write_state(self, state: Dict[str, Any]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _save_locked(self) -> None:
        self._write_state(self._state)

    def _is_legacy(self, state: Dict[str, Any]) -> bool:
        known = state.get("known")
        if isinstance(known, list):
            return True
        if isinstance(known, dict):
            for entry in known.values():
                if isinstance(entry, dict) and "potential" in entry:
                    return True
        return False

    def _coerce_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        known = state.get("known")
        if not isinstance(known, dict):
            known = {}
        coerced_known: Dict[str, Dict[str, Any]] = {}
        now = _now_iso()
        for key, entry in known.items():
            if not isinstance(entry, dict):
                continue
            coerced_known[str(key)] = self._coerce_entry(entry, now)
        order = state.get("known_order")
        if not isinstance(order, list):
            order = []
        order = [str(k) for k in order if str(k) in coerced_known]
        for key in coerced_known:
            if key not in order:
                order.append(key)
        pending: list[Dict[str, Any]] = []
        for item in state.get("pending", []):
            if not isinstance(item, dict):
                continue
            pending.append({
                "name": item.get("name", ""),
                "potential": item.get("potential"),
                "added_at": item.get("added_at") or _now_iso(),
            })
        return {"known": coerced_known, "known_order": order, "pending": pending}

    def _coerce_entry(self, entry: Dict[str, Any], default_ts: str) -> Dict[str, Any]:
        name = (entry.get("name") or "").strip()
        created_at = entry.get("created_at") or entry.get("updated_at") or default_ts
        updated_at = entry.get("updated_at") or created_at
        coerced = {
            "name": name,
            "notes": _normalize_comment(entry.get("notes")),
            "created_at": created_at,
            "updated_at": updated_at,
        }
        for pot in LP_RANGE:
            price_field = _price_field(pot)
            comment_field = _comment_field(pot)
            price_value = entry.get(price_field)
            comment_value = entry.get(comment_field)
            numeric_price: Optional[float] = None
            if isinstance(price_value, (int, float)):
                numeric_price = float(price_value)
            elif isinstance(price_value, str):
                try:
                    numeric_price = float(price_value.replace(',', '.'))
                except Exception:
                    if comment_value is None:
                        comment_value = price_value
                    numeric_price = None
            coerced[price_field] = numeric_price
            coerced[comment_field] = _normalize_comment(comment_value)
        return coerced

    def _generate_placeholder_key(self) -> str:
        return f"__draft_{uuid.uuid4().hex}"

    def _make_entry(self, name: str) -> Dict[str, Any]:
        now = _now_iso()
        entry: Dict[str, Any] = {
            "name": (name or "").strip(),
            "notes": None,
            "created_at": now,
            "updated_at": now,
        }
        for pot in LP_RANGE:
            entry[_price_field(pot)] = None
            entry[_comment_field(pot)] = None
        return entry

    def _ensure_entry_locked(self, name: str) -> Tuple[str, Dict[str, Any], bool]:
        canonical = _norm(name)
        if canonical and canonical in self._state["known"]:
            return canonical, self._state["known"][canonical], False
        key = canonical if canonical else self._generate_placeholder_key()
        if not canonical:
            # avoid collisions for empty names
            while key in self._state["known"]:
                key = self._generate_placeholder_key()
        entry = self._make_entry(name)
        self._state["known"][key] = entry
        if key not in self._state["known_order"]:
            self._state["known_order"].append(key)
        return key, entry, True

    def _clone_entry(self, key: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        clone = dict(entry)
        clone["key"] = key
        return clone

    def _remove_pending_locked(self, canonical_names: Iterable[str]) -> bool:
        names = {n for n in canonical_names if n}
        if not names:
            return False
        before = len(self._state["pending"])
        self._state["pending"] = [
            p for p in self._state["pending"] if _norm(p.get("name", "")) not in names
        ]
        return len(self._state["pending"]) != before

    def list_pending(self) -> list[Dict[str, Any]]:
        with _lock:
            return [dict(item) for item in self._state["pending"]]

    def list_known(self) -> list[Dict[str, Any]]:
        with _lock:
            rows: list[Dict[str, Any]] = []
            for key in self._state["known_order"]:
                entry = self._state["known"].get(key)
                if not entry:
                    continue
                rows.append(self._clone_entry(key, entry))
            return rows

    def ensure_pending(self, name: str, potential: int | None):
        canonical = _norm(name)
        with _lock:
            if canonical and canonical in self._state["known"]:
                return False
            for entry in self._state["known"].values():
                if canonical and _norm(entry.get("name", "")) == canonical:
                    return False
            for item in self._state["pending"]:
                if _norm(item.get("name", "")) == canonical:
                    if potential is not None and item.get("potential") is None:
                        item["potential"] = potential
                        self._save_locked()
                    return False
            self._state["pending"].append({
                "name": name.strip(),
                "potential": potential,
                "added_at": _now_iso(),
            })
            self._save_locked()
            return True

    def set_price(self, name: str, price: float, potential: int | None = None) -> str:
        pot = potential if potential is not None else 0
        if pot not in LP_RANGE:
            raise ValueError(f"Unsupported LP slot: {pot}")
        with _lock:
            key, entry, created = self._ensure_entry_locked(name)
            price_field = _price_field(pot)
            comment_field = _comment_field(pot)
            numeric = float(price)
            changed = created
            if entry.get(price_field) != numeric:
                entry[price_field] = numeric
                changed = True
            if entry.get(comment_field) is not None:
                entry[comment_field] = None
                changed = True
            pending_removed = self._remove_pending_locked({_norm(name)})
            if changed:
                entry["updated_at"] = _now_iso()
            if changed or created or pending_removed:
                self._save_locked()
            return key

    def add_known(self, name: str = "", price: float | str | None = None, potential: int | None = None) -> str:
        with _lock:
            key, entry, created = self._ensure_entry_locked(name)
            changed = created
            if price is not None:
                pot = potential if potential is not None else 0
                if pot not in LP_RANGE:
                    raise ValueError(f"Unsupported LP slot: {pot}")
                value, comment = _coerce_price_text(price)
                price_field = _price_field(pot)
                comment_field = _comment_field(pot)
                if entry.get(price_field) != value:
                    entry[price_field] = value
                    changed = True
                if entry.get(comment_field) != comment:
                    entry[comment_field] = comment
                    changed = True
            if changed:
                entry["updated_at"] = _now_iso()
                if created:
                    entry["created_at"] = entry["updated_at"]
                self._save_locked()
            return key

    def edit_known(
        self,
        key: str,
        *,
        name: str | None = None,
        notes: str | None = None,
        lp_values: Optional[Dict[int, Any]] = None,
    ) -> str:
        with _lock:
            if key not in self._state["known"]:
                raise KeyError(f"Unknown price entry key: {key}")
            entry = self._state["known"][key]
            changed = False
            if name is not None:
                new_name = (name or "").strip()
                if entry.get("name") != new_name:
                    entry["name"] = new_name
                    changed = True
                new_key = _norm(new_name)
                if new_key and new_key != key:
                    if new_key in self._state["known"] and self._state["known"].get(new_key) is not entry:
                        raise ValueError(f"Entry '{new_name}' already exists")
                    self._state["known"][new_key] = entry
                    del self._state["known"][key]
                    order = self._state["known_order"]
                    for idx, existing in enumerate(order):
                        if existing == key:
                            order[idx] = new_key
                            break
                    key = new_key
                    changed = True
            if notes is not None:
                normalized_notes = _normalize_comment(notes)
                if entry.get("notes") != normalized_notes:
                    entry["notes"] = normalized_notes
                    changed = True
            if lp_values:
                for pot, raw in lp_values.items():
                    if pot not in LP_RANGE:
                        continue
                    price, comment = _coerce_price_text(raw)
                    price_field = _price_field(pot)
                    comment_field = _comment_field(pot)
                    if entry.get(price_field) != price:
                        entry[price_field] = price
                        changed = True
                    if entry.get(comment_field) != comment:
                        entry[comment_field] = comment
                        changed = True
            if changed:
                entry["updated_at"] = _now_iso()
                self._save_locked()
            return key

    def delete_pending(self, names: list[str]) -> int:
        if not names:
            return 0
        targets = {_norm(n) for n in names if n}
        with _lock:
            before = len(self._state["pending"])
            self._state["pending"] = [
                p for p in self._state["pending"] if _norm(p.get("name", "")) not in targets
            ]
            removed = before - len(self._state["pending"])
            if removed:
                self._save_locked()
            return removed

    def delete_known(self, identifiers: list[str]) -> int:
        if not identifiers:
            return 0
        with _lock:
            keys = set()
            norms = {_norm(x) for x in identifiers if x}
            for key, entry in list(self._state["known"].items()):
                if key in identifiers or _norm(entry.get("name", "")) in norms:
                    keys.add(key)
            if not keys:
                return 0
            for key in keys:
                self._state["known"].pop(key, None)
            self._state["known_order"] = [k for k in self._state["known_order"] if k not in keys]
            self._save_locked()
            return len(keys)

    def get_price(self, name: str, potential: int | None = None):
        pot = potential if potential is not None else 0
        rec, _ = self.find_best([name], threshold=80, potential=pot if potential is not None else None)
        if not rec:
            return None, None
        value = _lp_display_value(rec, pot if pot in LP_RANGE else 0)
        return value, rec

    def get_prices_by_potential(self, name: str, threshold: int = 70) -> dict[int, Any]:
        rec, _ = self.find_best([name], threshold=threshold)
        if not rec:
            return {}
        return {pot: _lp_display_value(rec, pot) for pot in LP_RANGE}

    def find_best(
        self,
        lines: list[str],
        threshold: int = 80,
        potential: int | None = None,
        strict_potential: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        if not lines:
            return None, 0
        norm_lines = [_clean_for_match(x) for x in lines if x and _clean_for_match(x)]
        shape_lines = [_shape_fold(x) for x in lines if x and _shape_fold(x)]
        translit_lines = [_clean_for_match(_translit_ru_to_lat(x)) for x in lines if x]
        if not norm_lines:
            return None, 0
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        with _lock:
            for key, entry in self._state["known"].items():
                name_n = _clean_for_match(entry.get("name", ""))
                if not name_n:
                    continue
                if strict_potential and potential is not None and not _entry_has_lp(entry, potential):
                    continue
                sc = 0
                name_tokens = [t for t in name_n.split() if len(t) >= 2]
                for ln in norm_lines:
                    s1 = max(
                        fuzz.token_set_ratio(name_n, ln),
                        fuzz.partial_ratio(name_n, ln),
                    )
                    if name_n and (name_n in ln or ln in name_n):
                        s1 = max(s1, 100)
                    if name_tokens:
                        ln_tokens = {t for t in ln.split() if len(t) >= 2}
                        cov = len([t for t in name_tokens if t in ln_tokens]) / max(1, len(name_tokens))
                        if cov >= 0.6:
                            s1 = max(s1, int(95 + 5 * cov))
                    if s1 > sc:
                        sc = s1
                name_shape = _shape_fold(entry.get("name", ""))
                for ln in shape_lines:
                    s2 = max(
                        fuzz.token_set_ratio(name_shape, ln),
                        fuzz.partial_ratio(name_shape, ln),
                    )
                    if name_shape and (name_shape in ln or ln in name_shape):
                        s2 = max(s2, 100)
                    if s2 > sc:
                        sc = s2
                name_tr = _clean_for_match(_translit_ru_to_lat(entry.get("name", "")))
                for ln in translit_lines:
                    s3 = max(
                        fuzz.token_set_ratio(name_tr, ln),
                        fuzz.partial_ratio(name_tr, ln),
                    )
                    if name_tr and (name_tr in ln or ln in name_tr):
                        s3 = max(s3, 100)
                    if s3 > sc:
                        sc = s3
                if potential is not None and _entry_has_lp(entry, potential):
                    sc += 2
                if sc > best_score:
                    best = self._clone_entry(key, entry)
                    best_score = sc
        if best and best_score >= threshold:
            return best, best_score
        return None, 0