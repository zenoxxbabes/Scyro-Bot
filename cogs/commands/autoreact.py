import discord
from discord.ext import commands
import motor.motor_asyncio
import os

class Autoreact(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.collection = None

    async def cog_load(self):
        if not self.mongo_uri:
            print("CRITICAL: MONGO_URI not found for Autoreact cog!")
            return

        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.get_default_database()
        self.collection = self.db.autoreacts
        
        # Ensure unique index on guild_id + trigger
        # This prevents duplicate triggers for the same guild
        await self.collection.create_index([("guild_id", 1), ("trigger", 1)], unique=True)

    def is_manage_guild():
        async def predicate(ctx):
            if ctx.author.guild_permissions.manage_guild:
                return True
            return False
        return commands.check(predicate)

    @commands.group(name="autoreact", aliases=["atr"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autoreact(self, ctx):
        """Autoreact management commands."""
        embed = discord.Embed(
            title="Autoreact Commands",
            description=(
                "`autoreact create <trigger> <emoji>` - Create a new autoreact\n"
                "`autoreact list` - List all autoreacts\n"
                "`autoreact delete <trigger>` - Delete an autoreact\n"
                "`autoreact reset` - Delete all autoreacts"
            ),
            color=0x2b2d31
        )
        await ctx.send(embed=embed)

    @autoreact.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def create(self, ctx, trigger: str, emojistr: str):
        """Create a new autoreact."""
        # Validate emoji by trying to react
        try:
            emoji = discord.PartialEmoji.from_str(emojistr)
            await ctx.message.add_reaction(emoji)
        except discord.HTTPException:
             return await ctx.reply("You have to put a valid emoji that I can access.")
        except Exception:
             return await ctx.reply("You have to put a valid emoji.")

        try:
            # Upsert into MongoDB
            # We store emoji as string for easy display and partial emoji recreation
            await self.collection.update_one(
                {"guild_id": ctx.guild.id, "trigger": trigger.lower()},
                {"$set": {
                    "emoji": str(emoji),
                    "created_by": ctx.author.id
                }},
                upsert=True
            )
            
            embed = discord.Embed(
                description=f"Successfully created autoreact for `{trigger}` with {emoji}",
                color=0x43b581
            )
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @autoreact.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def list_cmd(self, ctx):
        """List all autoreacts."""
        rows = []
        async for doc in self.collection.find({"guild_id": ctx.guild.id}):
            rows.append((doc['trigger'], doc['emoji']))

        if not rows:
            return await ctx.send("No autoreacts found for this server.")

        description = ""
        for trigger, emojistr in rows:
            description += f"• `{trigger}` -> {emojistr}\n"

        embed = discord.Embed(
            title="Autoreacts",
            description=description,
            color=0x2b2d31
        )
        await ctx.send(embed=embed)

    @autoreact.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def delete(self, ctx, trigger: str):
        """Delete an autoreact."""
        result = await self.collection.delete_one({"guild_id": ctx.guild.id, "trigger": trigger.lower()})
        
        if result.deleted_count == 0:
            return await ctx.send(f"No autoreact found for `{trigger}`.")

        embed = discord.Embed(
            description=f"Successfully deleted autoreact for `{trigger}`",
            color=0xf04747
        )
        await ctx.send(embed=embed)

    @autoreact.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def reset(self, ctx):
        """Reset all autoreacts."""
        
        class ConfirmView(discord.ui.View):
            def __init__(self, ctx, collection):
                super().__init__(timeout=30)
                self.ctx = ctx
                self.collection = collection
                self.value = None

            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
                
                await self.collection.delete_many({"guild_id": self.ctx.guild.id})
                
                await interaction.response.send_message(embed=discord.Embed(description="All autoreacts have been reset.", color=0xf04747))
                self.value = True
                self.stop()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
                
                await interaction.response.send_message("Reset cancelled.", ephemeral=True)
                self.value = False
                self.stop()

        embed = discord.Embed(
            title="Reset Autoreacts",
            description="Are you sure you want to delete **ALL** autoreacts for this server? This action cannot be undone.",
            color=0xffcc00
        )
        view = ConfirmView(ctx, self.collection)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if view.value is None:
            await msg.edit(content="Confirmation timed out.", view=None)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        
        if self.collection is None:
            return

        content = message.content.lower()
        
        # Performance: Fetch all for guild might be slow if HUGE count, but for autoreacts it's usually small.
        # Alternatively, we could cache this in memory (self.cache[guild_id]) and update on create/delete.
        # Given "simple bot", direct DB query is safer for data consistency across instances (dashboard vs bot).
        # We will use direct query for now.
        
        cursor = self.collection.find({"guild_id": message.guild.id})
        async for doc in cursor:
            trigger = doc['trigger']
            if trigger in content:
                try:
                    emoji = discord.PartialEmoji.from_str(doc['emoji'])
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass 

async def setup(bot):
    await bot.add_cog(Autoreact(bot))
