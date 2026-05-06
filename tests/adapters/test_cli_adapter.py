from aps_adapters.cli import CliAdapter
from aps_sdk.types import Intent, TaskEnvelope


async def test_cli_adapter_echo():
    adapter = CliAdapter(command_template="echo {params.msg}")
    task = TaskEnvelope(intent=Intent(type="echo", params={"msg": "hello"}))
    result = await adapter.execute(task)
    assert result["output"] == "hello"
    assert result["exit_code"] == 0
