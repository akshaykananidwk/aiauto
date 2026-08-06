"""Tests for the update system's safety-critical pure logic."""
import io
import tarfile

import pytest

from app.services.update import is_protected, safe_extract_tar

PROTECTED = [".env", "config.php", "storage", "uploads", "backups"]


def test_protected_exact_file():
    assert is_protected(".env", PROTECTED)
    assert is_protected("config.php", PROTECTED)


def test_protected_directory_contents():
    assert is_protected("storage/results/abc/img.png", PROTECTED)
    assert is_protected("uploads/report.pdf", PROTECTED)
    assert is_protected("backups/backup_1.zip", PROTECTED)


def test_similar_names_not_protected():
    assert not is_protected(".env.example", PROTECTED)
    assert not is_protected("storage_utils.py", PROTECTED)
    assert not is_protected("backend/app/main.py", PROTECTED)


def test_windows_separators_normalised():
    assert is_protected("storage\\results\\x.png", PROTECTED)


def _make_tarball(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_safe_extract_normal_archive(tmp_path):
    data = _make_tarball({"repo-abc123/README.md": b"hello", "repo-abc123/app/x.py": b"pass"})
    root = safe_extract_tar(data, tmp_path / "out")
    assert (root / "README.md").read_text() == "hello"
    assert (root / "app" / "x.py").exists()


def test_safe_extract_rejects_traversal(tmp_path):
    data = _make_tarball({"repo-abc123/../../evil.txt": b"pwned"})
    with pytest.raises(Exception):
        safe_extract_tar(data, tmp_path / "out")
    assert not (tmp_path.parent / "evil.txt").exists()
