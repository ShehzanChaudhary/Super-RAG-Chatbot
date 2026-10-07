import asyncio

from app.adapters.search.ai_search_client import ai_search_client
from app.services.answer import answer_service
from app.services.retriever import retriever

EXIT_WORDS = {"exit", "quit", "q"}


async def main():
    print("Financial Bot test. Sawaal likho (band karne ke liye 'exit').\n")

    history = []

    try:
        while True:
            try:
                question = (await asyncio.to_thread(input, "You: ")).strip()
            except EOFError:
                break

            if not question:
                continue
            if question.lower() in EXIT_WORDS:
                break

            result = await retriever.retrieve(question, history)
            reply = await answer_service.answer(result["question"], result["chunks"])

            print(f"\n[Rewritten question] {result['question']}")
            pages = [f"{c['chunk_type']} p{c['pdf_page']}" for c in result["chunks"]]
            print(f"[Retrieved] {', '.join(pages)}\n")

            print(f"Bot: {reply['answer']}\n")

            if reply["citations"]:
                print("Sources:")
                for number, c in enumerate(reply["citations"], start=1):
                    print(f"  {number}. {c['doc_name']} | page {c['pdf_page']} | {c['url']}")
                print()

            # Save the turn, so the next question can be a follow-up
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": reply["answer"]})
    finally:
        await ai_search_client.close()


if __name__ == "__main__":
    asyncio.run(main())