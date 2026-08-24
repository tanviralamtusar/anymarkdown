"""Render Markdown text into a .docx document.

Deliberately self-contained (python-docx only, no pandoc binary) and scoped to
the Markdown MarkItDown itself emits: ATX/setext headings, paragraphs, fenced
code, blockquotes, nested ordered/unordered lists, horizontal rules, GFM pipe
tables, and inline bold/italic/strikethrough/code/links/images.
"""

import io
import re
from typing import List, Optional

import docx
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)\s*$")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT_H1_RE = re.compile(r"^ {0,3}=+\s*$")
_SETEXT_H2_RE = re.compile(r"^ {0,3}-{2,}\s*$")
_HR_RE = re.compile(r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_QUOTE_RE = re.compile(r"^ {0,3}>\s?(.*)$")
_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")

# Inline spans, most specific delimiters first so ``**`` wins over ``*``. The
# ``(?<!\\)`` guards keep backslash-escaped delimiters from opening or closing a
# span -- they are unescaped later, as literal text, by ``_ESCAPED_RE``.
_INLINE_RE = re.compile(
    r"(?<!\\)(?P<code>`+)(?P<code_text>.+?)(?P=code)"
    r"|(?<!\\)!\[(?P<img_alt>[^\]]*)\]\((?P<img_href>[^)\s]*)[^)]*\)"
    r"|(?<!\\)\[(?P<link_text>[^\]]*)\]\((?P<link_href>[^)\s]*)[^)]*\)"
    r"|(?<!\\)(?P<strong_em>\*\*\*|___)(?P<strong_em_text>.+?)(?<!\\)(?P=strong_em)"
    r"|(?<!\\)(?P<strong>\*\*|__)(?P<strong_text>.+?)(?<!\\)(?P=strong)"
    r"|(?<!\\)(?P<strike>~~)(?P<strike_text>.+?)(?<!\\)(?P=strike)"
    r"|(?<!\\)(?P<em>[*_])(?P<em_text>.+?)(?<!\\)(?P=em)",
    re.DOTALL,
)

_ESCAPED_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")

CODE_STYLE = "MarkItDown Code"
INLINE_CODE_STYLE = "MarkItDown Inline Code"


class _Renderer:
    def __init__(self) -> None:
        self.document = docx.Document()
        self._ensure_styles()

    # ------------------------------------------------------------------ styles

    def _ensure_styles(self) -> None:
        styles = self.document.styles

        if CODE_STYLE not in styles:
            style = styles.add_style(CODE_STYLE, WD_STYLE_TYPE.PARAGRAPH)
            style.base_style = styles["Normal"]
            style.font.name = "Consolas"
            style.font.size = Pt(9)
            fmt = style.paragraph_format
            fmt.space_before = Pt(6)
            fmt.space_after = Pt(6)
            fmt.left_indent = Pt(18)
            fmt.line_spacing = 1.0

        if INLINE_CODE_STYLE not in styles:
            style = styles.add_style(INLINE_CODE_STYLE, WD_STYLE_TYPE.CHARACTER)
            style.font.name = "Consolas"
            style.font.size = Pt(9)

    # -------------------------------------------------------------- inline runs

    def _add_inline(self, paragraph, text: str, **base) -> None:
        """Append `text` to `paragraph`, honouring inline Markdown markup."""
        pos = 0
        for match in _INLINE_RE.finditer(text):
            if match.start() > pos:
                self._add_run(paragraph, text[pos : match.start()], **base)

            if match.group("code"):
                run = self._add_run(paragraph, match.group("code_text"), literal=True, **base)
                run.style = self.document.styles[INLINE_CODE_STYLE]
            elif match.group("img_href") is not None:
                alt = match.group("img_alt") or "image"
                self._add_run(paragraph, f"[{alt}]", **{**base, "italic": True})
            elif match.group("link_text") is not None:
                href = match.group("link_href")
                self._add_hyperlink(paragraph, match.group("link_text") or href, href, **base)
            elif match.group("strong_em"):
                inner = {**base, "bold": True, "italic": True}
                self._add_inline(paragraph, match.group("strong_em_text"), **inner)
            elif match.group("strong"):
                self._add_inline(paragraph, match.group("strong_text"), **{**base, "bold": True})
            elif match.group("strike"):
                self._add_inline(paragraph, match.group("strike_text"), **{**base, "strike": True})
            elif match.group("em"):
                self._add_inline(paragraph, match.group("em_text"), **{**base, "italic": True})

            pos = match.end()

        if pos < len(text):
            self._add_run(paragraph, text[pos:], **base)

    def _add_run(
        self,
        paragraph,
        text: str,
        bold: bool = False,
        italic: bool = False,
        strike: bool = False,
        literal: bool = False,
    ):
        if not literal:
            text = _ESCAPED_RE.sub(r"\1", text)
        run = paragraph.add_run(text)
        if bold:
            run.bold = True
        if italic:
            run.italic = True
        if strike:
            run.font.strike = True
        return run

    def _add_hyperlink(self, paragraph, text: str, href: str, **base) -> None:
        if not href:
            self._add_inline(paragraph, text, **base)
            return

        r_id = paragraph.part.relate_to(href, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), r_id)

        run = self._add_run(paragraph, text, **base)
        run.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
        run.font.underline = True
        hyperlink.append(run._element)
        paragraph._p.append(hyperlink)

    # ------------------------------------------------------------ block helpers

    def add_horizontal_rule(self) -> None:
        paragraph = self.document.add_paragraph()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "auto")
        borders.append(bottom)
        paragraph._p.get_or_add_pPr().append(borders)

    def add_heading(self, level: int, text: str) -> None:
        paragraph = self.document.add_paragraph(style=f"Heading {level}")
        self._add_inline(paragraph, text)

    def add_paragraph(self, text: str, style: Optional[str] = None) -> None:
        paragraph = self.document.add_paragraph(style=style)
        self._add_inline(paragraph, text)

    def add_quote(self, text: str) -> None:
        style = "Quote" if "Quote" in self.document.styles else None
        paragraph = self.document.add_paragraph(style=style)
        if style is None:
            paragraph.paragraph_format.left_indent = Pt(24)
        self._add_inline(paragraph, text)

    def add_code_block(self, lines: List[str]) -> None:
        # One paragraph with line breaks keeps the block visually cohesive.
        paragraph = self.document.add_paragraph(style=CODE_STYLE)
        for index, line in enumerate(lines):
            if index:
                paragraph.add_run().add_break()
            paragraph.add_run(line)

    def add_table(
        self, header: List[str], aligns: List[Optional[str]], rows: List[List[str]]
    ) -> None:
        columns = max([len(header)] + [len(row) for row in rows])
        table = self.document.add_table(rows=1, cols=columns)
        table.style = "Table Grid"

        for index, cell in enumerate(table.rows[0].cells):
            paragraph = cell.paragraphs[0]
            if index < len(header):
                self._add_inline(paragraph, header[index], bold=True)
            _align(paragraph, aligns, index)

        for row in rows:
            cells = table.add_row().cells
            for index, cell in enumerate(cells):
                paragraph = cell.paragraphs[0]
                if index < len(row):
                    self._add_inline(paragraph, row[index])
                _align(paragraph, aligns, index)


def _align(paragraph, aligns: List[Optional[str]], index: int) -> None:
    align = aligns[index] if index < len(aligns) else None
    if align == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "right":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _split_table_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]

    cells: List[str] = []
    current = ""
    escaped = False
    for char in line:
        if escaped:
            current += char
            escaped = False
        elif char == "\\":
            current += char
            escaped = True
        elif char == "|":
            cells.append(current.strip())
            current = ""
        else:
            current += char
    cells.append(current.strip())
    return cells


def _table_alignments(separator: str) -> List[Optional[str]]:
    aligns: List[Optional[str]] = []
    for cell in _split_table_row(separator):
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        else:
            aligns.append(None)
    return aligns


def _list_style(ordered: bool, depth: int) -> str:
    """Map a nesting depth onto Word's built-in list styles (three levels)."""
    base = "List Number" if ordered else "List Bullet"
    level = min(depth, 2)
    return base if level == 0 else f"{base} {level + 1}"


def _list_depth(stack: List[int], indent: int) -> int:
    """Track indent widths so both 2- and 4-space nesting map onto real levels."""
    while stack and stack[-1] > indent:
        stack.pop()
    if not stack or stack[-1] < indent:
        stack.append(indent)
    return len(stack) - 1


def markdown_to_docx_bytes(markdown: str) -> bytes:
    """Convert Markdown text to the bytes of a .docx file."""
    renderer = _Renderer()

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    total = len(lines)
    list_stack: List[int] = []

    while index < total:
        line = lines[index]

        if not line.strip():
            list_stack.clear()
            index += 1
            continue

        # Fenced code block
        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            list_stack.clear()
            index += 1
            block: List[str] = []
            while index < total:
                closing = _FENCE_RE.match(lines[index])
                if (
                    closing
                    and closing.group(1)[0] == marker[0]
                    and len(closing.group(1)) >= len(marker)
                    and not closing.group(2)
                ):
                    index += 1
                    break
                block.append(lines[index])
                index += 1
            renderer.add_code_block(block)
            continue

        # Horizontal rule, checked before lists so `---` is not read as a bullet
        if _HR_RE.match(line):
            renderer.add_horizontal_rule()
            list_stack.clear()
            index += 1
            continue

        # ATX heading
        heading = _HEADING_RE.match(line)
        if heading:
            renderer.add_heading(len(heading.group(1)), heading.group(2))
            list_stack.clear()
            index += 1
            continue

        # Pipe table: a header row followed by a delimiter row
        if "|" in line and index + 1 < total and _TABLE_SEP_RE.match(lines[index + 1]):
            header = _split_table_row(line)
            aligns = _table_alignments(lines[index + 1])
            index += 2
            rows: List[List[str]] = []
            while index < total and lines[index].strip() and "|" in lines[index]:
                rows.append(_split_table_row(lines[index]))
                index += 1
            renderer.add_table(header, aligns, rows)
            list_stack.clear()
            continue

        # Blockquote: consecutive `>` lines become one indented paragraph
        quote = _QUOTE_RE.match(line)
        if quote:
            chunk = [quote.group(1)]
            index += 1
            while index < total:
                following = _QUOTE_RE.match(lines[index])
                if not following:
                    break
                chunk.append(following.group(1))
                index += 1
            renderer.add_quote(" ".join(part for part in chunk if part.strip()))
            list_stack.clear()
            continue

        # List item
        unordered = _UL_RE.match(line)
        ordered = _OL_RE.match(line)
        if unordered or ordered:
            match = unordered or ordered
            indent = len(match.group(1).expandtabs(4))
            depth = _list_depth(list_stack, indent)
            text = match.group(2) if unordered else match.group(3)
            renderer.add_paragraph(text, style=_list_style(bool(ordered), depth))
            index += 1
            continue

        list_stack.clear()

        # Paragraph: gather until a blank line or the start of another block
        chunk = [line.strip()]
        index += 1
        while index < total:
            following = lines[index]
            if not following.strip():
                break
            if (
                _HEADING_RE.match(following)
                or _HR_RE.match(following)
                or _FENCE_RE.match(following)
                or _QUOTE_RE.match(following)
                or _UL_RE.match(following)
                or _OL_RE.match(following)
                or _SETEXT_H1_RE.match(following)
                or _SETEXT_H2_RE.match(following)
            ):
                break
            chunk.append(following.strip())
            index += 1

        # Setext heading: the paragraph was underlined with `=` or `-`
        if index < total and len(chunk) == 1:
            if _SETEXT_H1_RE.match(lines[index]):
                renderer.add_heading(1, chunk[0])
                index += 1
                continue
            if _SETEXT_H2_RE.match(lines[index]):
                renderer.add_heading(2, chunk[0])
                index += 1
                continue

        renderer.add_paragraph(" ".join(chunk))

    buffer = io.BytesIO()
    renderer.document.save(buffer)
    return buffer.getvalue()
