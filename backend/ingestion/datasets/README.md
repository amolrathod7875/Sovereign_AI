# Datasets

This directory is used for local dataset storage and management, particularly for training, evaluation, and fine-tuning models.

## P&ID Dataset
The actual training dataset for P&IDs (e.g., `PID_Dataset`) should be placed here locally.
- **Purpose**: It is used for model training/evaluation.
- **Separation**: This dataset is entirely separate from enterprise/project data (which goes into `data/incoming/`).
- **Git Safety**: Large datasets should NOT be committed to the repository. Ensure they remain ignored by Git.
