# PID_Dataset

## Overview

A collection of **P&ID (Piping & Instrumentation Diagram)** images sourced from
industry and web scraping, intended to train ML/CV algorithms that **automate the
digitization of P&IDs** (detection and matching of piping / instrument symbols).

- **Source:** academic / industry dataset (contact `mgupta70@asu.edu`).
- **Relevance to Sovereign AI:** this is the "engineering drawings" input class used
  by the project's `MULTIMODAL_ANALYSIS` task and **Demo 3** (local vision workflow).
  The Qwen2.5-VL model can consume these JPGs directly for description / symbol
  identification without any training.

## Directory Structure

Total: ~5,500 files.

| Folder | Contents | Purpose |
|---|---|---|
| `0__raw_data/` | `sheets/` — 92 `.jpg`; `labels/` — 93 `.txt` | Raw P&ID pages + their symbol annotations |
| `1__processed_data/` | `crops/` — 765 `.jpg`; `labels/` — 766 `.txt` | Symbol-level crops + annotations (detection training set) |
| `2__Stage-1/` | `1__Pretrained_models/` (28 `.weights`, 44 `.txt`, 20 `.png`); `2__Sampling_methods/` (64 files); `3__Psuedolabels/` (18 files) | **Symbol detection** stage (Darknet/YOLO-style weights) |
| `3__Stage-2/` | `1_1__Train_data/anchor/` — 3,166 `.jpg`; `1_2__Trained_Weights/triplet_30_v1.pth`; `2__Test_data/100_classes_data_sheets_wise/` — 547 files across 100 classes; 2 notebooks | **Siamese network + Triplet loss** symbol matching/retrieval stage |
| `Readme.txt` | 1 file | Dataset description |

## Pipeline Implemented

1. **Stage 1 — Symbol detection**
   Detect symbols in raw P&IDs, produce cropped symbols + pseudo-labels.
   (Artifacts: Darknet `.weights`, sampling visualizations, pseudo-labels.)

2. **Stage 2 — Symbol matching / retrieval**
   A Siamese network trained with triplet loss learns to match a cropped
   symbol to its class.
   - `1_Siamese_network_model_architecture_Train.ipynb` — training
   - `2_Siamese_network_with_Triplet_loss_model_Inference.ipynb` — inference
   - Trained weights: `triplet_30_v1.pth`

## How This Maps to Sovereign AI

| Sovereign AI concept | PID_Dataset counterpart |
|---|---|
| `MULTIMODAL_ANALYSIS` task | P&ID JPGs (raw sheets + crops) |
| Demo 3 (engineering drawing) | `0__raw_data/sheets/*.jpg` as vision input |
| Vision model | `models/qwen-vision/` (Qwen2.5-VL 3B + mmproj) |
| Local embeddings / RAG | *Not applicable* — this is a training set, not a knowledge base |

## Caveats

- Stage-1 weights are **Darknet `.weights`** (legacy format); conversion required
  if they are ever reused.
- No explicit train/validation split manifest; the Stage-2 test set is small
  (~5–6 sheets per class across 100 classes).
- This dataset **does not** unblock the deferred embeddings/RAG workstream — it
  feeds the vision/multimodal workflow instead.

## Suggested Next Step

Validate Demo 3 immediately: run Qwen2.5-VL (`scripts/serve_model.py` on `:8003`)
over a few `0__raw_data/sheets/*.jpg` P&IDs and prompt for description / symbol
identification. No data preparation or training required.
