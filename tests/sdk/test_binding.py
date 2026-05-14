"""Tests for agentpassport.identity.binding — domain ownership binding."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from agentpassport.identity.binding import (
    DomainBinding,
    bind_domain,
    verify_domain_binding,
    verify_domain_binding_attestation,
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
    def test_returns_domain_binding(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        assert isinstance(binding, DomainBinding)
        assert binding.agent_did == did
        assert binding.domain == "rufus.dev"
        assert binding.version == "1"
        assert binding.type == "domain"
        assert binding.issued_at > 0
        assert len(binding.signature_hex) == 128  # 64 bytes hex

    def test_strips_scheme_error(self, keypair):
        priv, pub, did = keypair
        with pytest.raises(ValueError, match="scheme"):
            bind_domain(priv, did, "https://rufus.dev")

    def test_strips_trailing_slash(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev/")
        assert binding.domain == "rufus.dev"

    def test_lowercases_domain(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "Rufus.DEV")
        assert binding.domain == "rufus.dev"


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_round_trip(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        restored = DomainBinding.from_dict(binding.to_dict())
        assert restored.agent_did == binding.agent_did
        assert restored.domain == binding.domain
        assert restored.issued_at == binding.issued_at
        assert restored.signature_hex == binding.signature_hex

    def test_to_json_is_valid(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        parsed = json.loads(binding.to_json())
        assert parsed["claim"]["domain"] == "rufus.dev"


# ---------------------------------------------------------------------------
# verify_domain_binding_attestation (offline)
# ---------------------------------------------------------------------------

class TestVerifyOffline:
    def test_valid_binding_verifies(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        assert verify_domain_binding_attestation(binding) is True

    def test_tampered_signature_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        tampered = DomainBinding(
            version=binding.version,
            type=binding.type,
            agent_did=binding.agent_did,
            domain=binding.domain,
            issued_at=binding.issued_at,
            signature_hex="ff" * 64,
        )
        assert verify_domain_binding_attestation(tampered) is False

    def test_wrong_did_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        priv2, pub2 = generate_keypair()
        did2 = did_from_public_key(pub2)
        tampered = DomainBinding(
            version=binding.version,
            type=binding.type,
            agent_did=did2,  # different DID
            domain=binding.domain,
            issued_at=binding.issued_at,
            signature_hex=binding.signature_hex,
        )
        assert verify_domain_binding_attestation(tampered) is False

    def test_wrong_domain_fails(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")
        tampered = DomainBinding(
            version=binding.version,
            type=binding.type,
            agent_did=binding.agent_did,
            domain="evil.dev",  # different domain
            issued_at=binding.issued_at,
            signature_hex=binding.signature_hex,
        )
        assert verify_domain_binding_attestation(tampered) is False


# ---------------------------------------------------------------------------
# verify_domain_binding (online — mocked)
# ---------------------------------------------------------------------------

class TestVerifyOnline:
    def test_valid_well_known_verifies(self, keypair):
        priv, pub, did = keypair
        binding = bind_domain(priv, did, "rufus.dev")

        mock_resp = MagicMock()
        mock_resp.read.return_value = binding.to_json().encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = verify_domain_binding(did, "rufus.dev")

        assert result is True

    def test_wrong_did_in_well_known_fails(self, keypair):
        priv, pub, did = keypair
        priv2, pub2 = generate_keypair()
        did2 = did_from_public_key(pub2)
        binding = bind_domain(priv, did, "rufus.dev")

        mock_resp = MagicMock()
        mock_resp.read.return_value = binding.to_json().encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = verify_domain_binding(did2, "rufus.dev")  # different DID

        assert result is False

    def test_network_error_returns_false(self, keypair):
        import urllib.error
        priv, pub, did = keypair

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = verify_domain_binding(did, "rufus.dev")

        assert result is False

    def test_invalid_json_returns_false(self, keypair):
        priv, pub, did = keypair

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = verify_domain_binding(did, "rufus.dev")

        assert result is False
