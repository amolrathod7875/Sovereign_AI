"""Provenance and evidence trackers."""
from .evidence import Evidence
from .provenance import ProvenanceTracker

def create_evidence(**kwargs) -> Evidence:
    """Create a structured evidence object."""
    return Evidence(**kwargs)
