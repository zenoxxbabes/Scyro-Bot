import discord
from discord.ext import commands
import motor.motor_asyncio
import os
from utils.Tools import *

class Whitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.wl_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]
        self.antinuke_col = self.db["antinuke"]

    async def cog_load(self):
         # Index already planned
         print("✅ [Whitelist] Extension loaded & DB initialized (MongoDB).")

    @commands.hybrid_command(name='whitelist', aliases=['wl'], help="Whitelists a user from antinuke for a specific action.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def whitelist(self, ctx, member: discord.User = None):
        await ctx.defer()
        if ctx.guild.member_count < 2:
            embed = discord.Embed(
                color=0x2b2d31,
                description="> ❌ | Your Server Doesn't Meet My 30 Member Criteria"
            )
            return await ctx.send(embed=embed)

        prefix=ctx.prefix

        # Check Extra Owner
        check = await self.extra_col.find_one({"guild_id": ctx.guild.id, "owner_id": ctx.author.id})

        # Check Antinuke Status
        antinuke = await self.antinuke_col.find_one({"guild_id": ctx.guild.id})
        
        is_owner = ctx.author.id == ctx.guild.owner_id
        if not is_owner and not check:
            embed = discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=0x2b2d31,
                description="Only Server Owner or Extra Owner can Run this Command!"
            )
            return await ctx.send(embed=embed)

        if not antinuke or not antinuke.get("status"):
            embed = discord.Embed(
                color=0x2b2d31,
                description=(
                    f"**{ctx.guild.name} Security Settings <:4986usesautomod:1409414573269712896>\n"
                    "Ohh No! looks like your server doesn't enabled Antinuke\n\n"
                    "Current Status : <:disabled:1396473518962507866>\n\n"
                    f"To enable use `{prefix}antinuke enable` **"
                )
            )
            embed.set_thumbnail(url=ctx.bot.user.avatar.url)
            return await ctx.send(embed=embed)

        if not member:
            embed = discord.Embed(
                color=0x2b2d31,
                title="__**Whitelist Commands**__",
                description="**Adding a user to the whitelist means that no actions will be taken against them if they trigger the Anti-Nuke Module.**"
            )
            embed.add_field(name="__**Usage**__", value=f"<a:dot:1396429135588626442> `{prefix}whitelist @user/id`\n<a:dot:1396429135588626442> `{prefix}wl @user`")
            embed.set_thumbnail(url=ctx.bot.user.avatar.url)
            return await ctx.send(embed=embed)

        data = await self.wl_col.find_one({"guild_id": ctx.guild.id, "user_id": member.id})

        if data:
            embed = discord.Embed(title="<:no:1396838761605890090> Error",
                color=0x2b2d31,
                description=f"<@{member.id}> is already a whitelisted member, **Unwhitelist** the user and try again."
            )
            return await ctx.send(embed=embed)

        # Insert placeholder document
        await self.wl_col.insert_one({"guild_id": ctx.guild.id, "user_id": member.id})
        
        options = [
            discord.SelectOption(label="Ban", description="Whitelist a member with ban permission", value="ban"),
            discord.SelectOption(label="Kick", description="Whitelist a member with kick permission", value="kick"),
            discord.SelectOption(label="Prune", description="Whitelist a member with prune permission", value="prune"),
            discord.SelectOption(label="Bot Add", description="Whitelist a member with bot add permission", value="botadd"),
            discord.SelectOption(label="Server Update", description="Whitelist a member with server update permission", value="serverup"),
            discord.SelectOption(label="Member Update", description="Whitelist a member with member update permission", value="memup"),
            discord.SelectOption(label="Channel Create", description="Whitelist a member with channel create permission", value="chcr"),
            discord.SelectOption(label="Channel Delete", description="Whitelist a member with channel delete permission", value="chdl"),
            discord.SelectOption(label="Channel Update", description="Whitelist a member with channel update permission", value="chup"),
            discord.SelectOption(label="Role Create", description="Whitelist a member with role create permission", value="rlcr"),
            discord.SelectOption(label="Role Update", description="Whitelist a member with role update permission", value="rlup"),
            discord.SelectOption(label="Role Delete", description="Whitelist a member with role delete permission", value="rldl"),
            discord.SelectOption(label="Mention Everyone", description="Whitelist a member with mention everyone permission", value="meneve"),
            discord.SelectOption(label="Manage Webhook", description="Whitelist a member with manage webhook permission", value="mngweb")
        ]

        select = discord.ui.Select(placeholder="Choose Your Options", min_values=1, max_values=len(options), options=options, custom_id="nodefer_wl")
        button = discord.ui.Button(label="Add This User To All Categories", style=discord.ButtonStyle.primary, custom_id="nodefer_catWl")

        view = discord.ui.View()
        view.add_item(select)
        view.add_item(button)

        embed = discord.Embed(
            title=f"Whitelisting {member.name}",
            color=0x2b2d31,
            description="**Select permissions to whitelist for this user:**\n\n" +
                        "> <:disabled:1396473518962507866> **`Ban`**\n> <:disabled:1396473518962507866> **`Kick`**\n> <:disabled:1396473518962507866> **`Prune`**\n> <:disabled:1396473518962507866> **`Bot Add`**\n" +
                        "> <:disabled:1396473518962507866> **`Server Update`**\n> <:disabled:1396473518962507866> **`Member Update`**\n" +
                        "> <:disabled:1396473518962507866> **`Channel Create`**\n> <:disabled:1396473518962507866> **`Channel Delete`**\n> <:disabled:1396473518962507866> **`Channel Update`**\n" +
                        "> <:disabled:1396473518962507866> **`Role Create`**\n> <:disabled:1396473518962507866> **`Role Delete`**\n> <:disabled:1396473518962507866> **`Role Update`**\n" +
                        "> <:disabled:1396473518962507866> **`Mention Everyone`**\n> <:disabled:1396473518962507866> **`Manage Webhooks`**"
        )
        embed.add_field(name="Executor", value=f"{ctx.author.mention}", inline=True)
        embed.add_field(name="Target", value=f"{member.mention}", inline=True)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text=f"Powered by Scyro.xyz")

        msg = await ctx.send(embed=embed, view=view)

        def check(interaction):
            return interaction.user.id == ctx.author.id and interaction.message.id == msg.id

        try:
            interaction = await self.bot.wait_for("interaction", check=check, timeout=60.0)
            if interaction.data["custom_id"] == "nodefer_catWl":
                
                await self.wl_col.update_one(
                    {"guild_id": ctx.guild.id, "user_id": member.id},
                    {"$set": {
                        "ban": True, "kick": True, "prune": True, "botadd": True, 
                        "serverup": True, "memup": True, "chcr": True, "chdl": True, "chup": True, 
                        "rlcr": True, "rldl": True, "rlup": True, "meneve": True, "mngweb": True, "mngstemo": True
                        }}
                )

                # Success All
                embed.description = (
                        "> <:enabled:1396473501447098368> **`Ban`**\n> <:enabled:1396473501447098368> **`Kick`**\n> <:enabled:1396473501447098368> **`Prune`**\n> <:enabled:1396473501447098368> **`Bot Add`**\n" +
                        "> <:enabled:1396473501447098368> **`Server Update`**\n> <:enabled:1396473501447098368> **`Member Update`**\n" +
                        "> <:enabled:1396473501447098368> **`Channel Create`**\n> <:enabled:1396473501447098368> **`Channel Delete`**\n> <:enabled:1396473501447098368> **`Channel Update`**\n" +
                        "> <:enabled:1396473501447098368> **`Role Create`**\n> <:enabled:1396473501447098368> **`Role Delete`**\n> <:enabled:1396473501447098368> **`Role Update`**\n" +
                        "> <:enabled:1396473501447098368> **`Mention Everyone`**\n> <:enabled:1396473501447098368> **`Manage Webhooks`**"
                )
                embed.title = f"Whitelisted {member.name} (All)"
                await interaction.response.edit_message(embed=embed, view=None)

            else:
                fields = {
                    'ban': 'Ban', 'kick': 'Kick', 'prune': 'Prune', 'botadd': 'Bot Add',
                    'serverup': 'Server Update', 'memup': 'Member Update',
                    'chcr': 'Channel Create', 'chdl': 'Channel Delete', 'chup': 'Channel Update',
                    'rlcr': 'Role Create', 'rldl': 'Role Delete', 'rlup': 'Role Update',
                    'meneve': 'Mention Everyone', 'mngweb': 'Manage Webhooks'
                }

                embed_description = embed.description
                update_fields = {}
                
                for value in interaction.data["values"]:
                    update_fields[value] = True
                    # Replace disabled with enabled for selected items
                    target_str = f"> <:disabled:1396473518962507866> **`{fields[value]}`**"
                    replace_str = f"> <:enabled:1396473501447098368> **`{fields[value]}`**"
                    embed_description = embed_description.replace(target_str, replace_str)
                
                if update_fields:
                    await self.wl_col.update_one(
                         {"guild_id": ctx.guild.id, "user_id": member.id},
                         {"$set": update_fields}
                    )

                embed.description = embed_description
                await interaction.response.edit_message(embed=embed, view=None)
        except TimeoutError:
            await msg.edit(view=None)


    @commands.hybrid_command(name='whitelisted', aliases=['wlist'], help="Shows the list of whitelisted users.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def whitelisted(self, ctx):
        await ctx.defer()
        if ctx.guild.member_count < 2:
            embed = discord.Embed(
                color=0x2b2d31,
                description="> ❌ | Your Server Doesn't Meet My 30 Member Criteria"
            )
            return await ctx.send(embed=embed)

        pre=ctx.prefix

        # Check Extra Owner
        check = await self.extra_col.find_one({"guild_id": ctx.guild.id, "owner_id": ctx.author.id})

        # Check Antinuke Status
        antinuke = await self.antinuke_col.find_one({"guild_id": ctx.guild.id})
        
        is_owner = ctx.author.id == ctx.guild.owner_id
        if not is_owner and not check:
            embed = discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=0x2b2d31,
                description="Only Server Owner or Extra Owner can Run this Command!"
            )
            return await ctx.send(embed=embed)

        if not antinuke or not antinuke.get("status"):
            embed = discord.Embed(
                color=0x2b2d31,
                description=(
                    f"**{ctx.guild.name} security settings <:security:1396477817000034385>\n"
                    "Ohh NO! looks like your server doesn't enabled security\n\n"
                    "Current Status : <:disabled:1396473518962507866>\n\n"
                    f"To enable use `{pre}antinuke enable` **"
                )
            )
            return await ctx.send(embed=embed)

        cursor = self.wl_col.find({"guild_id": ctx.guild.id})
        data = await cursor.to_list(length=None)

        if not data:
            embed = discord.Embed(title="<:no:1396838761605890090> Error",
                color=0x2b2d31,
                description="No whitelisted users found."
            )
            return await ctx.send(embed=embed)

        whitelisted_users = [self.bot.get_user(user["user_id"]) for user in data]
        whitelisted_users_str = ", ".join(f"<@!{user.id}>" for user in whitelisted_users if user)

        embed = discord.Embed(
            color=0x2b2d31,
            title=f"__Whitelisted Users for {ctx.guild.name}__",
            description=whitelisted_users_str
        )
        await ctx.send(embed=embed)


    @commands.hybrid_command(name="whitelistreset", aliases=['wlreset'], help="Resets the whitelisted users.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def whitelistreset(self, ctx):
        await ctx.defer()
        if ctx.guild.member_count < 2:
            embed = discord.Embed(
                color=0x2b2d31,
                description="> ❌ | Your Server Doesn't Meet My 30 Member Criteria"
            )
            return await ctx.send(embed=embed)

        pre=ctx.prefix

        # Check Extra Owner
        check = await self.extra_col.find_one({"guild_id": ctx.guild.id, "owner_id": ctx.author.id})

        # Check Antinuke Status
        antinuke = await self.antinuke_col.find_one({"guild_id": ctx.guild.id})
        
        is_owner = ctx.author.id == ctx.guild.owner_id
        if not is_owner and not check:
            embed = discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=0x2b2d31,
                description="Only Server Owner or Extra Owner can Run this Command!"
            )
            return await ctx.send(embed=embed)

        if not antinuke or not antinuke.get("status"):
            embed = discord.Embed(
                color=0x2b2d31,
                description=(
                    f"**{ctx.guild.name} Security Settings <:4986usesautomod:1409414573269712896>\n"
                    "Ohh NO! looks like your server doesn't enabled security\n\n"
                    "Current Status : <:disabled:1396473518962507866>\n\n"
                    f"To enable use `{pre}antinuke enable` **"
                )
            )
            return await ctx.send(embed=embed)

        result = await self.wl_col.delete_many({"guild_id": ctx.guild.id})

        if result.deleted_count == 0:
            embed = discord.Embed(title="<:no:1396838761605890090> Error",
                color=0x2b2d31,
                description="No whitelisted members found to reset."
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            color=0x2b2d31,
            description=f"<:yes:1396838746862784582> | Removed all whitelisted members from {ctx.guild.name}"
        )
        await ctx.send(embed=embed)