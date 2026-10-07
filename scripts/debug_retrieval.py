import asyncio
import json
from pathlib import Path

from app.services.retriever import retriever

QUESTION = "What is the total of sources of funds in FY2024?"
KEYWORD = "sources of funds"
FY2024_CHUNKS = Path("output/chunks/Annual_Report_2023_24_chunks.jsonl")


async def main():
    # Part 1: what did the retriever actually pick?
    result = await retriever.retrieve(QUESTION)
    print("\n--- RETRIEVED ---")
    for i, chunk in enumerate(result["chunks"], start=1):
        has_keyword = KEYWORD in chunk["text"].lower()
        print(
            f"[{i}] {chunk['source_pdf']} pages {chunk['page_start']}-{chunk['page_end']} "
            f"| score {chunk['score']:.3f} | {len(chunk['text'])} chars | has '{KEYWORD}': {has_keyword}"
        )

    # Part 2: which chunks in the FY2024 file really contain the keyword?
    print(f"\n--- CHUNKS IN {FY2024_CHUNKS.name} WITH '{KEYWORD}' ---")
    for line in FY2024_CHUNKS.read_text(encoding="utf-8").splitlines():
        chunk = json.loads(line)
        if KEYWORD in chunk["text"].lower():
            print(f"pages {chunk['page_start']}-{chunk['page_end']}")


asyncio.run(main())