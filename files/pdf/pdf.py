"""PDF tools
=========
Read/create/merge/split PDF files. Uses pypdf (falls back to PyPDF2 if
that's what's installed) for reading/merging/splitting, and reportlab
for creating a simple text PDF from scratch.
"""

from pathlib import Path
from typing import Dict, List

try:
    from pypdf import PdfReader, PdfWriter

    HAS_PDF_LIB = True
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter

        HAS_PDF_LIB = True
    except ImportError:
        HAS_PDF_LIB = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


class PDFTools:
    """Read/create/merge/split PDF files."""

    def _resolve(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    def extract_text(self, file_path: str, max_chars: int = 8000) -> Dict:
        """Extract text content from a PDF."""
        if not HAS_PDF_LIB:
            return {"error": "pypdf not installed - run: pip install pypdf"}
        try:
            path = self._resolve(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            reader = PdfReader(str(path))
            text_parts = []
            for i, page in enumerate(reader.pages):
                text_parts.append(page.extract_text() or "")
            full_text = "\n".join(text_parts)
            truncated = len(full_text) > max_chars
            return {
                "file": str(path),
                "pages": len(reader.pages),
                "text": full_text[:max_chars],
                "truncated": truncated,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_page_count(self, file_path: str) -> Dict:
        """Get the number of pages in a PDF."""
        if not HAS_PDF_LIB:
            return {"error": "pypdf not installed - run: pip install pypdf"}
        try:
            path = self._resolve(file_path)
            reader = PdfReader(str(path))
            return {"file": str(path), "pages": len(reader.pages)}
        except Exception as e:
            return {"error": str(e)}

    def merge_pdfs(self, file_paths: List[str], output_path: str) -> Dict:
        """Merge multiple PDFs into one, in the given order."""
        if not HAS_PDF_LIB:
            return {"error": "pypdf not installed - run: pip install pypdf"}
        try:
            writer = PdfWriter()
            for fp in file_paths:
                p = self._resolve(fp)
                if not p.exists():
                    return {"error": f"File not found: {p}"}
                reader = PdfReader(str(p))
                for page in reader.pages:
                    writer.add_page(page)
            out = self._resolve(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)
            return {"success": True, "output": str(out), "merged_count": len(file_paths)}
        except Exception as e:
            return {"error": str(e)}

    def split_pdf(self, file_path: str, output_dir: str) -> Dict:
        """Split a PDF into one file per page."""
        if not HAS_PDF_LIB:
            return {"error": "pypdf not installed - run: pip install pypdf"}
        try:
            path = self._resolve(file_path)
            out_dir = self._resolve(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            reader = PdfReader(str(path))
            written = []
            for i, page in enumerate(reader.pages):
                writer = PdfWriter()
                writer.add_page(page)
                out_file = out_dir / f"{path.stem}_page{i + 1}.pdf"
                with open(out_file, "wb") as f:
                    writer.write(f)
                written.append(str(out_file))
            return {"success": True, "output_dir": str(out_dir), "files": written, "count": len(written)}
        except Exception as e:
            return {"error": str(e)}

    def create_pdf_from_text(self, file_path: str, text: str, title: str = "") -> Dict:
        """Create a simple PDF containing the given text (one page per ~45 lines)."""
        if not HAS_REPORTLAB:
            return {"error": "reportlab not installed - run: pip install reportlab"}
        try:
            path = self._resolve(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            c = canvas.Canvas(str(path), pagesize=letter)
            width, height = letter
            y = height - 60
            if title:
                c.setFont("Helvetica-Bold", 16)
                c.drawString(50, y, title)
                y -= 30
            c.setFont("Helvetica", 11)
            for line in text.splitlines() or [""]:
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 60
                c.drawString(50, y, line[:110])
                y -= 16
            c.save()
            return {"success": True, "file": str(path)}
        except Exception as e:
            return {"error": str(e)}

    def rotate_pdf(self, file_path: str, output_path: str, degrees: int = 90) -> Dict:
        """Rotate every page of a PDF by the given degrees (multiple of 90)."""
        if not HAS_PDF_LIB:
            return {"error": "pypdf not installed - run: pip install pypdf"}
        try:
            path = self._resolve(file_path)
            reader = PdfReader(str(path))
            writer = PdfWriter()
            for page in reader.pages:
                page.rotate(degrees)
                writer.add_page(page)
            out = self._resolve(output_path)
            with open(out, "wb") as f:
                writer.write(f)
            return {"success": True, "output": str(out)}
        except Exception as e:
            return {"error": str(e)}
