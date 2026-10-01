"""一个很小的 .xlsx 写入器。

不依赖任何第三方库：xlsx 本身就是一个 zip 包，里面是几个 XML。
表格用内联字符串，Excel／WPS／Numbers 都能正常打开。
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def col_name(index: int) -> str:
    """0 → A，25 → Z，26 → AA。"""
    name = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = LETTERS[rem] + name
    return name


def _cell(ref: str, value, bold: bool) -> str:
    style = ' s="1"' if bold else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        value = "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(str(value))
    return (
        f'<c r="{ref}"{style} t="inlineStr"><is>'
        f'<t xml:space="preserve">{text}</t></is></c>'
    )


def _sheet_xml(headers: list[str], rows: list[list], widths: list[int] | None) -> str:
    cols = ""
    if widths:
        parts = [
            f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
            for i, w in enumerate(widths)
        ]
        cols = "<cols>" + "".join(parts) + "</cols>"

    out = [f'<row r="1">']
    for i, head in enumerate(headers):
        out.append(_cell(f"{col_name(i)}1", head, True))
    out.append("</row>")

    for r, row in enumerate(rows, start=2):
        out.append(f'<row r="{r}">')
        for i, value in enumerate(row):
            out.append(_cell(f"{col_name(i)}{r}", value, False))
        out.append("</row>")

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{cols}<sheetData>{''.join(out)}</sheetData></worksheet>"
    )


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def build_xlsx(sheets: list[tuple[str, list[str], list[list]]]) -> bytes:
    """sheets: [(表名, 表头, 数据行), ...]"""
    if not sheets:
        sheets = [("空", ["没有数据"], [])]

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(len(sheets)):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")

    sheet_tags = []
    sheet_rels = []
    for i, (name, _headers, _rows) in enumerate(sheets, start=1):
        safe = escape(name)[:31]
        sheet_tags.append(f'<sheet name="{safe}" sheetId="{i}" r:id="rId{i}"/>')
        sheet_rels.append(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
        )
    styles_id = len(sheets) + 1
    sheet_rels.append(
        f'<Relationship Id="rId{styles_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheet_tags)}</sheets></workbook>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(sheet_rels)}</Relationships>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "".join(content_types))
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", _STYLES)
        for i, (_name, headers, rows) in enumerate(sheets, start=1):
            widths = [
                min(32, max(8, max([len(str(h))] + [len(str(r[j])) for r in rows if j < len(r)] or [8]) + 4))
                for j, h in enumerate(headers)
            ]
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(headers, rows, widths))
    return buffer.getvalue()
