"""GDPR helpers — self-service ``!forget_me`` flow.

This module concentrates the confirmation UI and the erasure logic so that the
classic prefix command (``!forget_me``) and the Canvas dropdown entry can
share a single implementation. The flow is always:

1. The user triggers the action.
2. We reply ephemerally with a :class:`ForgetMeConfirmView` (two buttons).
3. On confirm, we call :func:`agent_db.forget_user_across_servers` targeting
   *only* the interacting user (never another user) and report the outcome.

Only the requesting user can click the buttons; any other click is rejected.

All user-facing strings are loaded at runtime from the active personality's
``answers.json`` → ``general`` section (``forget_me_*`` keys), with English
fallback constants so the flow works even without a personality loaded.
"""

from __future__ import annotations

from typing import Optional, Union

import discord
from discord.ext import commands

from agent_logging import get_logger

logger = get_logger("gdpr")


# ── English fallback strings (used when personality JSON is unavailable) ──

_FB_CONFIRM_TITLE = "🧹 Confirm erasure"
_FB_CONFIRM_PROMPT = (
    "⚠️ **Forget me — GDPR right to erasure**\n\n"
    "This will irreversibly remove your personal data from **all servers where "
    "this bot operates**:\n"
    "• Raw interaction log entries attributed to you.\n"
    "• Per-user relationship memories the bot built about you.\n"
    "• Fatigue counters keyed to your user id.\n"
    "• Mentions of your display name in daily/relationship summaries will be "
    "redacted to ``[redacted]``.\n\n"
    "This action cannot be undone. Do you want to proceed?"
)
_FB_BTN_CONFIRM = "Yes, erase my data"
_FB_BTN_CANCEL = "Cancel"
_FB_RESULT_HEADER = "✅ Your personal data has been erased."
_FB_NO_DATA = "ℹ️ No personal data of yours was found on any known server."
_FB_CANCELLED = "❎ Cancelled. No data was modified."
_FB_NOT_YOURS = "❌ This confirmation belongs to another user."
_FB_TIMED_OUT = "⌛ Confirmation timed out. No data was modified."
_FB_DM_SENT = "📬 Sent you a DM to confirm."


def _load_gdpr_strings(server_id: Optional[str]) -> dict[str, str]:
    """Return a dict of ``forget_me_*`` strings from the personality JSON.

    Falls back to English constants for any missing key.
    """
    defaults = {
        "forget_me_confirm_title": _FB_CONFIRM_TITLE,
        "forget_me_confirm_prompt": _FB_CONFIRM_PROMPT,
        "forget_me_btn_confirm": _FB_BTN_CONFIRM,
        "forget_me_btn_cancel": _FB_BTN_CANCEL,
        "forget_me_result_header": _FB_RESULT_HEADER,
        "forget_me_no_data": _FB_NO_DATA,
        "forget_me_cancelled": _FB_CANCELLED,
        "forget_me_not_yours": _FB_NOT_YOURS,
        "forget_me_timed_out": _FB_TIMED_OUT,
        "forget_me_dm_sent": _FB_DM_SENT,
    }
    if not server_id:
        return defaults
    try:
        from agent_runtime import get_personality_message
        general: dict = get_personality_message("answers.json", ["general"], server_id, {}) or {}
        for key in defaults:
            val = general.get(key)
            if val:
                defaults[key] = val
    except Exception:
        pass
    return defaults


class ForgetMeConfirmView(discord.ui.View):
    """Two-button confirmation restricted to the requesting user.

    Button labels are set dynamically from personality strings so that they
    honour the server language.
    """

    def __init__(self, user_id: int, display_name: str, user_name: str,
                 strings: dict[str, str]):
        super().__init__(timeout=60)
        self.user_id = int(user_id)
        self.display_name = display_name
        self.user_name = user_name
        self.s = strings
        self._settled = False

        # Dynamically set button labels from localised strings.
        self.confirm.label = strings.get("forget_me_btn_confirm", _FB_BTN_CONFIRM)
        self.cancel.label = strings.get("forget_me_btn_cancel", _FB_BTN_CANCEL)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                self.s.get("forget_me_not_yours", _FB_NOT_YOURS), ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        if self._settled:
            return
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # We cannot edit the original ephemeral message from here reliably;
        # the timeout just disables the buttons in-place.

    @discord.ui.button(label="…", style=discord.ButtonStyle.danger, emoji="🧹")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._settled = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        # Gather aliases so redaction covers display name AND username.
        aliases: list[str] = []
        for name in (self.display_name, self.user_name):
            if name and name not in aliases:
                aliases.append(name)
        primary = aliases[0] if aliases else None
        extras = aliases[1:] if len(aliases) > 1 else []

        # Run the sweep off the event loop.
        import asyncio
        from agent_db import forget_user_across_servers

        try:
            report = await asyncio.to_thread(
                forget_user_across_servers,
                self.user_id,
                primary,
                extras,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"forget_user_across_servers failed for {self.user_id}: {exc}")
            await interaction.response.edit_message(
                content=f"❌ Erasure failed: `{exc}`. Nothing was modified.",
                view=self,
            )
            return

        no_data = self.s.get("forget_me_no_data", _FB_NO_DATA)
        if not report:
            await interaction.response.edit_message(content=no_data, view=self)
            logger.info(f"[GDPR] forget_me for {self.user_id}: no data found")
            return

        result_header = self.s.get("forget_me_result_header", _FB_RESULT_HEADER)
        lines = [result_header, ""]
        for sid, server_report in report.items():
            ops = ", ".join(f"{k}={v}" for k, v in server_report.items() if v)
            if ops:
                lines.append(f"• Server `{sid}`: {ops}")
        if len(lines) == 2:
            lines.append("(no rows matched on any server)")
        summary = "\n".join(lines)[:1900]  # Discord hard limit 2000.

        await interaction.response.edit_message(content=summary, view=self)
        logger.info(f"[GDPR] forget_me for {self.user_id}: {report}")

    @discord.ui.button(label="…", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._settled = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        cancelled = self.s.get("forget_me_cancelled", _FB_CANCELLED)
        await interaction.response.edit_message(content=cancelled, view=self)


async def send_forget_me_prompt(
    target: Union[commands.Context, discord.Interaction],
    user: Optional[discord.abc.User] = None,
) -> None:
    """Send the confirmation prompt, ephemeral when the target supports it.

    Accepts either a classic prefix :class:`commands.Context` (for ``!forget_me``)
    or a :class:`discord.Interaction` (for the Canvas dropdown).
    """
    if user is None:
        user = target.user if isinstance(target, discord.Interaction) else target.author

    # Resolve server_id so we can load localised strings.
    guild = getattr(target, "guild", None)
    server_id: Optional[str] = None
    if guild is not None:
        try:
            from discord_bot.canvas.state import get_server_key
            server_id = get_server_key(guild)
        except Exception:
            server_id = str(guild.id)

    s = _load_gdpr_strings(server_id)

    display_name = getattr(user, "display_name", None) or getattr(user, "name", "")
    user_name = getattr(user, "name", "")
    view = ForgetMeConfirmView(user.id, display_name, user_name, s)

    title = s.get("forget_me_confirm_title", _FB_CONFIRM_TITLE)
    prompt = s.get("forget_me_confirm_prompt", _FB_CONFIRM_PROMPT)
    content = f"**{title}**\n\n{prompt}"

    if isinstance(target, discord.Interaction):
        if target.response.is_done():
            await target.followup.send(content, view=view, ephemeral=True)
        else:
            await target.response.send_message(content, view=view, ephemeral=True)
    else:
        # Classic context: ephemeral is not available outside interactions,
        # so we DM the prompt to avoid leaking the action in public chat.
        dm_sent = s.get("forget_me_dm_sent", _FB_DM_SENT)
        try:
            await user.send(content, view=view)
            if target.guild is not None:
                await target.reply(dm_sent, mention_author=False)
        except discord.Forbidden:
            # User has DMs closed — reply privately is not possible; fall back
            # to channel reply. The View is still scoped to this user only.
            await target.reply(content, view=view, mention_author=False)
