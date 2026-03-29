"""
Fatigue statistics Discord command
"""

import discord
from discord.ext import commands
from discord import app_commands
from agent_db import get_fatigue_stats, get_active_server_name
from agent_logging import get_logger

logger = get_logger('fatigue_commands')

class FatigueCommands(commands.Cog):
    """Commands for viewing fatigue statistics"""
    
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
            
            server_name = get_active_server_name()
            if not server_name:
                await interaction.followup.send("❌ Unable to determine server name")
                return
            
            if user:
                # Show specific user stats
                stats = get_fatigue_stats(server_name, str(user.id))
                
                if not stats:
                    embed = discord.Embed(
                        title="📊 Fatigue Statistics",
                        description=f"No data found for {user.mention}",
                        color=discord.Color.orange()
                    )
                else:
                    embed = discord.Embed(
                        title="📊 Fatigue Statistics",
                        description=f"Statistics for {user.mention}",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(name="📅 Daily Requests", value=str(stats.get('daily_requests', 0)), inline=True)
                    embed.add_field(name="📈 Total Requests", value=str(stats.get('total_requests', 0)), inline=True)
                    embed.add_field(name="📅 Last Request", value=stats.get('last_request_date', 'Never'), inline=False)
                
                embed.set_footer(text=f"Server: {server_name}")
                await interaction.followup.send(embed=embed)
                
            else:
                # Show server-wide stats
                all_stats = get_fatigue_stats(server_name)
                users = all_stats.get('users', [])
                
                if not users:
                    embed = discord.Embed(
                        title="📊 Server Fatigue Statistics",
                        description="No usage data available",
                        color=discord.Color.orange()
                    )
                else:
                    embed = discord.Embed(
                        title="📊 Server Fatigue Statistics",
                        description=f"Usage statistics for {server_name}",
                        color=discord.Color.blue()
                    )
                    
                    # Find server total
                    server_stats = None
                    user_stats = []
                    
                    for user_data in users:
                        if user_data['user_id'].startswith('server_'):
                            server_stats = user_data
                        else:
                            user_stats.append(user_data)
                    
                    # Show server total
                    if server_stats:
                        embed.add_field(
                            name="🖥️ Server Total",
                            value=f"Daily: {server_stats['daily_requests']} | Total: {server_stats['total_requests']}",
                            inline=False
                        )
                    
                    # Show top users
                    if user_stats:
                        top_users = sorted(user_stats, key=lambda x: x['total_requests'], reverse=True)[:10]
                        
                        user_list = []
                        for i, user_data in enumerate(top_users, 1):
                            user_list.append(f"**{i}.** {user_data['user_name']}: {user_data['daily_requests']} daily / {user_data['total_requests']} total")
                        
                        if user_list:
                            embed.add_field(
                                name="👥 Top Users",
                                value="\n".join(user_list),
                                inline=False
                            )
                
                embed.set_footer(text="Use /fatigue_stats @user to see individual stats")
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in fatigue_stats command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching statistics")

async def setup(bot: commands.Bot):
    """Setup function for the cog"""
    await bot.add_cog(FatigueCommands(bot))
