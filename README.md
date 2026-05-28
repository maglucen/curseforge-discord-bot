# CurseForge Discord Bot Manager

Desktop-managed Discord bot for tracking CurseForge mod releases and posting update announcements to Discord.

This is my fork of CICDodo, adapted for my own modding workflow. The original bot focused on monitoring CurseForge projects and announcing new releases. This version adds a Windows manager UI, per-game/per-mod Discord routing, easier tracked-mod management, release testing tools, and basic stats for the mods being followed.

![CurseForge Discord Bot Manager](docs/screenshots/manager.png)

## What It Does

- monitors configured CurseForge project IDs for new files
- posts release announcements to Discord channels
- can route announcements by mod, by game, or by the original mod/channel order
- supports global, per-game, and per-mod mention tags
- stores already-announced versions so releases are not posted twice
- lets you mark which configured mods are currently followed
- resolves mod names, game names, downloads, likes, CurseForge links, and stored versions
- includes buttons for setup, start, stop, restart, one-time checks, and test messages
- lets you add or remove tracked mods from the UI
- can send the latest release for a selected mod to debug or release channels
- opens public CurseForge pages, author file pages, comments, logs, and project folder

## Quick Start

1. Install Python 3.11 or newer.
2. Copy `.env.example` to `.env`.
3. Fill in your Discord bot token, CurseForge API key, Discord channel IDs, and mod IDs.
4. Double-click `CurseForge Discord Bot Manager.vbs`.
5. Press `Setup` once to create the virtual environment and install dependencies.
6. Press `Start` to run the bot.

The `.env` file and `.local/` runtime folder are ignored by git. `.local/` contains the virtual environment, logs, release database, PID file, and manager window state.

## Configuration

Required values:

```env
BOT_TOKEN=your_discord_bot_token_here
CURSEFORGE_API_KEY=your_curseforge_api_key_here
DEBUG_CHANNEL_ID=123456789012345678
MOD_IDS=123456,789012
RELEASES_CHANNEL_IDS=123456789012345678,123456789012345679
```

Optional routing:

```env
FOLLOWING_MOD_IDS=123456,789012
GAME_RELEASE_CHANNEL_IDS=83374:123456789012345678;264710:123456789012345679
MOD_RELEASE_CHANNEL_IDS=123456:123456789012345678
MESSAGE_TAG=@everyone
GAME_MESSAGE_TAGS=83374:<@&123456789012345678>
MOD_MESSAGE_TAGS=123456:<@&123456789012345678>
```

`MOD_RELEASE_CHANNEL_IDS` has priority over `GAME_RELEASE_CHANNEL_IDS`. If neither exists for a mod, the bot falls back to the channel at the same index in `RELEASES_CHANNEL_IDS`, then to the first release channel.

`MOD_MESSAGE_TAGS` has priority over `GAME_MESSAGE_TAGS`. If neither exists, the bot uses `MESSAGE_TAG`.

Other useful values:

```env
MESSAGE_HEADER=New version available on CurseForge.
MESSAGE_FOOTER=Links
SHOW_LOGO=true
LOGO_STYLE=thumbnail
ANNOUNCE_MESSAGES=true
ADD_REACTIONS=true
CHECK_INTERVAL_MINUTES=5
LOG_LEVEL=INFO
DEBUG=false
MESSAGE_CONTENT_INTENT=false
```

## Manager UI

The manager is the intended way to use this fork locally.

It can create the Python environment, start/stop the bot, run a one-time update check, send test messages, inspect logs, manage tracked mods, toggle following state, set per-mod overrides, and review stored versions.

The UI saves its own window placement and sort/tab preferences locally under `.local/`, so those files do not pollute the repository.

## Notes

This is not a polished general-purpose product. It is a practical tool built around my Discord/mod publishing workflow, but it should be configurable for other CurseForge release-monitoring setups.

The Discord bot itself needs permission to send messages in the configured channels. If you want command message content access, enable the Discord message content intent and set `MESSAGE_CONTENT_INTENT=true`.
