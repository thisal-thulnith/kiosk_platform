# ruff: noqa: E501
"""Turn one of our Markdown guides into a clean PDF (headings, paragraphs, lists, tables, code).

uv run --with reportlab python tools/docs/md_to_pdf.py docs/ANDROID_APP_GUIDE.md docs/Android-App-Developer-Guide.pdf
"""

import re
import sys
from datetime import date
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#1c2b33")
MUTED = colors.HexColor("#65676b")
ACCENT = colors.HexColor("#0866ff")
LINE = colors.HexColor("#e4e6eb")
SUBTLE = colors.HexColor("#f7f8fa")

BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK, spaceAfter=5)
S = {
    "title": ParagraphStyle(
        "title", parent=BASE, fontName="Helvetica-Bold", fontSize=24, leading=29, spaceAfter=8
    ),
    "h2": ParagraphStyle(
        "h2",
        parent=BASE,
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        spaceBefore=6,
        spaceAfter=8,
        textColor=INK,
    ),
    "h3": ParagraphStyle(
        "h3",
        parent=BASE,
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        spaceBefore=8,
        spaceAfter=4,
        textColor=ACCENT,
    ),
    "p": BASE,
    "li": ParagraphStyle("li", parent=BASE, leftIndent=12, bulletIndent=2, spaceAfter=2.5),
    "li2": ParagraphStyle("li2", parent=BASE, leftIndent=24, bulletIndent=14, spaceAfter=2.5),
    "cell": ParagraphStyle("cell", parent=BASE, fontSize=8.3, leading=11, spaceAfter=0),
    "head": ParagraphStyle(
        "head", parent=BASE, fontSize=8.3, leading=11, spaceAfter=0, fontName="Helvetica-Bold"
    ),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=9.8, textColor=INK),
}


def inline(text: str) -> str:
    """Markdown inline (**bold**, `code`, links) -> reportlab mini-HTML."""
    codes: list[str] = []

    def keep(m: re.Match[str]) -> str:
        codes.append(f'<font face="Courier" color="#0b4fbf">{escape(m.group(1))}</font>')
        return f"\x00{len(codes) - 1}\x00"

    s = escape(re.sub(r"`([^`]+)`", keep, text), quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    s = re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], s)
    return s.replace("✓", "Yes").replace("–", "-")


# Courier has no box-drawing glyphs: draw the little flow charts with plain characters.
ASCII = str.maketrans({"─": "-", "►": ">", "│": "|", "▼": "v", "…": "..."})


def table(rows: list[list[str]], width: float) -> Table:
    n = len(rows[0])
    lens = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(n)]
    weights = [min(max(x, 10), 60) for x in lens]
    total = sum(weights)
    widths = [width * w / total for w in weights]
    data = [
        [Paragraph(inline(c), S["head" if r == 0 else "cell"]) for c in row + [""] * (n - len(row))]
        for r, row in enumerate(rows)
    ]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SUBTLE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def build(src: Path, out: Path) -> None:
    lines = src.read_text().splitlines()
    width = A4[0] - 3.6 * cm
    story: list = []
    i = 0
    first_h2 = True
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            pre = Preformatted("\n".join(block).translate(ASCII), S["code"], maxLineLength=118)
            box = Table([[pre]], colWidths=[width])
            box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), SUBTLE),
                        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story += [box, Spacer(1, 6)]
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", lines[i].strip())[1:-1]]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append([c.replace("\\|", "|") for c in cells])
                i += 1
            story += [table(rows, width), Spacer(1, 8)]
            continue
        elif line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), S["title"]))
        elif line.startswith("## "):
            if not first_h2:
                story.append(PageBreak())
            first_h2 = False
            story.append(Paragraph(inline(line[3:]), S["h2"]))
        elif line.startswith("### "):
            nxt = []
            story.append(KeepTogether([Paragraph(inline(line[4:]), S["h3"])] + nxt))
        elif re.match(r"^\s*(- |\d+\. )", line):
            indent = len(line) - len(line.lstrip())
            m = re.match(r"^\s*(- |(\d+)\. )(.*)", line)
            assert m
            text = m.group(3)
            while (
                i + 1 < len(lines)
                and lines[i + 1].startswith(" " * (indent + 2))
                and not re.match(r"^\s*(- |\d+\. )", lines[i + 1])
            ):
                i += 1
                text += " " + lines[i].strip()
            bullet = "•" if m.group(1) == "- " else f"{m.group(2)}."
            text = text.replace("[ ] ", "")
            story.append(Paragraph(inline(text), S["li2" if indent >= 2 else "li"], bulletText=bullet))
        elif line.strip() == "---" or not line.strip():
            pass
        else:
            text = line
            while (
                i + 1 < len(lines)
                and lines[i + 1].strip()
                and not re.match(r"^(#|\||```|\s*- |\s*\d+\. |---)", lines[i + 1])
            ):
                i += 1
                text += " " + lines[i].strip()
            story.append(Paragraph(inline(text), S["p"]))
        i += 1

    title = src.read_text().splitlines()[0].lstrip("# ")

    def page(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.8 * cm, 1.1 * cm, f"{title} · {date.today():%d %b %Y}")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.1 * cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.8 * cm,
        title=title,
        author="Kiosk Platform",
    )
    doc.build(story, onFirstPage=page, onLaterPages=page)


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
