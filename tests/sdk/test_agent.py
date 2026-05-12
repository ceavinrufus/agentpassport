from aps_sdk.agent import Agent
from aps_sdk.types import Intent, TaskEnvelope


def test_agent_registers_capability():
    agent = Agent(name="test-agent")

    @agent.capability("search")
    async def handle_search(task: TaskEnvelope) -> dict:
        return {"results": ["a", "b"]}

    assert "search" in agent.capabilities


def test_agent_has_did():
    agent = Agent(name="test-agent")
    assert agent.did.startswith("did:key:z")


async def test_agent_handles_task():
    agent = Agent(name="test-agent")

    @agent.capability("echo")
    async def handle_echo(task: TaskEnvelope) -> dict:
        return {"echo": task.intent.params.get("msg")}

    task = TaskEnvelope(intent=Intent(type="echo", params={"msg": "hello"}))
    result = await agent.handle(task)
    assert result == {"echo": "hello"}
