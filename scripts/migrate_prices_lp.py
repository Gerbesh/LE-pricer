import argparse
import json
import shutil
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

LP_RANGE = range(5)


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def _blank_entry(name: str, timestamp: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": (name or "").strip(),
        "notes": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    for pot in LP_RANGE:
        entry[f"price_lp{pot}"] = None
        entry[f"comment_lp{pot}"] = None
    return entry


def _coerce_price(value: Any) -> tuple[Any, Any]:
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


def migrate(input_path: Path, output_path: Path, backup: bool = True) -> None:
    with input_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    known = data.get("known")
    if isinstance(known, dict):
        print("prices.json already uses the new LP schema; no changes made.")
        return
    if not isinstance(known, list):
        raise SystemExit("Unsupported prices.json format: expected list under 'known'.")

    pending = data.get("pending") if isinstance(data.get("pending"), list) else []

    grouped: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

    for record in known:
        if not isinstance(record, dict):
            continue
        raw_name = (record.get("name") or "").strip()
        canonical = _norm(raw_name) or f"unnamed-{len(grouped)}"
        timestamp = record.get("updated_at") or record.get("created_at") or datetime.now().isoformat(timespec="seconds")
        entry = grouped.get(canonical)
        if entry is None:
            entry = _blank_entry(raw_name or canonical, timestamp)
            grouped[canonical] = entry
        else:
            if raw_name:
                entry["name"] = raw_name
            entry["created_at"] = min(entry.get("created_at") or timestamp, timestamp)
        entry["updated_at"] = max(entry.get("updated_at") or timestamp, timestamp)

        pot_raw = record.get("potential")
        try:
            pot = int(pot_raw)
        except Exception:
            pot = 0
        pot = max(0, min(4, pot))

        price, comment = _coerce_price(record.get("price"))
        price_field = f"price_lp{pot}"
        comment_field = f"comment_lp{pot}"
        existing_price = entry.get(price_field)
        existing_comment = entry.get(comment_field)
        if price is not None:
            if existing_price is not None or (isinstance(existing_comment, str) and existing_comment.strip()):
                print(f"Warning: overwriting LP{pot} for '{entry['name']}' with newer numeric value")
            entry[price_field] = price
            entry[comment_field] = None
        elif comment:
            if existing_price is not None or (isinstance(existing_comment, str) and existing_comment.strip()):
                print(f"Warning: overwriting LP{pot} for '{entry['name']}' with newer comment")
            entry[price_field] = None
            entry[comment_field] = comment

    new_data = {
        "known": {key: value for key, value in grouped.items()},
        "known_order": list(grouped.keys()),
        "pending": pending,
    }

    if output_path == input_path and backup:
        backup_path = input_path.with_suffix(input_path.suffix + f".{datetime.now():%Y%m%d_%H%M%S}.bak")
        shutil.copy2(input_path, backup_path)
        print(f"Backup created at {backup_path}")

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(new_data, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(output_path)
    print(f"Migrated data written to {output_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate prices.json to LP column schema")
    parser.add_argument("--input", type=Path, default=Path("prices.json"), help="Path to legacy prices.json")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path; defaults to --input")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup when writing in place")
    args = parser.parse_args(argv)

    input_path: Path = args.input
    output_path: Path = args.output or input_path

    if not input_path.exists():
        raise SystemExit(f"Input file '{input_path}' does not exist")

    migrate(input_path, output_path, backup=not args.no_backup)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(1)
