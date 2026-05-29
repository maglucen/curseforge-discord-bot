from __future__ import annotations

import logging

import discord

from src.config import config
from src.release_embed import build_release_embed


DEFAULT_REACTIONS = ["❤️"]


def allowed_release_mentions() -> discord.AllowedMentions:
    return discord.AllowedMentions(roles=True, everyone=True)


async def add_default_reactions(message: discord.Message) -> None:
    if not config.add_reactions:
        return

    for reaction in DEFAULT_REACTIONS:
        try:
            await message.add_reaction(reaction)
            logging.debug(f"Added reaction {reaction} to message")
        except discord.errors.Forbidden:
            logging.error("Failed to add reaction - missing permissions")
        except discord.errors.HTTPException:
            logging.error(f"Failed to add reaction {reaction}")


async def publish_if_configured(message: discord.Message, *, target: str = "release") -> None:
    if not config.announce_messages or config.debug or target != "release":
        return

    try:
        await message.publish()
        logging.debug("Message published successfully")
    except discord.errors.Forbidden:
        logging.error("Failed to publish message - missing permissions")
    except discord.errors.HTTPException:
        logging.error("Failed to publish message - not in news channel")


async def send_release_message(
    channel: discord.abc.Messageable,
    mod_id: int,
    mod_info: dict,
    latest_file: dict,
    *,
    target: str = "release",
) -> discord.Message:
    game_id = mod_info.get("gameId")
    embed = build_release_embed(mod_info, latest_file)
    message = await channel.send(
        content=config.resolve_message_tag(mod_id, int(game_id) if game_id else None) or "",
        embed=embed,
        allowed_mentions=allowed_release_mentions(),
    )
    await add_default_reactions(message)
    await publish_if_configured(message, target=target)
    return message
