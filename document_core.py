import io
import os
import zipfile


class DocumentProcessor:
    @staticmethod
    def create_document_bytes(file_format):
        output = io.BytesIO()
        if file_format == "txt":
            return b""
        if file_format == "docx":
            from docx import Document
            Document().save(output)
        elif file_format == "xlsx":
            from openpyxl import Workbook
            Workbook().save(output)
        elif file_format == "pptx":
            from pptx import Presentation
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            box = slide.shapes.add_textbox(914400, 914400, 7315200, 1828800)
            box.text_frame.text = "Введите текст слайда"
            presentation.save(output)
        else:
            raise ValueError("Неизвестный формат документа")
        return output.getvalue()

    @staticmethod
    def detect_format(file_name, mime_type="", file_bytes=None):
        extension = os.path.splitext(str(file_name).lower())[1]
        if file_bytes:
            # Identify common image formats by their file signatures as well as
            # their extension. Android document providers often omit MIME types.
            if file_bytes.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
                return "image"
            if file_bytes.startswith(b"\\xff\\xd8\\xff"):
                return "image"
            if file_bytes.startswith((b"GIF87a", b"GIF89a")):
                return "image"
            if file_bytes.startswith(b"BM") or file_bytes.startswith((b"II*\\x00", b"MM\\x00*")):
                return "image"
            if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
                return "image"
            if file_bytes.lstrip().startswith(b"%PDF-"):
                return "pdf"
            # Determine Office format from the internal package structure.
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as package:
                    members = set(package.namelist())
                if "[Content_Types].xml" in members:
                    if "word/document.xml" in members:
                        return "docx"
                    if "xl/workbook.xml" in members:
                        return "xlsx"
                    if "ppt/presentation.xml" in members:
                        return "pptx"
            except (zipfile.BadZipFile, OSError):
                pass
        by_extension = {
            ".txt": "txt",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".webp": "image",
            ".gif": "image",
            ".bmp": "image",
            ".tif": "image",
            ".tiff": "image",
            ".docx": "docx",
            ".xlsx": "xlsx",
            ".pdf": "pdf",
            ".pptx": "pptx",
        }
        if extension in by_extension:
            return by_extension[extension]
        by_mime = {
            "text/plain": "txt",
            "image/png": "image",
            "image/jpeg": "image",
            "image/webp": "image",
            "image/gif": "image",
            "image/bmp": "image",
            "image/tiff": "image",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        }
        if mime_type in by_mime:
            return by_mime[mime_type]
        raise ValueError(
            "Формат не поддерживается. Используйте TXT, DOCX, XLSX, PPTX или PDF."
        )

    @staticmethod
    def normalize_image_bytes(file_bytes):
        """Decode an image with Pillow and return a display-safe PNG.

        This avoids relying on Kivy's platform-specific loaders for WebP,
        TIFF, animated GIFs, and images with EXIF orientation.
        """
        from PIL import Image, ImageOps
        source = io.BytesIO(file_bytes)
        with Image.open(source) as image:
            try:
                image.seek(0)  # first frame for animated formats
            except EOFError:
                pass
            image = ImageOps.exif_transpose(image)
            image.load()
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            converted = image.convert("RGBA" if has_alpha else "RGB")
            output = io.BytesIO()
            converted.save(output, format="PNG", optimize=True)
            return output.getvalue()

    @staticmethod
    def read_txt_bytes(file_bytes):
        return file_bytes.decode("utf-8-sig", errors="replace")

    @staticmethod
    def modify_txt_bytes(new_text):
        return new_text.encode("utf-8")

    @staticmethod
    def _iter_word_paragraphs(parent, seen_cells=None):
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        if seen_cells is None:
            seen_cells = set()
        if hasattr(parent, "element") and hasattr(parent.element, "body"):
            container = parent.element.body
        elif hasattr(parent, "_tc"):
            container = parent._tc
        else:
            container = parent
        for child in container.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                table = Table(child, parent)
                for row in table.rows:
                    for cell in row.cells:
                        cell_key = id(cell._tc)
                        if cell_key in seen_cells:
                            continue
                        seen_cells.add(cell_key)
                        yield from DocumentProcessor._iter_word_paragraphs(
                            cell, seen_cells
                        )

    @staticmethod
    def read_word_bytes(file_bytes):
        from docx import Document
        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            raise ValueError('Выбранный файл не является корректным DOCX. Возможно, это старый формат DOC или файл повреждён.')
        document = Document(io.BytesIO(file_bytes))
        paragraphs = list(DocumentProcessor._iter_word_paragraphs(document))
        return "\n".join(paragraph.text for paragraph in paragraphs)

    @staticmethod
    def extract_docx_images(file_bytes):
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as package:
            return [package.read(name) for name in sorted(package.namelist())
                    if name.startswith("word/media/") and not name.endswith("/")]

    @staticmethod
    def extract_pptx_slides(file_bytes):
        from pptx import Presentation
        presentation = Presentation(io.BytesIO(file_bytes))
        result = []
        for slide in presentation.slides:
            texts, images = [], []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    texts.append(shape.text.strip())
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        texts.append(" | ".join(cell.text for cell in row.cells))
                if getattr(shape, "shape_type", None) == 13:
                    try:
                        images.append(shape.image.blob)
                    except Exception:
                        pass
            result.append({"texts": texts, "images": images})
        return result

    @staticmethod
    def _parse_rich_runs(paragraph, value):
        import re
        from docx.shared import RGBColor
        from docx.enum.text import WD_COLOR_INDEX
        token = re.compile(r"(\[b\]|\[/b\]|\[color=#[0-9A-Fa-f]{6}\]|\[/color\]|\[highlight=#[0-9A-Fa-f]{6}\]|\[/highlight\])")
        pieces = token.split(value)
        # Clear text nodes but keep drawing elements (embedded pictures).
        for node in paragraph._p.xpath(".//w:t"):
            node.text = ""
        bold = False
        color = None
        highlight = None
        for piece in pieces:
            if not piece:
                continue
            if piece == "[b]":
                bold = True
            elif piece == "[/b]":
                bold = False
            elif piece.startswith("[color="):
                color = piece[7:-1]
            elif piece == "[/color]":
                color = None
            elif piece.startswith("[highlight="):
                highlight = piece[11:-1]
            elif piece == "[/highlight]":
                highlight = None
            else:
                run = paragraph.add_run(piece)
                if bold:
                    run.bold = True
                if color:
                    run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
                if highlight:
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW

    @staticmethod
    def _replace_paragraph_text_preserving_xml(paragraph, value):
        text_nodes = paragraph._p.xpath(".//w:t")
        if text_nodes:
            text_nodes[0].text = value
            for node in text_nodes[1:]:
                node.text = ""
        elif value:
            paragraph.add_run(value)

    @staticmethod
    def modify_word_bytes(old_bytes, new_text):
        from docx import Document
        # Keep the original document package. Replace only text nodes, so
        # paragraph properties, tables, pictures, headers, and other XML parts
        # remain in the DOCX instead of rebuilding a blank document.
        document = Document(io.BytesIO(old_bytes))
        paragraphs = list(DocumentProcessor._iter_word_paragraphs(document))
        lines = new_text.split("\n")

        for index, paragraph in enumerate(paragraphs):
            value = lines[index] if index < len(lines) else ""
            DocumentProcessor._parse_rich_runs(paragraph, value)

        for value in lines[len(paragraphs):]:
            paragraph = document.add_paragraph()
            DocumentProcessor._parse_rich_runs(paragraph, value)

        output = io.BytesIO()
        document.save(output)
        return output.getvalue()


    @staticmethod
    def read_excel_grid(file_bytes):
        from openpyxl import load_workbook
        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            raise ValueError("Файл XLSX повреждён или имеет неверный формат.")
        workbook = load_workbook(io.BytesIO(file_bytes), data_only=False)
        try:
            sheet = workbook.active
            rows = max(sheet.max_row, 12)
            cols = max(sheet.max_column, 8)
            return [[sheet.cell(row=r, column=c).value for c in range(1, cols + 1)]
                    for r in range(1, rows + 1)]
        finally:
            workbook.close()

    @staticmethod
    def modify_excel_grid(old_bytes, values):
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(old_bytes), data_only=False)
        try:
            sheet = workbook.active
            for r, row in enumerate(values, start=1):
                for c, value in enumerate(row, start=1):
                    cell = sheet.cell(row=r, column=c)
                    if cell.__class__.__name__ != "MergedCell":
                        cell.value = DocumentProcessor._parse_excel_value(str(value))
            output = io.BytesIO()
            workbook.save(output)
            return output.getvalue()
        finally:
            workbook.close()

    @staticmethod
    def add_slide_to_pptx(old_bytes):
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        presentation = Presentation(io.BytesIO(old_bytes))
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(245, 248, 255)
        shape = slide.shapes.add_textbox(Inches(0.8), Inches(0.65), Inches(8.2), Inches(1.1))
        frame = shape.text_frame
        frame.text = "Новый слайд"
        frame.paragraphs[0].font.size = Pt(30)
        frame.paragraphs[0].font.bold = True
        frame.paragraphs[0].font.color.rgb = RGBColor(25, 65, 120)
        output = io.BytesIO()
        presentation.save(output)
        return output.getvalue()

    @staticmethod
    def add_image_to_pptx(old_bytes, image_bytes):
        from pptx import Presentation
        presentation = Presentation(io.BytesIO(old_bytes))
        slide = presentation.slides[-1] if presentation.slides else presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.shapes.add_picture(io.BytesIO(image_bytes), 914400, 914400, width=5486400)
        output = io.BytesIO()
        presentation.save(output)
        return output.getvalue()

    @staticmethod
    def add_table_to_docx(old_bytes, rows=3, cols=3, values=None):
        from docx import Document
        document = Document(io.BytesIO(old_bytes))
        row_count, col_count = max(1, int(rows)), max(1, int(cols))
        table = document.add_table(rows=row_count, cols=col_count)
        table.style = "Table Grid"
        for r in range(row_count):
            for c in range(col_count):
                if values and r < len(values) and c < len(values[r]):
                    table.cell(r, c).text = str(values[r][c])
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()

    @staticmethod
    def add_image_to_docx(old_bytes, image_bytes):
        from docx import Document
        from docx.shared import Inches
        document = Document(io.BytesIO(old_bytes))
        document.add_picture(io.BytesIO(image_bytes), width=Inches(4.5))
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()

    @staticmethod
    def read_excel_bytes(file_bytes):
        from openpyxl import load_workbook
        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            raise ValueError('Выбранный файл не является корректной книгой XLSX. Проверьте расширение или целостность файла.')
        workbook = load_workbook(io.BytesIO(file_bytes), data_only=False)
        try:
            sheet = workbook.active
            rows = []
            for row in sheet.iter_rows():
                values = [cell.value for cell in row]
                if any(value is not None for value in values):
                    rows.append(" | ".join(
                        "" if value is None else str(value) for value in values
                    ))
            return "\n".join(rows)
        finally:
            workbook.close()

    @staticmethod
    def _parse_excel_value(value):
        value = value.strip()
        if value == "":
            return None
        try:
            if value.lstrip("+-").isdigit():
                return int(value)
            return float(value.replace(",", "."))
        except ValueError:
            return value

    @staticmethod
    def modify_excel_bytes(old_bytes, new_text):
        from openpyxl import load_workbook
        # Update only the active sheet's values; keep workbook sheets,
        # formatting, widths, merged cells, and other workbook structures.
        workbook = load_workbook(io.BytesIO(old_bytes), data_only=False)
        try:
            sheet = workbook.active
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.__class__.__name__ != "MergedCell":
                        cell.value = None

            for row_index, line in enumerate(new_text.split("\n"), start=1):
                for column_index, value in enumerate(line.split(" | "), start=1):
                    target = sheet.cell(row=row_index, column=column_index)
                    if target.__class__.__name__ != "MergedCell":
                        target.value = DocumentProcessor._parse_excel_value(value)

            output = io.BytesIO()
            workbook.save(output)
            return output.getvalue()
        finally:
            workbook.close()

    @staticmethod
    def read_pdf_bytes(file_bytes):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def modify_pdf_bytes(old_bytes, new_text):
        from pypdf import PdfReader, PdfWriter
        # pypdf cannot rewrite arbitrary page text in-place. Preserve every
        # page and store the edited text in PDF Description metadata.
        reader = PdfReader(io.BytesIO(old_bytes))
        writer = PdfWriter()
        writer.append(reader)
        metadata = dict(reader.metadata or {})
        metadata["/Description"] = new_text
        writer.add_metadata(metadata)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()


    @staticmethod
    def read_pptx_bytes(file_bytes):
        from pptx import Presentation
        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            raise ValueError('Выбранный файл не является корректной презентацией PPTX. Возможно, это старый формат PPT или файл повреждён.')
        presentation = Presentation(io.BytesIO(file_bytes))
        lines = []
        for number, slide in enumerate(presentation.slides, start=1):
            lines.append("[Слайд " + str(number) + "]")
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    lines.append(shape.text.strip())
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        lines.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(lines)

    @staticmethod
    def modify_pptx_bytes(old_bytes, new_text):
        from pptx import Presentation
        presentation = Presentation(io.BytesIO(old_bytes))
        current_slide = -1
        slide_text = {}
        for line in new_text.splitlines():
            marker = line.strip()
            if marker.startswith("[Слайд ") and marker.endswith("]"):
                try:
                    current_slide = int(marker[7:-1]) - 1
                    slide_text.setdefault(current_slide, [])
                except ValueError:
                    current_slide = -1
            elif current_slide >= 0 and line.strip():
                slide_text[current_slide].append(line)
        # Edit only the first text box on each slide. All other shapes,
        # pictures, tables, backgrounds and later slide content stay intact.
        for index, slide in enumerate(presentation.slides):
            values = slide_text.get(index, [])
            if not values:
                continue
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    shape.text_frame.text = values[0]
                    break
        output = io.BytesIO()
        presentation.save(output)
        return output.getvalue()
