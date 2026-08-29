import pytest
import os
from pathlib import Path
from app.ingestion import process_project

def test_empty_file(tmp_path):
    project_dir = tmp_path / "TestEmpty"
    project_dir.mkdir()
    empty_file = project_dir / "empty.txt"
    empty_file.touch() # 0 bytes
    
    stats = process_project(project_dir)
    assert stats["discovered"] == 1
    assert stats["processed"] == 0
    assert stats["failed"] == 1
    assert "EMPTY_FILE" in stats["files"][0]["error"]

def test_large_file(tmp_path, monkeypatch):
    import app.ingestion
    monkeypatch.setattr(app.ingestion, "MAX_FILE_SIZE_BYTES", 10)
    
    project_dir = tmp_path / "TestLarge"
    project_dir.mkdir()
    large_file = project_dir / "large.txt"
    large_file.write_text("This file is larger than 10 bytes")
    
    stats = process_project(project_dir)
    assert stats["discovered"] == 1
    assert stats["processed"] == 0
    assert stats["failed"] == 1
    assert "FILE_TOO_LARGE" in stats["files"][0]["error"]

def test_extraction_validation(tmp_path, monkeypatch):
    import app.parsers
    
    def fake_parse(filepath, parser_name):
        return {"raw_text": ""}
    
    monkeypatch.setattr(app.ingestion, "process_file", fake_parse)
    
    project_dir = tmp_path / "TestExtraction"
    project_dir.mkdir()
    test_file = project_dir / "bad_extract.txt"
    test_file.write_text("Hello")
    
    stats = process_project(project_dir)
    assert stats["discovered"] == 1
    assert stats["processed"] == 0
    assert stats["failed"] == 1
    assert "EXTRACTION_EMPTY" in stats["files"][0]["error"]
