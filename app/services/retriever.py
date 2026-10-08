import asyncio
import json
import math
import re
from collections import Counter

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.adapters.search.ai_search_client import ai_search_client
from app.core.config import PROJECT_ROOT, settings
from app.prompts import get_prompt_template

# Financial year (end year) -> report that contains it.
# FY2021 numbers are in the 2021-22 report (as last year's column).
REPORT_FILES = settings.REPORT_FILES
YEAR_TO_REPORT = {
    2021: REPORT_FILES[0],
    2022: REPORT_FILES[0],
    2023: REPORT_FILES[1],
    2024: REPORT_FILES[2],
}

# Matches 2024, FY2024, 2023-24, 2022-2024
YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?:\s*[-–/]\s*(\d{2,4}))?(?!\d)")

# Words that tell us the question needs data from all the reports
WIDE_QUESTION_RE = re.compile(
    r"\b(compare|comparison|versus|vs|trend|growth|change|forecast|predict|prediction|"
    r"projection|project|estimate|expected|future|next year|over the years|yoy|cagr|"
    r"increase|decrease|all years|three years|3 years)\b",
    re.IGNORECASE,
)

IMAGE_ID_RE = re.compile(r"\[IMAGE id=(\S+) page=")
IMAGE_FILE_RE = re.compile(r" file=\S+\]")  # the saved-file path is useless for the LLM

STOP_WORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are", "was",
    "were", "be", "been", "what", "which", "who", "how", "much", "many", "me", "tell", "give",
    "show", "please", "about", "with", "from", "by", "as", "it", "its", "this", "that", "do",
    "does", "did", "can", "you", "i", "my", "ok", "okay", "also", "then", "than", "total",
}

RRF_K = 60  # standard constant for rank fusion
PAGE_EMBED_CHARS = 12000  # a page is cut to this size before embedding (model token limit)
HISTORY_CONTENT_CHARS = 600  # old bot answers are cut to this size in the rewrite prompt


def find_years(text: str) -> set[int]:
    """All financial years mentioned in the text. '2023-24' means FY2024."""
    years = set()
    for match in YEAR_RE.finditer(text):
        start = int(match.group(1))
        second = match.group(2)
        if second is None:
            years.add(start)
            continue
        end = int(second) if len(second) == 4 else int(str(start)[:2] + second)
        if end == start + 1:
            years.add(end)
        else:
            years.update({start, end})
    return years


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def rank_positions(scores: dict) -> dict:
    """{key: score} -> {key: position}, best score gets position 0."""
    ordered = sorted(scores, key=scores.get, reverse=True)
    return {key: position for position, key in enumerate(ordered)}


def dot(a: list[float], b: list[float]) -> float:
    # OpenAI embeddings are unit length, so dot product = cosine similarity
    return sum(x * y for x, y in zip(a, b))


class Retriever:
    """Finds the pages of the reports that can answer a question.

    Steps: rewrite follow-up -> search every report -> split chunks into pages
    -> pick the best pages of every report (exact page = exact citation).
    """

    def __init__(self):
        self.pages: dict[tuple[str, int], str] = {}  # (pdf, page) -> page text
        self.page_terms: dict[tuple[str, int], Counter] = {}
        self.doc_freq: Counter = Counter()
        self.page_vectors: dict[tuple[str, int], list[float]] = {}  # filled on demand
        self.image_paths: dict[str, str] = {}  # image id -> saved png path

        self.load_pages()
        self.load_image_paths()

    # ---------- Loading local files (once, at startup) ----------

    def load_pages(self):
        """Read output/pages/*_pages.jsonl (one line per PDF page)."""
        for path in sorted(settings.PAGES_DIR.glob("*_pages.jsonl")):
            pdf = path.name.removesuffix("_pages.jsonl") + ".pdf"
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (pdf, row["page_number"])
                terms = Counter(tokenize(row["text"]))
                self.pages[key] = row["text"]
                self.page_terms[key] = terms
                self.doc_freq.update(terms.keys())

        if self.pages:
            logger.info(f"Retriever loaded {len(self.pages)} pages")
        else:
            logger.warning(f"No page files found in {settings.PAGES_DIR}; using chunk-level results")

    def load_image_paths(self):
        """Read output/metadata/*_images.jsonl so we can say where each figure is saved."""
        for path in sorted(settings.METADATA_DIR.glob("*_images.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                saved = PROJECT_ROOT / row["image_path"].replace("\\", "/")
                self.image_paths[row["image_id"]] = str(saved)
        logger.info(f"Retriever knows {len(self.image_paths)} figure images")

    # ---------- Step 1: follow-up question -> standalone question ----------

    async def rewrite_question(self, question: str, history: list[dict]) -> str:
        if not history:
            return question  # first question, nothing to resolve

        recent = []
        for message in history[-settings.RETRIEVAL_HISTORY_MESSAGES:]:
            recent.append(
                {"role": message["role"], "content": message["content"][:HISTORY_CONTENT_CHARS]}
            )

        prompt = get_prompt_template("query_rewrite.jinja2").render(history=recent, question=question)
        raw = ""
        for attempt in range(2):
            try:
                raw = await azure_openai_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                    max_tokens=settings.REWRITE_MAX_TOKENS,
                )
                standalone = self.parse_rewrite(raw)
                if standalone:
                    logger.info(f"Question rewritten: '{question}' -> '{standalone}'")
                    return standalone
            except Exception as e:
                logger.error(f"Rewrite call failed (attempt {attempt + 1}): {e}")
            logger.warning(f"Rewrite attempt {attempt + 1} gave no usable question. Raw reply: {raw!r}")

        return self.fallback_question(question, history)

    @staticmethod
    def parse_rewrite(raw: str) -> str | None:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            standalone = json.loads(match.group(0)).get("standalone_question")
        except json.JSONDecodeError:
            return None
        if isinstance(standalone, str) and 0 < len(standalone.strip()) <= 600:
            return standalone.strip()
        return None

    @staticmethod
    def fallback_question(question: str, history: list[dict]) -> str:
        """Used only when the rewrite fails: a short follow-up gets the last user question in front."""
        if len(question.split()) > 6:
            return question
        for message in reversed(history):
            if message["role"] == "user":
                return f"{message['content']} ({question})"
        return question

    # ---------- Step 2: which reports matter most ----------

    @staticmethod
    def pick_focus_reports(question: str, years: set[int]) -> set[str]:
        """Reports that get more pages. Every report is still searched."""
        all_reports = set(REPORT_FILES)

        if len(years) != 1:  # no year, or several years (comparison)
            return all_reports
        if not years.issubset(YEAR_TO_REPORT):  # future year (forecast) or very old year
            return all_reports
        if WIDE_QUESTION_RE.search(question):
            return all_reports

        return {YEAR_TO_REPORT[year] for year in years}

    # ---------- Step 3: search one report ----------

    @staticmethod
    def build_queries(question: str) -> list[str]:
        """The question itself, and the same question without years (report is already filtered)."""
        queries = [question]
        without_years = re.sub(r"\bFY\s*", "", YEAR_RE.sub(" ", question), flags=re.IGNORECASE)
        without_years = re.sub(r"\s+", " ", without_years).strip()
        if len(without_years.split()) >= 3 and without_years != question:
            queries.append(without_years)
        return queries

    async def search_report(self, report: str, queries: list[str], vectors: list[list[float]]) -> list[dict]:
        """Hybrid search inside one report. Returns unique chunks, best first."""
        report_filter = f"source_pdf eq '{report}'"
        result_lists = await asyncio.gather(
            *[
                ai_search_client.search(
                    query, vector, top_k=settings.RETRIEVAL_CHUNKS_PER_QUERY, filter=report_filter
                )
                for query, vector in zip(queries, vectors)
            ]
        )

        merged, seen = [], set()
        longest = max(len(hits) for hits in result_lists)
        for position in range(longest):  # take rank 1 of every query, then rank 2, ...
            for hits in result_lists:
                if position < len(hits):
                    hit = hits[position]
                    chunk_key = (hit["page_start"], hit["page_end"])
                    if chunk_key not in seen:
                        seen.add(chunk_key)
                        merged.append(hit)
        return merged

    # ---------- Step 4: chunks -> best pages ----------

    def keyword_score(self, key: tuple[str, int], query_terms: set[str]) -> float:
        counts = self.page_terms[key]
        total_pages = len(self.pages)
        score = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf:
                df = self.doc_freq[term]
                idf = math.log(1 + (total_pages - df + 0.5) / (df + 0.5))
                score += idf * tf / (tf + 1.2)
        return score

    async def embed_missing_pages(self, keys: list[tuple[str, int]]):
        """Embed pages we have not seen before. Vectors are kept, so each page is embedded once."""
        missing = [key for key in keys if key not in self.page_vectors]
        if not missing:
            return
        vectors = await azure_openai_client.embed([self.pages[key][:PAGE_EMBED_CHARS] for key in missing])
        for key, vector in zip(missing, vectors):
            self.page_vectors[key] = vector

    async def pick_pages(
        self,
        report: str,
        chunks: list[dict],
        query_vector: list[float],
        query_terms: set[str],
        how_many: int,
    ) -> list[tuple[tuple[str, int], float]]:
        """The best pages of one report, as [((pdf, page), score)]."""
        chunk_rank: dict[tuple[str, int], int] = {}  # page -> rank of the best chunk holding it
        for rank, chunk in enumerate(chunks):
            for page in range(chunk["page_start"], chunk["page_end"] + 1):
                key = (report, page)
                if key in self.pages and key not in chunk_rank:
                    chunk_rank[key] = rank

        candidates = list(chunk_rank)
        if not candidates:
            return []

        keyword_scores = {key: self.keyword_score(key, query_terms) for key in candidates}

        try:
            await self.embed_missing_pages(candidates)
            vector_scores = {key: dot(query_vector, self.page_vectors[key]) for key in candidates}
        except Exception as e:
            logger.error(f"Page embedding failed, using keyword + chunk rank only: {e}")
            vector_scores = {key: 0.0 for key in candidates}

        keyword_rank = rank_positions(keyword_scores)
        vector_rank = rank_positions(vector_scores)

        final = {}
        for key in candidates:
            final[key] = (
                1 / (RRF_K + vector_rank[key])
                + 1 / (RRF_K + keyword_rank[key])
                + 1 / (RRF_K + chunk_rank[key])
            )

        best = sorted(final, key=final.get, reverse=True)[:how_many]
        return [(key, final[key]) for key in best]

    def page_to_chunk(self, key: tuple[str, int], score: float) -> dict:
        pdf, page = key
        text = IMAGE_FILE_RE.sub("]", self.pages[key])
        image_ids = IMAGE_ID_RE.findall(text)
        return {
            "source_pdf": pdf,
            "page_start": page,
            "page_end": page,
            "text": text,
            "image_ids": image_ids,
            "images": [
                {"image_id": image_id, "path": self.image_paths[image_id]}
                for image_id in image_ids
                if image_id in self.image_paths
            ],
            "score": score,
        }

    # ---------- The one function the API calls ----------

    async def retrieve(self, question: str, history: list[dict] | None = None) -> dict:
        """Returns {"question": standalone question, "chunks": [one chunk per PDF page]}."""
        standalone = await self.rewrite_question(question, history or [])
        years = find_years(standalone)
        focus = self.pick_focus_reports(standalone, years)
        logger.info(f"Years found: {sorted(years)} | focus reports: {sorted(focus)}")

        queries = self.build_queries(standalone)
        vectors = await azure_openai_client.embed(queries)
        query_terms = set(tokenize(standalone))

        # Every report is searched, so every report is represented in the answer
        per_report_chunks = await asyncio.gather(
            *[self.search_report(report, queries, vectors) for report in REPORT_FILES]
        )

        result = []
        for report, chunks in zip(REPORT_FILES, per_report_chunks):
            if not self.pages:
                result.extend(chunks)  # no page files: fall back to whole chunks
                continue

            how_many = (
                settings.RETRIEVAL_PAGES_FOCUS_REPORT
                if report in focus
                else settings.RETRIEVAL_PAGES_PER_REPORT
            )
            picked = await self.pick_pages(report, chunks, vectors[0], query_terms, how_many)
            # Pages of one report are shown in page order
            for key, score in sorted(picked, key=lambda item: item[0][1]):
                result.append(self.page_to_chunk(key, score))

        pages = ", ".join(f"{c['source_pdf'][14:21]} p{c['page_start']}" for c in result)
        logger.info(f"Retrieved {len(result)} pages: {pages}")
        return {"question": standalone, "chunks": result}


retriever = Retriever()