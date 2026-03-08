"""
main.py — Application entry point.

Wires all components together and runs the MCP server alongside the Slack
Socket Mode handler on a single shared asyncio event loop. Using a single
event loop is critical: Slack reply events resolve Futures on the same loop
that ``ask_on_slack`` is awaiting them on.

Startup sequence:
  1. Load and validate configuration from environment variables.
  2. Instantiate SlackClient, MessageBroker, MCPServer, and FastMCP.
  3. Register MCP tools.
  4. Run the MCP server and the Slack handler concurrently via asyncio.gather().
"""

import asyncio
import logging

from fastmcp import FastMCP

from config import Config
from message_broker import MessageBroker
from mcp_server import MCPServer
from slack_client import SlackClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_app(config: Config) -> tuple[FastMCP, SlackClient]:
    """
    Construct and wire all application components.

    Returns the FastMCP instance and SlackClient so that ``main`` can run
    them concurrently. All inter-component wiring (dependency injection) lives
    here, keeping each class free of global state.

    Args:
        config: Validated application configuration.

    Returns:
        A tuple of (mcp, slack_client) ready to be run concurrently.
    """
    # Build bottom-up: SlackClient <- MessageBroker <- MCPServer <- FastMCP.

    # MessageBroker.resolve is the callback SlackClient calls on every reply.
    # We create the broker first with a placeholder, then wire it after
    # SlackClient exists — but since MessageBroker only needs the post_message
    # callable (not the full client), we can defer the circular reference cleanly.

    # Step 1: Create a temporary reference holder so we can pass broker.resolve
    #         as the on_reply callback without a circular constructor dependency.
    broker_ref: list[MessageBroker] = []

    async def on_reply(thread_ts: str, reply_text: str) -> None:
        """Forward Slack replies to the broker once it is initialised."""
        await broker_ref[0].resolve(thread_ts, reply_text)

    # Step 2: SlackClient — needs bot_token, app_token, channel, and the callback.
    slack_client = SlackClient(
        bot_token=config.slack_bot_token,
        app_token=config.slack_app_token,
        channel=config.slack_channel,
        on_reply=on_reply,
    )

    # Step 3: MessageBroker — needs only the post_message callable.
    broker = MessageBroker(post_message=slack_client.post_message, timeout_minutes=config.timeout_limit_minutes)
    broker_ref.append(broker)  # Wire the forward reference.

    # Step 4: MCPServer — registers tools on a FastMCP instance.
    mcp_server = MCPServer(broker=broker)
    mcp = FastMCP(name="ClaudeSlackBridge")
    mcp_server.register(mcp)

    return mcp, slack_client


async def run(config: Config) -> None:
    """
    Run the MCP server and Slack handler concurrently on a single event loop.

    ``asyncio.gather`` keeps both coroutines alive. If either raises an
    unhandled exception the gather propagates it, bringing the process down
    so the container restarts cleanly.

    Args:
        config: Validated application configuration.
    """
    mcp, slack_client = build_app(config)

    logger.info("Starting Claude <-> Slack Two-Way Bridge.")
    await asyncio.gather(
        mcp.run_async(),       # FastMCP async entry point (MCP transport)
        slack_client.start(),  # Slack Socket Mode handler (runs indefinitely)
    )


if __name__ == "__main__":
    cfg = Config()  # type: ignore[call-arg]  # pydantic-settings reads from env
    asyncio.run(run(cfg))
