import asyncio
import sys

from app.adapters.pdf.pdf_parser import pdf_parser
from app.core.config import settings
from app.services.ingestion import ingestion_service


async def main():
    pdf_name, pdf_page = sys.argv[1], int(sys.argv[2])
    pdf_path = settings.PDF_DIR / pdf_name

    pages = await pdf_parser.extract_pages(pdf_path)
    figures = ingestion_service.chunker.find_figure_pages(pages)
    figure = next((f for f in figures if f["pdf_page"] == pdf_page), None)
    if figure is None:
        print(f"No 'Figure' caption found on page {pdf_page}")
        return

    doc_name, doc_label, report_year = ingestion_service._describe(pdf_path)
    chunk = await ingestion_service._read_one_chart(
        asyncio.Semaphore(1), pdf_path, pages, figure,
        doc_name, doc_label, report_year
    )
    print(chunk["content"] if chunk else "The vision call failed, see the log above.")


if __name__ == "__main__":
    asyncio.run(main())