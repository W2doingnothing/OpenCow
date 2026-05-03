"""OpenCow programmatic facade -- the main entry point for the agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from loguru import logger

from opencow.agent.context import ContextBuilder
from opencow.bus.events import InboundMessage, OutboundMessage
from opencow.bus.queue import MessageBus
from opencow.command.router import CommandContext, CommandRouter
from opencow.command.builtin import register_builtin_commands
from opencow.config.loader import load_config, resolve_config_env_vars
from opencow.config.schema import Config
from opencow.providers.factory import make_chat_model
from opencow.session.manager import SessionManager
from opencow.tools.registry import ToolRegistry
from opencow.tools.filesystem import edit_file, list_dir, read_file, write_file
from opencow.tools.search import glob, grep
from opencow.tools.shell import exec_cmd
from opencow.tools.web import web_fetch, web_search
from opencow.utils.helpers import ensure_dir

_LLM_TIMEOUT_SECONDS = 120


class OpenCow:
    """Programmatic facade for running the opencow agent.

    Usage::

        cow = OpenCow.from_config()
        result = await cow.run("Hello, what can you do?")
    """

    def __init__(
        self,
        config: Config,
        *,
        chat_model: BaseChatModel | None = None,
    ) -> None:
        self.config = config
        self.workspace = config.workspace_path
        self._model_name = config.agents.defaults.model
        self._max_iterations = config.agents.defaults.max_tool_iterations

        ensure_dir(self.workspace)
        ensure_dir(self.workspace / "memory")

        self.chat_model = chat_model or make_chat_model(config)
        self.tools = self._build_tool_registry()

        db_path = str(self.workspace / "sessions.db")
        self.sessions = SessionManager(db_path)

        self.context_builder = ContextBuilder(
            self.workspace,
            timezone=config.agents.defaults.timezone,
        )

        self.commands = CommandRouter()
        register_builtin_commands(self.commands)

        self.bus = MessageBus()
        self._running = False

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
    ) -> OpenCow:
        """Create an OpenCow instance from a config file."""
        resolved = Path(config_path).expanduser().resolve() if config_path else None
        config = resolve_config_env_vars(load_config(resolved))
        return cls(config)

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(read_file)
        registry.register(write_file)
        registry.register(edit_file)
        registry.register(list_dir)
        registry.register(grep)
        registry.register(glob)
        registry.register(exec_cmd)
        registry.register(web_search)
        registry.register(web_fetch)
        return registry

    async def run(
        self,
        message: str,
        *,
        session_key: str = "cli:default",
        channel: str = "cli",
    ) -> str:
        msg = InboundMessage(
            text=message,
            channel=channel,
            chat_id=session_key.split(":", 1)[1] if ":" in session_key else "default",
        )
        result = await self._process_message(msg)
        return result.content if result else ""

    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """Process a single inbound message through the agent."""
        key = msg.session_key

        if self.commands.is_command(msg.text):
            ctx = CommandContext(msg=msg, raw=msg.text, loop=self)
            return await self.commands.dispatch(ctx)

        system_prompt = self.context_builder.build_system_prompt(channel=msg.channel)
        runtime_ctx = self.context_builder.build_runtime_context(
            channel=msg.channel,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
        )

        graph = self.sessions.get_graph(
            chat_model=self.chat_model,
            tools=self.tools.list_tools(),
            recursion_limit=self._max_iterations,
        )

        user_content = f"{runtime_ctx}\n\n{msg.text}"
        config_dict = {"configurable": {"thread_id": key}}

        try:
            result = await asyncio.wait_for(
                graph.ainvoke(
                    {
                        "messages": [("system", system_prompt), ("user", user_content)],
                        "session_key": key,
                        "iteration_count": 0,
                        "empty_response_count": 0,
                    },
                    config=config_dict,
                ),
                timeout=_LLM_TIMEOUT_SECONDS,
            )

            messages = result.get("messages", [])
            if messages:
                last = messages[-1]
                content = getattr(last, "content", str(last))
                if isinstance(content, list):
                    content = "".join(
                        b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in content
                    )
                # Reasoning models may return reasoning_content as the actual answer
                if not content:
                    reasoning = (getattr(last, "additional_kwargs", {}) or {}).get("reasoning_content", "")
                    content = reasoning or content
                # Reasoning models may return reasoning_content as the actual answer
                if not content:
                    content = reasoning or content
                return OutboundMessage(
                    content=str(content) if content else "",
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    session_key=key,
                )

        except asyncio.TimeoutError:
            msg_text = "Request timed out ({}s). Check your API key and network.".format(
                _LLM_TIMEOUT_SECONDS
            )
            print(f"\n[ERROR] {msg_text}", flush=True)
            logger.error(msg_text)
            return OutboundMessage(
                content=msg_text,
                channel=msg.channel,
                chat_id=msg.chat_id,
                session_key=key,
            )
        except Exception as e:
            msg_text = f"Agent error: {e}"
            print(f"\n[ERROR] {msg_text}", flush=True)
            logger.exception("Agent run failed for session {}", key)
            return OutboundMessage(
                content=msg_text,
                channel=msg.channel,
                chat_id=msg.chat_id,
                session_key=key,
            )

        return None

    async def serve(self) -> None:
        """Run the agent in interactive CLI mode."""
        from opencow.channels.cli_channel import CliChannel

        print(f"Model: {self._model_name}")
        print(f"Workspace: {self.workspace}")
        print()
        print("OpenCow ready. Type /help for commands, /stop to exit.")
        print()

        self._running = True
        cli = CliChannel(bus=self.bus)

        # Start stdin listener in background
        listen_task = asyncio.create_task(cli.listen())

        try:
            while self._running:
                msg = await self.bus.consume_inbound()

                text = msg.text.strip().lower()

                if text == "/stop":
                    print("Goodbye!")
                    self._running = False
                    break

                print(f"[...] Processing: {msg.text[:60]}{'...' if len(msg.text) > 60 else ''}", flush=True)

                result = await self._process_message(msg)

                if result and result.content:
                    await cli.send(result)
                else:
                    print("(no response)", flush=True)

        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye!")
        finally:
            self._running = False
            await cli.stop()
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
