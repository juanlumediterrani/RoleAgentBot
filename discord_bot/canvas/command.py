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

            section_name = (section or "home").strip().lower()
            target_name = (target or "").strip().lower()
            detail_name = (detail or "").strip().lower()
            admin_visible = bool(ctx.guild and core.is_admin(ctx))

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
                        if target_name == "banker":
                            role_embed = core._build_canvas_role_embed("banker", role_detail_view, admin_visible, detail_name, ctx.author)
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
                        "❌ Unknown or unavailable role. Use: `!canvas role news_watcher`, `!canvas role treasure_hatcher`, `!canvas role trickster`, `!canvas role banker`, `!canvas role mc`, or detailed views like `!canvas role trickster dice`."
                    )
                    return

                if target_name == "banker":
                    role_embed = core._build_canvas_role_embed("banker", role_view, admin_visible, "overview", ctx.author)
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

            sections = core._build_canvas_sections(
                agent_config,
                greet_name,
                nogreet_name,
                welcome_name,
                nowelcome_name,
                role_cmd_name,
                talk_cmd_name,
                admin_visible,
                core.get_server_key(ctx.guild) if ctx.guild else "default",
                ctx.author.id,
                ctx.guild,
            )

            if section_name not in sections:
                await ctx.send(
                    "❌ Unknown canvas section. Use: `!canvas home`, `!canvas roles`, `!canvas role <name>`, `!canvas personal`, or `!canvas help`."
                )
                return

            view = core.CanvasNavigationView(ctx.author.id, sections, admin_visible, agent_config, show_dropdown=(section_name not in {"home", "behavior"}))
            view.update_visibility()
            logger.info(
                f"Canvas top-level view prepared for {ctx.author.name}: section={section_name}, "
                f"admin_visible={admin_visible}, buttons={len(view.children)}, in_guild={bool(ctx.guild)}"
            )
            if section_name == "home":
                home_embed = core._build_canvas_embed("home", sections[section_name], admin_visible)
                message = await ctx.send(embed=home_embed, view=view)
            elif section_name == "behavior":
                behavior_embed = core._build_canvas_embed("behavior", sections[section_name], admin_visible)
                message = await ctx.send(embed=behavior_embed, view=view)
            else:
                message = await ctx.send(sections[section_name], view=view)
            view.message = message
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                logger.debug("Could not delete original !canvas command message due to missing permissions.")
            except discord.HTTPException as e:
                logger.debug(f"Could not delete original !canvas command message: {e}")
            logger.info(
                f"Canvas top-level view sent: message_id={message.id}, components={len(getattr(message, 'components', []))}"
            )

    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("Command canvas already registered, skipping...")
        else:
            logger.error(f"Error registering canvas: {e}")
