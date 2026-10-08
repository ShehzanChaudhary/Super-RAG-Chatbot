import json
import re

from app.adapters.llm.azure_openai_client import azure_openai_client
from app.adapters.logger.logger import logger
from app.core.config import settings
from app.prompts import get_prompt_template
from app.services.retriever import find_years

LAST_REPORT_YEAR = 2024  # the newest financial year in the reports
MAX_FORECAST_YEARS = 10

FORECAST_RE = re.compile(
    r"\b(forecast|predict|prediction|projection|projected|future|next year|"
    r"will be|would be|going to be)\b",
    re.IGNORECASE,
)
COMPARE_RE = re.compile(
    r"\b(compare|comparison|versus|vs|trend|growth|over the years|across|year[- ]on[- ]year|"
    r"yoy|difference|financial summary|all years|three years|3 years)\b",
    re.IGNORECASE,
)


def detect_intent(question: str) -> str:
    """'forecast', 'comparison' or 'qa'. Decided with simple rules, no LLM call."""
    years = find_years(question)
    if FORECAST_RE.search(question) or any(year > LAST_REPORT_YEAR for year in years):
        return "forecast"
    if COMPARE_RE.search(question) or len(years) >= 2:
        return "comparison"
    return "qa"


def format_indian(value: float, decimals: int = 0) -> str:
    """72867 -> 72,867 and 910863 -> 9,10,863 (the way the reports write numbers)."""
    sign = "-" if value < 0 else ""
    whole, _, fraction = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return sign + whole + ("." + fraction if fraction else "")


def parse_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def chart_block(chart: dict) -> str:
    """The chart as a fenced block. The frontend draws it, and it is saved with the message."""
    return "\n\n```chart\n" + json.dumps(chart, ensure_ascii=False) + "\n```"


class ChartService:
    """Collects exact numbers from the pages, then builds charts and forecasts in code."""

    # ---------- Step 1: numbers from the sources, every one checked ----------

    async def extract(self, question: str, chunks: list[dict], mode: str) -> dict | None:
        """Ask the LLM for the data points, then keep only the points that are really in the sources."""
        prompt = get_prompt_template("chart_extract.jinja2").render(
            question=question, chunks=chunks, mode=mode
        )
        for attempt in range(2):
            raw = ""
            try:
                raw = await azure_openai_client.chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                    max_tokens=settings.ANSWER_MAX_TOKENS,
                )
                data = parse_json(raw)
                if data is not None:
                    return self.verify(data, chunks)
            except Exception as e:
                logger.error(f"Chart extraction failed (attempt {attempt + 1}): {e}")
            logger.warning(f"Chart extraction gave no usable JSON (attempt {attempt + 1}): {raw!r}")
        return None

    @staticmethod
    def verify(data: dict, chunks: list[dict]) -> dict | None:
        """A point stays only if its text is written in the source page it points to."""
        series_list = []
        for series in data.get("series", [])[:5]:
            points, seen_years = [], set()
            for point in series.get("points", []):
                try:
                    source = int(point["source"])
                    text = str(point["text"]).strip()
                    years = find_years(str(point["year"]))
                    year = max(years) if len(years) == 1 else int(point["year"])
                    value = float(text.replace(",", ""))
                except (KeyError, ValueError, TypeError):
                    logger.warning(f"Chart point dropped (bad format): {point}")
                    continue

                if not 1 <= source <= len(chunks) or text not in chunks[source - 1]["text"]:
                    logger.warning(f"Chart point dropped (text not in source {source}): {point}")
                    continue
                if year in seen_years:
                    continue
                seen_years.add(year)
                points.append({"year": year, "value": value, "text": text, "source": source})

            if len(points) >= 2:
                series_list.append({"name": str(series.get("name", "")).strip(), "points": sorted(points, key=lambda p: p["year"])})

        if not series_list:
            return None
        return {
            "title": str(data.get("title", "")).strip(),
            "unit": str(data.get("unit", "")).strip(),
            "note": str(data.get("note", "")).strip(),
            "series": series_list,
        }

    # ---------- Step 2a: comparison chart ----------

    @staticmethod
    def comparison_chart(extraction: dict) -> dict:
        years = sorted({p["year"] for s in extraction["series"] for p in s["points"]})
        series = []
        for s in extraction["series"]:
            by_year = {p["year"]: p["value"] for p in s["points"]}
            series.append({"name": s["name"], "values": [by_year.get(y) for y in years], "dashed": False})
        return {
            "type": "bar",
            "title": extraction["title"],
            "unit": extraction["unit"],
            "labels": [f"FY{y}" for y in years],
            "series": series,
            "note": extraction["note"],
        }

    # ---------- Step 2b: forecast (the maths is done here, not by the LLM) ----------

    @staticmethod
    def forecast(question: str, extraction: dict) -> dict | None:
        """Linear trend and CAGR projection of the first series. Returns the chart and the facts."""
        history_series = [
            {**s, "points": [p for p in s["points"] if p["year"] <= LAST_REPORT_YEAR]}
            for s in extraction["series"]
        ]
        history_series = [s for s in history_series if len(s["points"]) >= 2]
        if not history_series:
            return None
        # The metric the question asks about is first; if it has too few years, take the longest one
        main = history_series[0] if extraction["series"][0]["name"] == history_series[0]["name"] else max(
            history_series, key=lambda s: len(s["points"])
        )

        # If the report itself states a value for the asked year (for example a FY2025 target),
        # this is not a forecast question: the normal answer will quote the report.
        asked_years = {y for y in find_years(question) if y > LAST_REPORT_YEAR}
        stated_years = {p["year"] for s in extraction["series"] for p in s["points"] if p["year"] > LAST_REPORT_YEAR}
        if asked_years & stated_years:
            logger.info(f"The report states a value for {sorted(asked_years & stated_years)}, no forecast needed")
            return None

        xs = [p["year"] for p in main["points"]]
        ys = [p["value"] for p in main["points"]]
        last_year = xs[-1]

        targets = sorted(y for y in find_years(question) if y > last_year) or [last_year + 1]
        if targets[-1] - last_year > MAX_FORECAST_YEARS:
            logger.warning(f"Forecast year too far: {targets[-1]}")
            return None
        horizon = list(range(last_year + 1, targets[-1] + 1))

        # Linear trend (least squares)
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sum((x - mean_x) ** 2 for x in xs)
        intercept = mean_y - slope * mean_x
        linear = {year: intercept + slope * year for year in horizon}

        # CAGR (only when the first and last values are positive)
        cagr_rate, cagr = None, {}
        if ys[0] > 0 and ys[-1] > 0 and xs[-1] > xs[0]:
            cagr_rate = (ys[-1] / ys[0]) ** (1 / (xs[-1] - xs[0])) - 1
            cagr = {year: ys[-1] * (1 + cagr_rate) ** (year - last_year) for year in horizon}

        decimals = 0 if max(ys) >= 1000 else 2
        labels = [f"FY{y}" for y in xs + horizon]

        def projection_values(projection: dict) -> list:
            values = [None] * len(xs) + [round(projection[y], decimals) for y in horizon]
            values[len(xs) - 1] = ys[-1]  # starts at the last real value, so the line is connected
            return values

        series = [{"name": main["name"], "values": ys + [None] * len(horizon), "dashed": False}]
        series.append({"name": "Linear trend (projection)", "values": projection_values(linear), "dashed": True})
        if cagr:
            series.append({"name": "CAGR (projection)", "values": projection_values(cagr), "dashed": True})

        chart = {
            "type": "line",
            "title": extraction["title"] or main["name"],
            "unit": extraction["unit"],
            "labels": labels,
            "series": series,
            "note": extraction["note"],
        }

        # Plain-text facts for the LLM to explain. These are the only numbers it may use.
        lines = [f"Metric: {main['name']} ({extraction['unit']})"]
        for p in main["points"]:
            lines.append(f"FY{p['year']} (reported, source {p['source']}): {p['text']}")
        lines.append(f"Method 1, linear trend: average change of {format_indian(slope, decimals)} per year")
        for year in horizon:
            lines.append(f"FY{year} linear trend projection: {format_indian(linear[year], decimals)}")
        if cagr:
            lines.append(f"Method 2, CAGR: {cagr_rate * 100:.2f}% per year from FY{xs[0]} to FY{last_year}")
            for year in horizon:
                lines.append(f"FY{year} CAGR projection: {format_indian(cagr[year], decimals)}")
        if extraction["note"]:
            lines.append(f"Note: {extraction['note']}")

        return {"chart": chart, "facts": "\n".join(lines), "targets": targets}

    # ---------- What answer.py calls ----------

    async def comparison(self, question: str, chunks: list[dict]) -> dict | None:
        extraction = await self.extract(question, chunks, mode="comparison")
        return self.comparison_chart(extraction) if extraction else None

    async def forecast_data(self, question: str, chunks: list[dict]) -> dict | None:
        extraction = await self.extract(question, chunks, mode="forecast")
        return self.forecast(question, extraction) if extraction else None


chart_service = ChartService()