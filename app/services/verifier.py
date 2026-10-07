import re

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_IMAGE_ID_RE = re.compile(r"\[IMAGE id=(\S+) page=")


def _norm(text: str) -> str:
    """Lowercase and drop markdown table pipes/emphasis so quotes compare fairly."""
    return re.sub(r"[\s|*_`]+", " ", text).strip().lower()


def _canon(number: str) -> float | None:
    try:
        return round(float(number.replace(",", "")), 6)
    except ValueError:
        return None


def _numbers_in(value) -> list[float]:
    return [c for c in (_canon(n) for n in _NUM_RE.findall(str(value))) if c is not None]


def verify(result: dict, pages: list[dict]) -> list[str]:
    """Check an answer against the pages it was written from. Returns a list of problems.

    - every citation quote must appear on the cited page (a wrong page number is fixed)
    - every number in tables / charts / forecast data must appear somewhere in the pages
    - every image id must belong to a retrieved page
    """
    problems = []
    normalized = {(p["source_pdf"], p["page"]): _norm(p["text"]) for p in pages}
    known_numbers = {c for p in pages for n in _NUM_RE.findall(p["text"]) if (c := _canon(n)) is not None}
    known_images = {i for p in pages for i in _IMAGE_ID_RE.findall(p["text"])}

    for cite in result.get("citations", []):
        pdf, page, quote = cite.get("source_pdf"), cite.get("page"), _norm(cite.get("evidence", ""))
        if not quote:
            problems.append(f"citation without evidence quote: {pdf} p.{page}")
        elif quote in normalized.get((pdf, page), ""):
            continue
        else:
            # The quote may be right but the page number wrong: look on the other pages
            actual = next((pg for (f, pg), t in normalized.items() if f == pdf and quote in t), None)
            if actual is not None:
                cite["page"] = actual
            else:
                problems.append(f"quote not found verbatim in {pdf} p.{page}: '{cite.get('evidence')}'")

    for table in result.get("tables", []):
        derived = set(table.get("derived_columns", []))
        for row in table.get("rows", []):
            for column, cell in zip(table["columns"][1:], row[1:]):
                if column in derived:
                    continue
                for n in _numbers_in(cell):
                    if n not in known_numbers:
                        problems.append(f"table value '{cell}' ({row[0]} / {column}) is not in the pages")

    chart = result.get("chart")
    if chart and not chart.get("derived"):
        for series in chart.get("series", []):
            for value in series.get("values", []):
                if value is not None and _canon(str(value)) not in known_numbers:
                    problems.append(f"chart value {value} ({series.get('name')}) is not in the pages")

    for series in result.get("series_for_forecast", []):
        for point in series.get("points", []):
            if any(n not in known_numbers for n in _numbers_in(point.get("value"))):
                problems.append(f"forecast input {point.get('value')} ({series.get('metric')} {point.get('period')}) is not in the pages")

    for image_id in result.get("image_ids", []):
        if image_id not in known_images:
            problems.append(f"image id {image_id} is not in the retrieved pages")

    return problems