# Discord Command for Admins to Force News Watcher

## Command to add to your Discord bot:

```python
@commands.has_permissions(administrator=True)
@bot.command(name='forcewatcher', help='Force news watcher to check subscriptions (Admin only)')
async def force_watcher(ctx):
    """Manually trigger news watcher to process all subscriptions."""
    import asyncio
    from roles.news_watcher.news_watcher import process_channel_subscriptions
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    
    try:
        await ctx.send("🔄 **Forcing news watcher iteration...**")
        
        # Get database instance
        db = get_news_watcher_db_instance(str(ctx.guild.id))
        
        # Create HTTP client (you'll need to implement this based on your bot's HTTP client)
        http = None  # Replace with your actual HTTP client
        
        # Force the watcher to process all channel subscriptions
        await process_channel_subscriptions(http, db, str(ctx.guild.id))
        
        await ctx.send("✅ **News watcher iteration completed!**\n"
                      "📊 Checked all channel subscriptions for new articles.\n"
                      "📰 Any new articles will be processed and notifications sent.")
        
    except Exception as e:
        await ctx.send(f"❌ **Error running news watcher:** `{str(e)}`")
        logger.exception(f"Error in force_watcher command: {e}")
```

## Alternative simpler version (if you don't have HTTP client setup):

```python
@commands.has_permissions(administrator=True)
@bot.command(name='testwatcher', help='Test news watcher subscription status (Admin only)')
async def test_watcher(ctx):
    """Check news watcher subscription status without fetching news."""
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    
    try:
        await ctx.send("🔍 **Checking news watcher status...**")
        
        # Get database instance
        db = get_news_watcher_db_instance(str(ctx.guild.id))
        
        # Get all channels with subscriptions
        channels = db.get_all_channels_with_subscriptions()
        
        if not channels:
            await ctx.send("📭 **No active subscriptions found**")
            return
            
        response = f"📊 **Found {len(channels)} channel(s) with subscriptions:**\n\n"
        
        for channel_id, channel_name, server_id in channels:
            # Get subscription details for this channel
            subs = db.get_channel_subscriptions(channel_id)
            
            response += f"🔹 **{channel_name}** (`{channel_id}`)\n"
            
            # Count subscription types
            flat_count = len([s for s in subs if s[1] is None])  # category subscriptions
            specific_count = len([s for s in subs if s[1] is not None])  # specific feed subscriptions
            
            response += f"   - 📰 Category subscriptions: {flat_count}\n"
            response += f"   - 🎯 Specific feed subscriptions: {specific_count}\n\n"
        
        response += "💡 **Use `!watcherchannel status` in any subscribed channel to see detailed subscription info**"
        
        await ctx.send(response)
        
    except Exception as e:
        await ctx.send(f"❌ **Error checking status:** `{str(e)}`")
        logger.exception(f"Error in test_watcher command: {e}")
```

## How to use:

1. **For server admins**: Type `!forcewatcher` or `!testwatcher` in any channel
2. **Requirements**: User must have Administrator permission
3. **Results**: 
   - `!forcewatcher`: Actually runs the news watcher and processes subscriptions
   - `!testwatcher`: Shows subscription status without fetching news

## Note:
- Replace `bot` with your actual bot instance name
- Make sure to import the command decorator (`@commands.has_permissions(administrator=True)`)
- You may need to adjust the HTTP client setup based on your bot's architecture
