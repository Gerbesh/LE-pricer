import json
from pathlib import Path

from db import PriceDB


def test_price_db_roundtrip(tmp_path: Path):
    db_path = tmp_path / "prices.json"
    price_db = PriceDB(str(db_path))
    assert db_path.exists()
    assert price_db.list_known() == []
    assert price_db.list_pending() == []

    price_db.ensure_pending("Лук тени", potential=2)
    assert len(price_db.list_pending()) == 1

    key = price_db.set_price("Лук тени", price=12345.0, potential=2)
    assert price_db.list_pending() == []
    known = price_db.list_known()
    assert len(known) == 1
    entry = known[0]
    assert entry["key"] == key
    assert entry["name"] == "Лук тени"
    assert entry["price_lp2"] == 12345.0
    assert entry["comment_lp2"] is None

    rec, score = price_db.find_best(["лук тени"], threshold=70)
    assert rec is not None
    assert rec["key"] == key
    assert score >= 90

    per_pot = price_db.get_prices_by_potential("Лук тени")
    assert per_pot.get(2) == 12345.0

    price_db.add_known("Лук тени", price="коммент", potential=None)
    price_db.add_known("Лук тени", price=22222.0, potential=3)

    entry = price_db.list_known()[0]
    assert entry["comment_lp0"] == "коммент"
    assert entry["price_lp3"] == 22222.0

    new_key = price_db.edit_known(entry["key"], name="Лук теней", notes="заметка", lp_values={3: "33333"})
    updated = price_db.list_known()[0]
    assert updated["key"] == new_key
    assert updated["name"] == "Лук теней"
    assert updated["notes"] == "заметка"
    assert updated["price_lp3"] == 33333.0
    assert updated["comment_lp3"] is None

    with open(db_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data["known"], dict)
    assert new_key in data["known"]
