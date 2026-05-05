from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import socket
from typing import Callable
from urllib.parse import urlparse
import os
import subprocess
import sys
import time

from src.config import config
from src.curseforge import CurseForgeAPI
from src.storage import ReleaseStorage


ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
PID_FILE = ROOT_DIR / "bot.pid"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "bot.log"
RELEASES_DIR = ROOT_DIR / "releases"
RELEASES_DB = RELEASES_DIR / "releases.db"
MANAGER_CONTROL_HOST = "127.0.0.1"
MANAGER_CONTROL_PORT = 47831

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
MOD_NAME_CACHE: dict[str, str] = {}
MOD_UPDATED_AT_CACHE: dict[str, str] = {}
MOD_INFO_CACHE: dict[str, dict[str, object]] = {}
RELEASE_SENT_MARKER = "Successfully sent release notification for"
CHECK_STARTED_MARKER = "Starting update check loop"
CHECK_COMPLETED_MARKER = "Completed update check loop"


@dataclass
class BotStatus:
    running: bool
    pid: int | None
    venv_ready: bool
    log_exists: bool
    log_size: int
    releases_db_exists: bool
    tracked_mod_count: int
    following_mod_count: int
    last_check_started: str
    last_check_completed: str
    last_release_sent: str
    last_error: str


@dataclass
class ReleaseRecord:
    mod_id: str
    version: str
    release_date: str


@dataclass
class ModReleaseSummary:
    mod_id: str
    mod_name: str
    release_channel_id: str
    following: bool
    curseforge_updated_at: str
    download_count: int
    thumbs_up_count: int
    comments_enabled: bool
    public_url: str
    author_files_url: str
    comments_url: str
    versions: list[ReleaseRecord]

    @property
    def latest_version(self) -> str:
        return self.versions[0].version if self.versions else "-"

    @property
    def latest_date(self) -> str:
        return self.versions[0].release_date if self.versions else "-"


@dataclass
class EditableSettings:
    message_tag: str
    debug_channel_id: str
    announce_messages: bool
    add_reactions: bool
    check_interval_minutes: str


@dataclass
class DashboardStats:
    total_downloads: int
    total_likes: int
    tracked_mod_count: int
    following_mod_count: int


def ensure_runtime_dirs() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    RELEASES_DIR.mkdir(exist_ok=True)


def read_env_values() -> dict[str, str]:
    env_path = ROOT_DIR / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _read_env_lines() -> list[str]:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8", errors="replace").splitlines()


def _write_env_lines(lines: list[str]) -> None:
    env_path = ROOT_DIR / ".env"
    text = "\n".join(lines).rstrip() + "\n"
    env_path.write_text(text, encoding="utf-8")


def _set_env_values(updates: dict[str, str]) -> None:
    lines = _read_env_lines()
    seen_keys: set[str] = set()

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue

        key, _value = raw_line.split("=", 1)
        key = key.strip()
        if key in updates:
            lines[index] = f"{key}={updates[key]}"
            seen_keys.add(key)

    for key, value in updates.items():
        if key not in seen_keys:
            lines.append(f"{key}={value}")

    _write_env_lines(lines)


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def get_editable_settings() -> EditableSettings:
    env_values = read_env_values()
    return EditableSettings(
        message_tag=env_values.get("MESSAGE_TAG", ""),
        debug_channel_id=env_values.get("DEBUG_CHANNEL_ID", ""),
        announce_messages=_parse_bool(env_values.get("ANNOUNCE_MESSAGES", "false")),
        add_reactions=_parse_bool(env_values.get("ADD_REACTIONS", "true"), default=True),
        check_interval_minutes=env_values.get("CHECK_INTERVAL_MINUTES", env_values.get("CHECK_INTERVAL", "5")),
    )


def save_editable_settings(settings: EditableSettings) -> None:
    debug_channel_id = settings.debug_channel_id.strip()
    if debug_channel_id and not debug_channel_id.isdigit():
        raise RuntimeError("Debug channel ID must be numeric.")

    interval_text = settings.check_interval_minutes.strip()
    try:
        interval_value = float(interval_text)
    except ValueError as exc:
        raise RuntimeError("Check interval must be numeric.") from exc
    if interval_value <= 0:
        raise RuntimeError("Check interval must be greater than 0.")

    _set_env_values(
        {
            "MESSAGE_TAG": settings.message_tag,
            "DEBUG_CHANNEL_ID": debug_channel_id,
            "ANNOUNCE_MESSAGES": "true" if settings.announce_messages else "false",
            "ADD_REACTIONS": "true" if settings.add_reactions else "false",
            "CHECK_INTERVAL_MINUTES": str(interval_value).rstrip("0").rstrip(".") if "." in str(interval_value) else str(interval_value),
        }
    )


def get_configured_mod_ids() -> list[str]:
    env_values = read_env_values()
    raw_mod_ids = env_values.get("MOD_IDS", "")
    return [mod_id.strip() for mod_id in raw_mod_ids.split(",") if mod_id.strip()]


def get_release_channel_ids() -> list[str]:
    env_values = read_env_values()
    raw_channel_ids = env_values.get("RELEASES_CHANNEL_IDS", "")
    return [channel_id.strip() for channel_id in raw_channel_ids.split(",") if channel_id.strip()]


def get_following_mod_ids() -> list[str]:
    env_values = read_env_values()
    if "FOLLOWING_MOD_IDS" not in env_values:
        return get_configured_mod_ids()

    raw_following_ids = env_values.get("FOLLOWING_MOD_IDS", "")
    return [mod_id.strip() for mod_id in raw_following_ids.split(",") if mod_id.strip()]


def _build_author_files_url(project_id: str) -> str:
    return f"https://authors.curseforge.com/#/projects/{project_id}/files"


def _build_comments_url(website_url: str) -> str:
    if not website_url:
        return ""
    return website_url.rstrip("/") + "/comments"


def _cache_mod_info(mod_id: str, mod_info: dict) -> str:
    mod_name = str(mod_info.get("name") or mod_id)
    updated_at = str(mod_info.get("dateModified") or mod_info.get("dateReleased") or "")
    links = mod_info.get("links") or {}
    website_url = str(links.get("websiteUrl") or "")
    cached_info = {
        "mod_name": mod_name,
        "curseforge_updated_at": updated_at,
        "download_count": int(mod_info.get("downloadCount") or 0),
        "thumbs_up_count": int(mod_info.get("thumbsUpCount") or 0),
        "comments_enabled": bool(mod_info.get("hasCommentsEnabled")),
        "public_url": website_url,
        "author_files_url": _build_author_files_url(mod_id),
        "comments_url": _build_comments_url(website_url),
    }
    MOD_NAME_CACHE[mod_id] = mod_name
    MOD_UPDATED_AT_CACHE[mod_id] = updated_at
    MOD_INFO_CACHE[mod_id] = cached_info
    return mod_name


async def _fetch_mod_names_async(mod_ids: list[str]) -> dict[str, str]:
    if not config.curseforge_api_key:
        return {}

    cf_api = CurseForgeAPI(config.curseforge_api_key)
    names: dict[str, str] = {}
    for mod_id in mod_ids:
        if mod_id in MOD_INFO_CACHE:
            names[mod_id] = MOD_NAME_CACHE[mod_id]
            continue

        try:
            mod_info = await cf_api.get_mod_info(int(mod_id))
            mod_name = _cache_mod_info(mod_id, mod_info)
            names[mod_id] = mod_name
        except Exception:
            names[mod_id] = mod_id
    return names


async def _fetch_mod_info_async(mod_id: str) -> dict:
    cf_api = CurseForgeAPI(config.curseforge_api_key)
    return await cf_api.get_mod_info(int(mod_id))


def get_mod_names(mod_ids: list[str]) -> dict[str, str]:
    unresolved_mod_ids = [mod_id for mod_id in mod_ids if mod_id not in MOD_INFO_CACHE]
    if unresolved_mod_ids:
        try:
            asyncio.run(_fetch_mod_names_async(unresolved_mod_ids))
        except Exception:
            pass

    return {mod_id: MOD_NAME_CACHE.get(mod_id, mod_id) for mod_id in mod_ids}


def get_mod_name(mod_id: str) -> str:
    names = get_mod_names([mod_id])
    return names.get(mod_id, mod_id)


def get_mod_updated_at(mod_id: str) -> str:
    get_mod_names([mod_id])
    return MOD_UPDATED_AT_CACHE.get(mod_id, "")


def get_mod_cached_info(mod_id: str) -> dict[str, object]:
    get_mod_names([mod_id])
    return MOD_INFO_CACHE.get(mod_id, {})


def add_tracked_mod(mod_id: str, release_channel_id: str | None = None) -> str:
    if not mod_id.isdigit():
        raise RuntimeError("MOD_ID must be numeric.")

    env_values = read_env_values()
    mod_ids = get_configured_mod_ids()
    if mod_id in mod_ids:
        raise RuntimeError(f"MOD_ID {mod_id} is already configured.")

    release_channels = [
        channel_id.strip()
        for channel_id in env_values.get("RELEASES_CHANNEL_IDS", "").split(",")
        if channel_id.strip()
    ]
    following_mod_ids = get_following_mod_ids()

    channel_to_add = (release_channel_id or "").strip()
    if channel_to_add:
        if not channel_to_add.isdigit():
            raise RuntimeError("Release channel ID must be numeric.")
    elif release_channels:
        channel_to_add = release_channels[0]
    else:
        raise RuntimeError("Release channel ID is required because no release channels are configured yet.")

    try:
        mod_info = asyncio.run(_fetch_mod_info_async(mod_id))
        mod_name = _cache_mod_info(mod_id, mod_info)
    except Exception as exc:
        raise RuntimeError(f"Failed to validate MOD_ID {mod_id} against CurseForge.") from exc

    mod_ids.append(mod_id)
    release_channels.append(channel_to_add)
    following_mod_ids.append(mod_id)
    _set_env_values(
        {
            "MOD_IDS": ",".join(mod_ids),
            "RELEASES_CHANNEL_IDS": ",".join(release_channels),
            "FOLLOWING_MOD_IDS": ",".join(following_mod_ids),
        }
    )
    return mod_name


def remove_tracked_mod(mod_id: str) -> bool:
    env_values = read_env_values()
    mod_ids = get_configured_mod_ids()
    if mod_id not in mod_ids:
        return False

    release_channels = [
        channel_id.strip()
        for channel_id in env_values.get("RELEASES_CHANNEL_IDS", "").split(",")
        if channel_id.strip()
    ]
    following_mod_ids = [current_mod_id for current_mod_id in get_following_mod_ids() if current_mod_id != mod_id]

    mod_index = mod_ids.index(mod_id)
    del mod_ids[mod_index]
    if mod_index < len(release_channels):
        del release_channels[mod_index]

    _set_env_values(
        {
            "MOD_IDS": ",".join(mod_ids),
            "RELEASES_CHANNEL_IDS": ",".join(release_channels),
            "FOLLOWING_MOD_IDS": ",".join(following_mod_ids),
        }
    )
    return True


def set_mod_following(mod_id: str, following: bool) -> bool:
    mod_ids = get_configured_mod_ids()
    if mod_id not in mod_ids:
        return False

    following_mod_ids = set(get_following_mod_ids())
    if following:
        following_mod_ids.add(mod_id)
    else:
        following_mod_ids.discard(mod_id)

    ordered_following_mod_ids = [current_mod_id for current_mod_id in mod_ids if current_mod_id in following_mod_ids]
    _set_env_values({"FOLLOWING_MOD_IDS": ",".join(ordered_following_mod_ids)})
    return True


def list_tracked_releases() -> list[ModReleaseSummary]:
    configured_mod_ids = get_configured_mod_ids()
    if not configured_mod_ids:
        return []

    mod_names = get_mod_names(configured_mod_ids)
    release_channel_ids = get_release_channel_ids()
    following_mod_ids = set(get_following_mod_ids())
    storage = ReleaseStorage(str(RELEASES_DB))
    rows = storage.get_all_releases()
    releases_by_mod: dict[str, list[ReleaseRecord]] = {mod_id: [] for mod_id in configured_mod_ids}

    for mod_id, version, release_date in rows:
        releases_by_mod.setdefault(str(mod_id), []).append(
            ReleaseRecord(mod_id=str(mod_id), version=str(version), release_date=str(release_date))
        )

    summaries: list[ModReleaseSummary] = []
    for index, mod_id in enumerate(configured_mod_ids):
        cached_info = get_mod_cached_info(mod_id)
        summaries.append(
            ModReleaseSummary(
                mod_id=mod_id,
                mod_name=str(cached_info.get("mod_name", mod_names.get(mod_id, mod_id))),
                release_channel_id=release_channel_ids[index] if index < len(release_channel_ids) else "",
                following=mod_id in following_mod_ids,
                curseforge_updated_at=str(cached_info.get("curseforge_updated_at", get_mod_updated_at(mod_id))),
                download_count=int(cached_info.get("download_count", 0)),
                thumbs_up_count=int(cached_info.get("thumbs_up_count", 0)),
                comments_enabled=bool(cached_info.get("comments_enabled", False)),
                public_url=str(cached_info.get("public_url", "")),
                author_files_url=str(cached_info.get("author_files_url", _build_author_files_url(mod_id))),
                comments_url=str(cached_info.get("comments_url", "")),
                versions=releases_by_mod.get(mod_id, []),
            )
        )

    return summaries


def forget_release(mod_id: str, version: str) -> bool:
    storage = ReleaseStorage(str(RELEASES_DB))
    return storage.delete_release(mod_id, version)


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None

    try:
        raw_pid = PID_FILE.read_text(encoding="utf-8").strip()
        return int(raw_pid) if raw_pid else None
    except (OSError, ValueError):
        return None


def is_process_running(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return result.returncode == 0 and str(pid) in result.stdout


def remove_stale_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _parse_log_timestamp(line: str) -> str:
    if " - " not in line:
        return ""
    timestamp = line.split(" - ", 1)[0].strip()
    try:
        parsed = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S,%f")
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.strptime(timestamp.split(",")[0], "%Y-%m-%d %H:%M:%S")
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return timestamp


def _extract_log_insights() -> tuple[str, str, str, str]:
    if not LOG_FILE.exists():
        return "", "", "", ""

    last_started = ""
    last_completed = ""
    last_release = ""
    last_error = ""
    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            timestamp = _parse_log_timestamp(line)
            if CHECK_STARTED_MARKER in line:
                last_started = timestamp or line
            if CHECK_COMPLETED_MARKER in line:
                last_completed = timestamp or line
            if RELEASE_SENT_MARKER in line:
                last_release = line
            if " - ERROR - " in line:
                last_error = line
    return last_started, last_completed, last_release, last_error


def get_status() -> BotStatus:
    pid = read_pid()
    running = False

    if pid is not None:
        running = is_process_running(pid)
        if not running:
            remove_stale_pid_file()
            pid = None

    log_exists = LOG_FILE.exists()
    log_size = LOG_FILE.stat().st_size if log_exists else 0
    configured_mod_ids = get_configured_mod_ids()
    following_mod_ids = get_following_mod_ids()
    last_started, last_completed, last_release, last_error = _extract_log_insights()

    return BotStatus(
        running=running,
        pid=pid,
        venv_ready=VENV_PYTHON.exists(),
        log_exists=log_exists,
        log_size=log_size,
        releases_db_exists=RELEASES_DB.exists(),
        tracked_mod_count=len(configured_mod_ids),
        following_mod_count=len(following_mod_ids),
        last_check_started=last_started,
        last_check_completed=last_completed,
        last_release_sent=last_release,
        last_error=last_error,
    )


def get_dashboard_stats() -> DashboardStats:
    summaries = list_tracked_releases()
    return DashboardStats(
        total_downloads=sum(summary.download_count for summary in summaries),
        total_likes=sum(summary.thumbs_up_count for summary in summaries),
        tracked_mod_count=len(summaries),
        following_mod_count=sum(1 for summary in summaries if summary.following),
    )


def start_bot() -> int:
    ensure_runtime_dirs()
    status = get_status()
    if status.running and status.pid is not None:
        return status.pid

    if not VENV_PYTHON.exists():
        raise RuntimeError("The environment is missing. Run Setup first.")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "src.main"],
            cwd=ROOT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(1)

    if process.poll() is not None:
        remove_stale_pid_file()
        raise RuntimeError("The bot exited during startup. Check the logs.")

    return process.pid


def stop_bot() -> bool:
    pid = read_pid()
    if pid is None:
        remove_stale_pid_file()
        return False

    if not is_process_running(pid):
        remove_stale_pid_file()
        return False

    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    remove_stale_pid_file()
    return True


def restart_bot() -> int:
    stop_bot()
    return start_bot()


def read_log_tail(max_lines: int = 300) -> str:
    if not LOG_FILE.exists():
        return ""

    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        return "".join(deque(handle, maxlen=max_lines))


def stream_command(command: list[str], callback: Callable[[str], None]) -> int:
    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )

    assert process.stdout is not None
    for line in process.stdout:
        callback(line.rstrip())

    return process.wait()


def setup_environment(callback: Callable[[str], None]) -> int:
    ensure_runtime_dirs()
    bootstrap_python = sys.executable or "python"

    if not VENV_PYTHON.exists():
        callback("Creating virtual environment...")
        code = stream_command([bootstrap_python, "-m", "venv", ".venv"], callback)
        if code != 0:
            return code
    else:
        callback("Virtual environment already exists.")

    callback("Upgrading pip...")
    code = stream_command([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], callback)
    if code != 0:
        return code

    callback("Installing requirements...")
    return stream_command([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"], callback)


def send_debug_test(callback: Callable[[str], None]) -> int:
    if not VENV_PYTHON.exists():
        callback("The environment is missing. Run Setup first.")
        return 1

    callback("Sending debug test message...")
    return stream_command([str(VENV_PYTHON), "-m", "src.test_debug_message"], callback)


def send_latest_release_test(callback: Callable[[str], None]) -> int:
    if not VENV_PYTHON.exists():
        callback("The environment is missing. Run Setup first.")
        return 1

    callback("Sending latest release test for the last configured mod...")
    return stream_command([str(VENV_PYTHON), "-m", "src.test_latest_release"], callback)


def run_update_check_once(callback: Callable[[str], None]) -> int:
    if not VENV_PYTHON.exists():
        callback("The environment is missing. Run Setup first.")
        return 1

    callback("Running a one-time update check...")
    return stream_command([str(VENV_PYTHON), "-m", "src.run_update_check_once"], callback)


def send_latest_release_for_mod(mod_id: str, target: str, callback: Callable[[str], None]) -> int:
    if not VENV_PYTHON.exists():
        callback("The environment is missing. Run Setup first.")
        return 1

    callback(f"Sending latest release for mod {mod_id} to {target} channel...")
    return stream_command(
        [str(VENV_PYTHON), "-m", "src.send_latest_release", "--mod-id", mod_id, "--target", target],
        callback,
    )


def request_existing_manager_shutdown() -> bool:
    try:
        with socket.create_connection((MANAGER_CONTROL_HOST, MANAGER_CONTROL_PORT), timeout=0.5) as sock:
            sock.sendall(b"exit")
        return True
    except OSError:
        return False
