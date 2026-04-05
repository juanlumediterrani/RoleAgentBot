"""
Fatigue Management Commands for Discord

This module provides Discord slash commands for managing and monitoring
fatigue limits and usage statistics.
"""

import discord
from discord.ext import commands
from discord import app_commands
from agent_fatigue_limits import get_usage_summary, get_fatigue_limits, format_limit_exceeded_message, check_fatigue_limit
from agent_db import get_fatigue_stats, get_active_server_id
from agent_logging import get_logger

logger = get_logger('fatigue_commands')

class FatigueCommands(commands.Cog):
    """Fatigue management commands"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="fatigue_stats",
        description="View LLM usage statistics for this server"
    )
    @app_commands.describe(
        user="Show stats for a specific user (optional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def fatigue_stats(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None
    ):
        """Show fatigue statistics"""
        try:
            await interaction.response.defer()
            
            server_id = get_active_server_id()
            if not server_id:
                await interaction.followup.send("❌ Unable to determine server ID")
                return
            
            if user:
                # Show specific user stats
                stats = get_usage_summary(str(user.id), user.display_name)
                
                if not stats or stats.get('daily_requests', 0) == 0:
                    embed = discord.Embed(
                        title=f"📊 Fatigue Stats - {user.display_name}",
                        description="No usage recorded yet.",
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
                    await interaction.followup.send(embed=embed)
                    return
                
                limits = get_fatigue_limits()
                user_limits = limits.get('user', {})
                
                daily_pct = min(100, (stats['daily_requests'] / user_limits.get('daily_max', 50)) * 100)
                hourly_pct = min(100, (stats['hourly_requests'] / user_limits.get('hourly_max', 10)) * 100)
                burst_pct = min(100, (stats['burst_requests'] / user_limits.get('burst_max', 5)) * 100)
                
                embed = discord.Embed(
                    title=f"📊 Fatigue Stats - {user.display_name}",
                    color=discord.Color.green() if daily_pct < 80 else discord.Color.orange() if daily_pct < 95 else discord.Color.red()
                )
                
                embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
                
                embed.add_field(
                    name="📅 Daily Usage",
                    value=f"**{stats['daily_requests']}** / {user_limits.get('daily_max', 50)} ({daily_pct:.1f}%)",
                    inline=False
                )
                
                embed.add_field(
                    name="⏰ Hourly Usage",
                    value=f"**{stats['hourly_requests']}** / {user_limits.get('hourly_max', 10)} ({hourly_pct:.1f}%)",
                    inline=False
                )
                
                embed.add_field(
                    name="⚡ Burst Usage (5min)",
                    value=f"**{stats['burst_requests']}** / {user_limits.get('burst_max', 5)} ({burst_pct:.1f}%)",
                    inline=False
                )
                
                embed.add_field(
                    name="📈 Total Requests",
                    value=f"**{stats['total_requests']}**",
                    inline=True
                )
                
                if stats.get('last_request_date'):
                    embed.add_field(
                        name="🕐 Last Request",
                        value=f"**{stats['last_request_date']}**",
                        inline=True
                    )
                
                embed.set_footer(text="Use /fatigue_limits to view current limits")
                await interaction.followup.send(embed=embed)
                
            else:
                # Show server-wide stats
                all_stats = get_fatigue_stats(server_id)
                users = all_stats.get('users', [])
                
                if not users:
                    embed = discord.Embed(
                        title="📊 Server Fatigue Stats",
                        description="No usage recorded yet.",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Separate server stats from user stats
                server_stats = None
                user_stats = []
                
                for stat in users:
                    if stat.get('user_id', '').startswith('server_'):
                        server_stats = stat
                    else:
                        user_stats.append(stat)
                
                embed = discord.Embed(
                    title="📊 Server Fatigue Stats",
                    color=discord.Color.blue()
                )
                
                # Server totals
                if server_stats:
                    limits = get_fatigue_limits()
                    server_limits = limits.get('server', {})
                    
                    daily_pct = min(100, (server_stats['daily_requests'] / server_limits.get('daily_max', 500)) * 100)
                    hourly_pct = min(100, (server_stats['hourly_requests'] / server_limits.get('hourly_max', 100)) * 100)
                    burst_pct = min(100, (server_stats['burst_requests'] / server_limits.get('burst_max', 20)) * 100)
                    
                    embed.add_field(
                        name="🖥️ Server Totals",
                        value=f"Daily: **{server_stats['daily_requests']}** / {server_limits.get('daily_max', 500)} ({daily_pct:.1f}%)\n"
                              f"Hourly: **{server_stats['hourly_requests']}** / {server_limits.get('hourly_max', 100)} ({hourly_pct:.1f}%)\n"
                              f"Burst: **{server_stats['burst_requests']}** / {server_limits.get('burst_max', 20)} ({burst_pct:.1f}%)",
                        inline=False
                    )
                
                # Top users
                if user_stats:
                    top_users = sorted(user_stats, key=lambda x: x['daily_requests'], reverse=True)[:10]
                    
                    user_list = []
                    for i, user_stat in enumerate(top_users, 1):
                        user_list.append(f"**{i}.** {user_stat.get('user_name', 'Unknown')}: **{user_stat['daily_requests']}** daily")
                    
                    embed.add_field(
                        name=f"👥 Top Users (Daily)",
                        value="\n".join(user_list) if user_list else "No users found",
                        inline=False
                    )
                
                embed.set_footer(text="Use /fatigue_stats @user to see individual stats")
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in fatigue_stats command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="fatigue_limits", description="View current fatigue limits configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def fatigue_limits(self, interaction: discord.Interaction):
        """Show current fatigue limits configuration."""
        try:
            limits = get_fatigue_limits()
            
            embed = discord.Embed(
                title="⚙️ Fatigue Limits Configuration",
                color=discord.Color.gold()
            )
            
            # User limits
            user_limits = limits.get('user', {})
            embed.add_field(
                name="👤 User Limits",
                value=f"Daily: **{user_limits.get('daily_max', 50)}**\n"
                      f"Hourly: **{user_limits.get('hourly_max', 10)}**\n"
                      f"Burst: **{user_limits.get('burst_max', 5)}**",
                inline=True
            )
            
            # Server limits
            server_limits = limits.get('server', {})
            embed.add_field(
                name="🖥️ Server Limits",
                value=f"Daily: **{server_limits.get('daily_max', 500)}**\n"
                      f"Hourly: **{server_limits.get('hourly_max', 100)}**\n"
                      f"Burst: **{server_limits.get('burst_max', 20)}**",
                inline=True
            )
            
            # Behavior settings
            behavior = limits.get('behavior', {})
            embed.add_field(
                name="🎛️ Behavior",
                value=f"Strict Mode: **{'Yes' if behavior.get('strict_mode', False) else 'No'}**\n"
                      f"Grace Period: **{behavior.get('grace_period', 3)}** requests\n"
                      f"Cooldown: **{behavior.get('cooldown_minutes', 15)}** minutes",
                inline=True
            )
            
            # Exemptions
            exemptions = limits.get('exemptions', {})
            admin_users = exemptions.get('admin_users', [])
            critical_tasks = exemptions.get('critical_tasks', [])
            
            embed.add_field(
                name="🛡️ Exemptions",
                value=f"Admin Users: **{len(admin_users)}** configured\n"
                      f"Critical Tasks: **{', '.join(critical_tasks) if critical_tasks else 'None'}**",
                inline=False
            )
            
            embed.set_footer(text="Configuration from agent_config.json")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in fatigue_limits command: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="fatigue_check", description="Check if a user would be limited")
    @app_commands.describe(user="User to check")
    @app_commands.checks.has_permissions(administrator=True)
    async def fatigue_check(self, interaction: discord.Interaction, user: discord.Member):
        """Check if a user would be limited by fatigue."""
        try:
            await interaction.response.defer()
            
            # Test with a default call type
            result = check_fatigue_limit(str(user.id), user.display_name, "default")
            
            color = discord.Color.green() if result.allowed else discord.Color.red()
            
            embed = discord.Embed(
                title=f"🔍 Fatigue Check - {user.display_name}",
                color=color
            )
            
            embed.add_field(
                name="Status",
                value="✅ **Allowed**" if result.allowed else "❌ **Blocked**",
                inline=False
            )
            
            embed.add_field(
                name="Reason",
                value=f"**{result.reason}**",
                inline=False
            )
            
            if not result.allowed and result.reset_time:
                embed.add_field(
                    name="Reset Time",
                    value=f"**{result.reset_time}**",
                    inline=False
                )
            
            embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in fatigue_check command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(FatigueCommands(bot))
