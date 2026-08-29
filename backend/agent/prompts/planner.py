"""Planner prompt + evidence-category catalogue.

The planner selects WHICH evidence categories are required for the task. It does
NOT blindly retrieve everything: it matches the user request against a known set
of evidence categories and emits a focused plan.
"""

# Each entry: category -> (document_type filter, retrieval query)
EVIDENCE_CATALOGUE = {
    "sensor_data": (
        "sensor_dataset",
        "R-1001 sensor dataset temperature pressure vibration threshold breach anomaly",
    ),
    "equipment_manual": (
        "equipment_manual",
        "R-1001 reactor equipment manual design operating parameters alarm setpoints",
    ),
    "operating_sop": (
        "operating_sop",
        "R-1001 operating SOP high-high temperature ESD reactor trip controlled shutdown",
    ),
    "preventive_maintenance_sop": (
        "preventive_maintenance_sop",
        "R-1001 preventive maintenance SOP corrective actions catalyst gasket thermowell approval gate",
    ),
    "inspection_report": (
        "inspection_report",
        "R-1001 inspection findings catalyst hotspot thermowell drift gasket weep abnormal conditions",
    ),
    "vendor_correspondence": (
        "vendor_correspondence",
        "R-1001 vendor correspondence recommendation spare parts catalyst gasket thermowell",
    ),
    "asset_profile": (
        "canonical_profile",
        "R-1001 alarm thresholds design operating parameters sensor definitions",
    ),
    "vision": (
        "pid_drawing",
        "P&ID equipment tags process streams relationships reactor vessel pump valve instrument",
    ),
}

# Keywords that signal a category is needed for a given request.
_CATEGORY_KEYWORDS = {
    "sensor_data": ["sensor", "operating data", "data", "temperature", "pressure", "vibration", "breach", "reading"],
    "equipment_manual": ["manual", "equipment", "design", "specification"],
    "operating_sop": ["sop", "operating", "procedure", "shutdown", "esd", "trip", "peration"],
    "preventive_maintenance_sop": ["maintenance", "pm", "corrective", "preventive"],
    "inspection_report": ["inspection", "finding", "inspect"],
    "vendor_correspondence": ["vendor", "recommend", "correspondence", "spare", "part"],
    "asset_profile": ["profile", "threshold", "alarm", "parameter"],
    "vision": ["image", "picture", "photo", "drawing", "diagram", "visual", "scan",
                "p&id", "pid", "inspect", "pdf", "document"],
}


def plan_for_request(request: str) -> list:
    """Return an ordered plan: list of {category, document_type, query}."""
    req = (request or "").lower()
    selected = []
    for category, (doc_type, query) in EVIDENCE_CATALOGUE.items():
        kws = _CATEGORY_KEYWORDS.get(category, [])
        if any(k in req for k in kws):
            selected.append({"category": category, "document_type": doc_type, "query": query})

    # Always ensure the core evidence chain is present for a maintenance-approval task.
    core = ["sensor_data", "equipment_manual", "operating_sop",
            "preventive_maintenance_sop", "inspection_report", "vendor_correspondence",
            "asset_profile"]
    for c in core:
        if not any(p["category"] == c for p in selected):
            doc_type, query = EVIDENCE_CATALOGUE[c]
            selected.append({"category": c, "document_type": doc_type, "query": query})

    # De-duplicate while preserving order.
    seen = set()
    ordered = []
    for p in selected:
        if p["category"] in seen:
            continue
        seen.add(p["category"])
        ordered.append(p)
    return ordered
