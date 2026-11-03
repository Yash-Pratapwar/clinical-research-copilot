"""Build the two-page handout from ARCHITECTURE.md (requires reportlab)."""
from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, PageBreak


ROOT = Path(__file__).resolve().parent


def inline(text):
    return re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>',
                  re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escape(text)))


def build():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyCopy', fontName='Helvetica', fontSize=9.2,
                              leading=12.2, spaceAfter=7, alignment=TA_LEFT,
                              textColor=colors.HexColor('#263447')))
    styles.add(ParagraphStyle('SectionTitle', fontName='Helvetica-Bold', fontSize=11,
                              leading=14, spaceBefore=6, spaceAfter=5,
                              textColor=colors.HexColor('#145b74'), keepWithNext=True))
    styles.add(ParagraphStyle('DocumentTitle', fontName='Helvetica-Bold', fontSize=21,
                              leading=25, spaceAfter=8, textColor=colors.HexColor('#15324f')))
    styles.add(ParagraphStyle('FlowCode', fontName='Courier', fontSize=7.4,
                              leading=10, backColor=colors.HexColor('#edf3f7'),
                              borderPadding=8, spaceBefore=5, spaceAfter=12))
    story, paragraph, code = [], [], None

    def flush():
        if paragraph:
            story.append(Paragraph(inline(' '.join(paragraph)), styles['BodyCopy']))
            paragraph.clear()

    for line in (ROOT / 'ARCHITECTURE.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            flush()
            if code is None:
                code = []
            else:
                story.append(Preformatted('\n'.join(code), styles['FlowCode']))
                code = None
        elif code is not None:
            code.append(line)
        elif line == '<!-- pagebreak -->':
            flush()
            story.append(PageBreak())
        elif line.startswith('# '):
            flush()
            story.append(Paragraph(inline(line[2:]), styles['DocumentTitle']))
        elif line.startswith('## '):
            flush()
            story.append(Paragraph(inline(line[3:]), styles['SectionTitle']))
        elif not line.strip():
            flush()
        else:
            paragraph.append(line)
    flush()

    def furniture(canvas, doc):
        width, height = A4
        canvas.setStrokeColor(colors.HexColor('#cbd8e4'))
        canvas.line(36, height - 31, width - 36, height - 31)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#526477'))
        canvas.drawString(36, height - 23, 'CLINICAL RESEARCH AI COPILOT  |  TECHNICAL ARCHITECTURE')
        canvas.drawString(36, 23, 'Synthetic / authorized research documents only  |  4 November 2026')
        canvas.drawRightString(width - 36, 23, str(doc.page))

    SimpleDocTemplate(str(ROOT / 'ARCHITECTURE.pdf'), pagesize=A4,
                      rightMargin=36, leftMargin=36, topMargin=43, bottomMargin=38,
                      title='Clinical Research AI Copilot - Technical Architecture',
                      author='Clinical Research AI Copilot').build(
                          story, onFirstPage=furniture, onLaterPages=furniture)


if __name__ == '__main__':
    build()
