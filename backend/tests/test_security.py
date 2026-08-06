import jwt as pyjwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_bad_hash():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_access_token_roundtrip():
    token = create_access_token(42, "admin")
    payload = decode_token(token, "access")
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_refresh_token_is_not_access_token():
    token = create_refresh_token(42)
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, "access")


def test_tampered_token_rejected():
    token = create_access_token(42, "staff") + "x"
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, "access")


def test_secret_encryption_roundtrip():
    secret = "ghp_example_token_1234"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret
    assert decrypt_secret("garbage") == ""
