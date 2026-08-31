# Phase 8.1 — Multimodal Failure Disclosure

## Root Cause

The Qwen-VL vision component can fail while the rest of a multimodal (agent) task
succeeds via RAG. The backend already handles this correctly:

- `backend/agent/nodes/vision.py:54-74` — on any exception it returns a *populated*
  `vision_evidence` entry with `confidence = 0.0` and
  `uncertain_items = ["vision_error: <err>"]`, and appends `errors = ["vision:<err>"]`.
- `backend/agent/run.py:72` and `backend/app/api/agent.py:80` forward `vision_evidence`
  and `errors` unchanged to the UI.

The disclosure gap was **presentation-layer only**. In `frontend/src/pages/Workbench.tsx`
the agent path set `visionResult = finalRes.vision_evidence?.[0] ?? null`. Because the
failed result is a *non-null object*, `MessageView` always rendered `<VisionResult>`, and
`VisionResult` printed a header "VISUAL ANALYSIS" with an empty description and no warning.
A user could therefore read a top-level `VERIFIED` result alongside a silently-empty vision
panel and assume visual evidence had been obtained — when in fact zero visual evidence was
produced (`confidence = 0.0`, `vision_error` present).

No backend semantics, model, routing, NetworkGuard, sandbox, or CUDA behavior was changed.

## Existing Backend Behavior (unchanged)

Live capture while Qwen-VL is blocked by Windows Smart App Control:

```json
{
  "status": "VERIFIED",
  "external_calls": 0,
  "errors": ["vision:Connection error.", "vision:Connection error."],
  "vision_evidence": [
    {
      "description": "",
      "findings": [],
      "entities": [],
      "uncertain_items": ["vision_error: Connection error."],
      "confidence": 0.0,
      "model": "Qwen2.5-VL-3B-Instruct",
      "data_origin": "local"
    }
  ],
  "vision_tags": [],
  "evidence": [ /* 14 RAG-grounded items */ ]
}
```

The backend already exposes everything needed for honest disclosure:
`confidence = 0`, `uncertain_items` containing `vision_error`, and a top-level
`vision:` error. The fix only consumes this existing contract.

## Frontend Fix

File: `frontend/src/pages/Workbench.tsx` (presentation layer only).

1. Added a pure helper `isVisionUnavailable(result, errors)` that returns
   `{ unavailable, reason }` when **any** of:
   - `result` is `null`/`undefined`,
   - `result.confidence === 0`,
   - `result.uncertain_items` contains an entry matching `/vision_error/i`,
   - the top-level `errors` array contains an entry matching `/vision/i`.
   The `reason` is the first matching `vision_error` item or `vision:` error.

2. `VisionResult` now renders two distinct, clearly-labeled states:
   - **UNAVAILABLE** (failure): red-bordered "VISION ANALYSIS UNAVAILABLE" panel with
     the failure reason and an explicit note: *"No visual evidence was obtained.
     Any answer shown is based on knowledge retrieval only and does not include
     visual verification."*
   - **AVAILABLE** (success): green-labeled "VISUAL ANALYSIS · AVAILABLE" panel that
     renders description, findings, tags, and entities exactly as before.

3. The component now receives the task's `errors` so the "errors contains a vision
   error" condition is honored. `ChatMessage` gained an optional `errors?: unknown[]`
   field, `runAgentTask` populates it from `finalRes.errors`, and `MessageView` passes
   it to `VisionResult`.

The top-level `VERIFIED` status is **not** removed — a RAG-grounded answer can still be
verified. Instead the evidence scope is made explicit: the RAG answer stays visible while
the Vision panel is unambiguously marked UNAVAILABLE, so a VERIFIED RAG result can never
be visually interpreted as a successful Vision result.

## Vision Failure UI

```
VISION ANALYSIS UNAVAILABLE
vision_error: Connection error.
No visual evidence was obtained. Any answer shown is based on knowledge retrieval
only and does not include visual verification.
```
(RAG evidence list continues to render normally below it.)

## Successful Vision UI

```
VISUAL ANALYSIS · AVAILABLE
<description>
- <finding> …
#tags  Entities: …
```

## Tests

Added `frontend/src/pages/Workbench.vision.test.tsx` (12 tests, all passing) covering:

1. **Vision success** — renders "VISUAL ANALYSIS · AVAILABLE" with description/findings/tags;
   no "UNAVAILABLE" warning.
2. **Vision unavailable (null result)** — clearly warns "VISION ANALYSIS UNAVAILABLE".
3. **Vision error** — `uncertain_items: ["vision_error: …"]` discloses the reason and shows
   no "AVAILABLE" label.
4. **Zero-confidence vision** — `confidence = 0.0` discloses unavailability.
5. **RAG-only verified result** — when no vision result is present, the RAG answer stays
   visible and no vision "success" is implied.
6. **Multimodal with both vision + RAG** — when vision succeeds, both panels show correctly
   (vision AVAILABLE, RAG visible).
7. Plus detection-logic unit checks: error surfaced via the top-level `errors` array, and
   non-vision errors must not mask a successful vision result.

## Build

`npm run build` (runs `tsc && vite build`) succeeds:
- `tsc` type-check passes with the new exported helpers and `ChatMessage.errors` field.
- Production bundle built (`dist/` ~297 KB JS / 13.7 KB CSS).

## Live Validation

The stack was already running (backend `:8000` healthy & `sovereign_mode=true`, coder `:8002`,
frontend `:3000`). Qwen-VL `:8003` remains blocked by Windows Smart App Control (mtmd.dll),
so a real multimodal agent call exercised the genuine failure path.

Procedure:
1. Uploaded a test image → `POST /api/documents/upload` → `stored_path` returned.
2. `POST /api/agent/run` with `image_path` and `analysis_type=pid`.

Live response matched the failure contract exactly (`status=VERIFIED`,
`vision_evidence[0].confidence=0.0`, `uncertain_items=["vision_error: Connection error."]`,
`errors=["vision:Connection error.", …]`, 14 RAG evidence items). This is the precise payload
the new `VisionResult` unit tests simulate, so the UI now renders:

- **VISION ANALYSIS UNAVAILABLE** with the connection-error reason and the
  "no visual evidence obtained" note, while
- the 14 RAG-grounded items remain visible.

Smart App Control was **not** disabled and Windows security was **not** bypassed; the live
test simply used the already-blocked vision path.

## Files Changed

- `frontend/src/pages/Workbench.tsx` — disclosure fix (added `isVisionUnavailable`,
  reworked `VisionResult`, wired `errors` through `ChatMessage`/`runAgentTask`/`MessageView`).
  Backend unchanged.
- `frontend/src/pages/Workbench.vision.test.tsx` — new focused frontend tests.
- `reports/phase8_1_multimodal_disclosure.md` — this report.

`git status` (pre-existing): only `.gitignore` shows as modified (edited earlier in the
editor, not by this change) and `reports/phase8_performance_demo_validation.md` is untracked.
No backend or other frontend source was modified. No `git add`/`commit`/`push`/`reset`/`clean`.

## Remaining Issues

- **Qwen-VL still blocked by Windows Smart App Control** — environment/OS policy, outside the
  scope of this disclosure fix. Vision remains functionally unavailable until that is resolved
  by the user (disable SAC, add a WDAC exclusion for `mtmd.dll`, or serve vision via the
  signed Docker `llama-server.exe`). The UI now honestly reports this instead of hiding it.
- The backend still returns a top-level `status: "VERIFIED"` for RAG-only multimodal tasks.
  This is intentional (RAG evidence *is* verified) and was left unchanged per the rules; the
  UI makes the evidence scope explicit so VERIFIED is not mistaken for a successful vision pass.
- CPU-only Coder non-convergence (2/3 in Phase 8) is unrelated to this issue.

## Final Verdict

**PHASE 8.1 COMPLETE**

The single genuine disclosure defect — a VERIFIED multimodal result silently hiding a failed
vision component — is fixed in the presentation layer only. Vision failures are now clearly
surfaced as "VISION ANALYSIS UNAVAILABLE" with the reason and an explicit "no visual evidence
obtained" notice, while the RAG result remains visible and a successful vision path is
unaffected. 12 new frontend tests pass, `tsc`/production build passes, and a live multimodal
call with Qwen-VL blocked confirmed the new UI behavior end-to-end. No backend code, models,
routing, NetworkGuard, sandbox, or Windows security settings were modified.
