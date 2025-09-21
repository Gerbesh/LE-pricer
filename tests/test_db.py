import json
from pathlib import Path

import pytest

from db import PriceDB


def test_price_db_roundtrip(tmp_path: Path):
    db_path = tmp_path / "prices.json"
    price_db = PriceDB(str(db_path))
    assert db_path.exists()
    assert price_db.list_known() == []
    assert price_db.list_pending() == []

    price_db.ensure_pending("Лук тени", potential=2)
    assert len(price_db.list_pending()) == 1

    price_db.set_price("Лук тени", price=12345.0, potential=2)
    assert price_db.list_pending() == []
    known = price_db.list_known()
    assert len(known) == 1
    assert known[0]["name"] == "Лук тени"
    assert known[0]["potential"] == 2
    assert known[0]["price"] == 12345.0

    rec, score = price_db.find_best(["лук тени"], threshold=70)
    assert rec is not None
    assert score >= 90

    rec_pending = price_db.ensure_pending("Лук тени", potential=None)
    assert rec_pending is False

    price_db.add_known("Лук тени", price="коммент", potential=None)
    price_db.add_known("Лук тени", price=22222.0, potential=3)

    per_pot = price_db.get_prices_by_potential("Лук тени")
    assert per_pot.get(0) == 'коммент'
    assert per_pot.get(2) == 12345.0
    assert per_pot.get(3) == 22222.0

    with open(db_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["known"], "known entries should persist on disk"
