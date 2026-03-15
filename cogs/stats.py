import discord
from discord.ext import commands
import datetime
import os

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vc_starts = {} # {member_id: start_time}

    @commands.Cog.listener()
    async def on_ready(self):
        # Optional: Indexing
        if hasattr(self.bot, 'db'):
            # Composite index for querying guild stats by date
            await self.bot.db.stats_daily.create_index([("guild_id", 1), ("date", 1)], unique=True)
            # Composite index for querying user stats by guild/date
            await self.bot.db.stats_user_daily.create_index([("guild_id", 1), ("user_id", 1), ("date", 1)], unique=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        date = datetime.date.today().isoformat()

        if not hasattr(self.bot, 'db') or self.bot.db is None:
            return

        try:
            # Update guild total
            await self.bot.db.stats_daily.update_one(
                {"guild_id": guild_id, "date": date},
                {"$inc": {"messages": 1}},
                upsert=True
            )

            # Update user total
            await self.bot.db.stats_user_daily.update_one(
                {"guild_id": guild_id, "user_id": user_id, "date": date},
                {"$inc": {"messages": 1}},
                upsert=True
            )
        except Exception as e:
            print(f"Error in stats on_message: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        user_id = member.id
        
        # User joined a VC
        if not before.channel and after.channel:
            self.vc_starts[user_id] = datetime.datetime.now()
        
        # User left a VC
        elif before.channel and not after.channel:
            start_time = self.vc_starts.pop(user_id, None)
            if start_time:
                duration = datetime.datetime.now() - start_time
                minutes = int(duration.total_seconds() / 60)
                
                if minutes > 0:
                    guild_id = member.guild.id
                    date = datetime.date.today().isoformat()
                    
                    if not hasattr(self.bot, 'db') or self.bot.db is None:
                        return
                        
                    try:
                        await self.bot.db.stats_daily.update_one(
                            {"guild_id": guild_id, "date": date},
                            {"$inc": {"vc_minutes": minutes}},
                            upsert=True
                        )
                        
                        await self.bot.db.stats_user_daily.update_one(
                            {"guild_id": guild_id, "user_id": user_id, "date": date},
                            {"$inc": {"vc_minutes": minutes}},
                            upsert=True
                        )
                    except Exception as e:
                        print(f"Error in stats on_voice: {e}")

async def setup(bot):
    await bot.add_cog(Stats(bot))
