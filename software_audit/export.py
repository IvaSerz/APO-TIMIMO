"""JSON/CSV/HTML/PDF exports. PDF depends on optional reportlab."""
from __future__ import annotations

import csv
from html import escape as html_escape
import json
from pathlib import Path
from typing import Iterable

from .models import Inventory, Software
from .branding import APP_NAME, APP_TEAM, APP_DEVELOPER

COLUMNS = [
    ("name", "Программа"),
    ("version", "Версия"),
    ("publisher", "Разработчик / издатель"),
    ("source", "Источник"),
    ("install_path", "Путь"),
    ("installed_at", "Дата установки"),
    ("identifier", "Идентификатор"),
    ("scope", "Область"),
]


def _csv_safe(text: str) -> str:
    # Prevent spreadsheet formula injection if a report is opened with Excel.
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def export_csv(inventory: Inventory, destination: Path, entries: Iterable[Software] | None = None) -> None:
    records = inventory.records if entries is None else list(entries)
    with Path(destination).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([caption for _, caption in COLUMNS])
        for item in records:
            writer.writerow([_csv_safe(str(getattr(item, field))) for field, _ in COLUMNS])


def export_json(inventory: Inventory, destination: Path, entries: Iterable[Software] | None = None) -> None:
    data = inventory.to_dict()
    if entries is not None:
        data["records"] = [item.to_dict() for item in entries]
    with Path(destination).open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def export_html(inventory: Inventory, destination: Path, entries: Iterable[Software] | None = None) -> None:
    records = inventory.records if entries is None else list(entries)
    heading = "".join(f"<th>{html_escape(title)}</th>" for _, title in COLUMNS)
    lines = []
    for item in records:
        cols = "".join(f"<td>{html_escape(str(getattr(item, key)))}</td>" for key, _ in COLUMNS)
        lines.append(f"<tr>{cols}</tr>")
    document = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Отчёт об установленном ПО</title>
<style>
body{{font:14px/1.4 system-ui,Arial,sans-serif;color:#172033;margin:40px}}
h1{{font-size:23px;margin-bottom:5px}}p{{color:#5c677b}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#e9eef5;text-align:left}}td,th{{padding:8px;border-bottom:1px solid #ddd;word-break:break-word}}
tr:nth-child(even){{background:#f8fafc}}
@page{{size:A4 landscape;margin:12mm}}
@media print{{body{{margin:0}}thead{{display:table-header-group}}}}
</style></head><body><h1>{html_escape(APP_NAME)} — Аудит установленного ПО</h1>
<p>Компьютер: {html_escape(inventory.hostname)} | ОС: {html_escape(inventory.operating_system)} |
Сканирование: {html_escape(inventory.scanned_at)} | Записей: {len(records)}</p>
<table><thead><tr>{heading}</tr></thead><tbody>{''.join(lines)}</tbody></table>\n<p>{html_escape(APP_TEAM)} · Разработчик: {html_escape(APP_DEVELOPER)}</p></body></html>'''
    Path(destination).write_text(document, encoding="utf-8")


def _find_pdf_font() -> str:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("Не найден подходящий шрифт с поддержкой кириллицы; используйте экспорт HTML")


def export_pdf(inventory: Inventory, destination: Path, entries: Iterable[Software] | None = None) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, LongTable, Paragraph, Spacer, TableStyle
    except ImportError as exc:
        raise RuntimeError("Для экспорта PDF установите пакет: python -m pip install reportlab") from exc

    fontfile = _find_pdf_font()
    if "AuditCyrillic" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("AuditCyrillic", fontfile))
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(str(destination), pagesize=pagesize, rightMargin=30,
                            leftMargin=30, topMargin=35, bottomMargin=35)
    title_style = ParagraphStyle("AuditTitle", fontName="AuditCyrillic", fontSize=16,
                                 leading=21, textColor=colors.HexColor("#152238"))
    subtitle_style = ParagraphStyle("AuditSubtitle", fontName="AuditCyrillic", fontSize=8,
                                    leading=12, textColor=colors.HexColor("#4c5a6d"))
    cell_style = ParagraphStyle("AuditCell", fontName="AuditCyrillic", fontSize=7,
                                leading=10, wordWrap="CJK")
    header_style = ParagraphStyle("AuditHeader", parent=cell_style,
                                  textColor=colors.white)
    rows = inventory.records if entries is None else list(entries)
    story = [Paragraph(html_escape(f"{APP_NAME} — Аудит установленного ПО"), title_style), Spacer(1, 9),
             Paragraph(html_escape(f"Компьютер: {inventory.hostname} | ОС: {inventory.operating_system} | "
                                   f"Дата: {inventory.scanned_at} | Записей: {len(rows)}"), subtitle_style),
             Spacer(1, 16)]
    fields = [("name", "Программа"), ("version", "Версия"), ("publisher", "Разработчик"),
              ("source", "Источник"), ("install_path", "Путь"), ("installed_at", "Дата установки")]
    data = [[Paragraph(name, header_style) for _, name in fields]]
    for item in rows:
        data.append([Paragraph(html_escape(str(getattr(item, field))) or "—", cell_style)
                     for field, _ in fields])
    available_width = pagesize[0] - 60
    widths = [0.19, 0.10, 0.17, 0.16, 0.28, 0.10]
    table = LongTable(data, colWidths=[available_width * width for width in widths], repeatRows=1,
                      hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b57")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#243b57")),
    ]))
    story.append(table)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("AuditCyrillic", 8)
        canvas.setFillColor(colors.HexColor("#687386"))
        canvas.drawString(30, 18, f"{APP_NAME} · {APP_TEAM}")
        canvas.drawRightString(pagesize[0] - 30, 18, f"Страница {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
