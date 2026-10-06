import asyncio
import re
from functools import lru_cache
from pathlib import Path

from app.adapters.llm.openrouter_client import openrouter_client
from app.adapters.logger import logger
from app.adapters.pdf.pdf_parser import pdf_parser
from app.adapters.search.ai_search_client import ai_search_client
from app.core.config import settings
from app.services.chunker import chunker
from app.prompts import get_prompt_template

MAX_PARALLEL_VISION_CALLS = 5

class IngestionService:
    """Reads the PDFs, makes chunks, embeds them and uploads them to AI Search."""

    def __init__(self):
        self.settings = settings
        self.parser = pdf_parser
        self.chunker = chunker
        self.llm = openrouter_client
        self.search = ai_search_client
        self.chart_template = get_prompt_template("chart_reading.jinja2")

    # ---------- Helpers ----------

    def _describe(self, pdf_path: Path) -> tuple[str, str, str]:
        """Annual_Report_2023_24.pdf -> (file name, 'Annual Report 2023-24', 'FY2024')."""
        doc_name = pdf_path.name
        match = re.search(r"(\d{4})_(\d{2})", doc_name)
        if not match:
            return doc_name, pdf_path.stem, ""

        start, end = match.group(1), match.group(2)
        doc_label = f"Annual Report {start}-{end}"
        report_year = f"FY{start[:2]}{end}"  # financial year ends in 2024 -> FY2024
        return doc_name, doc_label, report_year

    # ---------- Table chunks ----------

    async def _table_chunks(self, pdf_path, doc_name, doc_label, report_year) -> list[dict]:
        tables_by_page = await self.parser.extract_all_tables(pdf_path)

        chunks = []
        for pdf_page, tables in tables_by_page.items():
            for table_number, rows in enumerate(tables):
                chunks.extend(
                    self.chunker.chunk_table(
                        rows, doc_name, doc_label, report_year, pdf_page, table_number
                    )
                )
        return chunks

    # ---------- Chart chunks ----------

    async def _read_one_chart(
        self, semaphore, pdf_path, pages, figure, doc_name, doc_label, report_year
    ) -> dict | None:
        pdf_page = figure["pdf_page"]
        async with semaphore:  # only a few vision calls at the same time
            try:
                image = await self.parser.render_page(pdf_path, pdf_page)
                prompt = self.chart_template.render(
                    caption=figure["caption"],
                    neighbour_text=self.chunker.get_neighbour_text(pages, pdf_page),
                )
                description = await self.llm.vision(prompt, image)
            except Exception as e:
                logger.error(f"Chart on page {pdf_page} of {doc_name} failed: {e}")
                return None

        if not description.strip():
            logger.error(f"Empty chart description for page {pdf_page} of {doc_name}")
            return None

        return self.chunker.chunk_chart(
            description, doc_name, doc_label, report_year, pdf_page, figure["caption"]
        )

    async def _chart_chunks(self, pdf_path, pages, doc_name, doc_label, report_year) -> list[dict]:
        figures = self.chunker.find_figure_pages(pages)
        logger.info(f"{doc_name}: reading {len(figures)} chart pages with the vision model")

        semaphore = asyncio.Semaphore(MAX_PARALLEL_VISION_CALLS)
        tasks = [
            self._read_one_chart(
                semaphore, pdf_path, pages, figure, doc_name, doc_label, report_year
            )
            for figure in figures
        ]
        results = await asyncio.gather(*tasks)

        chunks = [r for r in results if r is not None]
        failed = len(figures) - len(chunks)
        if failed:
            logger.warning(f"{doc_name}: {failed} chart pages failed, run again to retry")
        return chunks

    # ---------- Main steps ----------

    async def ingest_pdf(self, pdf_path: Path) -> int:
        """Ingest one PDF. Returns the number of chunks uploaded."""
        doc_name, doc_label, report_year = self._describe(pdf_path)
        logger.info(f"Ingesting {doc_name} ({doc_label}, {report_year})")

        pages = await self.parser.extract_pages(pdf_path)

        chunks = self.chunker.chunk_text_pages(pages, doc_name, doc_label, report_year)
        chunks += await self._table_chunks(pdf_path, doc_name, doc_label, report_year)
        chunks += await self._chart_chunks(pdf_path, pages, doc_name, doc_label, report_year)

        vectors = await self.llm.embed([chunk["content"] for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError(f"Got {len(vectors)} vectors for {len(chunks)} chunks")
        for chunk, vector in zip(chunks, vectors):
            chunk["content_vector"] = vector

        await self.search.upload_chunks(chunks)

        counts = {}
        for chunk in chunks:
            counts[chunk["chunk_type"]] = counts.get(chunk["chunk_type"], 0) + 1
        logger.info(f"Done {doc_name}: {len(chunks)} chunks {counts}")
        return len(chunks)

    async def ingest_all(self, reset: bool = False) -> int:
        """Ingest every PDF in the PDFs folder. reset=True starts with an empty index."""
        pdf_files = sorted(self.settings.PDF_DIR.glob("*.pdf"))
        if not pdf_files:
            logger.error(f"No PDF files found in {self.settings.PDF_DIR}")
            return 0

        if reset:
            try:
                await self.search.delete_index()
            except Exception:
                logger.warning("Index could not be deleted (maybe it does not exist yet)")

        await self.search.create_index()

        total = 0
        for pdf_path in pdf_files:
            total += await self.ingest_pdf(pdf_path)

        logger.info(f"Ingestion finished: {total} chunks from {len(pdf_files)} PDFs")
        return total

ingestion_service = IngestionService()