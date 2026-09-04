"""Office document tools
======================
Read/create Word (.docx), Excel (.xlsx) and PowerPoint (.pptx) files.
Each format's library is optional and independent - missing one just
disables that format's methods (returns a clear pip-install error).
"""

from pathlib import Path
from typing import Dict, List

try:
    import docx

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import openpyxl

    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

try:
    from pptx import Presentation

    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False


class OfficeTools:
    """Read/create .docx, .xlsx and .pptx files."""

    def _resolve(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    # --- Word -------------------------------------------------------
    def read_docx(self, file_path: str) -> Dict:
        """Read all paragraph text from a Word document."""
        if not HAS_DOCX:
            return {"error": "python-docx not installed - run: pip install python-docx"}
        try:
            path = self._resolve(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            doc = docx.Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs]
            return {"file": str(path), "paragraphs": paragraphs, "text": "\n".join(paragraphs)}
        except Exception as e:
            return {"error": str(e)}

    def create_docx(self, file_path: str, content: str, title: str = "") -> Dict:
        """Create a Word document. `content` is split on blank lines into paragraphs."""
        if not HAS_DOCX:
            return {"error": "python-docx not installed - run: pip install python-docx"}
        try:
            path = self._resolve(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            doc = docx.Document()
            if title:
                doc.add_heading(title, level=1)
            for para in content.split("\n\n"):
                doc.add_paragraph(para)
            doc.save(str(path))
            return {"success": True, "file": str(path)}
        except Exception as e:
            return {"error": str(e)}

    # --- Excel ------------------------------------------------------
    def read_xlsx(self, file_path: str, sheet_name: str = None, max_rows: int = 200) -> Dict:
        """Read cell values from an Excel sheet (first sheet by default)."""
        if not HAS_XLSX:
            return {"error": "openpyxl not installed - run: pip install openpyxl"}
        try:
            path = self._resolve(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            wb = openpyxl.load_workbook(str(path), data_only=True)
            ws = wb[sheet_name] if sheet_name else wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows:
                    break
                rows.append(list(row))
            return {"file": str(path), "sheet": ws.title, "sheets": wb.sheetnames, "rows": rows}
        except Exception as e:
            return {"error": str(e)}

    def create_xlsx(self, file_path: str, rows: List[List], sheet_name: str = "Sheet1") -> Dict:
        """Create an Excel file from a list of rows (each row a list of cell values)."""
        if not HAS_XLSX:
            return {"error": "openpyxl not installed - run: pip install openpyxl"}
        try:
            path = self._resolve(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_name
            for row in rows:
                ws.append(row)
            wb.save(str(path))
            return {"success": True, "file": str(path), "rows_written": len(rows)}
        except Exception as e:
            return {"error": str(e)}

    # --- PowerPoint ---------------------------------------------------
    def read_pptx(self, file_path: str) -> Dict:
        """Read title + text from every slide in a PowerPoint file."""
        if not HAS_PPTX:
            return {"error": "python-pptx not installed - run: pip install python-pptx"}
        try:
            path = self._resolve(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            prs = Presentation(str(path))
            slides = []
            for i, slide in enumerate(prs.slides):
                texts = [shape.text for shape in slide.shapes if shape.has_text_frame]
                slides.append({"slide": i + 1, "text": texts})
            return {"file": str(path), "slide_count": len(slides), "slides": slides}
        except Exception as e:
            return {"error": str(e)}

    def create_pptx(self, file_path: str, slides: List[Dict]) -> Dict:
        """Create a PowerPoint file. Each slide dict: {"title": str, "body": str}."""
        if not HAS_PPTX:
            return {"error": "python-pptx not installed - run: pip install python-pptx"}
        try:
            path = self._resolve(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            prs = Presentation()
            layout = prs.slide_layouts[1]  # Title and Content
            for slide_data in slides:
                slide = prs.slides.add_slide(layout)
                slide.shapes.title.text = slide_data.get("title", "")
                if len(slide.placeholders) > 1:
                    slide.placeholders[1].text = slide_data.get("body", "")
            prs.save(str(path))
            return {"success": True, "file": str(path), "slide_count": len(slides)}
        except Exception as e:
            return {"error": str(e)}
