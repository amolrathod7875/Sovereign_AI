import os
import json
import pytest
from pathlib import Path
from app.ingestion import get_sha256, generate_document_id
from app.models import Document

def test_hashing_and_document_id(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Sovereign AI Test File")
    
    # Check hash
    file_hash = get_sha256(test_file)
    assert len(file_hash) == 64
    
    # Check document id
    doc_id = generate_document_id(file_hash)
    assert doc_id.startswith("DOC-")
    assert len(doc_id) == 16 # "DOC-" (4) + 12 chars
    
def test_pydantic_validation():
    # Test valid
    valid_data = {
        "document_id": "DOC-ABC123456789",
        "project_id": "PROJECT-XYZ",
        "source": {
            "filename": "test.pdf",
            "relative_path": "docs/test.pdf",
            "type": "local_project"
        },
        "file": {
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "sha256": "abc123456789def"
        },
        "metadata": {
            "title": "Test Title"
        },
        "content": {
            "pages": [
                {
                    "page_number": 1,
                    "elements": [
                        {"type": "paragraph", "text": "Hello World"}
                    ]
                }
            ]
        },
        "ingestion": {
            "parser": "docling_simulated",
            "pipeline_version": "0.1.0",
            "processed_at": "2026-08-28T12:00:00Z",
            "status": "processed"
        }
    }
    doc = Document(**valid_data)
    assert doc.document_id == "DOC-ABC123456789"
    
    # Test invalid (missing fields)
    with pytest.raises(ValueError):
        invalid_data = valid_data.copy()
        del invalid_data["document_id"]
        Document(**invalid_data)

@pytest.fixture(autouse=True)
def clean_data_dirs():
    import shutil
    from app.ingestion import RAW_DIR, PROCESSED_DIR, FAILED_DIR, MANIFEST_FILE
    # Clean before test
    for d in [RAW_DIR, PROCESSED_DIR, FAILED_DIR]:
        if d.exists():
            shutil.rmtree(d)
    if MANIFEST_FILE.exists():
        MANIFEST_FILE.unlink()
    yield
    # Clean after test
    for d in [RAW_DIR, PROCESSED_DIR, FAILED_DIR]:
        if d.exists():
            shutil.rmtree(d)
    if MANIFEST_FILE.exists():
        MANIFEST_FILE.unlink()

def test_first_ingestion(tmp_path):
    from app.ingestion import process_project
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    test_file = project_dir / "file1.txt"
    test_file.write_text("First file content")
    
    stats = process_project(project_dir)
    assert stats["processed"] == 1
    assert stats["duplicates"] == 0
    assert stats["failed"] == 0

def test_duplicate_ingestion(tmp_path):
    from app.ingestion import process_project
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    test_file = project_dir / "file1.txt"
    test_file.write_text("Duplicate file content")
    
    # First time
    stats1 = process_project(project_dir)
    assert stats1["processed"] == 1
    
    # Second time (exact same)
    stats2 = process_project(project_dir)
    assert stats2["processed"] == 0
    assert stats2["duplicates"] == 1

def test_same_content_different_filename(tmp_path):
    from app.ingestion import process_project
    project_dir1 = tmp_path / "TestProject1"
    project_dir1.mkdir()
    test_file1 = project_dir1 / "file1.txt"
    test_file1.write_text("Same content")
    
    stats1 = process_project(project_dir1)
    assert stats1["processed"] == 1
    
    project_dir2 = tmp_path / "TestProject2"
    project_dir2.mkdir()
    test_file2 = project_dir2 / "file2.txt"
    test_file2.write_text("Same content")
    
    stats2 = process_project(project_dir2)
    assert stats2["processed"] == 0
    assert stats2["duplicates"] == 1

def test_same_filename_different_content(tmp_path):
    from app.ingestion import process_project
    project_dir1 = tmp_path / "TestProject1"
    project_dir1.mkdir()
    test_file1 = project_dir1 / "file1.txt"
    test_file1.write_text("Content A")
    
    stats1 = process_project(project_dir1)
    assert stats1["processed"] == 1
    
    project_dir2 = tmp_path / "TestProject2"
    project_dir2.mkdir()
    test_file2 = project_dir2 / "file1.txt"
    test_file2.write_text("Content B")
    
    stats2 = process_project(project_dir2)
    assert stats2["processed"] == 1
    assert stats2["duplicates"] == 0

def test_delete_canonical_data_allows_reingestion(tmp_path):
    import shutil
    from app.ingestion import process_project, RAW_DIR, PROCESSED_DIR, FAILED_DIR, MANIFEST_FILE
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    test_file = project_dir / "file1.txt"
    test_file.write_text("Reset test content")
    
    stats1 = process_project(project_dir)
    assert stats1["processed"] == 1
    
    # Simulate a development reset without deleting the manifest
    for d in [RAW_DIR, PROCESSED_DIR, FAILED_DIR]:
        if d.exists():
            shutil.rmtree(d)
            
    assert MANIFEST_FILE.exists()
    
    # Second ingestion should process it again because canonical files are gone
    stats2 = process_project(project_dir)
    assert stats2["processed"] == 1
    assert stats2["duplicates"] == 0

def test_folder_ingestion(tmp_path):
    from app.ingestion import process_project
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    (project_dir / "folder1").mkdir()
    (project_dir / "folder1" / "fileA.txt").write_text("File A")
    (project_dir / "folder2").mkdir()
    (project_dir / "folder2" / "fileB.txt").write_text("File B")
    
    stats = process_project(project_dir)
    assert stats["processed"] == 2

