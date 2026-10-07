import asyncio
import json
import sys

from app.adapters.pdf.pdf_parser import pdf_parser
from app.core.config import settings


def load_all() -> dict[str, list[dict]]:
    """Read the saved chunks of every PDF: {'Annual_Report_2023_24.pdf': [chunk, ...]}."""
    folder = settings.DATA_DIR / "chunks"
    return {
        file.name.removesuffix(".json"): json.loads(file.read_text(encoding="utf-8"))
        for file in sorted(folder.glob("*.json"))
    }


def show_summary(data: dict):
    for name, chunks in data.items():
        kinds = {}
        for chunk in chunks:
            kinds[chunk["chunk_type"]] = kinds.get(chunk["chunk_type"], 0) + 1

        charts = [c for c in chunks if c["chunk_type"] == "chart"]
        no_summary = [c["pdf_page"] for c in charts if "Summary" not in c["content"]]
        estimated = [c["pdf_page"] for c in charts if "estimated" in c["content"].lower()]

        print(f"\n{name}: {len(chunks)} chunks {kinds}")
        print(f"  chart pages with no 'Summary' line (maybe cut off): {no_summary}")
        print(f"  chart pages with estimated values: {len(estimated)}")


def search_text(data: dict, text: str):
    for name, chunks in data.items():
        hits = [c for c in chunks if text in c["content"]]
        print(f"\n{name}: {len(hits)} chunks contain '{text}'")
        for chunk in hits[:6]:
            preview = chunk["content"].replace("\n", " ")[:140]
            print(f"  page {chunk['pdf_page']} [{chunk['chunk_type']}] {preview}")


async def show_chart(data: dict, pdf_name: str, pdf_page: int):
    charts = [
        c for c in data.get(pdf_name, [])
        if c["chunk_type"] == "chart" and c["pdf_page"] == pdf_page
    ]
    if not charts:
        print(f"No chart chunk for {pdf_name} page {pdf_page}")
        return

    print(charts[0]["content"])

    # Save the page as an image, so you can compare it with the text above
    image = await pdf_parser.render_page(settings.PDF_DIR / pdf_name, pdf_page)
    out_file = settings.DATA_DIR / "check" / f"{pdf_name}_p{pdf_page}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(image)
    print(f"\nPage image saved: {out_file}")


def main():
    data = load_all()
    args = sys.argv[1:]

    if not args:
        show_summary(data)
    elif len(args) == 2 and args[1].isdigit():
        asyncio.run(show_chart(data, args[0], int(args[1])))
    else:
        search_text(data, " ".join(args))


main()