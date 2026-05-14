"""Tests for agentpassport.identity.binding — ownership binding."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from agentpassport.identity.binding import (
    Binding,
    BindingDocument,
    bind_domain,
    verify_binding_attestation,
    verify_domain_binding,
)
from agentpassport.identity.did import did_from_public_key, generate_keypair


@pytest.fixture
def keypair():
    priv, pub = generate_keypair()
    return priv[:32], pub, did_from_public_key(pub)


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
# BindingDocument
# ---------------------------------------------------------------------------

class TestBindingDocument:
    def test_add_and_serialize(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        doc = BindingDocument(version="1")
        doc.add(binding)
        d = doc.to_dict()
        assert d["version"] == "1"
        assert len(d["bindings"]) == 1
        assert d["bindings"][0]["type"] == "domain"

    def test_multiple_bindings(self, keypair):
        priv, pub, did = keypair
        b1 = bind_domain(priv, did, "rufus.dev")
        b2 = bind_domain(priv, did, "rufus.io")
        doc = BindingDocument(version="1")
        doc.add(b1)
        doc.add(b2)
        assert len(doc.domain_bindings()) == 2

    def test_round_trip(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        doc = BindingDocument(version="1")
        doc.add(binding)
        restored = BindingDocument.from_dict(json.loads(doc.to_json()))
        assert len(restored.bindings) == 1
        assert restored.bindings[0].agent_did == did
        assert restored.bindings[0].claim["domain"] == "rufus.dev"


# ---------------------------------------------------------------------------
# verify_binding_attestation (offline)
# ---------------------------------------------------------------------------

class TestVerifyOffline:
    def test_valid_binding_verifies(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        assert verify_binding_attestation(binding) is True

    def test_expired_binding_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev", expires_at=int(time.time()) - 1)
        assert verify_binding_attestation(binding) is False

    def test_not_yet_expired_passes(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev", expires_at=int(time.time()) + 9999)
        assert verify_binding_attestation(binding) is True

    def test_tampered_signature_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        tampered = Binding(
            type=binding.type,
            agent_did=binding.agent_did,
            claim=binding.claim,
            issued_at=binding.issued_at,
            expires_at=binding.expires_at,
            signature_hex="ff" * 64,
        )
        assert verify_binding_attestation(tampered) is False

    def test_wrong_did_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        priv2, pub2 = generate_keypair()
        did2 = did_from_public_key(pub2)
        tampered = Binding(
            type=binding.type,
            agent_did=did2,
            claim=binding.claim,
            issued_at=binding.issued_at,
            expires_at=binding.expires_at,
            signature_hex=binding.signature_hex,
        )
        assert verify_binding_attestation(tampered) is False

    def test_wrong_domain_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        tampered = Binding(
            type=binding.type,
            agent_did=binding.agent_did,
            claim={"domain": "evil.dev"},
            issued_at=binding.issued_at,
            expires_at=binding.expires_at,
            signature_hex=binding.signature_hex,
        )
        assert verify_binding_attestation(tampered) is False

    def test_unknown_type_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        tampered = Binding(
            type="unknown",
            agent_did=binding.agent_did,
            claim=binding.claim,
            issued_at=binding.issued_at,
            expires_at=binding.expires_at,
            signature_hex=binding.signature_hex,
        )
        assert verify_binding_attestation(tampered) is False


# ---------------------------------------------------------------------------
# verify_domain_binding (online — mocked)
# ---------------------------------------------------------------------------

class TestVerifyOnline:
    def _make_doc(self, keypair, domain="rufus.dev", expires_at=None):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, domain, expires_at=expires_at)
        doc = BindingDocument(version="1")
        doc.add(binding)
        return did, doc.to_json().encode()

    def _mock_resp(self, body: bytes):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_valid_well_known_verifies(self, keypair):
        did, body = self._make_doc(keypair)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_domain_binding(did, "rufus.dev") is True

    def test_multiple_bindings_finds_correct(self, keypair):
        priv, pub, did = keypair
        b1 = bind_domain(priv, did, "rufus.dev")
        b2 = bind_domain(priv, did, "rufus.io")
        doc = BindingDocument(version="1")
        doc.add(b1)
        doc.add(b2)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(doc.to_json().encode())):
            assert verify_domain_binding(did, "rufus.dev") is True

    def test_wrong_did_fails(self, keypair):
        did, body = self._make_doc(keypair)
        priv2, pub2 = generate_keypair()
        did2 = did_from_public_key(pub2)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_domain_binding(did2, "rufus.dev") is False

    def test_expired_binding_fails(self, keypair):
        did, body = self._make_doc(keypair, expires_at=int(time.time()) - 1)
        with patch("urllib.request.urlopen", return_value=self._mock_resp(body)):
            assert verify_domain_binding(did, "rufus.dev") is False

    def test_network_error_returns_false(self, keypair):
        import urllib.error
        priv, pub, did = keypair
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            assert verify_domain_binding(did, "rufus.dev") is False

    def test_invalid_json_returns_false(self, keypair):
        priv, pub, did = keypair
        with patch("urllib.request.urlopen", return_value=self._mock_resp(b"not json")):
            assert verify_domain_binding(did, "rufus.dev") is False
