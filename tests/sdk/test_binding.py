"""Tests for agentpassport.identity.binding — ownership binding."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from agentpassport.identity.binding import (
    Binding,
    BindingDocument,
    Revocation,
    bind_domain,
    bind_wallet,
    revoke_wallet,
    validate_address,
    verify_binding_attestation,
    verify_domain_binding,
    verify_revocation_attestation,
    verify_wallet_binding,
)
from agentpassport.identity.did import did_from_public_key, generate_keypair


@pytest.fixture
def keypair():
    priv, pub = generate_keypair()
    return priv[:32], pub, did_from_public_key(pub)


# ---------------------------------------------------------------------------
# validate_address
# ---------------------------------------------------------------------------

class TestValidateAddress:
    def test_valid_ethereum(self):
        validate_address("ethereum", "0xAbCdEf1234567890abcdef1234567890abcdef12")

    def test_invalid_ethereum(self):
        with pytest.raises(ValueError, match="Ethereum"):
            validate_address("ethereum", "notanaddress")

    def test_evm_alias_base(self):
        validate_address("base", "0x" + "a" * 40)

    def test_valid_solana(self):
        validate_address("solana", "4Nd1mBQtrMJVYVfKf2PX98" + "a" * 22)

    def test_invalid_solana(self):
        with pytest.raises(ValueError, match="Solana"):
            validate_address("solana", "0xinvalid")

    def test_valid_bitcoin_legacy(self):
        validate_address("bitcoin", "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf" + "Na")

    def test_valid_bitcoin_bech32(self):
        validate_address("bitcoin", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")

    def test_unknown_chain_passes(self):
        # Unknown chains pass through — don't block new chains
        validate_address("mychain", "anything_goes_here")


# ---------------------------------------------------------------------------
# bind_domain
# ---------------------------------------------------------------------------

class TestBindDomain:
    def test_returns_binding(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        assert isinstance(binding, Binding)
        assert binding.type == "domain"
        assert binding.agent_did == did
        assert binding.claim == {"domain": "rufus.dev"}
        assert binding.issued_at > 0
        assert binding.expires_at is None
        assert len(binding.signature_hex) == 128

    def test_with_expires_at(self, keypair):
        priv, pub, did = keypair
        exp = int(time.time()) + 86400
        binding = bind_domain(priv, did, "rufus.dev", expires_at=exp)
        assert binding.expires_at == exp

    def test_strips_scheme_error(self, keypair):
        priv, pub, did = keypair
        with pytest.raises(ValueError, match="scheme"):
            bind_domain(priv, did, "https://rufus.dev")

    def test_strips_trailing_slash(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev/")
        assert binding.claim["domain"] == "rufus.dev"

    def test_lowercases_domain(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "Rufus.DEV")
        assert binding.claim["domain"] == "rufus.dev"


# ---------------------------------------------------------------------------
# bind_wallet
# ---------------------------------------------------------------------------

class TestBindWallet:
    def test_returns_binding(self, keypair):
        priv, pub, did = keypair
        binding = bind_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        assert isinstance(binding, Binding)
        assert binding.type == "wallet"
        assert binding.agent_did == did
        assert binding.claim["chain"] == "ethereum"
        assert binding.claim["address"] == "0x" + "a" * 40
        assert binding.expires_at is None
        assert len(binding.signature_hex) == 128

    def test_with_expires_at(self, keypair):
        priv, pub, did = keypair
        exp = int(time.time()) + 86400
        binding = bind_wallet(priv, did, "ethereum", "0x" + "a" * 40, expires_at=exp)
        assert binding.expires_at == exp

    def test_invalid_address_raises(self, keypair):
        priv, pub, did = keypair
        with pytest.raises(ValueError):
            bind_wallet(priv, did, "ethereum", "notanaddress")

    def test_lowercases_chain(self, keypair):
        priv, pub, did = keypair
        binding = bind_wallet(priv, did, "ETHEREUM", "0x" + "a" * 40)
        assert binding.claim["chain"] == "ethereum"

    def test_solana_binding(self, keypair):
        priv, pub, did = keypair
        addr = "4Nd1mBQtrMJVYVfKf2PX98" + "a" * 22
        binding = bind_wallet(priv, did, "solana", addr)
        assert binding.claim["chain"] == "solana"
        assert binding.claim["address"] == addr


# ---------------------------------------------------------------------------
# revoke_wallet
# ---------------------------------------------------------------------------

class TestRevokeWallet:
    def test_returns_revocation(self, keypair):
        priv, pub, did = keypair
        rev = revoke_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        assert isinstance(rev, Revocation)
        assert rev.type == "wallet"
        assert rev.agent_did == did
        assert rev.claim["chain"] == "ethereum"
        assert rev.revoked_at > 0
        assert len(rev.signature_hex) == 128

    def test_invalid_address_raises(self, keypair):
        priv, pub, did = keypair
        with pytest.raises(ValueError):
            revoke_wallet(priv, did, "ethereum", "notanaddress")


# ---------------------------------------------------------------------------
# BindingDocument
# ---------------------------------------------------------------------------

class TestBindingDocument:
    def test_add_domain_and_wallet(self, keypair):
        priv, pub, did = keypair
        doc = BindingDocument(version="1")
        doc.add(bind_domain(priv, did, "rufus.dev"))
        doc.add(bind_wallet(priv, did, "ethereum", "0x" + "a" * 40))
        assert len(doc.domain_bindings()) == 1
        assert len(doc.wallet_bindings()) == 1

    def test_revoke_adds_to_revocations(self, keypair):
        priv, pub, did = keypair
        doc = BindingDocument(version="1")
        rev = revoke_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        doc.revoke(rev)
        assert len(doc.revocations) == 1

    def test_is_revoked_matches_correctly(self, keypair):
        priv, pub, did = keypair
        addr = "0x" + "a" * 40
        binding = bind_wallet(priv, did, "ethereum", addr)
        rev = revoke_wallet(priv, did, "ethereum", addr)
        doc = BindingDocument(version="1")
        doc.add(binding)
        doc.revoke(rev)
        assert doc.is_revoked(binding) is True

    def test_is_revoked_different_address(self, keypair):
        priv, pub, did = keypair
        binding = bind_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        rev = revoke_wallet(priv, did, "ethereum", "0x" + "b" * 40)
        doc = BindingDocument(version="1")
        doc.add(binding)
        doc.revoke(rev)
        assert doc.is_revoked(binding) is False

    def test_round_trip(self, keypair):
        priv, pub, did = keypair
        doc = BindingDocument(version="1")
        doc.add(bind_domain(priv, did, "rufus.dev"))
        doc.add(bind_wallet(priv, did, "ethereum", "0x" + "a" * 40))
        doc.revoke(revoke_wallet(priv, did, "ethereum", "0x" + "b" * 40))
        restored = BindingDocument.from_dict(json.loads(doc.to_json()))
        assert len(restored.bindings) == 2
        assert len(restored.revocations) == 1


# ---------------------------------------------------------------------------
# verify_binding_attestation
# ---------------------------------------------------------------------------

class TestVerifyBindingAttestation:
    def test_valid_domain(self, keypair):
        priv, pub, did = keypair
        assert verify_binding_attestation(bind_domain(priv, did, "rufus.dev")) is True

    def test_valid_wallet(self, keypair):
        priv, pub, did = keypair
        assert verify_binding_attestation(
            bind_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        ) is True

    def test_expired(self, keypair):
        priv, pub, did = keypair
        b = bind_domain(priv, did, "rufus.dev", expires_at=int(time.time()) - 1)
        assert verify_binding_attestation(b) is False

    def test_tampered_sig(self, keypair):
        priv, pub, did = keypair
        b = bind_domain(priv, did, "rufus.dev")
        tampered = Binding(b.type, b.agent_did, b.claim, b.issued_at, b.expires_at, "ff" * 64)
        assert verify_binding_attestation(tampered) is False

    def test_unknown_type(self, keypair):
        priv, pub, did = keypair
        b = bind_domain(priv, did, "rufus.dev")
        tampered = Binding(
            "unknown", b.agent_did, b.claim, b.issued_at, b.expires_at, b.signature_hex
        )
        assert verify_binding_attestation(tampered) is False


# ---------------------------------------------------------------------------
# verify_revocation_attestation
# ---------------------------------------------------------------------------

class TestVerifyRevocationAttestation:
    def test_valid_revocation(self, keypair):
        priv, pub, did = keypair
        rev = revoke_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        assert verify_revocation_attestation(rev) is True

    def test_tampered_revocation(self, keypair):
        priv, pub, did = keypair
        rev = revoke_wallet(priv, did, "ethereum", "0x" + "a" * 40)
        tampered = Revocation(rev.type, rev.agent_did, rev.claim, rev.revoked_at, "ff" * 64)
        assert verify_revocation_attestation(tampered) is False


# ---------------------------------------------------------------------------
# verify_domain_binding / verify_wallet_binding (online — mocked)
# ---------------------------------------------------------------------------

class TestVerifyOnline:
    def _mock_resp(self, body: bytes):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def _make_doc(self, keypair) -> tuple[str, bytes]:
        priv, pub, did = keypair
        doc = BindingDocument(version="1")
        doc.add(bind_domain(priv, did, "rufus.dev"))
        doc.add(bind_wallet(priv, did, "ethereum", "0x" + "a" * 40))
        return did, doc.to_json().encode()

    def test_valid_domain_binding(self, keypair):
        did, body = self._make_doc(keypair)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_domain_binding(did, "rufus.dev") is True

    def test_valid_wallet_binding(self, keypair):
        did, body = self._make_doc(keypair)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_wallet_binding(did, "ethereum", "0x" + "a" * 40, "rufus.dev") is True

    def test_revoked_wallet_binding_fails(self, keypair):
        priv, pub, did = keypair
        addr = "0x" + "a" * 40
        doc = BindingDocument(version="1")
        doc.add(bind_wallet(priv, did, "ethereum", addr))
        doc.revoke(revoke_wallet(priv, did, "ethereum", addr))
        with patch("urllib.request.urlopen", return_value=self._mock_resp(doc.to_json().encode())):
            assert verify_wallet_binding(did, "ethereum", addr, "rufus.dev") is False

    def test_wrong_did_fails(self, keypair):
        did, body = self._make_doc(keypair)
        priv2, pub2 = generate_keypair()
        did2 = did_from_public_key(pub2)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_domain_binding(did2, "rufus.dev") is False

    def test_network_error_returns_false(self, keypair):
        import urllib.error
        priv, pub, did = keypair
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            assert verify_domain_binding(did, "rufus.dev") is False

    def test_invalid_json_returns_false(self, keypair):
        priv, pub, did = keypair
        with patch("urllib.request.urlopen", return_value=self._mock_resp(b"not json")):
            assert verify_wallet_binding(did, "ethereum", "0x" + "a" * 40, "rufus.dev") is False
