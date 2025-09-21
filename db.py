
import json, threading, time, os, sys, re
from datetime import datetime
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

def _now_iso():
    return datetime.now().isoformat(timespec="seconds")

def _norm(name: str) -> str:
    return (name or "").strip().lower()

_SHAPE_MAP = str.maketrans({
    # Cyrillic to Latin lookalikes (uppercase and lowercase)
    'А':'A','В':'B','С':'C','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P','Т':'T','Х':'X','У':'Y','Ш':'W','Щ':'W','Ь':'b','Я':'R','Л':'A',
    'а':'a','в':'b','с':'c','е':'e','к':'k','м':'m','н':'h','о':'o','р':'p','т':'t','х':'x','у':'y','ш':'w','щ':'w','ь':'b','я':'r','л':'a',
    # Latin to Latin (identity) for completeness
    'A':'A','B':'B','C':'C','E':'E','H':'H','K':'K','M':'M','O':'O','P':'P','T':'T','X':'X','Y':'Y','W':'W',
    'a':'a','b':'b','c':'c','e':'e','h':'h','k':'k','m':'m','o':'o','p':'p','t':'t','x':'x','y':'y','w':'w',
    # Common OCR digit confusions
    '0':'o','3':'e','4':'a','6':'b','8':'b'
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
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya'
}

def _translit_ru_to_lat(s: str) -> str:
    out = []
    for ch in (s or "").lower():
        out.append(_RU2LAT.get(ch, ch))
    return "".join(out)

class PriceDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        if not os.path.exists(self.path):
            self.data = {"known": [], "pending": []}
            self._save()
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def _save(self):
        with _lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def get_price(self, name: str):
        n = _norm(name)
        with _lock:
            for it in self.data["known"]:
                if _norm(it["name"]) == n:
                    return it["price"], it
        # fuzzy try (>=90)
        best = None
        best_score = 0
        with _lock:
            for it in self.data["known"]:
                score = fuzz.token_set_ratio(_norm(it["name"]), n)
                if score > best_score:
                    best, best_score = it, score
        if best and best_score >= 90:
            return best["price"], best
        return None, None

    def ensure_pending(self, name: str, potential: int | None):
        n = _norm(name)
        with _lock:
            # already known?
            for it in self.data["known"]:
                if _norm(it["name"]) == n:
                    return False
            for it in self.data["pending"]:
                if _norm(it["name"]) == n:
                    # update potential if new info arrived
                    if potential is not None and it.get("potential") is None:
                        it["potential"] = potential
                        self._save()
                    return False
            self.data["pending"].append({
                "name": name.strip(),
                "potential": potential,
                "added_at": _now_iso()
            })
            self._save()
            return True

    def set_price(self, name: str, price: float, potential: int | None = None):
        n = _norm(name)
        with _lock:
            # update known or add
            for it in self.data["known"]:
                if _norm(it["name"]) == n:
                    it["price"] = float(price)
                    if potential is not None:
                        it["potential"] = potential
                    it["updated_at"] = _now_iso()
                    self._save()
                    return
            # remove from pending if exists
            self.data["pending"] = [p for p in self.data["pending"] if _norm(p["name"]) != n]
            self.data["known"].append({
                "name": name.strip(),
                "potential": potential,
                "price": float(price),
                "updated_at": _now_iso()
            })
            self._save()

    def edit_known(self, index: int, name: str | None = None, price: float | str | None = None, potential: int | None = None):
        with _lock:
            if 0 <= index < len(self.data["known"]):
                it = self.data["known"][index]
                if name is not None:
                    it["name"] = name
                if price is not None:
                    # Allow textual comments in price; keep float when numeric
                    if isinstance(price, str):
                        txt = price.strip()
                        if txt == "":
                            it["price"] = None
                        else:
                            try:
                                it["price"] = float(txt.replace(",", "."))
                            except Exception:
                                it["price"] = txt
                    else:
                        it["price"] = float(price)
                if potential is not None:
                    it["potential"] = potential
                it["updated_at"] = _now_iso()
                self._save()

    def list_pending(self):
        with _lock:
            return list(self.data["pending"])

    def list_known(self):
        with _lock:
            return list(self.data["known"])

    def get_prices_by_potential(self, name: str, threshold: int = 70) -> dict[int, float | str | None]:
        """Return known prices for the given item grouped by potential (0..4)."""
        canonical = _norm(name)
        try:
            rec, score = self.find_best([name], threshold=threshold)
        except Exception:
            rec, score = (None, 0)
        if rec:
            canonical = _norm(rec.get("name", "")) or canonical
        prices: dict[int, float | str | None] = {}
        with _lock:
            for entry in self.data["known"]:
                if _norm(entry.get("name", "")) != canonical:
                    continue
                pot_raw = entry.get("potential")
                pot_key = int(pot_raw) if isinstance(pot_raw, int) else 0
                prices[pot_key] = entry.get("price")
        return prices



    # Direct editing helpers for GUI-driven workflow
    def add_known(self, name: str = "", price: float | str | None = None, potential: int | None = None) -> int:
        with _lock:
            # Normalize price: keep strings as-is (for comments), floats when numeric
            norm_price: float | str | None
            if isinstance(price, str):
                txt = price.strip()
                if txt == "":
                    norm_price = None
                else:
                    try:
                        norm_price = float(txt.replace(",", "."))
                    except Exception:
                        norm_price = txt
            elif price is not None:
                norm_price = float(price)
            else:
                norm_price = None
            rec = {
                "name": name.strip(),
                "potential": potential,
                "price": norm_price,
                "updated_at": _now_iso(),
            }
            self.data["known"].append(rec)
            self._save()
            return len(self.data["known"]) - 1

    def find_best(self, lines: list[str], threshold: int = 80, potential: int | None = None, strict_potential: bool = False):
        """Find best matching known item by fuzzy comparing provided lines.

        - Uses RapidFuzz token_set_ratio.
        - If potential is provided, prefer exact potential matches.
        Returns (record, score) or (None, 0).
        """
        if not lines:
            return None, 0
        norm_lines = [ _clean_for_match(x) for x in lines if x and _clean_for_match(x) ]
        shape_lines = [ _shape_fold(x) for x in lines if x and _shape_fold(x) ]
        translit_lines = [ _clean_for_match(_translit_ru_to_lat(x)) for x in lines if x ]
        if not norm_lines:
            return None, 0
        best = None
        best_score = 0
        with _lock:
            for rec in self.data["known"]:
                name_n = _clean_for_match(rec.get("name", ""))
                if not name_n:
                    continue
                if strict_potential and potential is not None and rec.get("potential") != potential:
                    continue
                # compute best line score with visual folding fallback
                sc = 0
                # quick substring and token coverage boosts
                name_tokens = [t for t in name_n.split() if len(t) >= 2]
                for ln in norm_lines:
                    s1 = max(
                        fuzz.token_set_ratio(name_n, ln),
                        fuzz.partial_ratio(name_n, ln),
                    )
                    # direct substring
                    if name_n and (name_n in ln or ln in name_n):
                        s1 = max(s1, 100)
                    # token coverage
                    if name_tokens:
                        ln_tokens = set([t for t in ln.split() if len(t) >= 2])
                        cov = len([t for t in name_tokens if t in ln_tokens]) / max(1, len(name_tokens))
                        if cov >= 0.6:
                            s1 = max(s1, int(95 + 5*cov))
                    if s1 > sc:
                        sc = s1
                # shape-folded comparison (handles Cyrillic/Latin lookalikes)
                name_shape = _shape_fold(rec.get("name", ""))
                for ln in shape_lines:
                    s2 = max(
                        fuzz.token_set_ratio(name_shape, ln),
                        fuzz.partial_ratio(name_shape, ln),
                    )
                    if name_shape and (name_shape in ln or ln in name_shape):
                        s2 = max(s2, 100)
                    if s2 > sc:
                        sc = s2
                # transliteration comparison (ru->lat)
                name_tr = _clean_for_match(_translit_ru_to_lat(rec.get("name", "")))
                for ln in translit_lines:
                    s3 = max(
                        fuzz.token_set_ratio(name_tr, ln),
                        fuzz.partial_ratio(name_tr, ln),
                    )
                    if name_tr and (name_tr in ln or ln in name_tr):
                        s3 = max(s3, 100)
                    if s3 > sc:
                        sc = s3
                # prefer potential match if provided
                if potential is not None and rec.get("potential") == potential:
                    sc += 2  # small bias
                if sc > best_score:
                    best, best_score = rec, sc
        if best and best_score >= threshold:
            return best, best_score
        return None, 0

    # Deletion helpers
    def delete_pending(self, names: list[str]) -> int:
        """Delete pending items by name. Returns count removed."""
        if not names:
            return 0
        targets = { _norm(n) for n in names if n }
        with _lock:
            before = len(self.data["pending"])
            self.data["pending"] = [p for p in self.data["pending"] if _norm(p.get("name","")) not in targets]
            after = len(self.data["pending"])
            if after != before:
                self._save()
            return before - after

    def delete_known(self, names: list[str]) -> int:
        """Delete known items by name. Returns count removed."""
        if not names:
            return 0
        targets = { _norm(n) for n in names if n }
        with _lock:
            before = len(self.data["known"])
            self.data["known"] = [k for k in self.data["known"] if _norm(k.get("name","")) not in targets]
            after = len(self.data["known"])
            if after != before:
                self._save()
            return before - after
