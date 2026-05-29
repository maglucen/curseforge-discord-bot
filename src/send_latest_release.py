import argparse
import asyncio
import sys

import discord

from src.config import config
from src.curseforge import CurseForgeAPI
from src.discord_delivery import send_release_message

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod-id", type=int, required=True)
    parser.add_argument("--target", choices=["debug", "release"], default="release")
    args = parser.parse_args()

    errors = config.validate()
    required = {"BOT_TOKEN is required", "CURSEFORGE_API_KEY is required"}
    blocking_errors = [error for error in errors if error in required]
    if args.target == "debug":
        if "DEBUG_CHANNEL_ID is required" in errors:
            blocking_errors.append("DEBUG_CHANNEL_ID is required")
    else:
        if "RELEASES_CHANNEL_IDS is required" in errors:
            blocking_errors.append("RELEASES_CHANNEL_IDS is required")

    if blocking_errors:
        print("Configuration errors:")
        for error in dict.fromkeys(blocking_errors):
            print(f"- {error}")
        sys.exit(1)

    cf_api = CurseForgeAPI(config.curseforge_api_key)
    latest_file = await cf_api.get_latest_file(args.mod_id)
    if not latest_file:
        print(f"No latest file found for mod ID {args.mod_id}.")
        sys.exit(1)

    mod_info = await cf_api.get_mod_info(args.mod_id)
    game_id = mod_info.get("gameId")

    if args.target == "debug":
        channel_id = config.debug_channel_id
    else:
        channel_id = config.resolve_release_channel_id(args.mod_id, int(game_id) if game_id else None)

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            channel = client.get_channel(channel_id)
            if channel is None:
                print(f"Could not find channel with ID {channel_id}")
                await client.close()
                return

            await send_release_message(channel, args.mod_id, mod_info, latest_file, target=args.target)

            print(
                f"Latest release sent to {args.target} channel {channel_id} "
                f"for mod {mod_info['name']} (MOD_ID {args.mod_id})."
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
