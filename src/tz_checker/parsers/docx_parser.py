import re
import zipfile
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from tz_checker.models.schemas import DocumentModel, Paragraph, Section, Table


class DocumentParseError(ValueError):
    pass


def _iter_blocks(document: DocxDocument):
    # python-docx хранит абзацы и таблицы отдельно, поэтому читаем XML для сохранения порядка.
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield DocxParagraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield DocxTable(child, document)


def _heading_level(style: str) -> int | None:
    match = re.search(r"(?:Heading|Заголовок)\s*(\d+)", style, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _section_number(text: str, fallback: int) -> str:
    match = re.match(r"^\s*((?:\d+\.)*\d+|Приложение\s+[А-ЯA-Z0-9]+)[.\s]", text, re.IGNORECASE)
    return match.group(1).rstrip(".") if match else str(fallback)


def parse_docx(path: Path, document_id: str) -> DocumentModel:
    if not path.exists() or path.stat().st_size == 0:
        raise DocumentParseError("DOCX file is empty")
    # Формат DOCX является ZIP-контейнером; ранняя проверка дает понятную ошибку для мусорных файлов.
    if not zipfile.is_zipfile(path):
        raise DocumentParseError("File is not a valid DOCX archive")
    try:
        document = Document(str(path))
    except Exception as exc:
        raise DocumentParseError("Unable to parse DOCX") from exc

    paragraphs: list[Paragraph] = []
    sections: list[Section] = []
    tables: list[Table] = []
    current: Section | None = None
    pending_caption = ""

    for block in _iter_blocks(document):
        if isinstance(block, DocxParagraph):
            text = block.text.strip()
            if not text:
                continue
            # Стабильная ссылка нужна для точной привязки замечаний к исходному фрагменту.
            ref = f"p_{len(paragraphs) + 1}"
            style = block.style.name if block.style else ""
            level = _heading_level(style)
            paragraphs.append(Paragraph(paragraph_id=ref, text=text, style=style))
            if level or re.match(r"^Приложение\s+[А-ЯA-Z0-9]+", text, re.IGNORECASE):
                current = Section(
                    section_id=_section_number(text, len(sections) + 1),
                    title=text,
                    level=level or 1,
                    paragraph_refs=[ref],
                )
                sections.append(current)
            else:
                if current is None:
                    # Текст до первого заголовка помещаем в синтетический вводный раздел.
                    current = Section(section_id="0", title="Общие сведения", level=1)
                    sections.append(current)
                current.paragraph_refs.append(ref)
                current.text = f"{current.text}\n{text}".strip()
            if text.lower().startswith(("таблица ", "table ")):
                pending_caption = text
        else:
            table_id = f"t_{len(tables) + 1}"
            rows = [[cell.text.strip() for cell in row.cells] for row in block.rows]
            columns = rows[0] if rows else []
            tables.append(Table(table_id=table_id, caption=pending_caption, columns=columns, rows=rows[1:]))
            if current is None:
                current = Section(section_id="0", title="Общие сведения")
                sections.append(current)
            current.tables.append(table_id)
            pending_caption = ""

    if not paragraphs and not tables:
        raise DocumentParseError("DOCX contains no readable content")
    title = document.core_properties.title or next((s.title for s in sections), path.stem)
    metadata = {
        "author": document.core_properties.author or "",
        "subject": document.core_properties.subject or "",
        "created": document.core_properties.created.isoformat() if document.core_properties.created else None,
    }
    return DocumentModel(document_id=document_id, title=title, metadata=metadata, paragraphs=paragraphs, sections=sections, tables=tables)
