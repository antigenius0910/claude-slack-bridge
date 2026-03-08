"""
slack_client.py — Slack integration layer.

Wraps slack_bolt's AsyncApp and AsyncSocketModeHandler to provide a clean
interface for posting messages and receiving threaded replies via Socket Mode.
No public URL or webhook configuration is required.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

# Type alias for the reply callback signature.
ReplyCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class SlackClient:
    """
    Manages the connection to Slack via Socket Mode.

    Responsibilities:
      - Authenticate with the Slack API using bot and app tokens.
      - Post messages to a configured channel and return the thread timestamp.
      - Listen for threaded replies and dispatch them to a registered callback.

    Args:
        bot_token:  The bot OAuth token (xoxb-...).
        app_token:  The app-level token for Socket Mode (xapp-...).
        channel:    The channel name or ID to post messages to.
        on_reply:   An async callback invoked with (thread_ts, reply_text)
                    whenever a valid threaded reply arrives.
    """

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        channel: str,
        on_reply: ReplyCallback,
    ) -> None:
        self._channel = channel
        self._on_reply = on_reply

        self._app = AsyncApp(token=bot_token)
        self._handler = AsyncSocketModeHandler(self._app, app_token)

        # Register the message event handler on construction.
        self._app.event("message")(self._handle_message)

    async def post_message(self, text: str) -> str:
        """
        Post a message to the configured Slack channel.

        Args:
            text: The message body to post.

        Returns:
            The timestamp (``ts``) of the posted message, which serves as the
            thread identifier for any replies.

        Raises:
            RuntimeError: If the Slack API call fails.
        """
        response = await self._app.client.chat_postMessage(
            channel=self._channel,
            text=f"<!channel> {text}",
            mrkdwn=True
        )
        if not response.get("ok"):
            raise RuntimeError(f"Slack API error posting message: {response.get('error')}")

        thread_ts: str = response["ts"]
        logger.info("Posted message to %s, thread_ts=%s", self._channel, thread_ts)
        return thread_ts

    async def start(self) -> None:
        """
        Start the Socket Mode connection and begin receiving events.

        This coroutine runs indefinitely; it should be gathered alongside other
        long-running coroutines (e.g. the MCP server) in ``asyncio.gather()``.
        """
        logger.info("Starting Slack Socket Mode handler.")
        await self._handler.start_async()

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """
        Internal event handler for Slack ``message`` events.

        Filters applied (both must pass for the reply to be dispatched):
          1. Ignores messages sent by bots (including this bot's own echoes).
          2. Ignores top-level messages (only threaded replies have ``thread_ts``).

        Args:
            event: The raw Slack event payload.
        """
        # Filter 1: Ignore bot messages (prevents self-echo loops).
        if event.get("bot_id"):
            return

        # Filter 2: Ignore top-level messages — we only care about thread replies.
        thread_ts: str | None = event.get("thread_ts")
        if not thread_ts:
            return

        reply_text: str = event.get("text", "")
        logger.info("Received reply in thread %s: %r", thread_ts, reply_text)

        # Dispatch to the broker using thread_ts (identifies the parent message).
        await self._on_reply(thread_ts, reply_text)
