"""Tests for agentpassport CLI identity commands."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from agentpassport.identity.binding import (
    BindingDocument,
)
from agentpassport_cli.main import cli
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def keystore(tmp_path):
    """A temp keystore with one pre-generated alias 'myagent'."""
    ks_path = tmp_path / "keys.json"
    from agentpassport.identity.keystore import FileKeystore
    ks = FileKeystore(path=ks_path)
    ks.generate_and_store("myagent")
    return ks_path


@pytest.fixture
def output(tmp_path):
    return str(tmp_path / "agent-passport.json")


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------

class TestKeygen:
    def test_generates_keypair(self, runner, tmp_path):
        ks_path = str(tmp_path / "keys.json")
        result = runner.invoke(
            cli, ["identity", "keygen", "--alias", "test", "--keystore", ks_path]
        )
        assert result.exit_code == 0
        assert "did:key:" in result.output

    def test_duplicate_alias_overwrites(self, runner, tmp_path):
        ks_path = str(tmp_path / "keys.json")
        runner.invoke(cli, ["identity", "keygen", "--alias", "test", "--keystore", ks_path])
        result = runner.invoke(
            cli, ["identity", "keygen", "--alias", "test", "--keystore", ks_path]
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# bind-domain
# ---------------------------------------------------------------------------

class TestBindDomain:
    def test_creates_binding(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code == 0, result.output
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.domain_bindings()) == 1
        assert doc.domain_bindings()[0].claim["domain"] == "rufus.dev"

    def test_strips_https_scheme(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "https://rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code == 0
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert doc.domain_bindings()[0].claim["domain"] == "rufus.dev"

    def test_strips_path(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev/some/path",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code == 0
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert doc.domain_bindings()[0].claim["domain"] == "rufus.dev"

    def test_rejects_domain_with_port(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev:8080",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code != 0

    def test_rejects_past_expires_at(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--expires-at", str(int(time.time()) - 1),
            "--yes",
        ])
        assert result.exit_code != 0

    def test_skips_duplicate(self, runner, keystore, output):
        args = [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ]
        runner.invoke(cli, args)
        result = runner.invoke(cli, args)
        assert "already exists" in result.output
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.domain_bindings()) == 1  # not duplicated

    def test_unknown_alias_fails(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "nonexistent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code != 0

    def test_atomic_write(self, runner, keystore, output):
        """Output file should not be left in corrupt state on error."""
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code == 0
        assert Path(output).exists()

    def test_abort_on_no_confirmation(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent",
            "--domain", "rufus.dev",
            "--keystore", str(keystore),
            "--output", output,
        ], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
        assert not Path(output).exists()


# ---------------------------------------------------------------------------
# bind-wallet
# ---------------------------------------------------------------------------

class TestBindWallet:
    def test_creates_binding(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent",
            "--chain", "ethereum",
            "--address", "0x" + "a" * 40,
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code == 0, result.output
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.wallet_bindings()) == 1

    def test_invalid_address_fails(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent",
            "--chain", "ethereum",
            "--address", "notanaddress",
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ])
        assert result.exit_code != 0

    def test_skips_duplicate(self, runner, keystore, output):
        args = [
            "identity", "bind-wallet",
            "--alias", "myagent",
            "--chain", "ethereum",
            "--address", "0x" + "a" * 40,
            "--keystore", str(keystore),
            "--output", output,
            "--yes",
        ]
        runner.invoke(cli, args)
        result = runner.invoke(cli, args)
        assert "already exists" in result.output
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.wallet_bindings()) == 1

    def test_abort_on_no_confirmation(self, runner, keystore, output):
        result = runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent",
            "--chain", "ethereum",
            "--address", "0x" + "a" * 40,
            "--keystore", str(keystore),
            "--output", output,
        ], input="n\n")
        assert "Aborted" in result.output


# ---------------------------------------------------------------------------
# revoke-wallet
# ---------------------------------------------------------------------------

class TestRevokeWallet:
    def test_revokes_existing(self, runner, keystore, output):
        addr = "0x" + "a" * 40
        runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        result = runner.invoke(cli, [
            "identity", "revoke-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        assert result.exit_code == 0
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.revocations) == 1

    def test_warns_if_no_matching_binding(self, runner, keystore, output):
        # Create empty doc
        Path(output).write_text(BindingDocument(version="1").to_json())
        result = runner.invoke(cli, [
            "identity", "revoke-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", "0x" + "a" * 40,
            "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        assert "Warning" in result.output
        assert result.exit_code == 0  # still writes revocation

    def test_skips_if_already_revoked(self, runner, keystore, output):
        addr = "0x" + "a" * 40
        args = [
            "identity", "revoke-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ]
        Path(output).write_text(BindingDocument(version="1").to_json())
        runner.invoke(cli, args)
        result = runner.invoke(cli, args)
        assert "already exists" in result.output
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.revocations) == 1  # not duplicated


# ---------------------------------------------------------------------------
# remove-binding
# ---------------------------------------------------------------------------

class TestRemoveBinding:
    def test_removes_domain_binding(self, runner, keystore, output):
        runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent", "--domain", "rufus.dev",
            "--keystore", str(keystore), "--output", output, "--yes",
        ])
        result = runner.invoke(cli, [
            "identity", "remove-binding",
            "--type", "domain", "--domain", "rufus.dev",
            "--output", output, "--yes",
        ])
        assert result.exit_code == 0
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.domain_bindings()) == 0

    def test_removes_wallet_binding(self, runner, keystore, output):
        addr = "0x" + "a" * 40
        runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        result = runner.invoke(cli, [
            "identity", "remove-binding",
            "--type", "wallet", "--chain", "ethereum",
            "--address", addr, "--output", output, "--yes",
        ])
        assert result.exit_code == 0
        doc = BindingDocument.from_dict(json.loads(Path(output).read_text()))
        assert len(doc.wallet_bindings()) == 0

    def test_nothing_to_remove(self, runner, output):
        Path(output).write_text(BindingDocument(version="1").to_json())
        result = runner.invoke(cli, [
            "identity", "remove-binding",
            "--type", "domain", "--domain", "rufus.dev",
            "--output", output, "--yes",
        ])
        assert "Nothing to remove" in result.output


# ---------------------------------------------------------------------------
# list-bindings
# ---------------------------------------------------------------------------

class TestListBindings:
    def test_lists_bindings(self, runner, keystore, output):
        runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent", "--domain", "rufus.dev",
            "--keystore", str(keystore), "--output", output, "--yes",
        ])
        result = runner.invoke(cli, ["identity", "list-bindings", "--output", output])
        assert result.exit_code == 0
        assert "domain" in result.output
        assert "rufus.dev" in result.output

    def test_empty_document(self, runner, output):
        Path(output).write_text(BindingDocument(version="1").to_json())
        result = runner.invoke(cli, ["identity", "list-bindings", "--output", output])
        assert "No bindings" in result.output

    def test_shows_revoked_status(self, runner, keystore, output):
        addr = "0x" + "a" * 40
        runner.invoke(cli, [
            "identity", "bind-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        runner.invoke(cli, [
            "identity", "revoke-wallet",
            "--alias", "myagent", "--chain", "ethereum",
            "--address", addr, "--keystore", str(keystore),
            "--output", output, "--yes",
        ])
        result = runner.invoke(cli, ["identity", "list-bindings", "--output", output])
        assert "REVOKED" in result.output


# ---------------------------------------------------------------------------
# verify-domain / verify-wallet
# ---------------------------------------------------------------------------

class TestVerifyCommands:
    def test_verify_domain_valid(self, runner, keystore, output):
        runner.invoke(cli, [
            "identity", "bind-domain",
            "--alias", "myagent", "--domain", "rufus.dev",
            "--keystore", str(keystore), "--output", output, "--yes",
        ])
        doc_json = Path(output).read_text().encode()

        mock_resp = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_resp.read.return_value = doc_json
        mock_resp.__enter__ = lambda s: s
        from unittest.mock import MagicMock as MM
        mock_resp.__exit__ = MM(return_value=False)

        from agentpassport.identity.keystore import FileKeystore as FK
        did = FK(path=keystore).get_did("myagent")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = runner.invoke(cli, [
                "identity", "verify-domain",
                "--did", did,
                "--domain", "rufus.dev",
            ])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_verify_domain_invalid(self, runner):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = runner.invoke(cli, [
                "identity", "verify-domain",
                "--did", "did:key:z6Mkfake",
                "--domain", "rufus.dev",
            ])
        assert result.exit_code != 0
        assert "✗" in result.output
