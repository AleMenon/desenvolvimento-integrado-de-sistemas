"""TASK-25: regression tests for evidence integrity and release verification.

These tests use synthetic fixtures; they do not claim to have executed the
real Python/C++ servers, Moodle submission or a second person's review.
"""
import hashlib
import json
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from scripts.task25_release import verify_release
from scripts.task25_validate import verify_image_report, verify_png


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _fixture(tmp_path):
    clients = {}
    records = []
    for i in range(3):
        cid = f"client-{i}"
        submissions = []
        for n in range(15):
            sid = f"signal-{i}-{n}"
            submissions.append({"signal_id": sid})
            for impl in ("python", "cpp"):
                records.append({"implementation": impl, "client_id": cid,
                                "signal_id": sid, "status": "completed",
                                "model_id": "demo_identity_3",
                                "metadata": {"client_id": cid, "signal_id": sid},
                                "image": {"shape": [1, 3], "vector": [1.0, 2.0, 3.0]}})
        clients[cid] = {"client_id": cid, "status": "completed",
                        "signal_count": 15, "submissions": submissions}
    execution = {"schema_version": 1, "status": "completed", "client_count": 3,
                 "total_signals": 45, "total_http_submissions": 90, "clients": clients}
    images = {"schema_version": 1, "experiment_status": "completed",
              "image_count": 90, "total_records": 90, "failed_count": 0,
              "pending_count": 0, "reconstructions": records}
    _write_json(tmp_path / "execution.json", execution)
    _write_json(tmp_path / "images.json", images)
    return tmp_path / "execution.json", tmp_path / "images.json"


def test_valid_paired_images_and_three_clients(tmp_path):
    result = verify_image_report(*_fixture(tmp_path))
    assert result["image_count"] == 90
    assert result["images_python"] == result["images_cpp"] == 45


def test_incomplete_images_fail(tmp_path):
    a, b = _fixture(tmp_path)
    data = json.loads(b.read_text())
    data["reconstructions"].pop()
    _write_json(b, data)
    with pytest.raises(ValueError, match="Missing reconstructed records"):
        verify_image_report(a, b)


def test_numeric_disagreement_is_detected(tmp_path):
    a, b = _fixture(tmp_path)
    data = json.loads(b.read_text())
    data["reconstructions"][1]["image"]["vector"] = [99.0, 2.0, 3.0]
    _write_json(b, data)
    with pytest.raises(ValueError, match="numeric discrepancy"):
        verify_image_report(a, b)


def png_fixture():
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    body = zlib.compress(b"\0\0\0\0")
    return header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", body) + chunk(b"IEND", b"")


def test_png_integrity_detects_corruption(tmp_path):
    path = tmp_path / "plot.png"
    content = png_fixture()
    path.write_bytes(content)
    verify_png(path)
    corrupt = bytearray(content)
    corrupt[-17] ^= 1
    path.write_bytes(corrupt)
    with pytest.raises(ValueError, match="CRC mismatch"):
        verify_png(path)


def test_release_hashes_verify_and_detect_tampering(tmp_path):
    path = tmp_path / "release.zip"
    data = b"hello"
    manifest = {"schema_version": 1, "task": "TASK-25", "git_sha": "abc",
                "draft": False, "validated_by": ["A", "B"],
                "sha256": {"README.md": hashlib.sha256(data).hexdigest()}}
    with zipfile.ZipFile(path, "w") as stream:
        stream.writestr("README.md", data)
        stream.writestr("release_manifest.json", json.dumps(manifest))
    assert verify_release(path)["files"] == 1
    with zipfile.ZipFile(path, "w") as stream:
        stream.writestr("README.md", b"tampered")
        stream.writestr("release_manifest.json", json.dumps(manifest))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_release(path)


def test_release_duplicate_entries_rejected(tmp_path):
    path = tmp_path / "duplicated.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(path, "w") as stream:
            stream.writestr("README.md", b"same")
            stream.writestr("README.md", b"same")
            stream.writestr("release_manifest.json", "{}")
    with pytest.raises(ValueError, match="duplicate"):
        verify_release(path)
