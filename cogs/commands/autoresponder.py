import discord
from discord.ext import commands
import motor.motor_asyncio
import os
import asyncio

class AutoResponder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.collection = None

    async def cog_load(self):
        if not self.mongo_uri:
            print("CRITICAL: MONGO_URI not found for AutoResponder cog!")
            return

        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.get_default_database()
        self.collection = self.db.autoresponders
        
        # Ensure unique index on guild_id + trigger
        await self.collection.create_index([("guild_id", 1), ("trigger", 1)], unique=True)

    @commands.group(name="autoresponder", aliases=["ar"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autoresponder(self, ctx):
        """Autoresponder management commands."""
        embed = discord.Embed(
            title="Autoresponder Commands",
            description=(
                "`autoresponder create <trigger> <response>` - Create a new auto response\n"
                "`autoresponder list` - List all auto responses\n"
                "`autoresponder delete <trigger>` - Delete an auto response\n"
                "`autoresponder reset` - Delete all auto responses"
            ),
            color=0x2b2d31
        )
        await ctx.send(embed=embed)

    @autoresponder.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def create(self, ctx, trigger: str, *, response: str):
        """Create a new auto response."""
        trigger_clean = trigger.lower()

        try:
            # Upsert into MongoDB
            await self.collection.update_one(
                {"guild_id": ctx.guild.id, "trigger": trigger_clean},
                {"$set": {
                    "response": response,
                    "created_by": ctx.author.id
                }},
                upsert=True
            )
            
            embed = discord.Embed(
                description=f"Successfully created auto response for `{trigger}`",
                color=0x43b581
            )
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @autoresponder.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def list_cmd(self, ctx):
        """List all auto responses."""
        rows = []
        async for doc in self.collection.find({"guild_id": ctx.guild.id}):
            rows.append((doc['trigger'], doc['response']))

        if not rows:
            return await ctx.send("No auto responders found for this server.")

        description = ""
        for trigger, response in rows:
            # Truncate response if too long for list
            preview_response = (response[:200] + '..') if len(response) > 200 else response
            description += f"• `{trigger}` -> {preview_response}\n"

        embed = discord.Embed(
            title="Auto Responders",
            description=description,
            color=0x2b2d31
        )
        await ctx.send(embed=embed)

    @autoresponder.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def delete(self, ctx, trigger: str):
        """Delete an auto response."""
        result = await self.collection.delete_one({"guild_id": ctx.guild.id, "trigger": trigger.lower()})
        
        if result.deleted_count == 0:
            return await ctx.send(f"No auto response found for `{trigger}`.")

        embed = discord.Embed(
            description=f"Successfully deleted auto response for `{trigger}`",
            color=0xf04747
        )
        await ctx.send(embed=embed)

    @autoresponder.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def reset(self, ctx):
        """Reset all auto responses."""
        
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
                
                await interaction.response.send_message(embed=discord.Embed(description="All auto responders have been reset.", color=0xf04747))
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
            title="Reset Auto Responders",
            description="Are you sure you want to delete **ALL** auto responders for this server? This action cannot be undone.",
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

        # Don't respond to commands
        try:
            prefix = await self.bot.get_prefix(message) if asyncio.iscoroutinefunction(self.bot.get_prefix) else self.bot.command_prefix
            if isinstance(prefix, str):
                prefixes = (prefix,)
            else:
                prefixes = tuple(prefix)
            
            valid_prefixes = tuple(p for p in prefixes if p) # Remove empty
            
            if valid_prefixes and message.content.startswith(valid_prefixes):
                 return
        except Exception:
            pass

        msg_content_nospaces = message.content.lower().replace(" ", "")
        
        # Async iterator for MongoDB cursor
        async for doc in self.collection.find({"guild_id": message.guild.id}):
            trigger = doc['trigger']
            response = doc['response']
            
            trigger_nospaces = trigger.lower().replace(" ", "")
            
            if trigger_nospaces in msg_content_nospaces:
                try:
                    await message.channel.send(response)
                    return 
                except discord.Forbidden:
                    pass
                except Exception:
                    pass

async def setup(bot):
    await bot.add_cog(AutoResponder(bot))
