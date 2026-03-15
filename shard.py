import os
import sys
import asyncio
import logging
from typing import Optional, Any
import discord
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('ShardManager')

class ShardManager:
    """Manages automatic sharding for the Discord bot"""
    
    def __init__(self, token: str):
        self.token = token
        self.shard_count: Optional[int] = None
        
    async def get_shard_count(self) -> int:
        """Get recommended shard count from Discord API"""
        if self.shard_count is not None:
            return self.shard_count
            
        try:
            # For now, we'll use a simpler approach to avoid the complex http client issues
            # Discord recommends 1 shard per 2500 guilds, but we'll start with 4 as requested
            self.shard_count = 4  # Default to 4 shards as requested
            logger.info(f"Using default shard count: {self.shard_count}")
            return self.shard_count
        except Exception as e:
            logger.error(f"Failed to get shard count: {e}")
            # Fallback to 4 shards
            self.shard_count = 4
            return self.shard_count
    
    async def launch_shards(self):
        """Launch all shards using Discord's recommended sharding"""
        try:
            # Get shard count
            shard_count = await self.get_shard_count()
            
            logger.info(f"Launching bot with {shard_count} automatically managed shards")
            
            # Import the existing bot class
            from core.Scyro import Scyro
            
            # Comment out automatic sharding for now to avoid conflicts with manual sharding
            # Create bot instance with automatic sharding and specified shard count
            # bot = Scyro(shard_count=shard_count)
            
            # For manual sharding, we should let main.py handle the bot creation
            # The shard manager approach conflicts with manual sharding
            raise Exception("Automatic sharding is disabled when using manual sharding. Please use main.py with AUTO_SHARDING=false")
            
            # Add event handlers for shard management
            @bot.event
            async def on_shard_ready(shard_id):
                logger.info(f"Shard {shard_id} is ready")
                
            @bot.event
            async def on_shard_connect(shard_id):
                logger.info(f"Shard {shard_id} connected to Discord")
                
            @bot.event
            async def on_shard_disconnect(shard_id):
                logger.warning(f"Shard {shard_id} disconnected from Discord")
                
            @bot.event
            async def on_shard_resumed(shard_id):
                logger.info(f"Shard {shard_id} resumed connection")
            
            # Start the bot
            await bot.start(self.token)
            
        except Exception as e:
            logger.error(f"Error launching shards: {e}")
            raise

async def run_shard_manager():
    """Run the shard manager asynchronously"""
    # Get token from environment
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN not found in environment variables")
        sys.exit(1)
    
    # Create shard manager
    manager = ShardManager(token)
    
    try:
        # Launch shards
        await manager.launch_shards()
    except KeyboardInterrupt:
        logger.info("Shutting down bot...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Run the async function properly
    try:
        asyncio.run(run_shard_manager())
    except RuntimeError:
        # Handle case where event loop is already running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_shard_manager())