from typing import Optional
import asyncio
import logging

import discord
from discord.ext import commands, tasks

from src.config import config
from src.curseforge import CurseForgeAPI
from src.discord_delivery import send_release_message
from src.storage import ReleaseStorage


class ModUpdateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        logging.debug("Initializing ModUpdateCog")
        self.bot = bot
        self.cf_api = CurseForgeAPI(config.curseforge_api_key)
        self.storage = ReleaseStorage()
        self.check_updates.change_interval(minutes=config.check_interval_minutes)
        self.check_updates.start()
        logging.info(f"Update check interval set to {config.check_interval_minutes} minutes")
        logging.debug("ModUpdateCog initialization complete")

    def cog_unload(self):
        logging.debug("Unloading ModUpdateCog")
        self.check_updates.cancel()

    async def send_release_notification(
        self,
        mod_id: int,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Send a release notification for a specific mod to the specified channel."""
        try:
            latest_file = await self.cf_api.get_latest_file(mod_id)
            if not latest_file:
                logging.warning(f"No latest file found for mod ID: {mod_id}")
                return

            mod_info = await self.cf_api.get_mod_info(mod_id)
            game_id = mod_info.get("gameId")
            version = latest_file["version"]
            logging.debug(f"Found version {version} for mod {mod_info['name']}")

            if channel is None:
                if config.debug:
                    logging.debug("Debug mode enabled, using debug channel")
                    channel = self.bot.get_channel(config.debug_channel_id)
                else:
                    try:
                        channel_id = config.resolve_release_channel_id(mod_id, int(game_id) if game_id else None)
                        channel = self.bot.get_channel(channel_id)
                        logging.debug(f"Retrieved channel object: {channel}")
                    except RuntimeError as exc:
                        logging.error(f"Failed to find matching channel for mod {mod_id}: {str(exc)}")
                        return False

                if not channel:
                    logging.error(f"Channel not found for mod {mod_id}")
                    return False

            await send_release_message(channel, mod_id, mod_info, latest_file)

            logging.info(f"Successfully sent release notification for {mod_info['name']} version {version}")
            return True
        except Exception as exc:
            logging.error(f"Error sending release notification for mod {mod_id}: {str(exc)}", exc_info=True)
            return False

    @tasks.loop(minutes=5)
    async def check_updates(self):
        logging.info("Starting update check loop")
        for mod_id in config.mod_ids:
            if mod_id not in config.following_mod_ids:
                logging.debug(f"Skipping mod ID {mod_id} because following is disabled")
                continue
            logging.debug(f"Checking updates for mod ID: {mod_id}")
            try:
                latest_file = await self.cf_api.get_latest_file(mod_id)
                if not latest_file:
                    logging.warning(f"No latest file found for mod ID: {mod_id}")
                    continue

                version = latest_file["version"]
                if not self.storage.is_version_released(str(mod_id), version):
                    if await self.send_release_notification(mod_id):
                        self.storage.mark_version_released(str(mod_id), version)
                else:
                    logging.debug(f"Version {version} already released for mod ID: {mod_id}")
            except Exception as exc:
                logging.error(f"Error checking mod {mod_id}: {str(exc)}", exc_info=True)
                continue

            await asyncio.sleep(2)
        logging.info("Completed update check loop")

    @check_updates.before_loop
    async def before_check_updates(self):
        logging.debug("Waiting for bot to be ready before starting update checks")
        await self.bot.wait_until_ready()
        logging.debug("Bot ready, update checks can now begin")

    @commands.command()
    @commands.is_owner()
    async def force_check(self, ctx):
        logging.info("Force check command received")
        await ctx.send("Forcing update check...")
        await self.check_updates()
        logging.info("Force check completed")
        await ctx.send("Update check completed.")

    @commands.command()
    @commands.is_owner()
    async def test_release(self, ctx):
        """Send the latest release of the first mod to the current channel for testing."""
        logging.info("Test release command received")
        try:
            if not config.mod_ids:
                await ctx.send("No mod IDs configured.")
                return

            mod_id = config.mod_ids[0]
            success = await self.send_release_notification(mod_id, ctx.channel)
            if not success:
                await ctx.send(f"Failed to send test release for mod ID: {mod_id}")
        except Exception as exc:
            error_msg = f"Error sending test release: {str(exc)}"
            logging.error(error_msg, exc_info=True)
            await ctx.send(error_msg)


async def setup(bot: commands.Bot):
    logging.debug("Setting up ModUpdateCog")
    await bot.add_cog(ModUpdateCog(bot))
    logging.debug("ModUpdateCog setup complete")
