import asyncio

from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.services.retriever import retriever

# (question, text that MUST appear in at least one retrieved page)
CHECKS = [
    ("What is the total of sources of funds in FY2024?", "9,10,863"),
    # Apne sawaal aur report me dikhne wala exact number yahan jodo:
    # ("What is the own funds in FY2023?", "82,868"),
]


async def run_checks():
    """Automatic test: does the right number come in the retrieved pages?"""
    for question, expected in CHECKS:
        result = await retriever.retrieve(question)
        found_on = [
            f"{c['source_pdf']} p{c['page_start']}"
            for c in result["chunks"]
            if expected in c["text"]
        ]
        status = "PASS" if found_on else "FAIL"
        print(f"[{status}] {question}")
        print(f"        expected '{expected}' -> {found_on or 'not found in any page'}\n")


async def run_chat():
    """Manual test: ask questions, follow-ups work like in the real chat."""
    print("Retriever test. Sawaal likho (band karne ke liye 'exit').\n")
    history = []

    while True:
        question = (await asyncio.to_thread(input, "You: ")).strip()
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break

        result = await retriever.retrieve(question, history)
        print(f"\n[Standalone question] {result['question']}")
        print(f"[Pages: {len(result['chunks'])}]")
        for number, chunk in enumerate(result["chunks"], start=1):
            preview = chunk["text"][:150].replace("\n", " ")
            print(
                f"  {number}. {chunk['source_pdf']} p{chunk['page_start']} "
                f"| score {chunk['score']:.4f} | images {len(chunk['image_ids'])} | {preview}"
            )
        print()

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": "(answer)"})


async def main():
    try:
        await run_checks()
        await run_chat()
    finally:
        await ai_search_client.close()


if __name__ == "__main__":
    asyncio.run(main())