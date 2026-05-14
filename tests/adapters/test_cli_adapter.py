from agentpassport.types import Intent, TaskEnvelope
from agentpassport_adapters.cli import CliAdapter


async def test_cli_adapter_echo():
    adapter = CliAdapter(command_template="echo {params.msg}")
    task = TaskEnvelope(intent=Intent(type="echo", params={"msg": "hello"}))
    result = await adapter.execute(task)
    assert result["output"] == "hello"
    assert result["exit_code"] == 0
