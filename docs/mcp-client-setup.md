# MCP Client Setup — Connecting Claude Code to the Bridge

This guide explains how to configure a Claude Code project to use the bridge via an `.mcp.json` file.

---

## How It Works

The bridge exposes a single MCP tool, `ask_on_slack`, over stdio.
Claude Code runs the Docker container as a subprocess and communicates with it over stdin/stdout — no ports, no webhooks needed.

---

## Step 1 — Build the Docker Image

From the root of this repository:

```bash
docker build -t claude-slack-bridge .
```

You only need to do this once (or after pulling updates).

---

## Step 2 — Add `.mcp.json` to Your Project

Create a `.mcp.json` file in the root of any Claude Code project where you want the tool available:

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
        "SLACK_CHANNEL": "#your-channel",
        "TIMEOUT_LIMIT_MINUTES": "5"
      }
    }
  }
}
```

Replace the token placeholders with your real values (see [slack-setup.md](slack-setup.md)).

> **Tip:** Set `SLACK_CHANNEL` per project so each project posts to its own dedicated channel.

---

## Step 3 — Add `.mcp.json` to `.gitignore`

Your `.mcp.json` contains secrets. Never commit it to version control:

```
# .gitignore
.mcp.json
.env
```

Store your tokens in a password manager or secret manager and paste them into `.mcp.json` locally.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | Bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | — | Socket Mode app token (`xapp-...`) |
| `SLACK_CHANNEL` | Yes | — | Channel name or ID (e.g. `#my-project`) |
| `TIMEOUT_LIMIT_MINUTES` | No | `5` | Minutes to wait for a reply before timing out |

---

## Verifying the Setup

1. Open a project that has `.mcp.json` in Claude Code.
2. Ask Claude: *"What MCP tools do you have available?"* — it should list `ask_on_slack`.
3. Ask Claude to use it: *"Ask on Slack whether I should use tabs or spaces."*
4. Check your Slack channel — the message should appear, and Claude will block until you reply in the thread.
