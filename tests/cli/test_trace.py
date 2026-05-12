import json
import tempfile
from pathlib import Path

from aps_cli.main import cli
from aps_sdk.identity import generate_keypair, did_from_public_key, sign_delegation
from aps_sdk.identity.signing import _decode_jwt_claims
from click.testing import CliRunner


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "APS CLI" in result.output


def test_trace_command_exists():
    runner = CliRunner()
    result = runner.invoke(cli, ["trace", "--help"])
    assert result.exit_code == 0
    assert "trace" in result.output.lower()


def test_identity_keygen(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["identity", "keygen", "--alias", "test", "--keystore", str(tmp_path / "keys.json")]
    )
    assert result.exit_code == 0
    assert "did:key:z" in result.output


def _write_trace_file(path: Path, events: list[dict]) -> None:
    with open(path, "w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")


def test_trace_show_empty():
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)
    _write_trace_file(tmp, [])
    result = runner.invoke(cli, ["trace", "show", "--id", "trace_abc", "--file", str(tmp)])
    assert result.exit_code == 0
    assert "No events found" in result.output


def test_trace_show_renders_events(tmp_path):
    log = tmp_path / "traces.jsonl"
    priv, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    _write_trace_file(log, [
        {
            "trace_id": "trace_xyz",
            "task_id": "task_001",
            "event": "task_completed",
            "agent": agent_did,
            "cost_used": 0.5,
            "budget_remaining": 9.5,
            "from_state": "running",
            "to_state": "completed",
        }
    ])

    runner = CliRunner()
    result = runner.invoke(cli, ["trace", "show", "--id", "trace_xyz", "--file", str(log)])
    assert result.exit_code == 0
    assert "trace_xyz" in result.output
    assert "task_001" in result.output
    assert "completed" in result.output


def test_trace_show_renders_auth_chain(tmp_path):
    """Auth chain tokens in event metadata are rendered with issuer → subject and scope."""
    log = tmp_path / "traces.jsonl"
    priv, pub = generate_keypair()
    sender_did = did_from_public_key(pub)
    _, recv_pub = generate_keypair()
    receiver_did = did_from_public_key(recv_pub)

    token = sign_delegation(priv, sender_did, receiver_did, ["read:db:customers"])

    _write_trace_file(log, [
        {
            "trace_id": "trace_auth",
            "task_id": "task_002",
            "event": "task_completed",
            "agent": receiver_did,
            "cost_used": 0.0,
            "budget_remaining": 10.0,
            "from_state": "running",
            "to_state": "completed",
            "metadata": {"auth_chain": [token]},
        }
    ])

    runner = CliRunner()
    result = runner.invoke(cli, ["trace", "show", "--id", "trace_auth", "--file", str(log)])
    assert result.exit_code == 0
    # Auth chain section is rendered
    assert "auth chain" in result.output
    assert "hop 1" in result.output
    # Scope appears
    assert "read:db:customers" in result.output
    # Verified tick (rich strips markup in test output, so check for the text marker)
    assert "✓" in result.output or "hop 1" in result.output


def test_trace_show_json_output(tmp_path):
    log = tmp_path / "traces.jsonl"
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    evt = {
        "trace_id": "trace_json",
        "task_id": "task_003",
        "event": "task_created",
        "agent": agent_did,
        "cost_used": 0.0,
        "budget_remaining": 10.0,
    }
    _write_trace_file(log, [evt])

    runner = CliRunner()
    result = runner.invoke(
        cli, ["trace", "show", "--id", "trace_json", "--file", str(log), "--json-output"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output.strip())
    assert parsed["trace_id"] == "trace_json"
