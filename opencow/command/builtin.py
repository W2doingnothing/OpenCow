"""Built-in slash command handlers."""

from opencow.bus.events import OutboundMessage
from opencow.command.router import CommandContext, CommandRouter


def _reply(ctx: CommandContext, text: str) -> OutboundMessage:
    return OutboundMessage(
        content=text,
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        session_key=ctx.msg.session_key,
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage | None:
    return _reply(ctx, """**Available commands:**
/help     - Show this help
/status   - Show agent status
/new      - Start a new conversation
/dream    - Manually run memory consolidation
/stop     - Stop the agent (CLI only)""")


async def cmd_status(ctx: CommandContext) -> OutboundMessage | None:
    info = []
    if ctx.loop:
        info.append(f"Model: {ctx.loop._model_name}")
        info.append(f"Workspace: {ctx.loop.workspace}")
    info.append(f"Session: {ctx.msg.session_key}")
    return _reply(ctx, "\n".join(info))


async def cmd_new(ctx: CommandContext) -> OutboundMessage | None:
    """Start a new conversation by clearing the system prompt priming.

    The checkpointer still has the old history, but without the system
    prompt being re-injected, the model treats this as a fresh start.
    The _primed_sessions set is cleared so the next message will inject
    a fresh system prompt.
    """
    if ctx.loop:
        ctx.loop.forget_session(ctx.msg.session_key)
    return _reply(ctx, "Starting a new conversation.")


async def cmd_history(ctx: CommandContext) -> OutboundMessage | None:
    return _reply(ctx, "History is preserved by the LangGraph checkpointer. Use /status for session info.")


def register_builtin_commands(router: CommandRouter) -> None:
    router.exact("/help", cmd_help)
    router.exact("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/history", cmd_history)
