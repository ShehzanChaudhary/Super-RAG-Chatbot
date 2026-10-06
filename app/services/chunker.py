import re
from functools import lru_cache

from app.adapters.logger import logger

MAX_CHARS = 1000        # size of one text chunk
OVERLAP = 100           # characters repeated between two chunks of the same page
TABLE_MAX_CHARS = 1500  # size of one table chunk
MIN_PAGE_CHARS = 80     # pages with less text than this are skipped

# "Figure 10.1: Sources of funds"
CAPTION_RE = re.compile(r"(?m)^\s*(Figure\s+\d+(?:\.\d+)?\s*:\s*[^\n]+)$")
# "10.1.1 Capital, reserves, and NRC funds"
HEADING_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,2}\s+[A-Z][^\n]{3,90}$")


class Chunker:
    """Turns PDF pages, tables and chart descriptions into chunks for AI Search."""

    # ---------- Helpers ----------

    def _make_id(self, doc_name: str, pdf_page: int, number: int, kind: str) -> str:
        stem = doc_name.rsplit(".", 1)[0]
        raw = f"{stem}_{kind}_p{pdf_page}_{number}"
        return re.sub(r"[^A-Za-z0-9_\-=]", "_", raw)  # AI Search key rules

    def _make_chunk(
        self, doc_name, doc_label, report_year, pdf_page, number, kind, section, body
    ) -> dict:
        header = f"[{doc_label} | PDF page {pdf_page}"
        if section:
            header += f" | {section}"
        header += "]"
        return {
            "id": self._make_id(doc_name, pdf_page, number, kind),
            "content": f"{header}\n{body}",
            "doc_name": doc_name,
            "report_year": report_year,
            "pdf_page": pdf_page,
            "chunk_type": kind,
        }

    def _split_long_paragraph(self, text: str) -> list[str]:
        pieces = []
        start = 0
        while start < len(text):
            pieces.append(text[start : start + MAX_CHARS])
            start += MAX_CHARS - OVERLAP
        return pieces

    # ---------- Text chunks ----------

    def chunk_text_pages(
        self, pages: list[dict], doc_name: str, doc_label: str, report_year: str
    ) -> list[dict]:
        """Split every page into paragraph-based chunks. Never crosses a page."""
        chunks = []
        section = ""  # the latest heading we have seen (carried across pages)

        for page in pages:
            pdf_page = page["pdf_page"]
            text = page["text"]
            if len(text) < MIN_PAGE_CHARS:
                continue

            # Break paragraphs that are too long, and remember headings
            paragraphs = []
            for para in text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                if HEADING_RE.match(para):
                    section = " ".join(para.split())  # remove tabs / extra spaces
                if len(para) > MAX_CHARS:
                    paragraphs.extend(self._split_long_paragraph(para))
                else:
                    paragraphs.append(para)

            # Pack paragraphs into chunks of about MAX_CHARS
            current = ""
            number = 0
            for para in paragraphs:
                if current and len(current) + len(para) + 2 > MAX_CHARS:
                    chunks.append(
                        self._make_chunk(
                            doc_name, doc_label, report_year, pdf_page,
                            number, "text", section, current,
                        )
                    )
                    number += 1
                    current = current[-OVERLAP:] + "\n\n" + para  # small overlap
                else:
                    current = f"{current}\n\n{para}" if current else para
            if current:
                chunks.append(
                    self._make_chunk(
                        doc_name, doc_label, report_year, pdf_page,
                        number, "text", section, current,
                    )
                )

        logger.info(f"{doc_name}: made {len(chunks)} text chunks")
        return chunks

    # ---------- Table chunks ----------

    def chunk_table(
        self, rows: list[list], doc_name: str, doc_label: str,
        report_year: str, pdf_page: int, table_number: int = 0,
    ) -> list[dict]:
        """One table -> one chunk (or several, each repeating the header row)."""
        lines = []
        for row in rows:
            cells = [" ".join(str(c or "").split()) for c in row]  # tidy each cell
            if any(cells):
                lines.append(" | ".join(cells))

        if len(lines) < 2:  # a real table has a header and at least one row
            return []

        header_line = lines[0]
        chunks = []
        current = header_line
        for line in lines[1:]:
            if len(current) + len(line) + 1 > TABLE_MAX_CHARS and current != header_line:
                chunks.append(current)
                current = header_line
            current += "\n" + line
        chunks.append(current)

        return [
            self._make_chunk(
                doc_name, doc_label, report_year, pdf_page,
                table_number * 100 + i, "table", "", body,
            )
            for i, body in enumerate(chunks)
        ]

    # ---------- Chart chunk ----------

    def chunk_chart(
        self, description: str, doc_name: str, doc_label: str,
        report_year: str, pdf_page: int, caption: str,
    ) -> dict:
        """The vision model's reading of a chart becomes one chunk."""
        body = f"{caption}\n{description}"
        return self._make_chunk(
            doc_name, doc_label, report_year, pdf_page, 0, "chart", "", body
        )

    # ---------- Figure pages and neighbour context ----------

    def find_figure_pages(self, pages: list[dict]) -> list[dict]:
        """Pages that carry a 'Figure X.Y: ...' caption (these go to the vision model)."""
        found = []
        for page in pages:
            match = CAPTION_RE.search(page["text"])
            if match:
                found.append(
                    {"pdf_page": page["pdf_page"], "caption": match.group(1).strip()}
                )
        return found

    def get_neighbour_text(
        self, pages: list[dict], pdf_page: int, max_chars: int = 3000
    ) -> str:
        """Text of the page before and after, only to help understand the page."""
        parts = []
        for number in (pdf_page - 1, pdf_page + 1):
            if 1 <= number <= len(pages):
                text = pages[number - 1]["text"][:max_chars]
                parts.append(f"--- PDF page {number} ---\n{text}")
        return "\n\n".join(parts)

chunker = Chunker()