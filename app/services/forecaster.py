import re

import numpy as np

YEAR_RANGE_RE = re.compile(r"(?<!\d)(20\d{2})\s*[-–/]\s*(\d{2})(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)20\d{2}(?!\d)")


def _start_year(label: str) -> int:
    return int(YEAR_RE.search(label).group())


def project(series: list[dict], periods: list[int]) -> tuple[list[dict], dict | None, list[str]]:
    """Project historical values forward with code (never with the LLM).

    series:  [{"metric", "unit", "points": [{"period": "2022-23", "value": 1200}, ...]}]
    periods: years the user asked for (2025, 2026). With range labels like "2024-25",
             a requested 2025 means the financial year ending 2025 ("2024-25").
    Returns (tables, chart, warnings). The chart is for the first usable series.
    """
    tables, chart, warnings = [], None, []

    for s in series:
        metric = s.get("metric", "value")
        try:
            points = sorted(s["points"], key=lambda p: _start_year(p["period"]))
            xs = np.array([_start_year(p["period"]) for p in points], dtype=float)
            ys = np.array([float(str(p["value"]).replace(",", "").replace("(", "-").replace(")", "")) for p in points])
        except (KeyError, ValueError, AttributeError):
            warnings.append(f"Could not read the historical data for {metric}")
            continue
        if len(points) < 3:
            warnings.append(f"Only {len(points)} data points for {metric}: not enough to project")
            continue

        labels = [p["period"] for p in points]
        range_style = bool(YEAR_RANGE_RE.search(labels[-1]))
        asked = periods or [int(xs[-1]) + (2 if range_style else 1)]

        slope, intercept = np.polyfit(xs, ys, 1)
        span = xs[-1] - xs[0]
        cagr = (ys[-1] / ys[0]) ** (1 / span) - 1 if ys[0] > 0 and ys[-1] > 0 else None

        rows, future_labels, linear, geometric = [], [], [], []
        for year in asked:
            x = year - 1 if range_style else year
            label = f"{year - 1}-{str(year)[2:]}" if range_style else str(year)
            lin = float(slope * x + intercept)
            geo = float(ys[-1] * (1 + cagr) ** (x - xs[-1])) if cagr is not None else None
            future_labels.append(label)
            linear.append(lin)
            geometric.append(geo)
            rows.append([label, f"{lin:,.2f}", f"{geo:,.2f}" if geo is not None else "n/a"])

        unit = s.get("unit", "")
        tables.append(
            {
                "title": f"Projection (estimate, not from the report): {metric} {unit}".strip(),
                "columns": ["Period", "Linear trend", f"CAGR ({cagr * 100:.2f}% per year)" if cagr is not None else "CAGR"],
                "rows": rows,
                "derived_columns": ["Linear trend", f"CAGR ({cagr * 100:.2f}% per year)" if cagr is not None else "CAGR"],
            }
        )

        if chart is None:
            pad = [None] * (len(ys) - 1)
            chart = {
                "type": "line",
                "title": f"{metric}: actual vs projected",
                "y_label": unit,
                "labels": labels + future_labels,
                "derived": True,
                "series": [
                    {"name": "Actual", "values": [float(v) for v in ys] + [None] * len(rows)},
                    {"name": "Linear trend", "values": pad + [float(ys[-1])] + linear},
                ],
            }
            if cagr is not None:
                chart["series"].append({"name": "CAGR", "values": pad + [float(ys[-1])] + geometric})

    return tables, chart, warnings