"""OpenCow programmatic facade -- the main entry point for the agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from loguru import logger

from opencow.agent.context import ContextBuilder
from opencow.agent.memory import AutoCompact, Consolidator, MemoryStore
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
from opencow.tools import cron as cron_tools
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

        # LLM
        self.chat_model = chat_model or make_chat_model(config)

        # Tools
        self.tools = self._build_tool_registry()

        # Session
        self.sessions = SessionManager()

        # Memory (Phase 2)
        self.memory_store = MemoryStore(self.workspace)
        self.consolidator = Consolidator(self.chat_model)
        self.autocompact = AutoCompact(
            self.consolidator,
            session_ttl_minutes=config.agents.defaults.session_ttl_minutes,
        )

        # Skills (Phase 2)
        from opencow.agent.skills import SkillsLoader
        self.skills_loader = SkillsLoader(
            self.workspace,
            disabled_skills=set(config.agents.defaults.disabled_skills)
            if hasattr(config.agents.defaults, 'disabled_skills') else None,
        )

        # Context
        self.context_builder = ContextBuilder(
            self.workspace,
            timezone=config.agents.defaults.timezone,
        )
        # Wire memory and skills into context builder
        self.context_builder.memory = self.memory_store
        self.context_builder.skills = self.skills_loader

        # Commands
        self.commands = CommandRouter()
        register_builtin_commands(self.commands)

        # Dream (Phase 2)
        from opencow.agent.dream import Dream
        self.dream = Dream(
            self.workspace,
            self.chat_model,
            self.memory_store,
            timezone=config.agents.defaults.timezone,
        )

        # Cron (Phase 2)
        cron_path = self.workspace / "cron" / "jobs.json"
        ensure_dir(self.workspace / "cron")
        from opencow.cron.service import CronService
        self.cron = CronService(
            store_path=cron_path,
            on_job=self._handle_cron_job,
            max_sleep_ms=10_000,  # Check every 10s for due jobs
        )
        cron_tools.set_cron_service(self.cron)

        # Heartbeat (Phase 2)
        from opencow.heartbeat.service import HeartbeatService
        self.heartbeat = HeartbeatService(
            workspace=self.workspace,
            chat_model=self.chat_model,
            model=self._model_name,
            on_execute=self._handle_heartbeat_task,
            interval_s=30 * 60,
            enabled=True,
            timezone=config.agents.defaults.timezone,
        )

        # Bus
        self.bus = MessageBus()
        self._running = False

        # Track which sessions have already received a system prompt.
        # Only inject system prompt on the first message of each session;
        # subsequent messages just pass the user input (history is in checkpointer).
        self._primed_sessions: set[str] = set()

    # -- public API -----------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
    ) -> OpenCow:
        resolved = Path(config_path).expanduser().resolve() if config_path else None
        config = resolve_config_env_vars(load_config(resolved))
        return cls(config)

    async def run(
        self,
        message: str,
        *,
        session_key: str = "cli:default",
        channel: str = "cli",
    ) -> str:
        chat_id = session_key.split(":", 1)[1] if ":" in session_key else "default"
        msg = InboundMessage(
            text=message,
            channel=channel,
            chat_id=chat_id,
        )
        cron_tools.set_context(channel=channel, chat_id=chat_id, session_key=session_key)
        result = await self._process_message(msg)
        return result.content if result else ""

    def forget_session(self, session_key: str) -> None:
        """Clear session priming so the next message re-injects a fresh system prompt."""
        self._primed_sessions.discard(session_key)

    def _reset_corrupted_session(self, session_key: str) -> None:
        """Replace the MemorySaver to clear all corrupted state.

        Called when a tool-call sequence error or timeout leaves the
        checkpointer in an unrecoverable state.
        """
        self._primed_sessions.discard(session_key)
        self.sessions._graph = None
        self.sessions._checkpointer = None
        logger.warning("Session {} corrupted, resetting checkpointer", session_key)

    async def serve(self) -> None:
        """Run in interactive CLI mode with all Phase 2 services."""
        from opencow.channels.cli_channel import CliChannel

        print(f"Model: {self._model_name}")
        print(f"Workspace: {self.workspace}")
        print()

        self._running = True

        # Start background services
        cron_task = asyncio.create_task(self.cron.start())
        heartbeat_task = asyncio.create_task(self.heartbeat.start())

        cli = CliChannel(bus=self.bus)
        listen_task = asyncio.create_task(cli.listen())

        print("OpenCow ready. Type /help for commands, /stop to exit.")
        print()

        async def _next_message() -> InboundMessage:
            """Read inbound messages while also delivering outbound notifications."""
            while True:
                # Poll: check outbound queue first (non-blocking), then wait for inbound
                if self.bus.outbound_size > 0:
                    out = await self.bus.consume_outbound()
                    try:
                        await cli.send(out)
                    except Exception:
                        pass
                    continue

                # Short timeout on inbound so we periodically check outbound
                try:
                    inbound_task = asyncio.create_task(self.bus.consume_inbound())
                    msg = await asyncio.wait_for(inbound_task, timeout=1.0)
                    return msg
                except asyncio.TimeoutError:
                    pass

        try:
            while self._running:
                msg = await _next_message()

                text = msg.text.strip().lower()

                if text == "/stop":
                    print("Goodbye!")
                    self._running = False
                    break

                if text == "/dream":
                    print("[...] Running memory consolidation...", flush=True)
                    result = await self.dream.run()
                    if result:
                        print("Memory updated.")
                    else:
                        print("Nothing new to remember.")
                    continue

                print(f"[...] {msg.text[:60]}{'...' if len(msg.text) > 60 else ''}", flush=True)

                # Set cron context so tools capture the current channel/chat
                cron_tools.set_context(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    session_key=msg.session_key,
                )

                result = await self._process_message(msg)

                # Record in history (best-effort, never crash)
                try:
                    self.memory_store.append_history(f"user: {msg.text}")
                    if result and result.content:
                        self.memory_store.append_history(f"assistant: {result.content[:200]}")
                except Exception:
                    pass

                try:
                    if result and result.content:
                        await cli.send(result)
                    else:
                        print("(no response)", flush=True)
                except Exception:
                    print("(display error)", flush=True)

        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye!")
        finally:
            self._running = False
            await cli.stop()
            listen_task.cancel()
            for t in [listen_task, cron_task, heartbeat_task]:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            await self.cron.stop()
            await self.heartbeat.stop()

    async def serve_api(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Run as an OpenAI-compatible API server."""
        from opencow.api.server import create_app
        from aiohttp import web

        app = create_app(self)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        logger.info("API server listening on http://{}:{}", host, port)
        print(f"OpenCow API server: http://{host}:{port}")
        print("Endpoints:")
        print("  POST /v1/chat/completions")
        print("  GET  /v1/models")

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await runner.cleanup()

    # -- internal -------------------------------------------------------------

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
        registry.register(cron_tools.add_cron)
        registry.register(cron_tools.list_cron)
        registry.register(cron_tools.remove_cron)
        return registry

    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
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

        # Only inject the system prompt on the FIRST message of a session.
        # Subsequent messages carry the context via the checkpointer's history.
        is_new_session = key not in self._primed_sessions
        if is_new_session:
            self._primed_sessions.add(key)
            input_messages = [("system", system_prompt), ("user", user_content)]
        else:
            input_messages = [("user", user_content)]

        try:
            result = await asyncio.wait_for(
                graph.ainvoke(
                    {
                        "messages": input_messages,
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
                if not content:
                    reasoning = (getattr(last, "additional_kwargs", {}) or {}).get("reasoning_content", "")
                    content = reasoning or content
                return OutboundMessage(
                    content=str(content) if content else "",
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    session_key=key,
                )

        except asyncio.TimeoutError:
            msg_text = f"Request timed out ({_LLM_TIMEOUT_SECONDS}s). Check your API key and network."
            print(f"\n[ERROR] {msg_text}", flush=True)
            logger.error(msg_text)
            self._reset_corrupted_session(key)
            return OutboundMessage(content=msg_text, channel=msg.channel, chat_id=msg.chat_id, session_key=key)
        except Exception as e:
            if "tool_calls" in str(e) or "400" in str(e):
                # Tool-call sequence corruption — reset session state
                self._reset_corrupted_session(key)
            msg_text = f"Agent error: {e}"
            print(f"\n[ERROR] {msg_text}", flush=True)
            logger.exception("Agent run failed for session {}", key)
            return OutboundMessage(content=msg_text, channel=msg.channel, chat_id=msg.chat_id, session_key=key)

        return None

    async def _handle_cron_job(self, job) -> str | None:
        """Callback: execute a cron job prompt and deliver to the configured channel.

        Uses a SEPARATE session key (cron:<id>) to avoid polluting the user's
        conversation history with cron tool-call sequences.
        """
        message = job.payload.message
        channel = job.payload.channel or "cli"
        to = job.payload.to or "cli-default"

        # Use a dedicated session so cron interactions don't corrupt user history
        result = await self.run(message, session_key=f"cron:{job.id}", channel=channel)

        if result and job.payload.deliver:
            # Set context so nested cron calls within execute would work correctly
            cron_tools.set_context(
                channel=channel,
                chat_id=to,
                session_key=session_key,
            )
            await self.bus.publish_outbound(OutboundMessage(
                content=f"[Cron: {job.name}] {result}",
                channel=channel,
                chat_id=to,
                session_key=session_key,
            ))
        return result

    async def _handle_heartbeat_task(self, task_summary: str) -> str:
        """Callback: execute a heartbeat-triggered task and deliver result."""
        result = await self.run(task_summary, session_key="heartbeat:default", channel="heartbeat")
        if result:
            await self.bus.publish_outbound(OutboundMessage(
                content=f"[Heartbeat] {result}",
                channel="cli",
                chat_id="cli-default",
                session_key="heartbeat:default",
            ))
        return result
