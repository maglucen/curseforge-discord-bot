import asyncio
import sys

import discord

from src.config import config
from src.curseforge import CurseForgeAPI
from src.release_embed import build_release_embed


async def main():
    errors = config.validate()
    required = {"BOT_TOKEN is required", "DEBUG_CHANNEL_ID is required", "CURSEFORGE_API_KEY is required"}
    blocking_errors = [error for error in errors if error in required]
    if blocking_errors:
        print("Configuration errors:")
        for error in blocking_errors:
            print(f"- {error}")
        sys.exit(1)

    if not config.mod_ids:
        print("No MOD_IDS configured.")
        sys.exit(1)

    mod_id = config.mod_ids[-1]
    cf_api = CurseForgeAPI(config.curseforge_api_key)

    latest_file = await cf_api.get_latest_file(mod_id)
    if not latest_file:
        print(f"No latest file found for mod ID {mod_id}.")
        sys.exit(1)

    mod_info = await cf_api.get_mod_info(mod_id)
    game_id = mod_info.get("gameId")
    embed = build_release_embed(mod_info, latest_file)

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            channel = client.get_channel(config.debug_channel_id)
            if channel is None:
                print(f"Could not find debug channel with ID {config.debug_channel_id}")
                await client.close()
                return

            await channel.send(
                content=config.resolve_message_tag(mod_id, int(game_id) if game_id else None) or "",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
            )
            print(
                f"Latest release test sent to channel {config.debug_channel_id} "
                f"for mod {mod_info['name']} (MOD_ID {mod_id})."
            )
        finally:
            await client.close()

    try:
        await client.start(config.bot_token)
    except discord.LoginFailure:
        print("Failed to login. Please check your bot token.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
