import io
from docx import Document
from openpyxl import load_workbook, Workbook
from pypdf import PdfReader, PdfWriter

class DocumentProcessor:
    @staticmethod
    def read_txt_bytes(file_bytes: bytes) -> str:
        """Читает TXT в UTF-8"""
        try:
            return file_bytes.decode('utf-8', errors='ignore')
        except Exception as e:
            return f"Ошибка чтения TXT: {str(e)}"

    @staticmethod
    def modify_txt_bytes(new_text: str) -> bytes:
        """Текст в байты UTF-8"""
        try:
            return new_text.encode('utf-8', errors='ignore')
        except Exception:
            return b""

    @staticmethod
    def read_word_bytes(file_bytes: bytes) -> str:
        """Word в текст"""
        try:
            doc_file = io.BytesIO(file_bytes)
            doc = Document(doc_file)
            return "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            return f"Ошибка чтения Word: {str(e)}"

    @staticmethod
    def modify_word_bytes(old_bytes: bytes, new_text: str) -> bytes:
        """Перезапись текста Word с сохранением XML"""
        try:
            doc_file = io.BytesIO(old_bytes)
            doc = Document(doc_file)
            for p in list(doc.paragraphs):
                p._element.getparent().remove(p._element)
            for line in new_text.split('\n'):
                doc.add_paragraph(line)
            output = io.BytesIO()
            doc.save(output)
            return output.getvalue()
        except Exception:
            doc = Document()
            for line in new_text.split('\n'):
                doc.add_paragraph(line)
            output = io.BytesIO()
            doc.save(output)
            return output.getvalue()

    @staticmethod
    def read_excel_bytes(file_bytes: bytes) -> str:
        """Excel в строки с разделителем '|'"""
        try:
            excel_file = io.BytesIO(file_bytes)
            wb = load_workbook(excel_file, read_only=True)
            sheet = wb.active
            lines = []
            for row in sheet.iter_rows(values_only=True):
                if any(row):
                    lines.append(" | ".join([str(cell) if cell is not None else "" for cell in row]))
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка чтения Excel: {str(e)}"

    @staticmethod
    def modify_excel_bytes(new_text: str) -> bytes:
        """Строки обратно в Excel-сетку"""
        wb = Workbook()
        sheet = wb.active
        for r_idx, line in enumerate(new_text.split('\n')):
            cells = line.split(' | ')
            for c_idx, val in enumerate(cells):
                try:
                    if '.' in val: sheet.cell(row=r_idx+1, column=c_idx+1, value=float(val))
                    else: sheet.cell(row=r_idx+1, column=c_idx+1, value=int(val))
                except ValueError:
                    sheet.cell(row=r_idx+1, column=c_idx+1, value=val)
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    @staticmethod
    def read_pdf_bytes(file_bytes: bytes) -> str:
        """Чтение текстового слоя PDF"""
        try:
            pdf_file = io.BytesIO(file_bytes)
            reader = PdfReader(pdf_file)
            return "\n".join([page.extract_text() or "" for page in reader.pages])
        except Exception as e:
            return f"Ошибка чтения PDF: {str(e)}"

    @staticmethod
    def modify_pdf_bytes(old_bytes: bytes, new_text: str) -> bytes:
        """Внедрение текста в метаданные описания PDF"""
        try:
            reader = PdfReader(io.BytesIO(old_bytes))
            writer = PdfWriter()
            writer.append(reader)
            writer.add_metadata({"/Description": new_text})
            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()
        except Exception:
            return old_bytes
