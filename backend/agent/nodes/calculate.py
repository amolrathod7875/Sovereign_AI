"""PYTHON_ANALYSIS node: perform numerical analysis in the local sandbox.

Demonstrates that the agent never asks the LLM to do arithmetic: the raw CSV is
analyzed by sandboxed Python for breach counts, first/last breach timestamps and
the temperature trend slope.
"""
import logging
import time
from typing import Dict, Any

from agent.tools.python_execute import python_execute
from agent.config import ASSETS_DIR
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)

_CODE = f"""
import csv

CSV = r"{str(ASSETS_DIR / 'sensors' / 'sensor_dataset.csv')}"
cols = {{
    "TI-1001_reactor_temp_C": 320.0,
    "PI-1001_reactor_pressure_bar": 21.0,
    "VI-1001_reactor_vibration_mm_s": 4.0,
}}
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
stat = {{c: {{"n":0, "first":None, "last":None, "max":float('-inf')}} for c in cols}}
for r in rows:
    ts = r.get("timestamp")
    for c, thr in cols.items():
        try:
            v = float(r[c])
        except (TypeError, ValueError):
            continue
        stat[c]["max"] = max(stat[c]["max"], v)
        if v >= thr:
            stat[c]["n"] += 1
            if stat[c]["first"] is None:
                stat[c]["first"] = ts
            stat[c]["last"] = ts

# Temperature trend slope (per reading) via least squares.
temp = [float(r["TI-1001_reactor_temp_C"]) for r in rows if r.get("TI-1001_reactor_temp_C")]
n = len(temp)
xs = list(range(n))
mx = sum(xs)/n; my = sum(temp)/n
slope = sum((x-mx)*(y-my) for x,y in zip(xs,temp)) / sum((x-mx)**2 for x in xs)

RESULT = {{"breach_summary": stat, "temperature_trend_slope_per_reading": round(slope,6), "n_rows": n}}
"""


def run(state: dict) -> dict:
    start = time.time()
    res = python_execute(_CODE, timeout=30)
    ok = res.get("exit_code") == 0
    py_result = None
    if ok and res.get("result"):
        try:
            import json
            py_result = json.loads(res["result"])
        except Exception:
            py_result = res.get("result")
    elif not ok:
        logger.error("python_analysis failed: %s", res.get("stderr"))

    calculations_update: Dict[str, Any] = {"python_analysis": py_result or {"raw": res}}
    return {
        "calculations": calculations_update,
        "errors": [] if ok else [f"python_analysis:{res.get('stderr')}"],
        "status": "CALCULATED",
        "trace": [trace_entry("python_analysis", "sandboxed_analysis", "python_execute",
                              elapsed_ms(start), "SUCCESS" if ok else "FAILED",
                              exit_code=res.get("exit_code"))],
    }
