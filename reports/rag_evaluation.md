# RAG Evaluation Report - Sovereign AI Hybrid Retrieval (Phase 3)

## Method
- Embedding model (local, offline): `sentence-transformers/all-MiniLM-L6-v2`
- Qdrant collection (local embedded, zero network): `sovereign_knowledge`
- BM25 (bm25s, local): index at `D:\Sovereign_AI\data\rag\bm25`
- Hybrid fusion: semantic_weight=0.7, bm25_weight=0.3
- Filters: asset_tag / document_type supported on both semantic and lexical paths.
- `cross_document_ground_truth.json` was used ONLY for evaluation and was NOT ingested.

## Retrieval test queries (6 required)

Each query filtered by `asset_tag=R-1001`. Scores are the fused hybrid score (semantic 0.7 + bm25 0.3, min-max normalised per result set).

```

======================================================================
QUERY: What are the high-temperature limits for R-1001?
======================================================================

#1 score=0.7  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET EVIDENCE SUMMARY. Over 2160 hourly readings, TI-1001 reactor temperature reached a maximum of 322.4 C, exceeding the 320 C HIGH-HIGH and 310 C HIGH alarms. PI-1001 reactor pressure peaked at 22.4 bar (HIGH 21). VI-1001
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

#2 score=0.3389  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   R-1001 Reactor - Operating SOP Synthetic demo operating procedure ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Purpose: safe startup, operation and normal shutdown of R-1001 within synthetic l
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]

#3 score=0.3246  type=inspection_report  file=inspection_report.pdf  origin=synthetic_demo
   R-1001 INSPECTION FINDINGS SUMMARY. Abnormal conditions observed during the latest inspection: 2. Findings - Catalyst bed thermal hotspot: local bed temperature non-uniformity > 10 C; activity test - Thermowell drift: TI-1001 reads ~3.5 C a
   [Source: R-1001 / inspection_report] | [Document type: inspection_report] | [Source file: inspection_report.pdf] | [Data origin: synthetic_demo]

#4 score=0.3  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   R-1001 Reactor - Operating SOP Synthetic demo operating procedure ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Purpose: safe startup, operation and normal shutdown of R-1001 within synthetic l
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]

#5 score=0.2705  type=equipment_manual  file=manual.docx  origin=synthetic_demo
   R-1001 Reactor - Equipment Manual Synthetic demo manual (not real plant data) ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo 1. Identity Asset tag: R-1001 (from verified P&ID, 158.jpg, Hydrogen 
   [Source: R-1001 / equipment_manual] | [Document type: equipment_manual] | [Source file: manual.docx] | [Data origin: synthetic_demo]

#6 score=0.2419  type=maintenance_approval_note  file=approval_note.docx  origin=synthetic_demo
   R-1001 Reactor - Maintenance Approval Note Synthetic demo approval request ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Request ID: APP-2026-0042   |   Date: 2026-08-29   |   Status: PENDING A
   [Source: R-1001 / maintenance_approval_note] | [Document type: maintenance_approval_note] | [Source file: approval_note.docx] | [Data origin: synthetic_demo]

======================================================================
QUERY: What does the maintenance SOP require when reactor temperature exceeds the high-high threshold?
======================================================================

#1 score=0.7  type=preventive_maintenance_sop  file=pm_sop.docx  origin=synthetic_demo
   PREVENTIVE MAINTENANCE SOP for R-1001 reactor. Defines PM intervals and the corrective actions triggered by alarms/inspection: catalyst change-out, gasket replacement, thermowell recalibration, and the approval gate for shutdown work. R-100
   [Source: R-1001 / preventive_maintenance_sop] | [Document type: preventive_maintenance_sop] | [Source file: pm_sop.docx] | [Data origin: synthetic_demo]

#2 score=0.6505  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   R-1001 Reactor - Operating SOP Synthetic demo operating procedure ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Purpose: safe startup, operation and normal shutdown of R-1001 within synthetic l
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]

#3 score=0.4363  type=vendor_correspondence  file=vendor_correspondence.eml  origin=synthetic_demo
   Dear Maintenance Lead,  Thank you for sharing the R-1001 sensor trend (TI-1001, PI-1001, VI-1001) covering the last 90 days. The gradual, correlated rise in reactor temperature (approaching the 320 C high-high), pressure (toward 21 bar) and
   [Source: R-1001 / vendor_correspondence] | [Document type: vendor_correspondence] | [Source file: vendor_correspondence.eml] | [Data origin: synthetic_demo]

#4 score=0.4019  type=inspection_report  file=inspection_report.pdf  origin=synthetic_demo
   INSPECTION REPORT for R-1001 reactor (Hydrogen Production Plant, 158.jpg). Records abnormal conditions (findings) discovered during inspection: catalyst-bed thermal hotspot / catalyst deactivation, thermowell reading drift (~3.5 C above ref
   [Source: R-1001 / inspection_report] | [Document type: inspection_report] | [Source file: inspection_report.pdf] | [Data origin: synthetic_demo]

#5 score=0.3587  type=maintenance_approval_note  file=approval_note.docx  origin=synthetic_demo
   R-1001 Reactor - Maintenance Approval Note Synthetic demo approval request ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Request ID: APP-2026-0042   |   Date: 2026-08-29   |   Status: PENDING A
   [Source: R-1001 / maintenance_approval_note] | [Document type: maintenance_approval_note] | [Source file: approval_note.docx] | [Data origin: synthetic_demo]

#6 score=0.3  type=vendor_correspondence  file=vendor_correspondence.eml  origin=synthetic_demo
   Dear Maintenance Lead,  Thank you for sharing the R-1001 sensor trend (TI-1001, PI-1001, VI-1001) covering the last 90 days. The gradual, correlated rise in reactor temperature (approaching the 320 C high-high), pressure (toward 21 bar) and
   [Source: R-1001 / vendor_correspondence] | [Document type: vendor_correspondence] | [Source file: vendor_correspondence.eml] | [Data origin: synthetic_demo]

======================================================================
QUERY: What abnormal conditions were observed during the latest inspection?
======================================================================

#1 score=0.7  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   synthetic_demo_profile / inspection_criteria synthetic_demo_profile / inspection_criteria / max_vibration_mm_s: 4.0 synthetic_demo_profile / inspection_criteria / max_shell_temp_gradient_c: 15.0 synthetic_demo_profile / inspection_criteria 
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#2 score=0.4138  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET: hourly process readings for TI-1001 reactor temperature (deg C; alarm HIGH 310, HIGH-HIGH 320), PI-1001 reactor pressure (bar; alarm HIGH 21), VI-1001 reactor vibration (mm/s; alarm HIGH 4.0), LI-1001 reactor level (%
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

#3 score=0.3434  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   Breach events must be correlated with assets/R-1001/sensors/sensor_dataset.csv and, if a defect is suspected, with the Inspection Report and Maintenance SOP before any corrective work. DISCLAIMER: synthetic demo SOP.
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]

#4 score=0.3  type=inspection_report  file=inspection_report.pdf  origin=synthetic_demo
   R-1001 INSPECTION FINDINGS SUMMARY. Abnormal conditions observed during the latest inspection: 2. Findings - Catalyst bed thermal hotspot: local bed temperature non-uniformity > 10 C; activity test - Thermowell drift: TI-1001 reads ~3.5 C a
   [Source: R-1001 / inspection_report] | [Document type: inspection_report] | [Source file: inspection_report.pdf] | [Data origin: synthetic_demo]

#5 score=0.2666  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET: hourly process readings for TI-1001 reactor temperature (deg C; alarm HIGH 310, HIGH-HIGH 320), PI-1001 reactor pressure (bar; alarm HIGH 21), VI-1001 reactor vibration (mm/s; alarm HIGH 4.0), LI-1001 reactor level (%
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

#6 score=0.2665  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET: hourly process readings for TI-1001 reactor temperature (deg C; alarm HIGH 310, HIGH-HIGH 320), PI-1001 reactor pressure (bar; alarm HIGH 21), VI-1001 reactor vibration (mm/s; alarm HIGH 4.0), LI-1001 reactor level (%
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

======================================================================
QUERY: What parts did the vendor recommend?
======================================================================

#1 score=0.7  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   synthetic_demo_profile / spare_parts synthetic_demo_profile / spare_parts / [0] part: Catalyst charge (Ni-based) synthetic_demo_profile / spare_parts / [0] pn: HRS-CAT-22 synthetic_demo_profile / spare_parts / [1] part: Top-head gasket kit 
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#2 score=0.3906  type=vendor_correspondence  file=vendor_correspondence.eml  origin=synthetic_demo
   Vendor Correspondence (EML) Subject: RE: R-1001 temperature & vibration trend - recommendation From: HydroReactor Systems GmbH <support@hydroreactor.example> (SYNTHETIC vendor) To: Hydrogen Plant Maintenance Lead <maintenance@plant.example>
   [Source: R-1001 / vendor_correspondence] | [Document type: vendor_correspondence] | [Source file: vendor_correspondence.eml] | [Data origin: synthetic_demo]

#3 score=0.382  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   synthetic_demo_profile / inspection_criteria synthetic_demo_profile / inspection_criteria / max_vibration_mm_s: 4.0 synthetic_demo_profile / inspection_criteria / max_shell_temp_gradient_c: 15.0 synthetic_demo_profile / inspection_criteria 
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#4 score=0.361  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   synthetic_demo_profile / design synthetic_demo_profile / design / pressure_bar: 25.0 synthetic_demo_profile / design / temperature_c: 350.0
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#5 score=0.3405  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   synthetic_demo_profile / failure_modes synthetic_demo_profile / failure_modes / [0] mode: Catalyst deactivation leading to thermal hotspot synthetic_demo_profile / failure_modes / [0] likelihood: medium synthetic_demo_profile / failure_mode
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#6 score=0.3364  type=plant_context  file=plant_context.json  origin=synthetic_demo
   synthetic_context / key_units synthetic_context / key_units / [0]: R-1001 reactor synthetic_context / key_units / [1]: C-1001 compressor synthetic_context / key_units / [2]: P-1001 pump synthetic_context / key_units / [3]: E-1005 heat excha
   [Source: R-1001 / plant_context] | [Document type: plant_context] | [Source file: plant_context.json] | [Data origin: synthetic_demo]

======================================================================
QUERY: Does the sensor data show a threshold breach?
======================================================================

#1 score=0.7  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   Breach events must be correlated with assets/R-1001/sensors/sensor_dataset.csv and, if a defect is suspected, with the Inspection Report and Maintenance SOP before any corrective work. DISCLAIMER: synthetic demo SOP.
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]

#2 score=0.3  type=plant_context  file=plant_context.json  origin=synthetic_demo
   plant: Hydrogen Production Plant source_drawing: 158.jpg note: Only the plant name and drawing 158.jpg are public-P&ID-derived. All other context below is synthetic demo data used to frame the R-1001 asset chain.
   [Source: R-1001 / plant_context] | [Document type: plant_context] | [Source file: plant_context.json] | [Data origin: synthetic_demo]

#3 score=0.2871  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET EVIDENCE SUMMARY. Over 2160 hourly readings, TI-1001 reactor temperature reached a maximum of 322.4 C, exceeding the 320 C HIGH-HIGH and 310 C HIGH alarms. PI-1001 reactor pressure peaked at 22.4 bar (HIGH 21). VI-1001
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

#4 score=0.2866  type=canonical_profile  file=profile.json  origin=synthetic_demo+public_pid
   public_pid_identity public_pid_identity / asset_tag: R-1001 public_pid_identity / equipment_type: Reactor public_pid_identity / source_drawing: 158.jpg public_pid_identity / plant: Hydrogen Production Plant public_pid_identity / verificatio
   [Source: R-1001 / canonical_profile] | [Document type: canonical_profile] | [Source file: profile.json] | [Data origin: synthetic_demo+public_pid]

#5 score=0.2809  type=vendor_correspondence  file=vendor_correspondence.eml  origin=synthetic_demo
   Vendor Correspondence (EML) Subject: RE: R-1001 temperature & vibration trend - recommendation From: HydroReactor Systems GmbH <support@hydroreactor.example> (SYNTHETIC vendor) To: Hydrogen Plant Maintenance Lead <maintenance@plant.example>
   [Source: R-1001 / vendor_correspondence] | [Document type: vendor_correspondence] | [Source file: vendor_correspondence.eml] | [Data origin: synthetic_demo]

#6 score=0.2803  type=equipment_manual  file=manual.docx  origin=synthetic_demo
   R-1001 Reactor - Equipment Manual Synthetic demo manual (not real plant data) ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo 1. Identity Asset tag: R-1001 (from verified P&ID, 158.jpg, Hydrogen 
   [Source: R-1001 / equipment_manual] | [Document type: equipment_manual] | [Source file: manual.docx] | [Data origin: synthetic_demo]

======================================================================
QUERY: Should R-1001 be shut down?
======================================================================

#1 score=0.7  type=maintenance_approval_note  file=approval_note.docx  origin=synthetic_demo
   3. Approval Required This corrective maintenance requires operations approval because it takes R-1001 offline (production impact) and consumes charged spares. Expected approval: YES, subject to shutdown-window scheduling. DISCLAIMER: synthe
   [Source: R-1001 / maintenance_approval_note] | [Document type: maintenance_approval_note] | [Source file: approval_note.docx] | [Data origin: synthetic_demo]

#2 score=0.5266  type=sensor_dataset  file=sensor_dataset.csv  origin=synthetic_demo
   R-1001 SENSOR DATASET EVIDENCE SUMMARY. Over 2160 hourly readings, TI-1001 reactor temperature reached a maximum of 322.4 C, exceeding the 320 C HIGH-HIGH and 310 C HIGH alarms. PI-1001 reactor pressure peaked at 22.4 bar (HIGH 21). VI-1001
   [Source: R-1001 / sensor_dataset] | [Document type: sensor_dataset] | [Source file: sensor_dataset.csv] | [Data origin: synthetic_demo]

#3 score=0.498  type=maintenance_approval_note  file=approval_note.docx  origin=synthetic_demo
   R-1001 Reactor - Maintenance Approval Note Synthetic demo approval request ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Request ID: APP-2026-0042   |   Date: 2026-08-29   |   Status: PENDING A
   [Source: R-1001 / maintenance_approval_note] | [Document type: maintenance_approval_note] | [Source file: approval_note.docx] | [Data origin: synthetic_demo]

#4 score=0.4396  type=inspection_report  file=inspection_report.pdf  origin=synthetic_demo
   R-1001 INSPECTION FINDINGS SUMMARY. Abnormal conditions observed during the latest inspection: 2. Findings - Catalyst bed thermal hotspot: local bed temperature non-uniformity > 10 C; activity test - Thermowell drift: TI-1001 reads ~3.5 C a
   [Source: R-1001 / inspection_report] | [Document type: inspection_report] | [Source file: inspection_report.pdf] | [Data origin: synthetic_demo]

#5 score=0.4099  type=inspection_report  file=inspection_report.pdf  origin=synthetic_demo
   INSPECTION REPORT for R-1001 reactor (Hydrogen Production Plant, 158.jpg). Records abnormal conditions (findings) discovered during inspection: catalyst-bed thermal hotspot / catalyst deactivation, thermowell reading drift (~3.5 C above ref
   [Source: R-1001 / inspection_report] | [Document type: inspection_report] | [Source file: inspection_report.pdf] | [Data origin: synthetic_demo]

#6 score=0.3978  type=operating_sop  file=operating_sop.docx  origin=synthetic_demo
   R-1001 Reactor - Operating SOP Synthetic demo operating procedure ASSET: R-1001  |  PLANT: Hydrogen Production Plant (158.jpg)  |  DATA ORIGIN: synthetic_demo Purpose: safe startup, operation and normal shutdown of R-1001 within synthetic l
   [Source: R-1001 / operating_sop] | [Document type: operating_sop] | [Source file: operating_sop.docx] | [Data origin: synthetic_demo]
```

## Evidence recovery (ground-truth driven)

| Evidence required | Result | Expected doc types | Top retrieved (type/score) |
|---|---|---|---|
| sensor anomaly | PASS | sensor_dataset | sensor_dataset(0.7), sensor_dataset(0.3), sensor_dataset(0.1061) |
| inspection finding | PASS | inspection_report | inspection_report(0.7), inspection_report(0.3083), inspection_report(0.3) |
| SOP requirement | PASS | operating_sop, preventive_maintenance_sop | preventive_maintenance_sop(0.7), operating_sop(0.6511), vendor_correspondence(0.4392) |
| vendor recommendation | PASS | vendor_correspondence | canonical_profile(0.7), maintenance_history_summary(0.3914), vendor_correspondence(0.3426) |
| shutdown requirement | PASS | maintenance_approval_note, operating_sop, preventive_maintenance_sop | operating_sop(0.7), maintenance_approval_note(0.6271), sensor_dataset(0.6122) |
| approval requirement | PASS | maintenance_approval_note | maintenance_approval_note(0.7), maintenance_approval_note(0.3), preventive_maintenance_sop(0.2883) |

## Overall: ALL EVIDENCE RECOVERED

## Expected agent outcome (from ground truth)
- expected_approval: `True`
- scenario: Gradual, correlated rise in reactor temperature (TI-1001), pressure (PI-1001) and vibration (VI-1001) over ~35 days, breaching the 320 C high-high temperature alarm, 21 bar pressure-high and 4.0 mm/s vibration-high. Evidence points to catalyst deactivation (thermal hotspot) plus thermowell drift and a top-head gasket weep. Inspection confirms; vendor recommends catalyst + gasket replacement and thermowell recalibration; a controlled shutdown and maintenance approval are required.

## Provenance example (returned with every chunk)
```
[Source: R-1001 / preventive_maintenance_sop]
[Document type: preventive_maintenance_sop]
[Source file: pm_sop.docx]
[Data origin: synthetic_demo]
```

## Security note
- No cloud APIs, no external embedding service, no external document processing.
- Embeddings generated locally via sentence-transformers (offline HF cache).
- Qdrant runs in local embedded (on-disk) mode; BM25 index persisted locally.
- External network calls during this run: ZERO.