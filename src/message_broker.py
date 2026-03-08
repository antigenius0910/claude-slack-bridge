"""
message_broker.py — Async bridge between MCP tool calls and Slack replies.

Each call to ``send_and_wait`` posts a message and suspends execution until a
threaded reply arrives or the 5-minute timeout expires. Multiple concurrent
calls are all pending simultaneously on the same event loop; each is keyed by
its unique thread timestamp so replies are routed to the correct waiter.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# Type alias matching SlackClient.post_message's signature.
PostMessageFn = Callable[[str], Coroutine[Any, Any, str]]

DEFAULT_TIMEOUT_MINUTES = 5


class MessageBroker:
    """
    Coordinates asynchronous request/reply cycles over Slack.

    Args:
        post_message: An async callable that sends a message to Slack and
                      returns the thread timestamp (``ts``) of the posted
                      message. In production this is ``SlackClient.post_message``.
        timeout_minutes: How long to wait for a reply before raising RuntimeError.
                         Defaults to DEFAULT_TIMEOUT_MINUTES.
    """

    def __init__(self, post_message: PostMessageFn, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES) -> None:
        self._post_message = post_message
        self._timeout_seconds = timeout_minutes * 60.0
        # Maps thread_ts -> Future that will be resolved with the reply text.
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def send_and_wait(self, message: str) -> str:
        """
        Post *message* to Slack and wait for a human reply in that thread.

        The calling coroutine suspends at ``await`` and the event loop remains
        free to process other requests and incoming Slack events while waiting.

        Args:
            message: The text to post to Slack.

        Returns:
            The text of the first threaded reply received.

        Raises:
            RuntimeError: If no reply arrives within 5 minutes.
        """
        thread_ts = await self._post_message(message)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[thread_ts] = future

        logger.info("Waiting for reply in thread %s (timeout=%.0fs)", thread_ts, self._timeout_seconds)

        try:
            reply = await asyncio.wait_for(future, timeout=self._timeout_seconds)
            logger.info("Got reply for thread %s", thread_ts)
            return reply
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"No reply received within {int(self._timeout_seconds // 60)} minutes "
                f"for thread {thread_ts}."
            )
        finally:
            # Always clean up stale futures, whether we succeeded, timed out,
            # or were cancelled externally.
            self._pending.pop(thread_ts, None)

    async def resolve(self, thread_ts: str, reply_text: str) -> None:
        """
        Resolve the pending Future for the given thread, unblocking the waiter.

        Called by ``SlackClient``'s reply callback whenever a valid threaded
        reply arrives. If no waiter exists for *thread_ts* (e.g. the request
        already timed out), the call is silently ignored.

        Args:
            thread_ts:  The timestamp of the parent (top-level) message.
            reply_text: The text of the reply to deliver to the waiter.
        """
        future = self._pending.get(thread_ts)
        if future is None:
            logger.debug("No pending request for thread %s — ignoring reply.", thread_ts)
            return

        if not future.done():
            future.set_result(reply_text)
            logger.info("Resolved Future for thread %s.", thread_ts)
