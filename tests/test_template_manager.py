import copy

import os
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("cv2")

import template_manager as tm


@pytest.fixture
def restore_cache():
    original = copy.deepcopy(tm._CACHE)
    yield
    tm._CACHE.clear()
    tm._CACHE.update(original)


def test_detect_potential_global_relaxed_accept(restore_cache, monkeypatch):
    monkeypatch.setattr(tm, "_build_cache_if_needed", lambda: None)
    monkeypatch.setattr(tm, "_prepare_gray_roi", lambda img: np.zeros((20, 20), dtype=np.uint8))
    monkeypatch.setattr(tm, "_scales_tuple", lambda: (1.0,))
    strong_tpl = np.ones((5, 5), dtype=np.uint8)
    weak_tpl = np.ones((4, 4), dtype=np.uint8)
    tm._CACHE["lp_global"] = {
        1: {"scaled": {(1.0,): [strong_tpl]}, "paths": []},
        2: {"scaled": {(1.0,): [weak_tpl]}, "paths": []},
        3: {"scaled": {(1.0,): []}, "paths": []},
        4: {"scaled": {(1.0,): []}, "paths": []},
    }

    def fake_best(gray, scaled):
        if scaled and scaled[0] is strong_tpl:
            return 0.86
        if scaled and scaled[0] is weak_tpl:
            return 0.70
        return 0.10

    monkeypatch.setattr(tm, "_best_match_scaled", fake_best)
    img = Image.new("RGB", (20, 20), color="black")
    pot, score = tm.detect_potential_global(img, threshold=0.90)
    assert pot == 1
    assert score == pytest.approx(0.86, rel=1e-3)

    monkeypatch.setattr(tm, "_best_match_scaled", lambda gray, scaled: 0.50)
    pot2, score2 = tm.detect_potential_global(img, threshold=0.90)
    assert pot2 == 0
    assert score2 == pytest.approx(0.50, rel=1e-3)


def test_match_inventory_regions_basic(restore_cache, monkeypatch):
    monkeypatch.setattr(tm, "_build_cache_if_needed", lambda: None)
    monkeypatch.setattr(tm, "_scales_tuple", lambda: (1.0,))
    base = np.zeros((40, 40), dtype=np.uint8)
    base[12:22, 18:28] = 255
    template = np.full((10, 10), 255, dtype=np.uint8)
    tm._CACHE["items"] = {
        "двузубец турани": {
            "name_scaled": {},
            "lp_scaled": {},
            "inventory_scaled": {(1.0,): [template]},
            "meta": "",
        }
    }
    tm._CACHE["inventory"] = {}
    monkeypatch.setattr(tm, "_prepare_gray_roi", lambda img: base)
    matches = tm.match_inventory_regions(Image.new("RGB", (40, 40)), threshold=0.8)
    assert matches
    rect = matches[0]["rect"]
    assert matches[0]["item"] == "двузубец турани"
    assert rect[0] >= 0 and rect[1] >= 0
    assert rect[2] - rect[0] == 10
    assert rect[3] - rect[1] == 10


def test_save_inventory_sample_and_list(tmp_path, restore_cache, monkeypatch):
    monkeypatch.setattr(tm, "TEMPLATE_ROOT", str(tmp_path))
    tm.invalidate_cache()
    img_path = tmp_path / "screen.png"
    Image.new("RGB", (20, 20), color="white").save(img_path)
    tm.item_dir("Без шаблонов")
    tm.save_inventory_sample(str(img_path), "С клипом", (0, 0, 10, 10))
    missing = tm.list_items_missing_inventory()
    assert tm.sanitize_name("С клипом") not in missing
    assert tm.sanitize_name("Без шаблонов") in missing


def test_list_all_items(tmp_path, restore_cache, monkeypatch):
    monkeypatch.setattr(tm, "TEMPLATE_ROOT", str(tmp_path))
    tm.invalidate_cache()
    os.makedirs(tmp_path / "item_a", exist_ok=True)
    os.makedirs(tmp_path / "item_b", exist_ok=True)
    (tmp_path / "item_a" / "name_x.png").write_bytes(b"fake")
    (tmp_path / "item_b" / "name_y.png").write_bytes(b"fake")
    items = tm.list_all_items()
    assert tm.sanitize_name("item_a") in items
    assert tm.sanitize_name("item_b") in items
