from aps_adapters.mcp import McpAdapter


def test_mcp_adapter_instantiable():
    adapter = McpAdapter(command=["echo"])
    assert adapter.command == ["echo"]
