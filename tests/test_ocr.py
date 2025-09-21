import pytest
pytest.importorskip("cv2")

from PIL import Image
import ocr


def _fake_data():
    return {
        "text": [
            "Легендарный предмет",
            "15% бонус",
            "Меч тени II",
            "ЛЕГЕНДАР 3",
        ],
        "left": [5, 6, 8, 12],
        "top": [10, 28, 18, 42],
        "conf": ["96", "88", "83", "90"],
        "page_num": [1, 1, 1, 1],
        "block_num": [1, 1, 1, 1],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 2, 3, 4],
    }


def test_parse_item_prefers_title_line_over_banners():
    data = _fake_data()
    result = ocr.parse_item(data)
    assert result["name"] == "Меч тени II"
    assert result["line_scores"]
    top_candidate = result["line_scores"][0]
    assert top_candidate["text"] == "Меч тени II"
    assert top_candidate["score"] > result["line_scores"][-1]["score"]


def test_detect_cropped_region_relaxes_threshold(monkeypatch):
    monkeypatch.setattr(ocr, "_template_scales", lambda: (1.0,))
    monkeypatch.setattr(ocr, "_get_templates_scaled", lambda scales=None: ([object()], [object()]))
    call_state = {"count": 0}

    def fake_match(gray, templates):
        call_state["count"] += 1
        if call_state["count"] == 1:
            return (0.65, (12, 10), (36, 20))
        return (0.59, (28, 24), (34, 20))

    monkeypatch.setattr(ocr, "_match_best", fake_match)
    img = Image.new("RGB", (200, 120), color="black")
    rect = ocr._detect_cropped_region(img, threshold=0.70)
    assert rect is not None
    stats = ocr.get_last_detection_stats()
    assert stats["result"] == "ok"
    assert stats["tl_threshold_used"] < 0.70
    assert stats["br_threshold_used"] < 0.70
    assert rect[2] > rect[0] and rect[3] > rect[1]
