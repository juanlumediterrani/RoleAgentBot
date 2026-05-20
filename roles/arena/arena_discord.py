"""
Discord integration for the Arena module.

Handles:
- Duel challenge DMs (send, accept, decline)
- Event registration embeds (coliseo, torneo)
- Battle result publication in Arena channel
- Weapon selection dropdowns
"""

import discord
from typing import Optional

from agent_logging import get_logger

logger = get_logger("arena_discord")


# ── Message Loading ─────────────────────────────────────────────────────

def _get_arena_messages(server_id: str) -> dict:
    """Load Arena messages from personality descriptions."""
    try:
        from discord_bot.canvas.content import _get_personality_descriptions
        personality_descriptions = _get_personality_descriptions(server_id)
        return personality_descriptions.get("arena", {})
    except Exception:
        return {}


def _text(messages: dict, key: str, fallback: str = "") -> str:
    """Get a nested message by key with dot notation."""
    if "." in key:
        keys = key.split(".")
        value = messages
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                value = None
                break
        return str(value).strip() if value else fallback
    return str(messages.get(key, fallback)).strip() if messages.get(key) else fallback

# ── Duel Challenge View ──────────────────────────────────────────────

class DuelChallengeView(discord.ui.View):
    """DM view sent to the challenged user. Accept/Decline buttons."""

    def __init__(
        self,
        challenger_id: int,
        challenger_name: str,
        server_id: str,
        challenger_weapon_id: str,
        guild: discord.Guild,
        bot_personality_name: str = "Bot",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.challenger_id = challenger_id
        self.challenger_name = challenger_name
        self.server_id = server_id
        self.challenger_weapon_id = challenger_weapon_id
        self.guild = guild
        self.bot_personality_name = bot_personality_name
        self.accepted = False
        self.receiver_weapon_id: Optional[str] = None
        self.msgs = _get_arena_messages(server_id)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="⚔️")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the duel and ask receiver to choose a weapon."""
        await interaction.response.defer(thinking=True)

        button.label = _text(self.msgs, "duelo.button_accept", "Accept")
        button.disabled = True
        self.decline_button.disabled = True
        await interaction.edit_original_response(view=self)

        self.accepted = True
        logger.info(f"[Arena] Duel accepted by {interaction.user.id} from {self.challenger_id}")

        # Notify challenger
        try:
            challenger = await interaction.client.fetch_user(self.challenger_id)
            accepted_msg = _text(self.msgs, "duelo.accepted", "**{user}** has accepted your duel. Choose your weapon...")
            await challenger.send(accepted_msg.format(user=interaction.user.display_name))
        except Exception as e:
            logger.warning(f"[Arena] Could not notify challenger: {e}")

        # Send weapon selection to receiver so the duel resolves immediately after choosing
        from roles.arena.arena_catalogs import get_unlocked_weapons
        from roles.arena.arena_db import ArenaDatabase
        db = ArenaDatabase(self.server_id)
        fighter = db.stats.get_fighter(str(interaction.user.id))
        xp = fighter.get("xp", 0.0)
        unlocked = get_unlocked_weapons(self.server_id, xp)
        if not unlocked:
            no_weapon_msg = _text(self.msgs, "duelo.no_weapons", "You have no unlocked weapons. Participate in battles to unlock them.")
            await interaction.followup.send(no_weapon_msg, ephemeral=False)
            return

        ws_view = DuelWeaponSelectView(
            server_id=self.server_id,
            challenger_id=self.challenger_id,
            challenger_name=self.challenger_name,
            challenger_weapon_id=self.challenger_weapon_id,
            receiver_id=interaction.user.id,
            receiver_name=interaction.user.display_name,
            guild=self.guild,
            bot_personality_name=self.bot_personality_name,
            unlocked_weapons=unlocked,
        )
        select_weapon_msg = _text(self.msgs, "duelo.select_weapon", "Choose your weapon for the duel:")
        await interaction.followup.send(select_weapon_msg, view=ws_view, ephemeral=False)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the duel."""
        await interaction.response.defer(thinking=True)

        button.label = _text(self.msgs, "duelo.button_decline", "Decline")
        button.disabled = True
        self.accept_button.disabled = True
        await interaction.edit_original_response(view=self)

        self.accepted = False
        logger.info(f"[Arena] Duel declined by {interaction.user.id} from {self.challenger_id}")

        # Notify challenger
        try:
            challenger = await interaction.client.fetch_user(self.challenger_id)
            declined_msg = _text(self.msgs, "duelo.declined", "**{user}** has declined your duel.")
            await challenger.send(declined_msg.format(user=interaction.user.display_name))
        except Exception as e:
            logger.warning(f"[Arena] Could not notify challenger: {e}")

        self.stop()


async def send_duel_invite(
    client: discord.Client,
    receiver: discord.Member,
    challenger: discord.Member,
    server_id: str,
    challenger_weapon: dict,
    guild: discord.Guild,
    bot_personality_name: str = "Bot",
) -> bool:
    """Sends a DM duel invitation to the receiver."""
    try:
        msgs = _get_arena_messages(server_id)
        
        title = _text(msgs, "duelo.challenge_received_title", "⚔️ YOU HAVE BEEN CHALLENGED TO A DUEL IN THE ARENA")
        desc_template = _text(msgs, "duelo.challenge_received_desc", "**{challenger}** has challenged you to a 1v1 duel.\n\nWeapon chosen by {challenger}: **{weapon}**\n\nDo you accept?")
        description = desc_template.format(challenger=challenger.display_name, weapon=challenger_weapon.get('name', '???'))
        footer = _text(msgs, "duelo.challenge_received_desc", "Server: {server}").format(server=bot_personality_name)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.dark_red(),
        )
        embed.set_footer(text=footer)

        view = DuelChallengeView(
            challenger_id=challenger.id,
            challenger_name=challenger.display_name,
            server_id=server_id,
            challenger_weapon_id=challenger_weapon.get("id", ""),
            guild=guild,
            bot_personality_name=bot_personality_name,
        )
        
        # Update button labels with personality-specific text
        view.accept_button.label = _text(msgs, "duelo.button_accept", "Accept")
        view.decline_button.label = _text(msgs, "duelo.button_decline", "Decline")
        
        await receiver.send(embed=embed, view=view)
        return True
    except discord.Forbidden:
        logger.warning(f"[Arena] Cannot DM user {receiver.id} - DMs disabled")
        return False
    except Exception as e:
        logger.error(f"[Arena] Error sending duel invite: {e}")
        return False


# ── Weapon Select Dropdown ─────────────────────────────────────────

class WeaponSelect(discord.ui.Select):
    """Dropdown to select an active weapon from unlocked weapons."""

    def __init__(self, server_id: str, user_id: str, unlocked_weapons: list[dict]):
        self.msgs = _get_arena_messages(server_id)
        options = []
        for w in unlocked_weapons:
            options.append(
                discord.SelectOption(
                    label=w["name"],
                    description=w.get("desc", "")[:100],
                    value=w["id"],
                )
            )
        super().__init__(
            placeholder=_text(self.msgs, "duelo.select_weapon", "Select your weapon..."),
            min_values=1,
            max_values=1,
            options=options,
        )
        self.server_id = server_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        try:
            from roles.arena.arena_db import ArenaDatabase
            db = ArenaDatabase(self.server_id)
            db.stats.set_active_weapon(self.user_id, selected)
            equipped_msg = _text(self.msgs, "weapons.equipped", "Weapon equipped: {weapon}").format(weapon=selected)
            await interaction.response.send_message(equipped_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"[Arena] Error equipping weapon: {e}")
            error_msg = _text(self.msgs, "errors.no_channel", "Error equipping weapon.")
            await interaction.response.send_message(error_msg, ephemeral=True)


class WeaponSelectView(discord.ui.View):
    """View with weapon selection dropdown."""

    def __init__(self, server_id: str, user_id: str, unlocked_weapons: list[dict]):
        super().__init__(timeout=60)
        self.add_item(WeaponSelect(server_id, user_id, unlocked_weapons))


# ── Duel Weapon Select (resolves battle immediately) ─────────────────

class DuelWeaponSelect(discord.ui.Select):
    """Dropdown to choose weapon for a duel; resolves the battle immediately."""

    def __init__(
        self,
        server_id: str,
        challenger_id: int,
        challenger_name: str,
        challenger_weapon_id: str,
        receiver_id: int,
        receiver_name: str,
        guild: discord.Guild,
        bot_personality_name: str,
        unlocked_weapons: list[dict],
    ):
        options = []
        for w in unlocked_weapons:
            options.append(
                discord.SelectOption(
                    label=w["name"],
                    description=w.get("desc", "")[:100],
                    value=w["id"],
                )
            )
        super().__init__(
            placeholder="Choose your weapon for the duel...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.server_id = server_id
        self.challenger_id = challenger_id
        self.challenger_name = challenger_name
        self.challenger_weapon_id = challenger_weapon_id
        self.receiver_id = receiver_id
        self.receiver_name = receiver_name
        self.guild = guild
        self.bot_personality_name = bot_personality_name

    async def callback(self, interaction: discord.Interaction):
        receiver_weapon_id = self.values[0]
        await interaction.response.defer(thinking=True)

        # Equip weapon for receiver
        from roles.arena.arena_db import ArenaDatabase
        from roles.arena.arena_catalogs import get_weapon_by_id
        from roles.arena.arena import execute_battle_1v1, calculate_xp
        from discord_bot.canvas.canvas_arena import _get_arena_messages

        db = ArenaDatabase(self.server_id)
        db.stats.set_active_weapon(str(self.receiver_id), receiver_weapon_id)

        # Load fighter data
        c_fighter = db.stats.get_fighter(str(self.challenger_id))
        r_fighter = db.stats.get_fighter(str(self.receiver_id))

        # Build participants
        participant_a = {
            "user_id": str(self.challenger_id),
            "username": self.challenger_name,
            "weapon": self.challenger_weapon_id,
            "fighter_personality": c_fighter.get("fighter_personality", "Unknown"),
            "xp": c_fighter.get("xp", 0),
        }
        participant_b = {
            "user_id": str(self.receiver_id),
            "username": self.receiver_name,
            "weapon": receiver_weapon_id,
            "fighter_personality": r_fighter.get("fighter_personality", "Unknown"),
            "xp": r_fighter.get("xp", 0),
        }

        # Execute battle
        result = await execute_battle_1v1(
            self.server_id,
            participant_a,
            participant_b,
            self.bot_personality_name,
        )

        if not result.get("success"):
            logger.error(f"[Arena] Duel battle failed: {result.get('error')}")
            await interaction.followup.send("The battle could not be resolved. Try again later.")
            return

        winner_id = result.get("winner_id")
        loser_id = result.get("loser_id")
        winner_name = result.get("winner_name", "???")
        loser_name = result.get("loser_name", "???")
        justification = result.get("justification", "")
        narrative = result.get("narrative", "")

        # Award XP
        xp_amount = calculate_xp("duelo", {})
        db.stats.record_battle_result(winner_id, True, "duelo", xp_amount)
        db.stats.record_battle_result(loser_id, False, "duelo", 0.0)

        # Publish in arena channel
        try:
            arena_channel = await get_arena_channel(self.guild)
            if arena_channel:
                embed = build_battle_result_embed(
                    winner_name, loser_name, "duelo", justification, narrative,
                    self.bot_personality_name,
                )
                mentions = f"<@{self.challenger_id}> <@{self.receiver_id}>"
                await arena_channel.send(content=mentions, embed=embed)
            else:
                logger.warning(f"[Arena] No arena channel found for guild {self.guild.id}")
        except Exception as e:
            logger.error(f"[Arena] Error publishing duel result: {e}")

        # Notify both users via DM
        msgs = _get_arena_messages(self.server_id)
        dm_title = _text(msgs, "battle_result.dm_title", "Result of your battle in the Arena")
        dm_msg = (
            f"**{dm_title}**\n\n"
            f"**Winner:** {winner_name}\n"
            f"**Loser:** {loser_name}\n"
            f"**Justification:** {justification}\n\n"
            f"Check the Arena channel for the full narrative!"
        )
        for uid in (self.challenger_id, self.receiver_id):
            try:
                user = await interaction.client.fetch_user(uid)
                await user.send(dm_msg[:2000])
            except Exception:
                pass

        # Confirm to receiver
        await interaction.followup.send(
            f"Duel resolved! **{winner_name}** wins! Check the Arena channel for the full story.",
            ephemeral=False,
        )


class DuelWeaponSelectView(discord.ui.View):
    """View with weapon selection that resolves the duel immediately."""

    def __init__(
        self,
        server_id: str,
        challenger_id: int,
        challenger_name: str,
        challenger_weapon_id: str,
        receiver_id: int,
        receiver_name: str,
        guild: discord.Guild,
        bot_personality_name: str,
        unlocked_weapons: list[dict],
    ):
        super().__init__(timeout=120)
        self.add_item(DuelWeaponSelect(
            server_id, challenger_id, challenger_name, challenger_weapon_id,
            receiver_id, receiver_name, guild, bot_personality_name, unlocked_weapons,
        ))


# ── Battle Result Embeds ────────────────────────────────────────────

def build_battle_result_embed(
    winner_name: str,
    loser_name: str,
    battle_type: str,
    justification: str,
    narrative: str,
    bot_personality_name: str = "Bot",
    server_id: str = None,
) -> discord.Embed:
    """Builds an embed for battle results."""
    msgs = _get_arena_messages(server_id) if server_id else {}
    
    title_map = {
        "duelo": _text(msgs, "battle_result.title", "Battle Result"),
        "coliseo": _text(msgs, "battle_result.title", "Battle Result"),
        "torneo": _text(msgs, "battle_result.title", "Battle Result"),
    }
    title = title_map.get(battle_type.lower(), _text(msgs, "battle_result.title", "Battle Result"))
    color_map = {
        "duelo": discord.Color.blue(),
        "coliseo": discord.Color.orange(),
        "torneo": discord.Color.gold(),
    }
    color = color_map.get(battle_type.lower(), discord.Color.default())

    embed = discord.Embed(title=f"⚔️ {title}", color=color)
    winner_label = _text(msgs, "battle_result.winner", "Winner: {winner}").format(winner=winner_name)
    loser_label = _text(msgs, "battle_result.loser", "Loser: {loser}").format(loser=loser_name) if "battle_result.loser" in str(msgs) else loser_name
    justification_label = _text(msgs, "battle_result.justification", "Justification: {justification}").format(justification=justification)
    
    embed.add_field(name=winner_label.split(":")[0], value=f"**{winner_name}**", inline=True)
    embed.add_field(name="Loser", value=f"{loser_name}", inline=True)
    embed.add_field(name=justification_label.split(":")[0], value=justification, inline=False)

    # Truncate narrative if too long
    narr = narrative.strip()
    if len(narr) > 4096:
        narr = narr[:4093] + "..."
    embed.description = narr

    footer = _text(msgs, "battle_result.footer", "Arena of {bot}").format(bot=bot_personality_name)
    embed.set_footer(text=footer)
    return embed


async def publish_battle_result(
    channel: discord.TextChannel,
    winner_name: str,
    loser_name: str,
    battle_type: str,
    justification: str,
    narrative: str,
    bot_personality_name: str = "Bot",
    ping_participants: list[int] = None,
    server_id: str = None,
) -> Optional[discord.Message]:
    """Publishes a battle result embed in the Arena channel."""
    try:
        embed = build_battle_result_embed(
            winner_name, loser_name, battle_type, justification, narrative, bot_personality_name, server_id
        )
        msgs = _get_arena_messages(server_id) if server_id else {}
        content = None
        if ping_participants:
            mentions = " ".join(f"<@{uid}>" for uid in ping_participants)
            content = _text(msgs, "battle_result.ping", "Battle result: {mentions}").format(mentions=mentions)
        msg = await channel.send(content=content, embed=embed)
        return msg
    except Exception as e:
        logger.error(f"[Arena] Error publishing battle result: {e}")
        return None


# ── Event Registration Embed ───────────────────────────────────────

def build_event_embed(
    event_type: str,
    participants: list[dict],
    scheduled_for: str,
    server_id: str,
) -> discord.Embed:
    """Builds the registration embed for coliseo/torneo."""
    msgs = _get_arena_messages(server_id)
    
    if event_type == "coliseo":
        title = _text(msgs, "coliseo.title", "Coliseum - Registration Open")
        description = _text(msgs, "coliseo.description", "Minimum 4 participants. Free for all.")
    elif event_type == "torneo":
        title = _text(msgs, "torneo.title", "Tournament - Registration Open")
        description = _text(msgs, "torneo.description", "Minimum 8 participants. Elimination by brackets.")
    else:
        title = _text(msgs, "battle_result.title", "Arena Event")
        description = _text(msgs, "battle_result.title", "Arena Event")
    
    embed = discord.Embed(
        title=f"🏟️ {title}",
        description=description,
        color=discord.Color.purple(),
    )
    
    scheduled_label = _text(msgs, "coliseo.scheduled", "Scheduled for") if event_type == "coliseo" else _text(msgs, "torneo.scheduled", "Scheduled for")
    participants_label = _text(msgs, "coliseo.participants", "Participants") if event_type == "coliseo" else _text(msgs, "torneo.participants", "Participants")
    
    embed.add_field(name=scheduled_label, value=scheduled_for, inline=True)
    embed.add_field(name=participants_label, value=str(len(participants)), inline=True)
    if participants:
        names = ", ".join(p.get("username", "???") for p in participants)
        registered_label = _text(msgs, "coliseo.registered", "Registered") if event_type == "coliseo" else _text(msgs, "torneo.registered", "Registered")
        embed.add_field(name=registered_label, value=names[:1024], inline=False)
    return embed


# ── Leaderboard Embed ──────────────────────────────────────────────

def build_leaderboard_embed(
    leaderboard: list[dict],
    bot_personality_name: str = "Bot",
    server_id: str = None,
) -> discord.Embed:
    """Builds the leaderboard embed."""
    msgs = _get_arena_messages(server_id) if server_id else {}
    
    title = _text(msgs, "ranking.title", "🏆 Arena Leaderboard - {bot}").format(bot=bot_personality_name)
    embed = discord.Embed(
        title=title,
        color=discord.Color.gold(),
    )
    if not leaderboard:
        embed.description = _text(msgs, "ranking.no_fighters", "No fighters registered yet.")
        return embed

    lines = []
    for i, f in enumerate(leaderboard[:20], 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        name = f.get("user_id", "???")[:20]
        wins = f.get("wins", 0)
        xp = f.get("xp", 0)
        wins_label = _text(msgs, "ranking.wins", "wins")
        xp_label = _text(msgs, "ranking.xp", "XP")
        lines.append(f"{medal} {name} — {wins} {wins_label}, {xp:.1f} {xp_label}")

    embed.description = "\n".join(lines)
    return embed


# ── Utility: Get Arena Channel ──────────────────────────────────────

async def get_arena_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Finds the Arena channel for a guild."""
    # Try exact name first
    channel = discord.utils.get(guild.text_channels, name="arena")
    if channel:
        return channel
    # Try with bot personality prefix
    bot_name = guild.me.display_name.lower().replace(" ", "-")
    channel = discord.utils.get(guild.text_channels, name=f"arena-{bot_name}")
    if channel:
        return channel
    return None


# ── Admin Event Proposal Modal ───────────────────────────────────────

class AdminEventProposalModal(discord.ui.Modal):
    """Modal for admins to propose a coliseo or torneo with date/time."""

    def __init__(self, server_id: str, bot_personality_name: str = "Bot"):
        self.server_id = server_id
        self.bot_personality_name = bot_personality_name
        self.msgs = _get_arena_messages(server_id)
        
        title = _text(self.msgs, "admin.title", "Propose Arena Event")
        super().__init__(title=title, timeout=300)
        
        event_type_label = _text(self.msgs, "admin.event_type", "Event type")
        event_type_placeholder = _text(self.msgs, "admin.event_type_placeholder", "coliseo or torneo")
        
        date_label = _text(self.msgs, "admin.date_label", "Date (YYYY-MM-DD)")
        date_placeholder = _text(self.msgs, "admin.date_placeholder", "2026-05-25")
        
        time_label = _text(self.msgs, "admin.time_label", "Time (HH:MM)")
        time_placeholder = _text(self.msgs, "admin.time_placeholder", "18:00")
        
        min_part_label = _text(self.msgs, "admin.min_participants", "Minimum participants")
        min_part_placeholder = _text(self.msgs, "admin.min_part_placeholder", "4 (coliseo) or 8 (torneo)")

        self.event_type = discord.ui.TextInput(
            label=event_type_label,
            placeholder=event_type_placeholder,
            default="coliseo",
            max_length=10,
        )
        self.add_item(self.event_type)

        self.scheduled_date = discord.ui.TextInput(
            label=date_label,
            placeholder=date_placeholder,
            max_length=10,
        )
        self.add_item(self.scheduled_date)

        self.scheduled_time = discord.ui.TextInput(
            label=time_label,
            placeholder=time_placeholder,
            max_length=5,
        )
        self.add_item(self.scheduled_time)

        self.min_participants = discord.ui.TextInput(
            label=min_part_label,
            placeholder=min_part_placeholder,
            default="4",
            max_length=2,
        )
        self.add_item(self.min_participants)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        event_type = str(self.event_type.value).strip().lower()
        date_str = str(self.scheduled_date.value).strip()
        time_str = str(self.scheduled_time.value).strip()
        min_p_str = str(self.min_participants.value).strip()

        if event_type not in ("coliseo", "torneo"):
            error_msg = _text(self.msgs, "errors.invalid_event_type", "Invalid event type. Use 'coliseo' or 'torneo'.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        try:
            from datetime import datetime
            scheduled_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            scheduled_iso = scheduled_dt.isoformat()
        except ValueError:
            error_msg = _text(self.msgs, "errors.invalid_datetime", "Incorrect date or time format. Use YYYY-MM-DD and HH:MM (24h).")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        try:
            min_participants = int(min_p_str)
        except ValueError:
            min_participants = 4 if event_type == "coliseo" else 8

        from roles.arena.arena_db import ArenaDatabase
        db = ArenaDatabase(self.server_id)
        active = db.events.get_active_event()
        if active and active.get("status") in ("registering", "ready", "in_progress"):
            error_msg = _text(self.msgs, "errors.event_in_progress", "There is already an active event. Wait for it to finish or cancel it first.")
            await interaction.followup.send(error_msg, ephemeral=True)
            return

        success = db.events.create_event(event_type, scheduled_iso, min_participants)
        if success:
            scheduled_msg = _text(self.msgs, "admin.scheduled", "Event scheduled for **{date}** at **{time}**.").format(date=date_str, time=time_str)
            min_part_msg = _text(self.msgs, "admin.min_participants", "Minimum participants")
            footer = _text(self.msgs, "battle_result.footer", "Arena of {bot}").format(bot=self.bot_personality_name)
            
            embed = discord.Embed(
                title=f"🏟️ {event_type.capitalize()} Scheduled",
                description=scheduled_msg,
                color=discord.Color.purple(),
            )
            embed.add_field(name=min_part_msg, value=str(min_participants), inline=True)
            embed.set_footer(text=footer)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            error_msg = _text(self.msgs, "errors.create_event_failed", "Error creating the event. Try again.")
            await interaction.followup.send(error_msg, ephemeral=True)


# ── Duel Opponent Select (Canvas) ──────────────────────────────────

class DuelOpponentSelect(discord.ui.UserSelect):
    """Select an opponent for a duel from Canvas."""

    def __init__(self, server_id: str, challenger_id: int, challenger_name: str):
        self.msgs = _get_arena_messages(server_id)
        super().__init__(
            placeholder=_text(self.msgs, "duelo.select_opponent", "Select who to challenge..."),
            min_values=1,
            max_values=1,
        )
        self.server_id = server_id
        self.challenger_id = challenger_id
        self.challenger_name = challenger_name

    async def callback(self, interaction: discord.Interaction):
        opponent = self.values[0]
        if opponent.id == self.challenger_id:
            error_msg = _text(self.msgs, "errors.self_challenge", "You cannot challenge yourself.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        if opponent.bot:
            error_msg = _text(self.msgs, "errors.challenge_bot", "You cannot challenge a bot.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        # Get challenger's active weapon
        from roles.arena.arena_db import ArenaDatabase
        from roles.arena.arena_catalogs import get_weapon_by_id, get_unlocked_weapons
        db = ArenaDatabase(self.server_id)
        fighter = db.stats.get_fighter(str(self.challenger_id))
        active_weapon_id = fighter.get("active_weapon")
        xp = fighter.get("xp", 0.0)

        if not active_weapon_id:
            unlocked = get_unlocked_weapons(self.server_id, xp)
            if not unlocked:
                error_msg = _text(self.msgs, "duelo.no_weapons", "You have no unlocked weapons. Participate in battles to unlock them.")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            active_weapon_id = unlocked[0]["id"]
            db.stats.set_active_weapon(str(self.challenger_id), active_weapon_id)

        weapon = get_weapon_by_id(self.server_id, active_weapon_id)
        if not weapon:
            weapon = {"id": active_weapon_id, "name": active_weapon_id}

        # Send duel invite DM
        challenger = interaction.user
        guild = interaction.guild
        sent = await send_duel_invite(
            interaction.client,
            opponent,
            challenger,
            self.server_id,
            weapon,
            guild,
            guild.me.display_name if guild else "Bot",
        )
        if sent:
            success_msg = _text(self.msgs, "duelo.challenge_sent", "Challenge sent to **{opponent}**. Waiting for response...").format(opponent=opponent.display_name)
            await interaction.response.send_message(success_msg, ephemeral=True)
        else:
            error_msg = _text(self.msgs, "errors.cannot_send_dm", "Could not send challenge to {opponent}. Maybe they have DMs disabled.").format(opponent=opponent.display_name)
            await interaction.response.send_message(error_msg, ephemeral=True)


class DuelOpponentSelectView(discord.ui.View):
    """View with opponent selection for duels."""

    def __init__(self, server_id: str, challenger_id: int, challenger_name: str):
        super().__init__(timeout=60)
        self.add_item(DuelOpponentSelect(server_id, challenger_id, challenger_name))


# ── Event Registration Button ──────────────────────────────────────

class EventRegisterButton(discord.ui.Button):
    """Button to register for the active arena event."""

    def __init__(self, server_id: str, event_type: str, label: str = None):
        self.server_id = server_id
        self.event_type = event_type
        self.msgs = _get_arena_messages(server_id)
        
        if label is None:
            if event_type == "coliseo":
                label = _text(self.msgs, "coliseo.register", "Register")
            elif event_type == "torneo":
                label = _text(self.msgs, "torneo.register", "Register")
            else:
                label = _text(self.msgs, "duelo.button", "Register")
        
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            emoji="📝",
        )

    async def callback(self, interaction: discord.Interaction):
        from roles.arena.arena_db import ArenaDatabase
        from roles.arena.arena_catalogs import get_unlocked_weapons
        db = ArenaDatabase(self.server_id)
        active = db.events.get_active_event()

        if not active:
            error_msg = _text(self.msgs, "errors.no_active_event", "There is no active event at the moment.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        if active.get("type") != self.event_type:
            error_msg = _text(self.msgs, "errors.wrong_event_type", "The active event is not a {event_type}.").format(event_type=self.event_type)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        if active.get("status") != "registering":
            error_msg = _text(self.msgs, "errors.registration_closed", "Registration for this event is already closed.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        if db.events.is_registered(str(interaction.user.id)):
            error_msg = _text(self.msgs, "errors.already_registered", "You are already registered for this event.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        fighter = db.stats.get_fighter(str(interaction.user.id))
        xp = fighter.get("xp", 0.0)
        active_weapon_id = fighter.get("active_weapon")
        unlocked = get_unlocked_weapons(self.server_id, xp)

        if not unlocked:
            error_msg = _text(self.msgs, "duelo.no_weapons", "You have no unlocked weapons. You cannot participate without a weapon.")
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        if not active_weapon_id:
            active_weapon_id = unlocked[0]["id"]
            db.stats.set_active_weapon(str(interaction.user.id), active_weapon_id)

        fp = fighter.get("fighter_personality", "")
        success = db.events.register_participant(
            str(interaction.user.id),
            interaction.user.display_name,
            active_weapon_id,
            fp,
        )
        if success:
            count = len(db.events.get_active_event().get("participants", {}))
            participants_label = _text(self.msgs, "coliseo.participants", "Participants") if self.event_type == "coliseo" else _text(self.msgs, "torneo.participants", "Participants")
            success_msg = _text(self.msgs, "coliseo.registered", "Registered in the {event_type}. {participants_label}: {count}").format(event_type=self.event_type, participants_label=participants_label, count=count)
            await interaction.response.send_message(success_msg, ephemeral=True)
        else:
            error_msg = _text(self.msgs, "errors.registration_failed", "Error registering. Try again.")
            await interaction.response.send_message(error_msg, ephemeral=True)


class EventRegistrationView(discord.ui.View):
    """View with event registration button."""

    def __init__(self, server_id: str, event_type: str, label: str = "Apuntarse"):
        super().__init__(timeout=60)
        self.add_item(EventRegisterButton(server_id, event_type, label))
