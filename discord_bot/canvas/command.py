"""Canvas command registration."""

import discord
from agent_logging import get_logger

logger = get_logger("discord_core")


def register_canvas_command(bot, agent_config, greet_name, nogreet_name, welcome_name, nowelcome_name, role_cmd_name, talk_cmd_name):
    from discord_bot import discord_core_commands as core

    try:
        @bot.command(name="canvas")
        async def cmd_canvas(ctx, section: str = "home", target: str = "", detail: str = ""):
            logger.info(
                f"Canvas command entered by {ctx.author.name}: raw_section={section!r}, raw_target={target!r}, raw_detail={detail!r}, "
                f"in_guild={bool(ctx.guild)}"
            )
            
            # Check if this is a name-filtered command
            # If section matches a bot name, treat it as name filter and shift parameters
            bot_name = ctx.bot.user.name.lower()
            section_lower = (section or "").strip().lower()
            valid_sections = {"home", "role", "roles", "personal", "help", "behavior"}
            
            if section_lower == bot_name:
                # This is a name-filtered command: !canvas <bot_name> [section] [target] [detail]
                logger.info(f"Canvas command targeted to bot '{section}' - name filter activated")
                # Shift parameters: section becomes target, target becomes detail, detail becomes empty
                section = target or "home"
                target = detail or ""
                detail = ""
            elif section_lower and section_lower not in valid_sections:
                # Check if this might be a name filter for a different bot
                logger.info(f"Canvas command with unknown name '{section}' - ignoring as it's for another bot")
                return  # Don't respond, let the targeted bot handle it
            
            # Auto-initialize news watcher premises on first canvas use
            if ctx.guild:
                try:
                    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
                    guild_id = str(ctx.guild.id)
                    user_id = str(ctx.author.id)
                    db_watcher = get_news_watcher_db_instance(guild_id)
                    
                    # Check if user already has premises
                    current_premises, context = db_watcher.get_premises_with_context(user_id)
                    if not current_premises:
                        # Initialize with default premises
                        success, message = db_watcher.initialize_user_premises(user_id, guild_id)
                        if success:
                            logger.info(f"Auto-initialized premises for user {user_id} on first canvas use")
                except Exception as e:
                    logger.warning(f"Could not auto-initialize premises for user {ctx.author.id}: {e}")
            
            section_name = (section or "home").strip().lower()
            target_name = (target or "").strip().lower()
            detail_name = (detail or "").strip().lower()
            admin_visible = bool(ctx.guild and core.is_admin(ctx))
            
            # Log the final parameter values after name filtering
            logger.info(f"Canvas command parameters after processing: section='{section_name}', target='{target_name}', detail='{detail_name}'")

            if section_name == "role":
                if detail_name:
                    role_detail_view = core._build_canvas_role_detail_view(
                        target_name,
                        detail_name,
                        agent_config,
                        admin_visible,
                        ctx.guild,
                        int(ctx.author.id),
                    )
                    if role_detail_view is not None:
                        # Store reference to original command message for timeout cleanup
                        role_detail_view.original_command_message = ctx.message
                        server_id = core.get_server_key(guild) if guild else None
                        if target_name == "banker":
                            role_embed = core._build_canvas_role_embed("banker", role_detail_view, admin_visible, detail_name, ctx.author, server_id=server_id)
                            canvas_sent_msg = core._personality_answers.get("general_messages", {}).get(
                                "canvas_sent_private",
                                "📩 Canvas guide sent by private message."
                            )
                            await core.send_embed_dm_or_channel(ctx, role_embed, canvas_sent_msg)
                        else:
                            canvas_sent_msg = core._personality_answers.get("general_messages", {}).get(
                                "canvas_sent_private",
                                "📩 Canvas guide sent by private message."
                            )
                            await core.send_dm_or_channel(ctx, role_detail_view, canvas_sent_msg)
                        return

                role_view = core._build_canvas_role_view(
                    target_name,
                    agent_config,
                    admin_visible,
                    ctx.guild,
                    int(ctx.author.id),
                )
                if role_view is None:
                    await ctx.send(
                        "❌ Unknown or unavailable role. Use: `!canvas role news_watcher`, `!canvas role treasure_hunter`, `!canvas role trickster`, `!canvas role banker`, `!canvas role mc`, or detailed views like `!canvas role trickster dice`. You can also use `!canvas <bot_name> role <name>` to target a specific bot."
                    )
                    return

                # Store reference to original command message for timeout cleanup
                role_view.original_command_message = ctx.message
                server_id = core.get_server_key(guild) if guild else None
                if target_name == "banker":
                    role_embed = core._build_canvas_role_embed("banker", role_view, admin_visible, "overview", ctx.author, server_id=server_id)
                    canvas_sent_msg = core._personality_answers.get("general_messages", {}).get(
                        "canvas_sent_private",
                        "📩 Canvas guide sent by private message."
                    )
                    await core.send_embed_dm_or_channel(ctx, role_embed, canvas_sent_msg)
                else:
                    canvas_sent_msg = core._personality_answers.get("general_messages", {}).get(
                        "canvas_sent_private",
                        "📩 Canvas guide sent by private message."
                    )
                    await core.send_dm_or_channel(ctx, role_view, canvas_sent_msg)
                return

            # Handle DM case by using default server
            guild = ctx.guild
            is_dm = not guild
            
            # Try to get user's last server or first available as default
            if is_dm:
                try:
                    from agent_db import get_user_last_server_id
                    bot = ctx.bot
                    
                    # Try to get user's last server first
                    user_id = str(ctx.author.id)
                    last_server_id = get_user_last_server_id(user_id)
                    
                    if last_server_id:
                        # Find the guild object for this server ID
                        guild = discord.utils.get(bot.guilds, id=int(last_server_id))
                        if guild:
                            logger.info(f"Using user's last server '{guild.name}' ({guild.id}) for Canvas command from DM")
                        else:
                            # Server not found in bot's guilds, fall back to first available
                            if bot.guilds:
                                guild = bot.guilds[0]
                                logger.info(f"User's last server not found, using default server '{guild.name}' for Canvas command from DM")
                            else:
                                await ctx.send("❌ No servers available. Please execute Canvas commands from a server.")
                                return
                    else:
                        # No last server found, use first available
                        if bot and bot.guilds:
                            guild = bot.guilds[0]
                            logger.info(f"No user history found, using default server '{guild.name}' for Canvas command from DM")
                        else:
                            await ctx.send("❌ No servers available. Please execute Canvas commands from a server.")
                            return
                except Exception as e:
                    logger.error(f"Could not get server for DM Canvas command: {e}")
                    await ctx.send("❌ Could not access a server. Please execute Canvas commands from a server.")
                    return
            
            sections = core._build_canvas_sections(
                agent_config,
                greet_name,
                nogreet_name,
                welcome_name,
                nowelcome_name,
                role_cmd_name,
                talk_cmd_name,
                admin_visible,
                core.get_server_key(guild) if guild else "default",
                ctx.author.id,
                guild,
                is_dm,
            )

            if section_name not in sections:
                await ctx.send(
                    "❌ Unknown canvas section. Use: `!canvas home`, `!canvas roles`, `!canvas role <name>`, `!canvas personal`, `!canvas help`, or `!canvas <bot_name> [section]` to target a specific bot."
                )
                return

            view = core.CanvasNavigationView(ctx.author.id, sections, admin_visible, agent_config, guild, show_dropdown=(section_name not in {"home", "behavior"}))
            view.update_visibility()
            logger.info(
                f"Canvas top-level view prepared for {ctx.author.name}: section={section_name}, "
                f"admin_visible={admin_visible}, buttons={len(view.children)}, in_guild={bool(ctx.guild)}"
            )
            server_id = core.get_server_key(guild) if guild else None
            if section_name == "home":
                home_embed = core._build_canvas_embed("home", sections[section_name], admin_visible, server_id=server_id)
                message = await ctx.send(embed=home_embed, view=view)
            elif section_name == "behavior":
                behavior_embed = core._build_canvas_embed("behavior", sections[section_name], admin_visible,
                                                          sections.get("behavior_title"), sections.get("behavior_description"), server_id=server_id)
                message = await ctx.send(embed=behavior_embed, view=view)
            else:
                message = await ctx.send(sections[section_name], view=view)
            view.message = message
            # Store reference to original command message for timeout cleanup
            view.original_command_message = ctx.message
            logger.info(
                f"Canvas top-level view sent: message_id={message.id}, components={len(getattr(message, 'components', []))}"
            )

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command canvas already registered, skipping...")
        else:
            logger.error(f"Error registering canvas: {e}")
