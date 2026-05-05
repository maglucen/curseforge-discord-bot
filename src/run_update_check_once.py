import asyncio
import sys

import discord

from src.config import config
from src.curseforge import CurseForgeAPI
from src.release_embed import build_release_embed
from src.storage import ReleaseStorage

DEFAULT_REACTIONS = ["❤️"]


def resolve_release_channel_id(mod_id: int) -> int:
    try:
        mod_index = config.mod_ids.index(mod_id)
    except ValueError as exc:
        raise RuntimeError(f"MOD_ID {mod_id} is not configured.") from exc

    if mod_index < len(config.releases_channel_ids):
        return config.releases_channel_ids[mod_index]
    if config.releases_channel_ids:
        return config.releases_channel_ids[0]
    raise RuntimeError("No release channel is configured.")


async def send_release_message(
    client: discord.Client,
    mod_id: int,
    mod_info: dict,
    latest_file: dict,
) -> bool:
    channel_id = resolve_release_channel_id(mod_id)
    channel = client.get_channel(channel_id)
    if channel is None:
        print(f"Could not find channel with ID {channel_id} for mod {mod_id}.")
        return False

    embed = build_release_embed(mod_info, latest_file)
    message = await channel.send(
        content=config.message_tag or "",
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

    if config.announce_messages and not config.debug:
        try:
            await message.publish()
        except discord.errors.Forbidden:
            print("Missing permissions to publish the message.")
        except discord.errors.HTTPException:
            print("Failed to publish message; channel is probably not a news channel.")

    print(f"Sent release notification for {mod_info['name']} version {latest_file['version']}.")
    return True


async def main() -> None:
    errors = config.validate()
    required = {
        "BOT_TOKEN is required",
        "CURSEFORGE_API_KEY is required",
        "RELEASES_CHANNEL_IDS is required",
    }
    blocking_errors = [error for error in errors if error in required]
    if blocking_errors:
        print("Configuration errors:")
        for error in dict.fromkeys(blocking_errors):
            print(f"- {error}")
        sys.exit(1)

    cf_api = CurseForgeAPI(config.curseforge_api_key)
    storage = ReleaseStorage()
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        sent_count = 0
        try:
            print("Starting one-time update check...")
            for mod_id in config.mod_ids:
                if mod_id not in config.following_mod_ids:
                    print(f"Skipping MOD_ID {mod_id} because following is disabled.")
                    continue

                latest_file = await cf_api.get_latest_file(mod_id)
                if not latest_file:
                    print(f"No latest file found for MOD_ID {mod_id}.")
                    continue

                version = latest_file["version"]
                if storage.is_version_released(str(mod_id), version):
                    print(f"Version {version} already released for MOD_ID {mod_id}.")
                    continue

                mod_info = await cf_api.get_mod_info(mod_id)
                if await send_release_message(client, mod_id, mod_info, latest_file):
                    storage.mark_version_released(str(mod_id), version)
                    sent_count += 1

            print(f"One-time update check completed. Releases sent: {sent_count}.")
        finally:
            await client.close()

    try:
        await client.start(config.bot_token)
    except discord.LoginFailure:
        print("Failed to login. Please check your bot token.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
