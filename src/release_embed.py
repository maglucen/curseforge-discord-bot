from __future__ import annotations

from datetime import datetime

import discord

from src.config import config


def format_description(mod_name: str, version: str) -> str:
    if config.message_header:
        return config.message_header.format(mod_name=mod_name, version=version)
    return "New version available on CurseForge."


def format_links_label(mod_name: str, version: str) -> str:
    if config.message_footer:
        return config.message_footer.format(mod_name=mod_name, version=version)
    return "Links"


def build_file_url(mod_info: dict, latest_file: dict) -> str:
    links = mod_info.get("links") or {}
    website_url = str(links.get("websiteUrl") or "").rstrip("/")
    file_id = latest_file.get("id")
    if website_url and file_id:
        return f"{website_url}/files/{file_id}"
    if latest_file.get("downloadUrl"):
        return str(latest_file["downloadUrl"])
    slug = str(mod_info.get("slug") or "").strip("/")
    return f"https://www.curseforge.com/mods/{slug}/files/{file_id}" if slug and file_id else "https://www.curseforge.com"


def build_release_embed(mod_info: dict, latest_file: dict) -> discord.Embed:
    version = latest_file["version"]
    description = format_description(mod_info["name"], version)
    file_url = build_file_url(mod_info, latest_file)
    download_url = latest_file.get("downloadUrl") or file_url
    embed = discord.Embed(
        title=f"{mod_info['name']} v{version}",
        description=description,
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )

    logo = mod_info.get("logo") or {}
    logo_url = logo.get("url")
    if config.show_logo and logo_url:
        if config.logo_style == "thumbnail":
            embed.set_thumbnail(url=logo_url)
        else:
            embed.set_image(url=logo_url)

    changelog = latest_file.get("changelog")
    if changelog:
        suffix = "...\n\n[View full changelog]({})".format(file_url)
        remaining_space = max(0, 1024 - len(suffix))

        if len(changelog) > remaining_space:
            changelog = f"{changelog[:remaining_space]}{suffix}"

        embed.add_field(name="Changes", value=changelog, inline=False)
    else:
        embed.add_field(name="Changes", value="No changelog provided.", inline=False)

    links_label = format_links_label(mod_info["name"], version)
    links_value = f"[Download]({download_url}) | [View changelog]({file_url})"
    embed.add_field(name=links_label, value=links_value, inline=False)

    return embed
