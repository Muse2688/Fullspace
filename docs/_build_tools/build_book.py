"""
Fullspace 教学文档 —— 渲染引擎
内容只写一遍（content_doc.py 中的 IR），由 render_md / render_pdf 双向输出。
图灵图书风格：封面页、章首页、页眉页脚、代码清单编号、提示框、斑马表格、PDF 书签。
"""
from __future__ import annotations

import os
import re
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Preformatted,
    Table, TableStyle, KeepTogether, PageBreak, NextPageTemplate, Flowable,
    HRFlowable, CondPageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents
from xml.sax.saxutils import escape as _xml_escape

# ───────────────────────── 字体注册 ─────────────────────────
def _label_no(num: str) -> str:
    """“第 4 章”→“4”，“附录 A”→“A”，用于清单/表格编号。"""
    m = re.search(r"\d+", num)
    if m:
        return m.group()
    m = re.search(r"[A-Za-z]+", num)
    return m.group() if m else num


def register_fonts() -> None:
    F = r"C:\Windows\Fonts"
    pdfmetrics.registerFont(TTFont("YaHei", os.path.join(F, "msyh.ttc")))
    pdfmetrics.registerFont(TTFont("YaHei-Bold", os.path.join(F, "msyhbd.ttc")))
    pdfmetrics.registerFont(TTFont("Hei", os.path.join(F, "simhei.ttf")))
    pdfmetrics.registerFont(TTFont("Consolas", os.path.join(F, "consola.ttf")))
    # NSimSun：simsun.ttc 的第二个 face，等宽且含中文，适合代码块
    try:
        pdfmetrics.registerFont(TTFont("NSimSun", os.path.join(F, "simsun.ttc"), subfontIndex=1))
    except Exception:
        pdfmetrics.registerFont(TTFont("NSimSun", os.path.join(F, "simsun.ttc")))
    pdfmetrics.registerFontFamily(
        "YaHei", normal="YaHei", bold="YaHei-Bold",
        italic="YaHei", boldItalic="YaHei-Bold",
    )
    pdfmetrics.registerFontFamily(
        "NSimSun", normal="NSimSun", bold="NSimSun",
        italic="NSimSun", boldItalic="NSimSun",
    )

# ───────────────────────── 调色板 ─────────────────────────
C_INK      = colors.HexColor("#1f2933")   # 正文墨色
C_MUTED    = colors.HexColor("#5b6770")   # 次要文字
C_NAVY     = colors.HexColor("#1a3a6c")   # 主色（深蓝）
C_NAVY_LT  = colors.HexColor("#2f5fa6")
C_RULE     = colors.HexColor("#c9d2dd")   # 细线
C_CODE_BG  = colors.HexColor("#f4f6fa")   # 代码块底
C_CODE_BAR = colors.HexColor("#1a3a6c")   # 代码块左竖线
C_TBL_HEAD = colors.HexColor("#1a3a6c")
C_TBL_ZEB  = colors.HexColor("#eef3fa")

CALLOUT = {
    "tip":       (colors.HexColor("#eafaf1"), colors.HexColor("#1e8449"), "提示"),
    "note":      (colors.HexColor("#fef9e7"), colors.HexColor("#b9770e"), "说明"),
    "principle": (colors.HexColor("#eaf2fb"), colors.HexColor("#1a3a6c"), "原理"),
    "warning":   (colors.HexColor("#fdedec"), colors.HexColor("#b03a2e"), "注意"),
    "key":       (colors.HexColor("#f5eef8"), colors.HexColor("#6c3483"), "要点"),
}

# ───────────────────────── 段落样式 ─────────────────────────
def make_styles() -> dict:
    s = {}
    s["body"] = ParagraphStyle("body", fontName="YaHei", fontSize=10.5, leading=17,
                               textColor=C_INK, firstLineIndent=21, alignment=TA_JUSTIFY,
                               spaceAfter=4, wordWrap="CJK")
    s["body_noindent"] = ParagraphStyle("body_noindent", parent=s["body"], firstLineIndent=0)
    s["lead"] = ParagraphStyle("lead", parent=s["body"], fontSize=11, leading=19,
                               textColor=C_MUTED, firstLineIndent=0, spaceAfter=6)
    s["h1"] = ParagraphStyle("h1", fontName="Hei", fontSize=11, leading=16,
                             textColor=C_NAVY, spaceBefore=2, spaceAfter=4)
    s["chap_num"] = ParagraphStyle("chap_num", fontName="Hei", fontSize=42, leading=46,
                                   textColor=C_NAVY_LT, spaceAfter=2)
    s["chap_title"] = ParagraphStyle("chap_title", fontName="Hei", fontSize=24, leading=30,
                                     textColor=C_INK, spaceAfter=10)
    s["h2"] = ParagraphStyle("h2", fontName="YaHei-Bold", fontSize=14, leading=20,
                             textColor=C_NAVY, spaceBefore=16, spaceAfter=6)
    s["h3"] = ParagraphStyle("h3", fontName="YaHei-Bold", fontSize=11.5, leading=17,
                             textColor=C_INK, spaceBefore=10, spaceAfter=3)
    s["code"] = ParagraphStyle("code", fontName="NSimSun", fontSize=8.8, leading=12.6,
                               textColor=colors.HexColor("#22303c"))
    s["cap"] = ParagraphStyle("cap", fontName="YaHei", fontSize=9, leading=13,
                              textColor=C_MUTED, spaceBefore=2, spaceAfter=8)
    s["bullet"] = ParagraphStyle("bullet", parent=s["body"], firstLineIndent=0,
                                 leftIndent=18, bulletIndent=4, spaceAfter=2)
    s["callout_title"] = ParagraphStyle("callout_title", fontName="YaHei-Bold", fontSize=10,
                                        leading=14, textColor=C_INK, spaceAfter=2)
    s["callout_body"] = ParagraphStyle("callout_body", fontName="YaHei", fontSize=10, leading=15.5,
                                       textColor=C_INK, firstLineIndent=0, spaceAfter=0,
                                       wordWrap="CJK")
    s["tbl"] = ParagraphStyle("tbl", fontName="YaHei", fontSize=9.3, leading=13,
                              wordWrap="CJK")
    s["tbl_head"] = ParagraphStyle("tbl_head", fontName="YaHei-Bold", fontSize=9.5,
                                   leading=13, textColor=colors.white)
    s["toc_l1"] = ParagraphStyle("toc_l1", fontName="YaHei-Bold", fontSize=11, leading=20,
                                 textColor=C_INK, spaceBefore=4)
    s["toc_l2"] = ParagraphStyle("toc_l2", fontName="YaHei", fontSize=10, leading=17,
                                 textColor=C_MUTED, leftIndent=16)
    return s

# ───────────────────────── 自定义 Flowable ─────────────────────────
class SetChapter(Flowable):
    """零宽 flowable：渲染前把当前章名写入文档状态，供页眉使用。"""
    def __init__(self, title: str):
        super().__init__(); self.title = title; self.width = 0; self.height = 0
    def draw(self): pass

class ChapterMarker(Flowable):
    """通知 doc 当前章号/章名，用于页眉与目录书签。"""
    def __init__(self, key: str, title: str, level: int = 0):
        super().__init__(); self.key = key; self.title = title
        self.level = level; self.width = 0; self.height = 0
    def draw(self): pass

# ───────────────────────── 页面装饰（页眉页脚） ─────────────────────────
class BookState:
    chapter_title = "前言"
    book_title = "Fullspace 实战"

def make_page_decorators(state: BookState, styles: dict):
    def _on_cover(canvas, doc):
        canvas.saveState()
        # 封面顶部装饰色带
        canvas.setFillColor(C_NAVY)
        canvas.rect(0, doc.pagesize[1] - 12 * mm, doc.pagesize[0], 12 * mm, stroke=0, fill=1)
        canvas.restoreState()

    def _on_body(canvas, doc):
        canvas.saveState()
        pw, ph = doc.pagesize
        lm, rm, tm, bm = doc.leftMargin, doc.rightMargin, doc.topMargin, doc.bottomMargin
        # 页眉
        canvas.setFont("YaHei", 8.5)
        canvas.setFillColor(C_MUTED)
        y_h = ph - tm + 8 * mm
        # 左：书名；右：章名（实体书偶数页/奇数页分别放，这里左右同时给出更清晰）
        canvas.drawString(lm, y_h, state.book_title)
        canvas.drawRightString(pw - rm, y_h, state.chapter_title)
        canvas.setStrokeColor(C_RULE); canvas.setLineWidth(0.5)
        canvas.line(lm, y_h - 2 * mm, pw - rm, y_h - 2 * mm)
        # 页脚页码
        canvas.setFont("YaHei", 9)
        canvas.setFillColor(C_MUTED)
        canvas.drawCentredString(pw / 2, bm - 8 * mm, f"— {doc.page} —")
        canvas.restoreState()

    return _on_cover, _on_body

# ───────────────────────── 文档构建器 ─────────────────────────
class FullspaceDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.styles = make_styles()
        self.state = BookState()
        self._toc = TableOfContents()
        self._toc.dotsMinLevel = 0
        cover_fn, body_fn = make_page_decorators(self.state, self.styles)
        pw, ph = self.pagesize
        lm = self.leftMargin; rm = self.rightMargin
        tm = self.topMargin; bm = self.bottomMargin
        body_frame = Frame(lm, bm, pw - lm - rm, ph - tm - bm, id="body",
                           leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        cover_frame = Frame(lm, bm, pw - lm - rm, ph - tm - bm, id="cover",
                            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_fn),
            PageTemplate(id="body", frames=[body_frame], onPage=body_fn),
        ])

    def afterFlowable(self, flowable):
        """收集目录条目 + PDF 书签。"""
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            txt = flowable.getPlainText()
            if style == "h2":
                self.notify("TOCEntry", (1, txt, self.page))
                key = f"h2_{self.page}_{abs(hash(txt)) % 10**6}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(txt, key, level=0, closed=False)
            elif style == "h3":
                self.notify("TOCEntry", (2, txt, self.page))
                key = f"h3_{self.page}_{abs(hash(txt)) % 10**6}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(txt, key, level=1, closed=True)
        if isinstance(flowable, ChapterMarker):
            self.state.chapter_title = flowable.title
            key = f"chap_{flowable.key}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.title, key, level=0, closed=False)

# ───────────────────────── 区块 → Flowable ─────────────────────────
def _code_flowable(payload, styles, chap_no, counter):
    counter["code"] += 1
    # 原样传入：Preformatted 保留字面 < > & 且不解析实体；
    # 代码里的 < 均后跟空格（如 < self.nlist），不会被当成 XML 标签。
    src = payload["src"].rstrip("\n")
    inner = Preformatted(src, styles["code"])
    bar_w = 2.4
    cell = Table([[inner]], colWidths=[None])
    cell.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_CODE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), bar_w, C_CODE_BAR),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    caption = payload.get("caption")
    label = f"清单 {_label_no(chap_no)}-{counter['code']}" + (f"　{caption}" if caption else "")
    cap = Paragraph(label, styles["cap"])
    return KeepTogether([Spacer(1, 4), cell, Spacer(1, 1), cap])

def _callout_flowable(payload, styles):
    kind = payload.get("kind", "note")
    bg, bar, default_label = CALLOUT.get(kind, CALLOUT["note"])
    title = payload.get("title", default_label)
    body = payload["body"]
    inner = [
        Paragraph(f"{default_label}｜{title}" if title == default_label else title, styles["callout_title"]),
        Paragraph(body, styles["callout_body"]),
    ]
    cell = Table([[inner]], colWidths=[None])
    cell.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.6, bar),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return KeepTogether([Spacer(1, 4), cell, Spacer(1, 6)])

def _table_flowable(payload, styles, chap_no, counter, content_width):
    counter["tbl"] += 1
    headers = payload["headers"]
    rows = payload["rows"]
    body_style = styles["tbl"]; head_style = styles["tbl_head"]
    data = [[Paragraph(str(h), head_style) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), body_style) for c in r])
    ncol = len(headers)
    col_w = content_width / ncol
    t = Table(data, colWidths=[col_w] * ncol, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_TBL_HEAD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_TBL_ZEB]),
        ("GRID", (0, 0), (-1, -1), 0.4, C_RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    caption = payload.get("caption")
    label = f"表 {_label_no(chap_no)}-{counter['tbl']}" + (f"　{caption}" if caption else "")
    cap = Paragraph(label, styles["cap"])
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 1), cap])

def _bullets_flowable(payload, styles):
    items = payload if isinstance(payload, list) else payload["items"]
    flow = []
    for it in items:
        flow.append(Paragraph(it, styles["bullet"], bulletText="•"))
    return flow

def block_to_flowables(block, styles, chap_no, counter, content_width):
    """单个 IR block → flowable 列表。"""
    t = block[0]; p = block[1] if len(block) > 1 else None
    if t == "p":
        return [Paragraph(p, styles["body"])]
    if t == "p_noindent":
        return [Paragraph(p, styles["body_noindent"])]
    if t == "lead":
        return [Paragraph(p, styles["lead"])]
    if t == "h2":
        # 孤行标题治理：剩余空间不足“标题+几行正文”则提前分页，让标题落到下一页顶部
        return [CondPageBreak(60), Paragraph(p, styles["h2"])]
    if t == "h3":
        return [CondPageBreak(44), Paragraph(p, styles["h3"])]
    if t == "spacer":
        return [Spacer(1, float(p or 6))]
    if t == "code":
        return [_code_flowable(p, styles, chap_no, counter)]
    if t == "callout":
        return [_callout_flowable(p, styles)]
    if t == "table":
        return [_table_flowable(p, styles, chap_no, counter, content_width)]
    if t in ("bullets", "ol"):
        return _bullets_flowable(p, styles)
    if t == "hr":
        return [Spacer(1, 4), HRFlowable(width="100%", thickness=0.5, color=C_RULE), Spacer(1, 4)]
    return []

# ───────────────────────── 章首页 ─────────────────────────
def chapter_open_flowables(chap_no_str, title, lead, styles):
    head = [
        NextPageTemplate("body"),
        PageBreak(),
        ChapterMarker(chap_no_str, title, level=0),
        Spacer(1, 26 * mm),
        Paragraph(chap_no_str, styles["chap_num"]),
        HRFlowable(width=46 * mm, thickness=2, color=C_NAVY, spaceBefore=2, spaceAfter=10),
        Paragraph(title, styles["chap_title"]),
        Spacer(1, 6),
    ]
    if lead:
        head.append(Paragraph(lead, styles["lead"]))
    head.append(HRFlowable(width="100%", thickness=0.5, color=C_RULE, spaceBefore=8, spaceAfter=2))
    head.append(Spacer(1, 6))
    return head

def chapter_close_flowables(styles):
    return [
        Spacer(1, 10),
        HRFlowable(width="40%", thickness=0.6, color=C_NAVY, hAlign="LEFT", spaceBefore=6),
        Spacer(1, 2),
    ]

# ───────────────────────── PDF 渲染入口 ─────────────────────────
def render_pdf(doc_ir: dict, out_path: str) -> str:
    register_fonts()
    PAGE = (170 * mm, 230 * mm)
    doc = FullspaceDocTemplate(
        out_path, pagesize=PAGE,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=24 * mm, bottomMargin=22 * mm,
        title=doc_ir["title"], author=doc_ir.get("author", "Fullspace"),
        subject=doc_ir.get("subtitle", ""),
    )
    doc.state.book_title = doc_ir["title"]
    styles = doc.styles
    content_width = PAGE[0] - 44 * mm

    story = []
    # 封面
    story += _cover_flowables(doc_ir, styles, PAGE)
    # 版权 / 前言
    story += _front_matter(doc_ir, styles, doc._toc, content_width)
    # 目录
    story += _toc_page(doc_ir, styles, doc._toc)
    # 正文
    for ch in doc_ir["chapters"]:
        no = ch["num"]
        story += chapter_open_flowables(no, ch["title"], ch.get("lead", ""), styles)
        counter = {"code": 0, "tbl": 0}
        for b in ch["blocks"]:
            for fl in block_to_flowables(b, styles, no, counter, content_width):
                story.append(fl)
        story += chapter_close_flowables(styles)
    # 附录
    for ap in doc_ir.get("appendices", []):
        story += chapter_open_flowables(ap["num"], ap["title"], ap.get("lead", ""), styles)
        counter = {"code": 0, "tbl": 0}
        for b in ap["blocks"]:
            for fl in block_to_flowables(b, styles, ap["num"], counter, content_width):
                story.append(fl)
        story += chapter_close_flowables(styles)

    doc.multiBuild(story)
    return out_path

def _cover_flowables(doc_ir, styles, PAGE):
    pw, ph = PAGE
    s_book = ParagraphStyle("s_book", fontName="Hei", fontSize=40, leading=50,
                            textColor=C_INK, alignment=TA_CENTER)
    s_book2 = ParagraphStyle("s_book2", fontName="YaHei-Bold", fontSize=26, leading=36,
                             textColor=C_NAVY, alignment=TA_CENTER)
    s_author = ParagraphStyle("s_author", fontName="YaHei-Bold", fontSize=17, leading=26,
                              textColor=C_INK, alignment=TA_CENTER)
    s_sub = ParagraphStyle("s_sub", fontName="YaHei", fontSize=13.5, leading=22,
                           textColor=C_MUTED, alignment=TA_CENTER)
    s_meta = ParagraphStyle("s_meta", fontName="YaHei", fontSize=10, leading=16,
                            textColor=C_MUTED, alignment=TA_CENTER)
    cover = [
        NextPageTemplate("cover"),
        Spacer(1, 50 * mm),
        Paragraph(doc_ir["title"], s_book),
        Spacer(1, 4 * mm),
        Paragraph(doc_ir.get("title_en", ""), s_book2),
        Spacer(1, 20 * mm),
        HRFlowable(width=60 * mm, thickness=1.2, color=C_NAVY, hAlign="CENTER"),
        Spacer(1, 10 * mm),
        Paragraph(doc_ir.get("author_line", ""), s_author),
        Spacer(1, 16 * mm),
        Paragraph(doc_ir.get("subtitle", ""), s_sub),
        Spacer(1, 6 * mm),
        Paragraph(doc_ir.get("tagline", ""), s_sub),
        Spacer(1, 58 * mm),
        Paragraph(doc_ir.get("edition_line", ""), s_meta),
        PageBreak(),
    ]
    return cover

def _front_matter(doc_ir, styles, toc, content_width):
    s = []
    s.append(NextPageTemplate("body"))
    s.append(ChapterMarker("FM", "前言"))
    s.append(Paragraph("前　言", styles["chap_title"]))
    s.append(HRFlowable(width="100%", thickness=0.5, color=C_RULE, spaceAfter=8))
    for b in doc_ir.get("preface", []):
        for fl in block_to_flowables(b, styles, "前言", {"code": 0, "tbl": 0}, content_width):
            s.append(fl)
    return s

def _toc_page(doc_ir, styles, toc):
    toc.levelStyles = [styles["toc_l1"], styles["toc_l2"]]
    return [
        PageBreak(),
        ChapterMarker("TOC", "目录"),
        Paragraph("目　录", styles["chap_title"]),
        HRFlowable(width="100%", thickness=0.5, color=C_RULE, spaceAfter=10),
        toc,
    ]

# ───────────────────────── Markdown 渲染器 ─────────────────────────
_MD_EMOJI = {"tip": "💡", "note": "📝", "principle": "🧭", "warning": "⚠️", "key": "🔑"}


def _md_inline(s: str) -> str:
    """把 PDF 用的内联标记转成 Markdown：&gt;→>、<b>→**、<i>→*。"""
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return (s.replace("<b>", "**").replace("</b>", "**")
             .replace("<i>", "*").replace("</i>", "*"))

def _md_blocks(blocks, chap_no):
    out, cc = [], {"code": 0, "tbl": 0}
    for b in blocks:
        t = b[0]
        p = b[1] if len(b) > 1 else None
        if t == "h2":
            out.append(f"\n## {p}\n")
        elif t == "h3":
            out.append(f"\n### {p}\n")
        elif t in ("p", "p_noindent"):
            out.append(f"\n{_md_inline(p)}\n")
        elif t == "lead":
            out.append(f"\n> {_md_inline(p)}\n")
        elif t == "spacer":
            out.append("")
        elif t == "hr":
            out.append("\n---\n")
        elif t == "code":
            cc["code"] += 1
            cap = p.get("caption", "")
            label = f"清单 {_label_no(chap_no)}-{cc['code']}" + (f"　{cap}" if cap else "")
            lang = p.get("lang", "")
            out.append(f"\n**{label}**\n```{lang}\n{p['src'].rstrip()}\n```\n")
        elif t == "callout":
            kind = p.get("kind", "note")
            title = p.get("title", "")
            emoji = _MD_EMOJI.get(kind, "📝")
            out.append(f"\n> **{emoji} {title}**\n>\n> {_md_inline(p['body'])}\n")
        elif t == "table":
            cc["tbl"] += 1
            cap = p.get("caption", "")
            label = f"表 {_label_no(chap_no)}-{cc['tbl']}" + (f"　{cap}" if cap else "")
            hdr = "| " + " | ".join(str(h) for h in p["headers"]) + " |"
            sep = "|" + "|".join(["---"] * len(p["headers"])) + "|"
            rows = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in p["rows"])
            out.append(f"\n**{label}**\n\n{hdr}\n{sep}\n{rows}\n")
        elif t in ("bullets", "ol"):
            items = p if isinstance(p, list) else p["items"]
            if t == "bullets":
                out.append("\n" + "\n".join(f"- {_md_inline(it)}" for it in items) + "\n")
            else:
                out.append("\n" + "\n".join(f"{i + 1}. {_md_inline(it)}" for i, it in enumerate(items)) + "\n")
    return "\n".join(out)


def render_md(doc_ir: dict, out_path: str) -> str:
    L = []
    L.append(f"# {doc_ir['title']}")
    if doc_ir.get("title_en"):
        L.append(f"## {doc_ir['title_en']}")
    L.append("")
    if doc_ir.get("subtitle"):
        L.append(f"**{doc_ir['subtitle']}**")
    if doc_ir.get("tagline"):
        L.append(f"*{doc_ir['tagline']}*")
    L.append("")
    if doc_ir.get("author_line"):
        L.append(doc_ir["author_line"])
    if doc_ir.get("edition_line"):
        L.append(doc_ir["edition_line"])
    L.append("\n\n---\n")
    # 前言
    L.append("# 前　言")
    L.append(_md_blocks(doc_ir.get("preface", []), "前言"))
    L.append("\n\n---\n")
    # 目录
    L.append("# 目　录")
    for ch in doc_ir["chapters"]:
        L.append(f"- **{ch['num']}　{ch['title']}**")
    for ap in doc_ir.get("appendices", []):
        L.append(f"- **{ap['num']}　{ap['title']}**")
    L.append("\n\n---\n")
    # 正文
    for ch in doc_ir["chapters"]:
        L.append(f"# {ch['num']}　{ch['title']}")
        if ch.get("lead"):
            L.append(f"\n> {ch['lead']}\n")
        L.append(_md_blocks(ch["blocks"], ch["num"]))
        L.append("\n\n---\n")
    for ap in doc_ir.get("appendices", []):
        L.append(f"# {ap['num']}　{ap['title']}")
        if ap.get("lead"):
            L.append(f"\n> {ap['lead']}\n")
        L.append(_md_blocks(ap["blocks"], ap["num"]))
        L.append("\n\n---\n")
    text = "\n".join(L)
    # 压缩多余空行
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path

# ───────────────────────── 主入口 ─────────────────────────
def main():
    import os
    from content_doc import DOC
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.dirname(here)  # docs/
    md_path = os.path.join(out_dir, "Fullspace实战-教学文档.md")
    pdf_path = os.path.join(out_dir, "Fullspace实战-教学文档.pdf")
    render_md(DOC, md_path)
    print("MD  ->", md_path)
    render_pdf(DOC, pdf_path)
    print("PDF ->", pdf_path)


if __name__ == "__main__":
    main()
