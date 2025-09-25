import json
from pathlib import Path

from scripts.migrate_prices_lp import migrate


def test_migrate_prices_lp(tmp_path: Path):
    legacy = {
        "known": [
            {
                "name": "Лук тени",
                "potential": None,
                "price": "коммент",
                "updated_at": "2024-01-01T00:00:00",
            },
            {
                "name": "Лук тени",
                "potential": 2,
                "price": 12345,
                "updated_at": "2024-01-02T00:00:00",
            },
        ],
        "pending": [
            {"name": "Ожидание", "potential": 1, "added_at": "2024-01-03T00:00:00"}
        ],
    }
    src = tmp_path / "prices.json"
    src.write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8")

    migrate(src, src, backup=False)

    migrated = json.loads(src.read_text(encoding="utf-8"))
    assert isinstance(migrated["known"], dict)
    assert migrated["known_order"] == ["лук тени"]

    entry = migrated["known"]["лук тени"]
    assert entry["name"] == "Лук тени"
    assert entry["comment_lp0"] == "коммент"
    assert entry["price_lp2"] == 12345.0
    assert migrated["pending"] == legacy["pending"]
