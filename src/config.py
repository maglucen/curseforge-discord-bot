from typing import List
import os
from dotenv import load_dotenv
import logging

VALID_LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def _parse_int_list(raw_value: str, *, name: str) -> list[int]:
    values: list[int] = []
    for item in raw_value.split(','):
        entry = item.strip()
        if not entry:
            continue
        try:
            values.append(int(entry))
        except ValueError:
            logging.warning(f"Skipping invalid {name} entry: {entry}")
    return values


def _parse_int_value(raw_value: str, *, name: str) -> int:
    value = raw_value.strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        logging.warning(f"Invalid {name} '{value}', defaulting to 0")
        return 0

def _parse_text_mapping(raw_value: str, *, item_separator: str = ";") -> dict[int, str]:
    mapping: dict[int, str] = {}
    for item in raw_value.split(item_separator):
        entry = item.strip()
        if not entry or ":" not in entry:
            continue
        key_text, value_text = entry.split(":", 1)
        key_text = key_text.strip()
        value_text = value_text.strip()
        if not key_text:
            continue
        try:
            mapping[int(key_text)] = value_text
        except ValueError:
            logging.warning(f"Skipping invalid text mapping entry: {entry}")
    return mapping


def _parse_int_mapping(raw_value: str, *, item_separator: str = ";") -> dict[int, int]:
    mapping: dict[int, int] = {}
    for item in raw_value.split(item_separator):
        entry = item.strip()
        if not entry or ":" not in entry:
            continue
        key_text, value_text = entry.split(":", 1)
        key_text = key_text.strip()
        value_text = value_text.strip()
        if not key_text or not value_text:
            continue
        try:
            mapping[int(key_text)] = int(value_text)
        except ValueError:
            logging.warning(f"Skipping invalid integer mapping entry: {entry}")
    return mapping


class Config:
    def __init__(self):
        # Always prefer the current .env values over inherited process variables.
        # The manager can edit .env while it stays open, and child processes should
        # pick up those edits instead of stale inherited values.
        load_dotenv(override=True)
        
        # Set up logging configuration
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        if log_level not in VALID_LOG_LEVELS:
            print(f"Invalid LOG_LEVEL '{log_level}', defaulting to INFO")
            log_level = 'INFO'
        
        # Configure logging
        logging.basicConfig(
            level=VALID_LOG_LEVELS[log_level],
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.info(f"Logging level set to {log_level}")
        self.log_level: str = log_level
        
        # Discord settings
        self.bot_token: str = os.getenv('BOT_TOKEN', '')
        self.debug_channel_id: int = _parse_int_value(os.getenv('DEBUG_CHANNEL_ID', '0'), name='DEBUG_CHANNEL_ID')
        
        # Parse releases channel IDs
        self.releases_channel_ids: List[int] = _parse_int_list(os.getenv('RELEASES_CHANNEL_IDS', ''), name='RELEASES_CHANNEL_IDS')
        self.game_release_channel_ids: dict[int, int] = _parse_int_mapping(
            os.getenv('GAME_RELEASE_CHANNEL_IDS', '')
        )
        self.mod_release_channel_ids: dict[int, int] = _parse_int_mapping(
            os.getenv('MOD_RELEASE_CHANNEL_IDS', '')
        )
        logging.debug(f"Loaded Discord settings - debug_channel_id: {self.debug_channel_id}, releases_channel_ids: {self.releases_channel_ids}")
        
        # CurseForge settings
        raw_key = os.getenv('CURSEFORGE_API_KEY', '')
        logging.debug(f"Raw Curseforge API Key from env: {raw_key}")
        self.curseforge_api_key: str = raw_key.replace("'", "").replace('"', '')
        self.mod_ids: List[int] = _parse_int_list(os.getenv('MOD_IDS', ''), name='MOD_IDS')
        following_mod_ids_env = os.getenv('FOLLOWING_MOD_IDS')
        if following_mod_ids_env is None:
            self.following_mod_ids: List[int] = list(self.mod_ids)
        else:
            self.following_mod_ids = _parse_int_list(following_mod_ids_env, name='FOLLOWING_MOD_IDS')
        logging.debug(f"Loaded CurseForge settings - mod_ids: {self.mod_ids}, following_mod_ids: {self.following_mod_ids}")
        
        # Message templates
        self.message_tag: str = os.getenv('MESSAGE_TAG', '')
        self.game_message_tags: dict[int, str] = _parse_text_mapping(
            os.getenv('GAME_MESSAGE_TAGS', '')
        )
        self.mod_message_tags: dict[int, str] = _parse_text_mapping(
            os.getenv('MOD_MESSAGE_TAGS', '')
        )
        self.message_header: str = os.getenv('MESSAGE_HEADER', '')
        self.message_footer: str = os.getenv('MESSAGE_FOOTER', '')
        logging.debug("Loaded message templates and labels")

        check_interval_raw = os.getenv('CHECK_INTERVAL_MINUTES', os.getenv('CHECK_INTERVAL', '5')).strip()
        try:
            self.check_interval_minutes: float = float(check_interval_raw)
        except ValueError:
            logging.warning(f"Invalid CHECK_INTERVAL_MINUTES '{check_interval_raw}', defaulting to 5")
            self.check_interval_minutes = 5.0
        if self.check_interval_minutes <= 0:
            logging.warning(f"CHECK_INTERVAL_MINUTES must be positive, got {self.check_interval_minutes}. Defaulting to 5")
            self.check_interval_minutes = 5.0
        
        # Feature flags
        self.announce_messages: bool = os.getenv('ANNOUNCE_MESSAGES', 'false').lower() == 'true'
        self.debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
        self.show_logo: bool = os.getenv('SHOW_LOGO', 'true').lower() == 'true'
        self.add_reactions: bool = os.getenv('ADD_REACTIONS', 'true').lower() == 'true'
        self.message_content_intent: bool = os.getenv('MESSAGE_CONTENT_INTENT', 'false').lower() == 'true'
        self.logo_style: str = os.getenv('LOGO_STYLE', 'thumbnail').strip().lower()
        if self.logo_style not in {'thumbnail', 'fullwidth'}:
            logging.warning(f"Invalid LOGO_STYLE '{self.logo_style}', defaulting to thumbnail")
            self.logo_style = 'thumbnail'
        logging.debug(f"Loaded feature flags - announce_messages: {self.announce_messages}, debug: {self.debug}, show_logo: {self.show_logo}, add_reactions: {self.add_reactions}")
    
    def validate(self) -> List[str]:
        """Validate the configuration and return a list of error messages."""
        logging.debug("Validating configuration")
        errors = []
        
        if not self.bot_token:
            errors.append("BOT_TOKEN is required")
        if not self.debug_channel_id:
            errors.append("DEBUG_CHANNEL_ID is required")
        if not self.releases_channel_ids:
            errors.append("RELEASES_CHANNEL_IDS is required")
        if not self.curseforge_api_key:
            errors.append("CURSEFORGE_API_KEY is required")
        if not self.mod_ids:
            errors.append("At least one MOD_ID is required")

        logging.debug(f"Curseforge API Key: {self.curseforge_api_key}")
        
        # Warn if number of channels doesn't match mods
        if len(self.mod_ids) > len(self.releases_channel_ids):
            logging.warning(
                f"Fewer release channels ({len(self.releases_channel_ids)}) "
                f"than mods ({len(self.mod_ids)}). "
                "Extra mods will use the first channel."
            )

        if self.check_interval_minutes <= 0:
            errors.append("CHECK_INTERVAL_MINUTES must be greater than 0")
            
        if errors:
            logging.error(f"Configuration validation failed with errors: {errors}")
        else:
            logging.debug("Configuration validation successful")
        return errors

    def resolve_release_channel_id(self, mod_id: int, game_id: int | None = None) -> int:
        if mod_id in self.mod_release_channel_ids:
            return self.mod_release_channel_ids[mod_id]
        if game_id is not None and game_id in self.game_release_channel_ids:
            return self.game_release_channel_ids[game_id]
        try:
            mod_index = self.mod_ids.index(mod_id)
        except ValueError as exc:
            raise RuntimeError(f"MOD_ID {mod_id} is not configured.") from exc

        if mod_index < len(self.releases_channel_ids):
            return self.releases_channel_ids[mod_index]
        if self.releases_channel_ids:
            return self.releases_channel_ids[0]
        raise RuntimeError("No release channel is configured.")

    def resolve_message_tag(self, mod_id: int, game_id: int | None = None) -> str:
        if mod_id in self.mod_message_tags:
            return self.mod_message_tags[mod_id]
        if game_id is not None and game_id in self.game_message_tags:
            return self.game_message_tags[game_id]
        return self.message_tag

config = Config()
