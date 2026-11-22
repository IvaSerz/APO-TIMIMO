"""Command-line frontend for automation and no-display environments."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .branding import APP_NAME
from .collector import scan_inventory
from .export import export_csv, export_html, export_json, export_pdf
from .models import compare
from .storage import latest_snapshot, list_snapshots, load_snapshot, save_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apo-timimo", description=f"{APP_NAME} — локальная инвентаризация ПО")
    actions = parser.add_subparsers(dest="command", required=True)
    scan = actions.add_parser("scan", help="Сканирование установленного ПО")
    scan.add_argument("--output", "-o", type=Path, help="Путь к отчёту; без него печатается JSON в stdout")
    scan.add_argument("--format", choices=["json", "csv", "html", "pdf"], default="json")
    scan.add_argument("--save-history", action="store_true", help="Сохранить снимок в локальной истории")
    scan.add_argument("--without-store", action="store_true", help="Не сканировать Microsoft Store")
    scan.add_argument("--without-profiler", action="store_true", help="Не запускать macOS system_profiler")
    actions.add_parser("history", help="Список локальных снимков")
    actions.add_parser("compare", help="Сравнить два последних снимка")
    args = parser.parse_args(argv)
    if args.command == "history":
        for path in list_snapshots():
            try:
                record = load_snapshot(path)
                print(f"{record.scanned_at}\t{len(record.records)}\t{path}")
            except (OSError, KeyError, ValueError):
                print(f"Повреждённый снимок: {path}", file=sys.stderr)
        return 0
    if args.command == "compare":
        history = list_snapshots()
        if len(history) < 2:
            print("Нужно минимум два сохранённых сканирования", file=sys.stderr)
            return 2
        change = compare(load_snapshot(history[1]), load_snapshot(history[0]))
        print(json.dumps({"added": [r.to_dict() for r in change.added],
                          "removed": [r.to_dict() for r in change.removed],
                          "updated": [{"before": a.to_dict(), "after": b.to_dict()} for a, b in change.updated]},
                         ensure_ascii=False, indent=2))
        return 0
    result = scan_inventory(include_store=not args.without_store,
                            include_profiler=not args.without_profiler,
                            progress=lambda message: print(message, file=sys.stderr))
    if args.save_history:
        save_snapshot(result)
    if args.output is None:
        if args.format != "json":
            parser.error("Для CSV/HTML/PDF укажите --output путь")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        exporters = {"csv": export_csv, "json": export_json,
                     "html": export_html, "pdf": export_pdf}
        try:
            exporters[args.format](result, args.output)
        except (OSError, RuntimeError) as exc:
            print(f"Ошибка экспорта: {exc}", file=sys.stderr)
            return 2
        print(f"Отчёт сохранён: {args.output} (записей: {len(result.records)})", file=sys.stderr)
    for warning in result.warnings:
        print("ПРЕДУПРЕЖДЕНИЕ: " + warning, file=sys.stderr)
    return 0 if not result.warnings else 1


if __name__ == "__main__":
    raise SystemExit(main())
