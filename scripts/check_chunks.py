import asyncio
import json
from pathlib import Path

from app.services.answer import answer_service

QUESTION = "What is the total of sources of funds in FY2024?"
FY2024_CHUNKS = Path("output/chunks/Annual_Report_2023_24_chunks.jsonl")
TARGET_PAGES = [(159, 160), (161, 162)]
TOTAL_NUMBER = "9,10,863"  # the FY2024 total that we expect to see
KEYWORD = "sources of funds"


def load_target_chunks() -> list[dict]:
    chunks = []
    for line in FY2024_CHUNKS.read_text(encoding="utf-8").splitlines():
        chunk = json.loads(line)
        if (chunk["page_start"], chunk["page_end"]) in TARGET_PAGES:
            chunks.append(chunk)
    return chunks


def show_snippet(text: str, needle: str) -> None:
    index = text.lower().find(needle.lower())
    start = max(0, index - 500)
    print(text[start : index + 1500])


async def main():
    chunks = load_target_chunks()

    # Part 1: look inside the chunks
    for chunk in chunks:
        text = chunk["text"]
        print(f"\n=== pages {chunk['page_start']}-{chunk['page_end']} ===")
        print(f"has total number '{TOTAL_NUMBER}': {TOTAL_NUMBER in text}")
        needle = TOTAL_NUMBER if TOTAL_NUMBER in text else KEYWORD
        print(f"--- text around '{needle}' ---")
        show_snippet(text, needle)

    # Part 2: ask the LLM with only these chunks
    print("\n=== ANSWER WITH ONLY THESE CHUNKS ===")
    result = await answer_service.answer(QUESTION, chunks)
    print(result["answer"])
    print("found:", result["found"], "| citations:", result["citations"])


asyncio.run(main())