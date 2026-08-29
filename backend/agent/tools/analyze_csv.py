"""Tool: analyze_csv

Programmatic analysis of the R-1001 sensor dataset (sensor_dataset.csv).

Thresholds are NOT hard-coded: they are discovered from the asset's own
``profile.json`` (alarm_high / alarm_high_high per sensor definition). The agent
must *discover* temperature / pressure / vibration breaches from the actual data.

Computes, per signal: min, max, mean, threshold breaches (count + first/last
timestamp), and a linear trend slope over the measurement window.
"""
import csv
import json
import logging
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional

from agent.config import ASSETS_DIR

logger = logging.getLogger(__name__)


def _load_thresholds(profile_path: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    """Derive per-signal alarm thresholds from profile.json sensor_definitions."""
    if profile_path is None:
        profile_path = str(ASSETS_DIR / "profile.json")
    with open(profile_path, encoding="utf-8") as f:
        prof = json.load(f)
    sd = prof.get("synthetic_demo_profile", {}).get("sensor_definitions", [])
    out: Dict[str, Dict[str, float]] = {}
    for s in sd:
        tag = s.get("tag")
        measurement = (s.get("measurement") or "").lower()
        # Map each sensor definition to its actual CSV column (naming convention).
        if "temperature" in measurement:
            col = f"{tag}_reactor_temp_C"
        elif "pressure" in measurement:
            col = f"{tag}_reactor_pressure_bar"
        elif "vibration" in measurement:
            col = f"{tag}_reactor_vibration_mm_s"
        elif "level" in measurement:
            col = f"{tag}_reactor_level_pct"
        else:
            col = None
        if not col:
            continue
        out[col] = {
            "label": s.get("measurement", tag),
            "unit": s.get("unit", ""),
            "high": float(s.get("alarm_high", 0) or 0),
            "high_high": float(s.get("alarm_high_high", 0) or 0),
            "tag": tag,
        }
    # Fallback if sensor_definitions missing.
    if not out:
        out = {
            "TI-1001_reactor_temp_C": {"label": "reactor temperature", "unit": "C", "high": 310.0, "high_high": 320.0, "tag": "TI-1001"},
            "PI-1001_reactor_pressure_bar": {"label": "reactor pressure", "unit": "bar", "high": 21.0, "high_high": 25.0, "tag": "PI-1001"},
            "VI-1001_reactor_vibration_mm_s": {"label": "reactor vibration", "unit": "mm/s", "high": 4.0, "high_high": 6.0, "tag": "VI-1001"},
        }
    return out


def _trend_slope(values: List[float]) -> float:
    """Least-squares slope of a uniformly-sampled series (per reading)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    return (num / den) if den else 0.0


def analyze_csv(csv_path: Optional[str] = None,
                profile_path: Optional[str] = None,
                thresholds: Optional[Dict[str, Dict[str, float]]] = None
                ) -> Dict[str, Any]:
    """Analyze a sensor CSV. Returns structured numerical results."""
    if csv_path is None:
        csv_path = str(ASSETS_DIR / "sensors" / "sensor_dataset.csv")

    if thresholds is None:
        thresholds = _load_thresholds(profile_path)

    cols = list(thresholds.keys())

    rows: List[Dict[str, str]] = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    if not rows:
        return {"error": "no rows", "signals": {}}

    signals: Dict[str, Any] = {}
    for col in cols:
        series: List[float] = []
        ts_for_val: List[str] = []
        for r in rows:
            try:
                v = float(r.get(col))
            except (TypeError, ValueError):
                continue
            series.append(v)
            ts_for_val.append(r.get("timestamp", ""))
        if not series:
            continue
        th = thresholds[col]
        breaches_high = [(t, v) for t, v, in zip(ts_for_val, series) if v >= th["high"]]
        breaches_hh = [(t, v) for t, v, in zip(ts_for_val, series) if th["high_high"] and v >= th["high_high"]]
        signals[col] = {
            "label": th["label"],
            "unit": th["unit"],
            "tag": th["tag"],
            "high": th["high"],
            "high_high": th["high_high"],
            "min": round(min(series), 3),
            "max": round(max(series), 3),
            "mean": round(statistics.mean(series), 3),
            "n_readings": len(series),
            "n_breach_high": len(breaches_high),
            "n_breach_high_high": len(breaches_hh),
            "first_breach_high": breaches_high[0][0] if breaches_high else None,
            "last_breach_high": breaches_high[-1][0] if breaches_high else None,
            "first_breach_high_high": breaches_hh[0][0] if breaches_hh else None,
            "last_breach_high_high": breaches_hh[-1][0] if breaches_hh else None,
            "trend_slope_per_reading": round(_trend_slope(series), 6),
        }

    # Overall anomaly flag tally (if present)
    n_anom = sum(1 for r in rows if str(r.get("anomaly_flag", "0")) == "1")
    any_breach = any(s["n_breach_high"] > 0 for s in signals.values())

    return {
        "csv_path": csv_path,
        "n_rows": len(rows),
        "n_anomaly_flag": n_anom,
        "any_threshold_breach": any_breach,
        "breached_signals": [c for c, s in signals.items() if s["n_breach_high"] > 0],
        "signals": signals,
    }
