"""Canvas Trickster content builders."""

import asyncio
import json

import discord

from discord_bot import discord_core_commands as core
from discord_bot.discord_utils import translate_dice_combination
from .state import (
    _get_canvas_dice_state,
    _get_canvas_dice_ranking,
)
from .canvas_base import CanvasModal

get_server_key = core.get_server_key


logger = core.logger
AgentDatabase = core.AgentDatabase
is_admin = core.is_admin
set_role_enabled = core.set_role_enabled

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


def build_canvas_role_trickster(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build the Trickster role view."""
    from .content import _get_personality_descriptions
    roles_messages = {}
    trickster_messages = {}
    try:
        server_id = get_server_key(guild) if guild else None
        personality_descriptions = _get_personality_descriptions(server_id)
        roles_messages = personality_descriptions.get("role_descriptions", {})
        trickster_messages = roles_messages.get("trickster", {})
    except Exception:
        pass

    def _trickster_text(key: str, fallback: str) -> str:
        """Get text from trickster messages with dot notation support."""
        # Handle dot notation for nested keys
        if "." in key:
            keys = key.split(".")
            value = trickster_messages
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None
                    break
        else:
            value = trickster_messages.get(key)
        
        return str(value).strip() if value else fallback

    # Load all subroles from roles_config database (single source of truth)
    active_subroles = []
    try:
        if get_roles_db_instance:
            server_key = get_server_key(guild)
            roles_db = get_roles_db_instance(server_key)
            
            # Check trickster role is enabled
            trickster_config = roles_db.get_role_config('trickster')
            if trickster_config and trickster_config.get('enabled', False):
                # Get all enabled trickster subroles from database
                trickster_subroles = ['dice_game']
                for subrole in trickster_subroles:
                    subrole_config = roles_db.get_role_config(subrole)
                    if subrole_config and subrole_config.get('enabled', False):
                        active_subroles.append(subrole)
                
    except Exception as e:
        logger.warning(f"Error loading subroles from roles_config: {e}")
        # Fallback to agent_config if database fails
        subroles = (agent_config or {}).get("roles", {}).get("trickster", {}).get("subroles", {})
        active_subroles = [name for name, cfg in subroles.items() if isinstance(cfg, dict) and cfg.get("enabled", False)]
    
    dice_state = _get_canvas_dice_state(guild)
    
    separator = _trickster_text("canvas_trickster_overview_separator", "---------")
    subrole_descriptions = trickster_messages.get("canvas_trickster_subrole_descriptions", {})
    
    active_descriptions = []
    for subrole in active_subroles:
        if subrole in subrole_descriptions:
            active_descriptions.append(subrole_descriptions[subrole])

    parts = [
        _trickster_text("canvas_trickster_overview_title", "🎭Canvas - Trickster"),
        _trickster_text("description", "Description: Trickster is a minigame based role."),
    ]

    if active_descriptions:
        parts.append("**Available subroles**")
        parts.extend(active_descriptions)

    parts += [
        "",
        "**Live state**",
        f"**Live state:** dice bet {dice_state['bet']:,} | pot {dice_state['pot_balance']:,}",
    ]

    return "\n".join(parts)


def build_canvas_role_trickster_detail(detail_name: str, admin_visible: bool, guild=None, author_id: int | None = None, agent_config: dict | None = None) -> str | None:
    """Build a detailed Trickster view."""
    # Handle overview case
    if detail_name == "overview":
        # Use the main overview function
        return build_canvas_role_trickster({}, admin_visible, guild)
    
    from .content import _get_personality_descriptions
    server_id = get_server_key(guild) if guild else None
    personality_descriptions = _get_personality_descriptions(server_id)
    roles_messages = personality_descriptions.get("role_descriptions", {})
    trickster_messages = roles_messages.get("trickster", {})

    def _trickster_text(key: str, fallback: str) -> str:
        """Get text from trickster messages with dot notation support."""
        # Handle dot notation for nested keys
        if "." in key:
            keys = key.split(".")
            value = trickster_messages
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None
                    break
        else:
            value = trickster_messages.get(key)
        
        return str(value).strip() if value else fallback

    if detail_name in {"dice", "game"}:
        dice_state = _get_canvas_dice_state(guild)
        descriptions = personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("dice_game", {})
        title = _trickster_text("dice_game.title", "🎲 DICE GAME")
        pot_title = _trickster_text("dice_game.current_balance", "💎 **CURRENT POT:**")
        fixed_bet = _trickster_text("dice_game.fixed_bet", "💎 **FIXED BET:**")
        game_description = _trickster_text("dice_game.description", "Test your luck against the Dice POT! Roll the dice and win big prizes!")
        dice_rules = _trickster_text("dice_game.rules", "-Triple Ones you won the POT!\n -n Hight Straight (4,5,6) you won x5 the bet.\n -Any Triple, you won x3 the bet.\n -The pairs will return you the bet.\n ")
        parts = [
            title,
            game_description,
            "**Rules**",
            dice_rules,
            "",
        ]

        ranking_data = _get_canvas_dice_ranking(guild, 10)
        ranking_title = _trickster_text("dice_game.ranking", "**🏆 DICE RANKING**")
        parts.append(ranking_title)
        if ranking_data:
            for player in ranking_data:
                medal = "🥇" if player["position"] == 1 else "🥈" if player["position"] == 2 else "🥉" if player["position"] == 3 else "🏅"
                parts.append(f"{medal} **#{player['position']}** {player['player_name']} | 🏆 Prize: {player['prize']:,} | Games: {player['total_plays']}")
        else:
            parts.append(_trickster_text("dice_game.rankingvoid", "📊 No ranked players yet. Be the first to play!"))

        parts.append("─" * 45)
        server_key = get_server_key(guild)
        server_id = str(guild.id) if guild else server_key
        if get_roles_db_instance is None:
            parts.append(_trickster_text("dice_game.historyvoid", "📊 Any play in the game. Be the first!"))
            return "\n".join(parts)
        db_dice = get_roles_db_instance(server_key)
        history = db_dice.get_dice_game_history(10)
        history_title = _trickster_text("dice_game.history", "**📜 DICE HISTORY**")
        parts.append(history_title)

        parts.append("─" * 45)
        if history:
            for record in history:
                user_name = record.get('user_name', 'Unknown')
                dice = record.get('dice', '')
                combination = record.get('combination', '')
                prize = record.get('prize', 0)
                created_at = record.get('created_at', '')
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = dt.strftime("%d/%m %H:%M")
                except:
                    date_str = created_at[:16] if created_at else ''
                
                dice_display = "🎲".join(dice.split('-')) if dice else "???"
                # Translate combination from English fallback to personality-specific text
                translated_combination = translate_dice_combination(combination, trickster_messages)
                prize_emoji = "💰" if prize > 0 else "💸"
                parts.append(f"👤 {user_name} | {dice_display} → {translated_combination} | {prize_emoji} {prize:,}")
        else:
            parts.append(descriptions.get("historyvoid", "📊 Any play in the game. Be the first!"))
        
        parts.append("─" * 45)
        parts += {  
            "",    
            f"**{pot_title} {dice_state['pot_balance']:,}** :coin: ",
            f"{fixed_bet} {dice_state.get('bet', 1):,} :coin:",
        }
        return "\n".join(parts)

    if detail_name in {"dice_admin"}:
        dice_state = _get_canvas_dice_state(guild)
        hot_pot = int(dice_state["bet"] * 72)
        
        # Get personality descriptions with English fallbacks
        descriptions = personality_descriptions.get("role_descriptions", {}).get("trickster", {}).get("dice_game", {})
        
        return "\n".join([
            "🎲 Trickster Canvas - Dice / Admin",
            _trickster_text("dice_game.admin_description", "Configure dice game settings and announcements"),
            _trickster_text("dice_game.current_settings", "**Current settings**"),
            f"{_trickster_text('dice_game.current_fixed_bet', '**Current fixed bet:**')} {dice_state['bet']:,} {_trickster_text('dice_game.gold_suffix', 'gold')}",
            f"{_trickster_text('dice_game.current_pot', '**Current pot:**')} {dice_state['pot_balance']:,} {_trickster_text('dice_game.gold_suffix', 'gold')}",
            f"{_trickster_text('dice_game.big_pot_threshold', '**Big pot threshold:**')} ~{hot_pot:,} {_trickster_text('dice_game.gold_suffix', 'gold')}",
            "",
            _trickster_text("dice_game.controls_title", "**Controls**"),
            f"{_trickster_text('dice_game.announcements_status', '- Announcements:')} {'On' if dice_state['announcements_active'] else 'Off'}",
            _trickster_text("dice_game.editable_fixed_bet", "- Editable fixed bet input"),
            _trickster_text("dice_game.editable_pot_value", "- Editable pot value input"),
            _trickster_text("dice_game.announcement_selector", "- Announcement on/off selector"),
            "",
            _trickster_text("dice_game.routing_title", "**Routing**"),
            _trickster_text("dice_game.back_only", "- Back only from here"),
            _trickster_text("dice_game.no_other_buttons", "- No other subrole buttons are shown in this admin screen"),
        ])

    return None


class TricksterActionModal(CanvasModal):
    def __init__(self, action_name: str, author_id: int, guild, admin_visible: bool, view=None):
        titles = {
            "dice_fixed_bet": "Dice Fixed Bet",
            "dice_pot_value": "Dice Pot Value",
            "beggar_frequency": "Beggar Frequency",
            "beggar_donate": "Beggar Donation",
        }
        super().__init__(title=titles.get(action_name, "Trickster Action"), author_id=author_id)
        self.action_name = action_name
        self.guild = guild
        self.admin_visible = admin_visible
        self.view = view
        label_map = {
            "dice_fixed_bet": "Gold amount",
            "dice_pot_value": "New pot balance",
            "beggar_frequency": "Hours",
            "beggar_donate": "Gold amount",
        }
        placeholder_map = {
            "dice_fixed_bet": "15",
            "dice_pot_value": "500",
            "beggar_frequency": "6",
            "beggar_donate": "25",
        }
        self.value_input = discord.ui.TextInput(
            label=label_map.get(action_name, "Value"),
            placeholder=placeholder_map.get(action_name, ""),
            required=True,
            max_length=120,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await handle_canvas_trickster_modal_submit(
            interaction,
            self.action_name,
            str(self.value_input.value).strip(),
            self.guild,
            self.author_id,
            self.admin_visible,
            self.view,
        )


async def handle_canvas_trickster_modal_submit(interaction: discord.Interaction, action_name: str, raw_value: str, guild, author_id: int, admin_visible: bool, view=None) -> None:
    # Defer immediately to prevent interaction timeout
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    
    server_key = get_server_key(guild)
    server_id = str(guild.id)
    server_name = guild.name

    from discord_bot.agent_discord import AGENT_CFG
    from agent_engine import PERSONALITY
    from .content import _build_canvas_role_embed, _build_canvas_sections, _build_canvas_embed
    from discord_bot.canvas.ui import CanvasRoleDetailView, _safe_edit_interaction_message

    sections = _build_canvas_sections(
        AGENT_CFG,
        "greetputre",
        "nogreetputre",
        "welcomeputre",
        "nowelcomeputre",
        "roleputre",
        "talkputre",
        admin_visible,
        server_id,
        author_id,
    )

    if action_name == "beggar_donate":
        # Defer the interaction to avoid timeout issues
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        if get_roles_db_instance is None:
            await interaction.followup.send("❌ Beggar donation systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.followup.send("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.followup.send("❌ Donation amount must be positive.", ephemeral=True)
            return
        db_banker = get_roles_db_instance(server_key)
        donor_id = str(author_id)
        donor_name = interaction.user.display_name
        from roles.banker.banker_db import get_banker_roles_db_instance
        from roles.banker.subroles.beggar.beggar_db import get_beggar_config
        db_banker_roles = get_banker_roles_db_instance(server_key)
        db_banker_roles.create_wallet(donor_id, donor_name, "user")
        wallet = db_banker.get_banker_wallet(donor_id)
        current_balance = wallet.get("balance", 0) if wallet else 0
        if current_balance < amount:
            await interaction.followup.send(f"❌ Solo tienes {current_balance:,} de oro disponible.", ephemeral=True)
            return
        beggar_config = get_beggar_config(server_id)
        reason = beggar_config.get_current_reason() or "el proyecto actual del clan"
        target_gold = beggar_config.get_target_gold()
        
        # Process donation with proper error handling
        donation_success = False
        error_message = ""
        
        try:
            # Update user balance (deduct donation)
            user_update_success = db_banker_roles.update_balance(
                donor_id, donor_name, 
                -amount, "BEGGAR_DONATION", f"Donation: {reason}"
            )
            
            if not user_update_success:
                error_message = "Error deducting gold from your account."
                logger.error(f"Failed to deduct {amount} gold from user {donor_id}")
                raise RuntimeError("User balance update failed")
            
            # Update beggar fund (add donation)
            fund_update_success = db_banker_roles.update_balance(
                "beggar_fund", "Beggar Fund", 
                amount, "BEGGAR_DONATION", f"Donation from {donor_name}: {reason}"
            )
            
            if not fund_update_success:
                error_message = "Error adding gold to beggar fund."
                logger.error(f"Failed to add {amount} gold to beggar fund")
                # Rollback user balance
                db_banker_roles.update_balance(
                    donor_id, donor_name, 
                    amount, "BEGGAR_DONATION", "Reversal - failed donation"
                )
                raise RuntimeError("Fund balance update failed")
            
            # Update beggar statistics
            roles_db = get_roles_db_instance(server_key)
            stats_update_success = roles_db.update_beggar_donation(donor_id, donor_name, amount, reason)
            
            if not stats_update_success:
                error_message = "Error updating donation statistics."
                logger.error(f"Failed to update beggar statistics for {donor_id}")
                # This is non-critical, donation still processed
            
            # Save donation request
            roles_db.save_beggar_request(
                donor_id,
                donor_name,
                "BEGGAR_DONATION",
                f"Donated {amount} gold",
                str(interaction.channel.id) if interaction.channel else None,
                None,
            )
            
            donation_success = True
            
        except Exception as e:
            logger.error(f"Donation processing error for {donor_id}: {e}")
            if not error_message:
                error_message = "Database error during donation processing."
        
        if not donation_success:
            await interaction.followup.send(
                f"❌ {error_message} Please try again later.",
                ephemeral=True
            )
            return

        fund_balance = db_banker_roles.get_balance("beggar_fund")
        
        # Try to refresh the view, but don't let it prevent the success message
        try:
            current_detail = getattr(view, "current_detail", "beggar") if view else "beggar"
            if current_detail.startswith("beggar"):
                new_content = build_canvas_role_trickster_detail(current_detail, admin_visible, guild, author_id, view.agent_config if view else AGENT_CFG)
                if new_content:
                    server_id = get_server_key(guild) if guild else None
                    embed = _build_canvas_embed("roles", new_content, admin_visible, server_id=server_id)
                    if view:
                        await _safe_edit_interaction_message(interaction, embed=embed, view=view)
                    # Note: We can't edit the message directly if interaction is deferred and no view
        except Exception as refresh_error:
            logger.warning(f"Could not refresh Canvas view after donation: {refresh_error}")
            # Don't return here - continue to show success message

        # Show success message using followup since interaction is deferred
        success_message = (
            f"✅ Donation accepted: {amount:,} gold.\n"
            f"🪙 Fund: {fund_balance:,}\n"
            f"🎯 Target: {target_gold:,}\n"
            f"📣 Reason: {reason}"
        )
        
        await interaction.followup.send(success_message, ephemeral=True)
        return

    if not admin_visible or not is_admin(interaction):
        await interaction.followup.send("❌ This trickster option is admin-only.", ephemeral=True)
        return

    if action_name == "beggar_frequency":
        try:
            hours = int(raw_value)
        except ValueError:
            await interaction.followup.send("❌ Enter a valid number of hours.", ephemeral=True)
            return
        if hours < 1 or hours > 168:
            await interaction.followup.send("❌ Frequency must be between 1 and 168 hours.", ephemeral=True)
            return
        try:
            from roles.banker.subroles.beggar.beggar_db import get_beggar_config
            beggar_config = get_beggar_config(server_id)
            ok = beggar_config.set_frequency_hours(hours)
            if not ok:
                raise RuntimeError("Could not update beggar frequency")
            target_gold = beggar_config.get_target_gold()
            message = (
                f"✅ Beggar frequency updated to `{hours}` hours.\n"
                f"Current target: {target_gold:,} gold"
            )
        except Exception as e:
            logger.exception(f"Canvas trickster frequency update failed: {e}")
            await interaction.followup.send("❌ Could not update frequency.", ephemeral=True)
            return
        await interaction.followup.send(message, ephemeral=True)
        return

    if action_name in {"dice_fixed_bet", "dice_pot_value"}:
        if get_roles_db_instance is None or get_roles_db_instance is None:
            await interaction.followup.send("❌ Dice game systems are not available.", ephemeral=True)
            return
        try:
            amount = int(raw_value)
        except ValueError:
            await interaction.followup.send("❌ Enter a valid gold amount.", ephemeral=True)
            return
        if amount < 0:
            await interaction.followup.send("❌ Amount must be zero or greater.", ephemeral=True)
            return
        try:
            if action_name == "dice_fixed_bet":
                if amount < 1 or amount > 1000:
                    await interaction.followup.send("❌ Fixed bet must be between 1 and 1000 gold.", ephemeral=True)
                    return
                roles_db = get_roles_db_instance(server_key)
                ok = roles_db.save_role_config("dice_game", True, json.dumps({"fixed_bet": amount}))
                if not ok:
                    raise RuntimeError("Could not update fixed bet")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice fixed bet updated to `{amount}` gold.\n"
                    f"Current pot: {state['pot_balance']:,} gold"
                )
            else:
                from roles.banker.banker_db import get_banker_roles_db_instance
                db_banker = get_banker_roles_db_instance(server_key)
                db_banker.create_wallet("dice_game_pot", "Dice Game Pot", wallet_type="system")
                current_balance = db_banker.get_balance("dice_game_pot")
                delta = amount - current_balance
                ok = db_banker.update_balance("dice_game_pot", "Dice Game Pot", delta, "DICE_POT_ADMIN_SET", "Canvas pot update", str(interaction.user.id), interaction.user.display_name)
                if not ok:
                    raise RuntimeError("Could not update pot balance")
                state = _get_canvas_dice_state(guild)
                message = (
                    f"✅ Dice pot balance updated to `{amount}` gold.\n"
                    f"Current fixed bet: {state['bet']:,} gold"
                )
        except Exception as e:
            logger.exception(f"Canvas trickster dice update failed: {e}")
            await interaction.followup.send("❌ Could not update dice settings.", ephemeral=True)
            return
        await interaction.followup.send(message, ephemeral=True)


async def handle_canvas_trickster_action(interaction: discord.Interaction, action_name: str, view) -> None:
    from .content import _build_canvas_role_embed
    from discord_bot.canvas.ui import CanvasRoleDetailView, _safe_send_interaction_message

    try:
        server_key = get_server_key(interaction.guild)
        server_id = str(interaction.guild.id)
        if action_name in {"announcements_on", "announcements_off"}:
            if get_roles_db_instance is None:
                await interaction.response.send_message("❌ Dice game database is not available.", ephemeral=True)
                return
            enabled = action_name == "announcements_on"
            roles_db = get_roles_db_instance(server_key)
            ok = roles_db.save_role_config("dice_game", True, json.dumps({"announcements_active": enabled}))
            current_detail = "dice_admin"
            applied_text = f"Dice announcements {'enabled' if enabled else 'disabled'}."
        elif action_name in {"beggar_on", "beggar_off"}:
            try:
                from roles.banker.subroles.beggar.beggar_db import get_beggar_config
                from roles.banker.subroles.beggar.beggar_task import execute_beggar_task

                server_id_str = str(interaction.guild.id)
                beggar_config = get_beggar_config(server_id_str)
                enabled = action_name == "beggar_on"

                if beggar_config.set_enabled(enabled):
                    if enabled:
                        selected_reason = beggar_config.select_new_reason()
                        try:
                            success = await execute_beggar_task(server_id=server_id_str, bot_instance=interaction.client)
                            if success:
                                applied_text = f"🙏 **Beggar enabled** - First message sent with reason: '{selected_reason}'"
                            else:
                                applied_text = f"🙏 **Beggar enabled** - Reason selected: '{selected_reason}' (First message will be sent on next cycle)"
                        except Exception as e:
                            applied_text = f"🙏 **Beggar enabled** - Reason selected: '{selected_reason}' (First message failed: {str(e)})"
                    else:
                        applied_text = "🚫 **Beggar disabled** - No more periodic beggar requests."
                    ok = True
                else:
                    applied_text = "❌ Error updating beggar configuration."
                    ok = False
            except ImportError:
                await interaction.response.send_message("❌ Beggar system is not available.", ephemeral=True)
                return
            except Exception as e:
                applied_text = f"❌ Error: {str(e)}"
                ok = False

            current_detail = "beggar_admin"
        elif action_name == "beggar_force_minigame":
            try:
                from roles.banker.subroles.beggar.beggar_minigame import BeggarMinigame

                server_id_str = str(interaction.guild.id)
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)

                async def execute_minigame_background():
                    try:
                        minigame = BeggarMinigame(server_id_str)
                        result = await minigame.force_weekly_minigame(fallback_channel=interaction.channel)
                        logger.info(f"Background minigame completed for server {server_id_str}: {result['success']}")
                    except Exception as e:
                        logger.error(f"Error in background minigame execution: {e}")

                asyncio.create_task(execute_minigame_background())
                applied_text = "🎲 Minigame iniciado en background..."
                ok = True
            except ImportError:
                applied_text = "❌ Beggar minigame system is not available."
                ok = False
            except Exception as e:
                logger.error(f"Error in beggar force minigame setup: {e}")
                applied_text = f"❌ Error forcing minigame: {str(e)}"
                ok = False

            current_detail = "beggar_admin"
        else:
            await interaction.response.send_message("❌ Unknown trickster action.", ephemeral=True)
            return
    except Exception as e:
        logger.exception(f"Canvas trickster action failed: {e}")
        ok = False

    if not ok:
        error_message = applied_text if "applied_text" in locals() and applied_text else "❌ Could not update trickster settings."
        await _safe_send_interaction_message(interaction, error_message, ephemeral=True)
        return

    if interaction.guild is None or not hasattr(interaction.guild, "id"):
        logger.warning(f"Canvas trickster action: invalid interaction.guild (type: {type(interaction.guild)}, value: {interaction.guild})")
        await _safe_send_interaction_message(interaction, "❌ Invalid guild context.", ephemeral=True)
        return

    content = build_canvas_role_trickster_detail(current_detail, view.admin_visible, interaction.guild, view.author_id, view.agent_config)

    next_view = CanvasRoleDetailView(
        author_id=view.author_id,
        role_name=view.role_name,
        agent_config=view.agent_config,
        admin_visible=view.admin_visible,
        sections=view.sections,
        current_detail=current_detail,
        guild=interaction.guild,
    )
    next_view.auto_response_preview = applied_text
    action_embed = _build_canvas_role_embed("trickster", content or "", view.admin_visible, current_detail, None, next_view.auto_response_preview)
    try:
        await interaction.response.edit_message(content=None, embed=action_embed, view=next_view)
    except discord.InteractionResponded:
        await interaction.followup.edit_message(interaction.message.id, embed=action_embed, view=next_view)
    except discord.NotFound:
        try:
            await interaction.followup.send(embed=action_embed, view=next_view, ephemeral=True)
        except discord.NotFound:
            logger.warning("Canvas trickster interaction expired completely - unable to send followup")
        except Exception as e:
            logger.exception(f"Failed to send canvas trickster followup: {e}")
    except Exception as e:
        logger.exception(f"Failed to edit canvas trickster message: {e}")
        try:
            await interaction.followup.send("❌ Error al actualizar vista. Por favor intenta de nuevo.", ephemeral=True)
        except discord.NotFound:
            logger.warning("Canvas trickster interaction expired during error handling")
        except Exception as followup_e:
            logger.exception(f"Failed to send error followup: {followup_e}")
