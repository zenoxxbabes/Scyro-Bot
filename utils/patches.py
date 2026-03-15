# utils/patches.py
import discord
from discord.ext import commands
from discord import app_commands

def apply_patches():
    """
    Convert ALL prefix commands into slash commands automatically.
    Keeps prefix commands ($) working too.
    """
    async def bridge_command(ctx_or_interaction, command, *args, **kwargs):
        """Helper to run the command for both ctx + interaction."""
        if isinstance(ctx_or_interaction, commands.Context):
            await command(ctx_or_interaction, *args, **kwargs)
        elif isinstance(ctx_or_interaction, discord.Interaction):
            # Build a fake Context for slash commands
            ctx = await ctx_or_interaction.client.get_context(ctx_or_interaction)
            ctx.interaction = ctx_or_interaction
            await command.callback(ctx, *args, **kwargs)

    original_add_command = commands.Bot.add_command

    def new_add_command(self, command: commands.Command, *args, **kwargs):
        # Register the normal prefix command
        original_add_command(self, command, *args, **kwargs)

        # If slash already exists, skip
        if any(cmd.name == command.name for cmd in self.tree.get_commands()):
            return

        # Register a slash version
        @app_commands.command(
            name=command.name,
            description=command.help or f"Runs {command.name}"
        )
        async def slash(interaction: discord.Interaction, args: str = "", **kwargs):
            # Convert args string back to tuple if needed
            args_tuple = tuple(args.split()) if args else ()
            await bridge_command(interaction, command, *args_tuple, **kwargs)

        try:
            self.tree.add_command(slash)
        except Exception as e:
            print(f"[Patch Error] Failed to bridge {command.name}: {e}")

    # Monkey patch the method
    commands.Bot.add_command = new_add_command