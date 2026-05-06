from aps_cli.main import cli
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
    assert "did:aps:" in result.output
