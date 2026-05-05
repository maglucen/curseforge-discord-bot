import asyncio
from datetime import datetime
import sys

import discord

from src.config import config


async def main():
    errors = config.validate()
    required = {"BOT_TOKEN is required", "DEBUG_CHANNEL_ID is required"}
    blocking_errors = [error for error in errors if error in required]
    if blocking_errors:
        print("Configuration errors:")
        for error in blocking_errors:
            print(f"- {error}")
        sys.exit(1)

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

            embed = discord.Embed(
                title="Debug Test Message",
                description="This is a manual test message from the CurseForge bot.",
                color=discord.Color.blurple(),
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="Mention check",
                value="If the role mention is configured correctly, it should appear above this embed.",
                inline=False,
            )

            await channel.send(
                content=config.message_tag or "Debug test message",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
            )
            print(f"Test message sent to channel {config.debug_channel_id}")
        finally:
            await client.close()

    try:
        await client.start(config.bot_token)
    except discord.LoginFailure:
        print("Failed to login. Please check your bot token.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
