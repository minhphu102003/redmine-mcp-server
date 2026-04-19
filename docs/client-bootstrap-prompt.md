# Client Bootstrap Policy: Always Read Server Prompt First

This guide explains how to force MCP clients/agents to read a global prompt
before they execute any tool on this server.

## Global prompt exposed by this server

- Prompt name: `redmine_server_operating_prompt`
- Purpose: global operating protocol for all tools/resources.

## Important limitation

MCP servers expose prompts, but they **cannot force** the client runtime to
invoke a prompt automatically. Enforcement must be implemented in your client
or agent orchestrator.

## Required policy

Before the first tool call in each task/session:

1. `get_prompt("redmine_server_operating_prompt", {"user_goal": <goal>})`
2. Append returned prompt content into the agent context/instructions.
3. Only then allow tool execution.

For write actions (`create_*`, `update_*`, `delete_*`, `manage_time_entries`
with `create|update`), run step 1 again if task scope changes.

## Reference implementation (generic MCP client wrapper)

```python
class RedmineMcpPolicyClient:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self._bootstrapped = False
        self._bootstrap_goal = ""
        self._bootstrap_text = ""

    async def bootstrap(self, user_goal: str) -> str:
        prompt = await self.mcp.get_prompt(
            "redmine_server_operating_prompt",
            {"user_goal": user_goal},
        )
        # Depending on your MCP SDK, prompt messages may be in prompt.messages.
        text = "\n".join([m["content"]["text"] for m in prompt["messages"]])
        self._bootstrapped = True
        self._bootstrap_goal = user_goal
        self._bootstrap_text = text
        return text

    async def call_tool(self, tool_name: str, arguments: dict, user_goal: str):
        if (not self._bootstrapped) or (self._bootstrap_goal != user_goal):
            await self.bootstrap(user_goal)

        # Inject bootstrap text into your model/system context here.
        # Then execute tool call.
        return await self.mcp.call_tool(tool_name, arguments)
```

## Agent loop policy checklist

- [ ] Every new task starts with `redmine_server_operating_prompt`.
- [ ] Agent context always includes the latest bootstrap prompt text.
- [ ] Tool execution is blocked if bootstrap has not run.
- [ ] Task goal change invalidates old bootstrap and triggers re-bootstrap.
- [ ] Write tools require explicit constraints check from resources first.

## Suggested prompt+resource sequence

1. `redmine_server_operating_prompt`
2. Task-specific prompt (for selected tool)
3. Relevant resources (`issue-contract`, `workflow`, `time-entry/contract`, etc.)
4. Tool execution

