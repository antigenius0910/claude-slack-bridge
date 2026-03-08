# Claude ↔ Slack Bridge

An MCP server that lets Claude Code pause and ask a human a question via Slack — then resume once you reply.

```
Claude Code  ──ask_on_slack──▶  Slack channel  ──your reply──▶  Claude Code resumes
```

---

## What It Does

When Claude is mid-task and needs a human decision — approval, clarification, a missing credential — it calls the `ask_on_slack` MCP tool. The bridge:

1. Posts the question to a Slack channel.
2. Blocks Claude's execution and waits.
3. Captures your reply — **you must reply in the Slack thread, not in the channel directly**.
4. Returns the reply text to Claude, which continues from where it left off.

Multiple concurrent requests are all handled on the same event loop; each is keyed to its Slack thread so replies are routed to the right waiter.

---

## Quickstart

### 1. Create a Slack app and get tokens

Follow [docs/slack-setup.md](docs/slack-setup.md) to create a Slack app, get your `xoxb-` and `xapp-` tokens, and invite the bot to a channel.

### 2. Clone and build

```bash
git clone https://github.com/your-username/claude-slack-bridge.git
cd claude-slack-bridge
docker build -t claude-slack-bridge .
```

### 3. Add `.mcp.json` to your Claude Code project

Create `.mcp.json` in the root of any project where you want Claude to be able to ask you questions:

```json
{
  "mcpServers": {
    "claude-slack-bridge": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "SLACK_BOT_TOKEN",
        "-e", "SLACK_APP_TOKEN",
        "-e", "SLACK_CHANNEL",
        "claude-slack-bridge"
      ],
      "env": {
        "SLACK_BOT_TOKEN": "xoxb-...",
        "SLACK_APP_TOKEN": "xapp-...",
        "SLACK_CHANNEL": "#your-project-channel",
        "TIMEOUT_LIMIT_MINUTES": "5"
      }
    }
  }
}
```

> **Important:** Add `.mcp.json` and `.env` to your `.gitignore` — they contain secrets.

That's it. Open the project in Claude Code and Claude will have access to `ask_on_slack`.

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | Bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | — | Socket Mode app token (`xapp-...`) |
| `SLACK_CHANNEL` | Yes | — | Target channel name or ID (e.g. `#my-project`) |
| `TIMEOUT_LIMIT_MINUTES` | No | `5` | Minutes to wait before timing out |

Set `SLACK_CHANNEL` per project so each project gets its own dedicated channel.

---

## The `ask_on_slack` Tool

Claude calls this tool automatically whenever it needs a human decision it cannot resolve from context.

**Input:** `message` — the question or statement to send.
**Output:** the text of your reply.
**Timeout:** raises an error if no reply arrives within `TIMEOUT_LIMIT_MINUTES`.

> **Reply in the thread.** When the message appears in Slack, click **Reply** to open the thread and type your answer there. A top-level message in the channel will not be picked up.

You can also prompt Claude explicitly:

> *"Ask on Slack whether you should overwrite the existing file."*

---

## Running With Docker Compose

If you want the bridge running as a persistent background service instead of spawned per-session:

```bash
cp .env.example .env   # fill in your tokens
docker compose up -d
```

The container restarts automatically (`restart: unless-stopped`) and uses Socket Mode — no public URL or inbound firewall rules needed.

---

## Project Structure

```
claude-slack-two-way/
├── src/
│   ├── main.py           # Entry point — wires components and starts the event loop
│   ├── mcp_server.py     # Registers the ask_on_slack MCP tool
│   ├── slack_client.py   # Slack Socket Mode connection and message posting
│   ├── message_broker.py # Async request/reply coordination (Future-based)
│   └── config.py         # Environment variable validation (pydantic-settings)
├── docs/
│   ├── slack-setup.md    # Step-by-step Slack app creation guide
│   └── mcp-client-setup.md  # How to wire .mcp.json in a Claude Code project
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## How It Works (Internals)

1. **FastMCP** exposes `ask_on_slack` over stdio (MCP transport).
2. **SlackClient** connects to Slack via Socket Mode (no public URL needed) and posts messages with `chat.postMessage`.
3. **MessageBroker** creates an `asyncio.Future` per request, keyed by the Slack thread timestamp (`ts`). It suspends the caller with `await` until the Future resolves or times out.
4. When a threaded reply arrives, `SlackClient` calls `MessageBroker.resolve()`, which sets the Future's result and unblocks the waiting tool call.
5. All components run on a **single shared asyncio event loop** — this is what makes the Future-based handoff work correctly.

See [docs/mcp-client-setup.md](docs/mcp-client-setup.md) for detailed client configuration.

---

## Requirements

- Docker
- A Slack workspace where you can create apps
- Claude Code (or any MCP-compatible client)

---

## License

MIT
