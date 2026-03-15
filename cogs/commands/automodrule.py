import discord
from discord.ext import commands

ALLOWED_USERS = [1218037361926209640, 1368916092260712509]

class AutoModRule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.author.id in ALLOWED_USERS

    @commands.group(name="am", invoke_without_command=True)
    async def am(self, ctx):
        await ctx.send("Available commands: `am show`, `am start`")

    @am.command(name="show")
    async def am_show(self, ctx):
        print(f"[DEBUG] am_show invoked by {ctx.author.id}")
        total_rules = 0
        servers_with_rules = 0
        server_stats = []

        for guild in self.bot.guilds:
            try:
                rules = await guild.fetch_automod_rules()
                count = len(rules)
                if count > 0:
                    total_rules += count
                    servers_with_rules += 1
                    server_stats.append((guild.name, count))
            except:
                pass
        
        # Sort by count descending
        server_stats.sort(key=lambda x: x[1], reverse=True)
        top_servers = "\n".join([f"- **{name}**: {count}" for name, count in server_stats[:5]])

        embed = discord.Embed(title="🛡️ AutoMod Stats", color=discord.Color.blue())
        embed.add_field(name="Total Rules", value=str(total_rules), inline=True)
        embed.add_field(name="Active Servers", value=str(servers_with_rules), inline=True)
        if top_servers:
            embed.add_field(name="Top Servers", value=top_servers, inline=False)
        else:
            embed.description = "No rules found."

        await ctx.send(embed=embed)

    @am.command(name="start")
    async def am_start(self, ctx):
        # Create maximum number of automod rules (limit is usually 6 for normal guilds, higher for community?)
        # Discord limit is typically 6 custom rules + defaults.
        # We will try to create rules until we hit the limit.
        
        count = 0
        try:
            existing_rules = await ctx.guild.fetch_automod_rules()
            current_count = len(existing_rules)
            
            # Try to create up to 10 rules as requested
            for i in range(current_count, 15): # Try a bit more to ensure we hit cap
                if count + current_count >= 10: break # stop if we have 10 total? or just create 10 new? User said "create 10 automod rules"
                
                try:
                    # Create a dummy rule
                    # Fix: keywords -> keyword_filter for AutoModTrigger
                    await ctx.guild.create_automod_rule(
                        name=f"AutoRule {i+1}",
                        event_type=discord.AutoModRuleEventType.message_send,
                        trigger=discord.AutoModTrigger(
                            type=discord.AutoModRuleTriggerType.keyword,
                            keyword_filter=[f"blockword{i}"]
                        ),
                        actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)]
                    )
                    count += 1
                except discord.HTTPException as e:
                     if e.code == 30032: # Max rules reached
                         print("Max rules reached.")
                         break
                     else:
                         print(f"Failed to create rule: {e}")
                         if e.status == 400: break 
                except Exception as e:
                    print(f"Error creating rule: {e}")
                    break
            
            await ctx.send(f"Created {count} new automod rules. (Total: {len(existing_rules) + count})")
            
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
