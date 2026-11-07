"""Export the eight data-access notes as individual, print-ready PDFs."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    PageBreak,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path.home() / "Desktop" / "Spring Boot 数据访问知识库"
PDF_NAMES = {
    "01": "01-配置JDBC驱动与DataSource.pdf",
    "02": "02-使用JdbcTemplate查询和更新数据.pdf",
    "03": "03-使用Druid管理连接与监控SQL.pdf",
    "04": "04-MyBatis自动配置与数据库接入.pdf",
    "05": "05-MyBatis Mapper注解与XML映射.pdf",
    "06": "06-配置Redis并使用Template读写.pdf",
    "07": "07-Lettuce与Jedis客户端切换.pdf",
    "08": "08-Servlet与MVC及Druid Filter的区别.pdf",
}


def register_fonts() -> None:
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    bold_path = Path("C:/Windows/Fonts/msyhbd.ttc")
    if not font_path.is_file() or not bold_path.is_file():
        raise FileNotFoundError("Microsoft YaHei fonts are unavailable")
    pdfmetrics.registerFont(TTFont("YaHei", str(font_path), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("YaHeiBold", str(bold_path), subfontIndex=0))
    pdfmetrics.registerFontFamily(
        "YaHei", normal="YaHei", bold="YaHeiBold", italic="YaHei", boldItalic="YaHeiBold"
    )


def make_styles() -> dict[str, ParagraphStyle]:
    common = dict(fontName="YaHei", wordWrap="CJK", allowWidows=0, allowOrphans=0)
    return {
        "kicker": ParagraphStyle(
            "Kicker", **common, fontSize=9, leading=13, textColor=colors.HexColor("#3970B2"),
            spaceAfter=10,
        ),
        "title": ParagraphStyle(
            "Title", **(common | {"fontName": "YaHeiBold"}), fontSize=20, leading=29,
            textColor=colors.HexColor("#182E49"),
            spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "H2", **(common | {"fontName": "YaHeiBold"}), fontSize=13, leading=19,
            textColor=colors.HexColor("#1B4D86"),
            spaceBefore=17, spaceAfter=8, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3", **(common | {"fontName": "YaHeiBold"}), fontSize=10.5, leading=16,
            textColor=colors.HexColor("#304B69"),
            spaceBefore=12, spaceAfter=5, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", **common, fontSize=9.7, leading=16.5, textColor=colors.HexColor("#28384B"),
            alignment=TA_LEFT, spaceAfter=8,
        ),
        "list": ParagraphStyle(
            "List", **common, fontSize=9.6, leading=16.2, textColor=colors.HexColor("#28384B"),
            leftIndent=16, firstLineIndent=-12, spaceAfter=5,
        ),
        "code": ParagraphStyle(
            "Code", fontName="Courier", fontSize=8.3, leading=11.3,
            textColor=colors.HexColor("#23364C"),
        ),
    }


def inline_markup(value: str) -> str:
    value = html.escape(value)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: f'<link href="{m.group(2)}" color="#2665A5">{m.group(1)}</link>',
        value,
    )
    value = re.sub(
        r"`([^`]+)`",
        lambda m: f'<font color="#174C7B">{m.group(1)}</font>',
        value,
    )
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return value


def code_flowable(lines: list[str], style: ParagraphStyle, width: float):
    code = "\n".join(lines).rstrip()
    max_length = max((len(line) for line in lines), default=0)
    font_size = 8.3 if max_length <= 95 else max(6.8, 8.3 * 95 / max_length)
    code_style = ParagraphStyle("CodeBlock", parent=style, fontSize=font_size, leading=font_size + 3)
    block = Preformatted(code, code_style)
    table = Table([[block]], colWidths=[width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6FA")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DBE4ED")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def parse_note(text: str, styles: dict[str, ParagraphStyle], width: float, article_number: str):
    story = []
    code_lines: list[str] | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            story.append(Paragraph(inline_markup(" ".join(paragraph_lines)), styles["body"]))
            paragraph_lines.clear()

    for raw in text.splitlines()[1:]:
        line = raw.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            if code_lines is None:
                code_lines = []
            else:
                block = code_flowable(code_lines, styles["code"], width)
                if story and isinstance(story[-1], Paragraph) and story[-1].style.name == "Body":
                    story.append(KeepTogether([story.pop(), block]))
                else:
                    story.append(block)
                story.append(Spacer(1, 9))
                code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if line.startswith("### "):
            flush_paragraph()
            if article_number == "05" and line[4:] == "XML 模式":
                story.append(PageBreak())
            story.append(Paragraph(inline_markup(line[4:]), styles["h3"]))
            continue
        if line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[3:]), styles["h2"]))
            continue
        match = re.match(r"^(\d+\.|-)\s+(.+)$", line)
        if match:
            flush_paragraph()
            marker = "•" if match.group(1) == "-" else match.group(1)
            story.append(Paragraph(f"{marker}  {inline_markup(match.group(2))}", styles["list"]))
            continue
        paragraph_lines.append(line.strip())

    flush_paragraph()
    if code_lines is not None:
        raise ValueError("Unclosed code fence")
    return story


def page_decoration(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D7E0E9"))
    canvas.setLineWidth(0.6)
    canvas.line(48, height - 37, width - 48, height - 37)
    canvas.setFont("YaHei", 8)
    canvas.setFillColor(colors.HexColor("#697B90"))
    canvas.drawString(48, height - 29, "SPRING BOOT  /  数据访问")
    canvas.line(48, 41, width - 48, 41)
    canvas.drawString(48, 28, "专题文章")
    canvas.drawRightString(width - 48, 28, f"第 {doc.page} 页")
    canvas.restoreState()


def export_one(source: Path, output: Path, styles: dict[str, ParagraphStyle]) -> None:
    text = source.read_text(encoding="utf-8")
    title = text.splitlines()[0].removeprefix("# ").strip()
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=48, leftMargin=48,
        topMargin=54, bottomMargin=59, title=title,
        author="Deep Pilot 知识库", subject="Spring Boot 数据访问知识点",
    )
    story = [
        Spacer(1, 17),
        Paragraph("SPRING BOOT · 数据访问专题", styles["kicker"]),
        Paragraph(inline_markup(title), styles["title"]),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#3F78B8")),
        Spacer(1, 8),
    ]
    story.extend(parse_note(text, styles, doc.width, source.name[:2]))
    doc.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    register_fonts()
    styles = make_styles()
    for index, pdf_name in PDF_NAMES.items():
        source = next(HERE.glob(f"{index}-*.md"))
        output = args.output_dir / pdf_name
        export_one(source, output, styles)
        print(output)


if __name__ == "__main__":
    main()
