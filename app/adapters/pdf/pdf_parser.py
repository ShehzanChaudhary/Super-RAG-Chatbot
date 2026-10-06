import pymupdf
import asyncio
import re
from pathlib import Path

from app.adapters.logger import logger

class PDFParser:
    def _clean(self, text: str) -> str:
        text = text.replace("\xad", "")  # invisible soft hyphens
        return text.strip()

    def _fix_drop_caps(self, text: str) -> str:
        # The big first letter of a paragraph is a separate block:
        # "A\n\ns on 31 March" -> "As on 31 March"
        return re.sub(r"(?m)^([A-Z])\n+([a-z])", r"\1\2", text)

    def _extract_pages(self, pdf_path: Path) -> list[dict]:
        pages = []
        with pymupdf.open(pdf_path) as doc:
            for index, page in enumerate(doc):
                blocks = page.get_text("blocks", sort=True)
                paragraphs = [
                    self._clean(b[4]) for b in blocks if b[6] == 0 and b[4].strip()
                ]
                pages.append(
                    {
                        "pdf_page": index + 1,  # PDF page number (starts at 1)
                        "text": self._fix_drop_caps("\n\n".join(paragraphs)),
                    }
                )
        return pages

    def _render_page(self, pdf_path: Path, pdf_page: int, zoom: float) -> bytes:
        with pymupdf.open(pdf_path) as doc:
            page = doc[pdf_page - 1]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)) 
            return pixmap.tobytes("png")

    def _extract_tables(self, pdf_path: Path, pdf_page: int) -> list[list[list[str]]]:
        with pymupdf.open(pdf_path) as doc:
            page = doc[pdf_page - 1]
            found = page.find_tables()
            return [table.extract() for table in found.tables]

    def _extract_all_tables(self, pdf_path: Path) -> dict[int, list]:
        result = {}
        with pymupdf.open(pdf_path) as doc:  # open the PDF only once
            for index, page in enumerate(doc):
                tables = [t.extract() for t in page.find_tables().tables]
                # keep only real tables: a header + 1 row, and at least 2 columns
                tables = [t for t in tables if len(t) >= 2 and max(len(r) for r in t) >= 2]
                if tables:
                    result[index + 1] = tables
        return result

    async def extract_pages(self, pdf_path: Path) -> list[dict]:
        try:
            pages = await asyncio.to_thread(self._extract_pages, pdf_path)
        except Exception as e:
            logger.error(f"Cound not read {pdf_path.name}: {e}")
            raise

        logger.info(f"Read {len(pages)} pages from {pdf_path.name}")
        return pages

    async def render_page(
        self, pdf_path: Path, pdf_page: int, zoom: float = 2.0
    ) -> bytes:
        """Return one PDF page as a PNG image (for the vision model)."""
        try:
            return await asyncio.to_thread(self._render_page, pdf_path, pdf_page, zoom)
        except Exception as e:
            logger.error(f"Could not render page {pdf_page} of {pdf_path.name}: {e}")
            raise

    async def extract_tables(
        self, pdf_path: Path, pdf_page: int
    ) -> list[list[list[str]]]:
        """Return the tables on one page, each as a list of rows."""
        try:
            return await asyncio.to_thread(self._extract_tables, pdf_path, pdf_page)
        except Exception as e:
            logger.error(f"Could not read tables on page {pdf_page}: {e}")
            raise

    async def extract_all_tables(self, pdf_path: Path) -> dict[int, list]:
        """Return {pdf_page: [table, table, ...]} for every page that has tables."""
        try:
            result = await asyncio.to_thread(self._extract_all_tables, pdf_path)
        except Exception as e:
            logger.error(f"Could not read tables from {pdf_path.name}: {e}")
            raise

        total = sum(len(tables) for tables in result.values())
        logger.info(f"Found {total} tables on {len(result)} pages in {pdf_path.name}")
        return result

pdf_parser = PDFParser()