import argparse
import asyncio
import sys

import discord

from src.config import config
from src.curseforge import CurseForgeAPI
from src.release_embed import build_release_embed

DEFAULT_REACTIONS = ["❤️"]
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
    embed = build_release_embed(mod_info, latest_file)

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

            message = await channel.send(
                content=config.resolve_message_tag(args.mod_id, int(game_id) if game_id else None) or "",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
            )

            if config.add_reactions:
                for reaction in DEFAULT_REACTIONS:
                    try:
                        await message.add_reaction(reaction)
                    except discord.errors.Forbidden:
                        print(f"Missing permissions to add reaction {reaction}.")
                    except discord.errors.HTTPException:
                        print(f"Failed to add reaction {reaction}.")

                if config.announce_messages and args.target == "release" and not config.debug:
                    try:
                        await message.publish()
                    except discord.errors.Forbidden:
                        print("Missing permissions to publish the message.")
                    except discord.errors.HTTPException:
                        print("Failed to publish message; channel is probably not a news channel.")

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
