"""did:key 공개키 디코딩 — _b58encode/_b58decode 역연산, _decode_did_key 정확성."""
import os

import pytest

from ossverify.credential.vc_issuer import VCIssuer, _b58encode
from ossverify.credential.vc_verifier import _b58decode, _decode_did_key


# ── _b58encode / _b58decode 역연산 ─────────────────────────────────────────

def test_b58_roundtrip_simple():
    assert _b58decode(_b58encode(b"hello")) == b"hello"

def test_b58_roundtrip_32_bytes():
    data = bytes(range(32))
    assert _b58decode(_b58encode(data)) == data

def test_b58_roundtrip_leading_zeros():
    data = b"\x00\x00\x00test"
    assert _b58decode(_b58encode(data)) == data

def test_b58_roundtrip_all_zeros():
    data = b"\x00" * 10
    assert _b58decode(_b58encode(data)) == data

def test_b58_roundtrip_ed25519_multicodec():
    data = b"\xed\x01" + os.urandom(32)
    assert _b58decode(_b58encode(data)) == data


# ── _decode_did_key ────────────────────────────────────────────────────────

def test_decode_did_key_matches_issuer_public_key():
    issuer = VCIssuer()
    did = issuer.generate_did()
    decoded = _decode_did_key(did)
    assert len(decoded) == 32
    assert decoded == issuer._public_key_bytes

def test_decode_did_key_same_key_stable_did():
    # 키가 영속화된 이후 두 인스턴스는 동일한 DID를 반환해야 한다
    did_a = VCIssuer().generate_did()
    did_b = VCIssuer().generate_did()
    assert did_a == did_b
    assert _decode_did_key(did_a) == _decode_did_key(did_b)

def test_decode_did_key_invalid_method():
    with pytest.raises(ValueError, match="지원하지 않는"):
        _decode_did_key("did:web:example.com")

def test_decode_did_key_missing_prefix():
    with pytest.raises(ValueError):
        _decode_did_key("z6Mkabcdef")  # did:key: 없음

def test_decode_did_key_wrong_multicodec():
    # secp256k1 multicodec (0xe701) — Ed25519가 아님
    fake_multicodec = _b58encode(b"\xe7\x01" + os.urandom(33))
    with pytest.raises(ValueError, match="Ed25519"):
        _decode_did_key(f"did:key:z{fake_multicodec}")
