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
/history  - Show recent message count
/stop     - Stop the agent (CLI only)""")


async def cmd_status(ctx: CommandContext) -> OutboundMessage | None:
    info = []
    if ctx.loop:
        info.append(f"Model: {ctx.loop._model}")
        info.append(f"Workspace: {ctx.loop._workspace}")
    info.append(f"Session: {ctx.msg.session_key}")
    return _reply(ctx, "\n".join(info))


async def cmd_new(ctx: CommandContext) -> OutboundMessage | None:
    if ctx.loop:
        ctx.loop.sessions.invalidate(ctx.msg.session_key)
    return _reply(ctx, "Starting a new conversation. Previous history archived.")


async def cmd_history(ctx: CommandContext) -> OutboundMessage | None:
    return _reply(ctx, "Use /status to see session info. History is stored in SQLite checkpoints.")


def register_builtin_commands(router: CommandRouter) -> None:
    router.exact("/help", cmd_help)
    router.exact("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/history", cmd_history)
    # /stop is handled before dispatch (priority command)
