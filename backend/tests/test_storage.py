import pytest

from app.services.storage import guess_mime, is_image, safe_filename


def test_safe_filename_strips_paths():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\x\\report.pdf") != ""
    assert "/" not in safe_filename("a/b/c.txt")


def test_safe_filename_sanitises():
    assert safe_filename("my file (1).png") == "my_file_1_.png"
    assert safe_filename("") == "file"
    assert safe_filename("....") == "file"


def test_guess_mime():
    assert guess_mime("photo.PNG") == "image/png"
    assert guess_mime("doc.docx").startswith("application/vnd.openxmlformats")
    assert guess_mime("unknown.xyz") == "application/octet-stream"


def test_is_image():
    assert is_image("a.jpg")
    assert not is_image("a.pdf")
