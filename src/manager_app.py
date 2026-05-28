from __future__ import annotations

from datetime import datetime
import ctypes
import json
import os
import queue
import re
import socket
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import simpledialog
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from src import manager_service


APP_ID = "Maglucen.CurseForgeDiscordBot.Manager"
WINDOW_GEOMETRY_FILE = manager_service.LOCAL_DIR / "manager-window-geometry.txt"
UI_STATE_FILE = manager_service.LOCAL_DIR / "manager-ui-state.json"
BG = "#0F1117"
PANEL = "#171A22"
PANEL_ALT = "#11141B"
ACCENT = "#33D1C6"
ACCENT_BORDER = "#52E6DB"
BORDER = "#2A3242"
MUTED = "#9CA7BA"
TEXT = "#E6EAF2"
CONTROL = "#10151D"
CONTROL_ALT = "#141B26"
SELECTION = "#214D56"
BUTTON_BG = "#1E2430"
BUTTON_HOVER = "#263041"
BUTTON_PRESSED = "#2D384C"
MOD_COLUMN_LABELS = {
    "following": "Following",
    "mod_name": "Mod",
    "game_name": "Game",
    "mod_id": "MOD_ID",
    "download_count": "Downloads",
    "curseforge_updated_at": "CurseForge Updated",
    "latest_version": "Latest Stored",
    "latest_date": "Stored At",
}
VERSION_COLUMN_LABELS = {
    "version": "Version",
    "release_date": "Stored At",
}
DEFAULT_GEOMETRY = "1480x920"
GEOMETRY_PATTERN = re.compile(r"^(\d+)x(\d+)([+-]\d+)?([+-]\d+)?$")
SORT_ARROW_ASC = " \u25b2"
SORT_ARROW_DESC = " \u25bc"
RELEASE_SENT_MARKER = "Successfully sent release notification for"
AUTHOR_DASHBOARD_URL = "https://authors.curseforge.com/#/downloads-statistics"
CONFIRMATION_WINDOW_SECONDS = 5.0


def _rounded_rect_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius,
        y1,
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]


class RoundedSurface(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        bg_fill: str,
        border_color: str = BORDER,
        padding: int = 18,
        radius: int = 18,
        border_width: int = 1,
    ) -> None:
        parent_bg = parent.cget("bg") if "bg" in parent.keys() else BG
        super().__init__(parent, bg=parent_bg, bd=0, highlightthickness=0)
        self._bg_fill = bg_fill
        self._border_color = border_color
        self._padding = padding
        self._radius = radius
        self._border_width = border_width
        self.canvas = tk.Canvas(
            self,
            bg=parent_bg,
            bd=0,
            highlightthickness=0,
            relief="flat",
            width=1,
            height=1,
        )
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg_fill, bd=0, highlightthickness=0)
        self._body_window = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.canvas.bind("<Configure>", self._redraw, add="+")
        self.body.bind("<Configure>", self._on_body_configure, add="+")

    def _on_body_configure(self, _event=None) -> None:
        requested_width = self.body.winfo_reqwidth() + ((self._padding + self._border_width) * 2)
        requested_height = self.body.winfo_reqheight() + ((self._padding + self._border_width) * 2)
        if self.canvas.winfo_width() <= 2:
            self.canvas.configure(width=requested_width)
        self.canvas.configure(height=requested_height)
        self._redraw()

    def _redraw(self, _event=None) -> None:
        requested_width = self.body.winfo_reqwidth() + ((self._padding + self._border_width) * 2)
        requested_height = self.body.winfo_reqheight() + ((self._padding + self._border_width) * 2)
        width = self.canvas.winfo_width()
        if width <= 2:
            width = requested_width
        height = max(self.canvas.winfo_height(), requested_height)
        self.canvas.delete("surface")
        outer_points = _rounded_rect_points(0, 0, width, height, self._radius)
        self.canvas.create_polygon(
            outer_points,
            smooth=True,
            splinesteps=24,
            fill=self._border_color,
            outline="",
            tags="surface",
        )

        inset = self._border_width
        inner_points = _rounded_rect_points(
            inset,
            inset,
            width - inset,
            height - inset,
            max(0, self._radius - inset),
        )
        self.canvas.create_polygon(
            inner_points,
            smooth=True,
            splinesteps=24,
            fill=self._bg_fill,
            outline="",
            tags="surface",
        )

        content_x = self._padding + self._border_width
        content_y = self._padding + self._border_width
        self.canvas.coords(self._body_window, content_x, content_y)
        self.canvas.itemconfigure(
            self._body_window,
            width=max(1, width - (content_x * 2)),
            height=max(1, height - (content_y * 2)),
        )


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command,
        accent: bool = False,
        radius: int = 12,
    ) -> None:
        parent_bg = parent.cget("bg") if "bg" in parent.keys() else BG
        super().__init__(parent, bg=parent_bg, bd=0, highlightthickness=0, relief="flat", cursor="hand2")
        self._text = text
        self._command = command
        self._accent = accent
        self._radius = radius
        self._selected = False
        self._pressed = False
        self._hover = False
        self._font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._text_id = self.create_text(0, 0, text=text, font=self._font)
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self._sync_requested_size()

    def _colors(self) -> tuple[str, str, str]:
        if self._selected and not self._accent:
            return CONTROL_ALT, "#5A6578", TEXT
        if self._accent:
            if self._pressed:
                return "#2FBDB2", ACCENT_BORDER, "#07161A"
            if self._hover:
                return "#46DDD1", ACCENT_BORDER, "#07161A"
            return ACCENT, ACCENT_BORDER, "#07161A"
        if self._pressed:
            return BUTTON_PRESSED, "#3D485A", "#EDF2F7"
        if self._hover:
            return BUTTON_HOVER, "#3D485A", "#EDF2F7"
        return BUTTON_BG, BORDER, "#EDF2F7"

    def _sync_requested_size(self) -> None:
        text_width = self._font.measure(self._text)
        text_height = self._font.metrics("linespace")
        self.configure(width=text_width + 34, height=text_height + 20)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._redraw()

    def _redraw(self, _event=None) -> None:
        width = max(self.winfo_width(), int(self.cget("width")))
        height = max(self.winfo_height(), int(self.cget("height")))
        fill, border_color, text_color = self._colors()
        self.delete("button_shape")
        points = _rounded_rect_points(0, 0, width, height, self._radius)
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=border_color,
            outline="",
            tags="button_shape",
        )
        inner = 1
        inner_points = _rounded_rect_points(inner, inner, width - inner, height - inner, max(0, self._radius - inner))
        self.create_polygon(
            inner_points,
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline="",
            tags="button_shape",
        )
        self.tag_raise(self._text_id)
        self.coords(self._text_id, width / 2, height / 2)
        self.itemconfigure(self._text_id, text=self._text, fill=text_color)

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event=None) -> None:
        self._pressed = True
        self._redraw()

    def _on_release(self, event=None) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and event is not None and self._command:
            if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
                self._command()


class BotManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CurseForge Discord Bot")
        self.root.minsize(1240, 800)
        self._icon_image: tk.PhotoImage | None = None
        self._control_server_socket: socket.socket | None = None
        self._control_stop_event = threading.Event()
        self._geometry_save_after_id: str | None = None
        self._geometry_save_enabled = False
        self._last_normal_geometry = DEFAULT_GEOMETRY
        self._release_refresh_in_progress = False
        manager_service.ensure_runtime_dirs()
        self._set_window_icon()
        self._restore_window_geometry()
        ui_state = self._load_ui_state()

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.action_lock = threading.Lock()
        self.follow_logs = tk.BooleanVar(value=True)
        self.new_mod_id = tk.StringVar(value="")
        self.new_release_channel_id = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Checking...")
        self.pid_text = tk.StringVar(value="-")
        self.venv_text = tk.StringVar(value="Checking...")
        self.log_text = tk.StringVar(value="-")
        self.db_text = tk.StringVar(value="-")
        self.last_check_text = tk.StringVar(value="-")
        self.last_release_text = tk.StringVar(value="-")
        self.last_error_text = tk.StringVar(value="-")
        self.following_count_text = tk.StringVar(value="-")
        self.notice_text = tk.StringVar(value="Ready.")
        current_settings = manager_service.get_editable_settings()
        self.setting_message_tag = tk.StringVar(value=current_settings.message_tag)
        self.setting_debug_channel_id = tk.StringVar(value=current_settings.debug_channel_id)
        self.setting_announce_messages = tk.BooleanVar(value=current_settings.announce_messages)
        self.setting_add_reactions = tk.BooleanVar(value=current_settings.add_reactions)
        self.setting_check_interval_minutes = tk.StringVar(value=current_settings.check_interval_minutes)
        self.game_release_channel_vars: dict[str, tk.StringVar] = {}
        self.game_message_tag_vars: dict[str, tk.StringVar] = {}
        self.game_name_by_id: dict[str, str] = {}
        self.game_defaults_frame: tk.Frame | None = None
        self.last_log_snapshot = ""
        self.last_log_signature: tuple[bool, int] | None = None
        self.release_summaries: list[manager_service.ModReleaseSummary] = []
        self.pending_confirmations: dict[str, float] = {}
        self.sidebar_panes: tk.PanedWindow | None = None
        self.releases_panes: tk.PanedWindow | None = None
        self.tab_frames: dict[str, tk.Frame] = {}
        self.tab_buttons: dict[str, RoundedButton] = {}
        self.mod_sort_column, self.mod_sort_direction = self._normalize_sort_state(
            ui_state.get("mod_sort_column"),
            ui_state.get("mod_sort_direction"),
            MOD_COLUMN_LABELS,
        )
        self.version_sort_column, self.version_sort_direction = self._normalize_sort_state(
            ui_state.get("version_sort_column"),
            ui_state.get("version_sort_direction"),
            VERSION_COLUMN_LABELS,
        )
        self.selected_tab = self._normalize_tab_name(ui_state.get("selected_tab"))
        self._configure_dark_theme()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._schedule_geometry_save, add="+")
        self._refresh_status()
        self._refresh_logs(force=True)
        self._start_control_server()
        self._process_events()
        self._schedule_refresh()
        self.root.after(100, self._refresh_releases)
        self.root.after_idle(self._apply_initial_pane_layouts)

    def _set_window_icon(self) -> None:
        tools_dir = manager_service.ROOT_DIR / "tools"
        icon_path = tools_dir / "bot-manager.ico"
        image_path = tools_dir / "bot-manager.png"

        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

        if image_path.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(image_path))
                self.root.iconphoto(True, self._icon_image)
            except tk.TclError:
                self._icon_image = None

    def _restore_window_geometry(self) -> None:
        geometry = DEFAULT_GEOMETRY
        window_state = "normal"
        if WINDOW_GEOMETRY_FILE.exists():
            try:
                raw_value = WINDOW_GEOMETRY_FILE.read_text(encoding="utf-8").strip()
                if raw_value.startswith("{"):
                    stored_state = json.loads(raw_value)
                    normal_geometry = str(stored_state.get("normal_geometry") or "").strip()
                    stored_window_state = str(stored_state.get("window_state") or "normal").strip()
                    if self._is_valid_geometry(normal_geometry):
                        geometry = self._safe_normal_geometry(normal_geometry)
                    if stored_window_state in {"normal", "zoomed"}:
                        window_state = stored_window_state
                elif self._is_valid_geometry(raw_value):
                    if self._looks_like_saved_maximized_geometry(raw_value):
                        geometry = DEFAULT_GEOMETRY
                        window_state = "zoomed"
                    else:
                        geometry = raw_value
            except (OSError, json.JSONDecodeError):
                geometry = DEFAULT_GEOMETRY
                window_state = "normal"
        self._last_normal_geometry = geometry
        self.root.geometry(geometry)
        self.root.after_idle(lambda: self._apply_restored_window_state(window_state))

    def _schedule_geometry_save(self, _event=None) -> None:
        if not self._geometry_save_enabled:
            return
        if self.root.state() == "normal":
            current_geometry = self.root.geometry()
            if self._is_valid_geometry(current_geometry) and not self._looks_like_saved_maximized_geometry(current_geometry):
                self._last_normal_geometry = current_geometry
        if self._geometry_save_after_id is not None:
            self.root.after_cancel(self._geometry_save_after_id)
        self._geometry_save_after_id = self.root.after(250, self._save_window_geometry)

    def _apply_restored_window_state(self, window_state: str) -> None:
        if window_state == "zoomed":
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass
        self.root.after(800, self._enable_geometry_saves)

    def _enable_geometry_saves(self) -> None:
        if self.root.state() == "normal":
            current_geometry = self.root.geometry()
            if self._is_valid_geometry(current_geometry) and not self._looks_like_saved_maximized_geometry(current_geometry):
                self._last_normal_geometry = current_geometry
        self._geometry_save_enabled = True

    def _is_valid_geometry(self, geometry: str) -> bool:
        return bool(GEOMETRY_PATTERN.match(geometry))

    def _safe_normal_geometry(self, geometry: str) -> str:
        if self._looks_like_saved_maximized_geometry(geometry):
            return DEFAULT_GEOMETRY
        return geometry

    def _looks_like_saved_maximized_geometry(self, geometry: str) -> bool:
        match = GEOMETRY_PATTERN.match(geometry)
        if not match:
            return False
        width = int(match.group(1))
        height = int(match.group(2))
        x = int(match.group(3) or 0)
        y = int(match.group(4) or 0)
        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        return width >= screen_width or height >= screen_height or x < -24 or y < -24

    def _load_ui_state(self) -> dict[str, str | None]:
        if not UI_STATE_FILE.exists():
            return {}
        try:
            data = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _normalize_sort_state(
        self,
        column: object,
        direction: object,
        valid_columns: dict[str, str],
    ) -> tuple[str | None, str | None]:
        normalized_column = str(column) if isinstance(column, str) and column in valid_columns else None
        normalized_direction = str(direction) if direction in {"asc", "desc"} else None
        if normalized_column is None or normalized_direction is None:
            return None, None
        return normalized_column, normalized_direction

    def _normalize_tab_name(self, tab_name: object) -> str:
        if isinstance(tab_name, str) and tab_name in {"Logs", "Activity", "Releases", "Settings", "Stats"}:
            return tab_name
        return "Logs"

    def _configure_dark_theme(self) -> None:
        self.root.configure(bg=BG)
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, fieldbackground=CONTROL_ALT)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 26))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 11))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 10))
        style.configure(
            "TButton",
            background=BUTTON_BG,
            foreground="#EDF2F7",
            borderwidth=1,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            focusthickness=0,
            focuscolor=BUTTON_BG,
            padding=(14, 10),
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TButton",
            background=[("active", BUTTON_HOVER), ("pressed", BUTTON_PRESSED)],
            foreground=[("disabled", "#6f8095")],
            bordercolor=[("active", "#3D485A"), ("pressed", "#3D485A")],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#07161A",
            borderwidth=1,
            bordercolor=ACCENT_BORDER,
            lightcolor=ACCENT_BORDER,
            darkcolor=ACCENT_BORDER,
            focusthickness=0,
            focuscolor=ACCENT,
            padding=(14, 10),
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#46DDD1"), ("pressed", "#2FBDB2")],
            foreground=[("disabled", "#244B50")],
            bordercolor=[("active", ACCENT_BORDER), ("pressed", ACCENT_BORDER)],
        )
        style.configure(
            "TEntry",
            fieldbackground=CONTROL,
            background=CONTROL,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(10, 8),
        )
        style.configure(
            "TCheckbutton",
            background=PANEL,
            foreground=TEXT,
            indicatorbackground=CONTROL,
            indicatormargin=4,
            font=("Segoe UI", 10),
        )
        style.map(
            "TCheckbutton",
            background=[("active", PANEL)],
            foreground=[("disabled", "#6f8095")],
            indicatorbackground=[("selected", ACCENT), ("active", CONTROL)],
        )
        style.configure("TNotebook", background=PANEL, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=PANEL,
            foreground=MUTED,
            padding=(18, 12),
            borderwidth=0,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CONTROL_ALT), ("active", CONTROL_ALT)],
            foreground=[("selected", TEXT), ("active", TEXT)],
        )
        style.configure(
            "Treeview",
            background=CONTROL,
            fieldbackground=CONTROL,
            foreground=TEXT,
            rowheight=32,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#1B2230",
            foreground=MUTED,
            bordercolor="#1B2230",
            lightcolor="#1B2230",
            darkcolor="#1B2230",
            font=("Segoe UI Semibold", 10),
            padding=(10, 8),
        )
        style.map(
            "Treeview",
            background=[("selected", SELECTION)],
            foreground=[("selected", "#ffffff")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#243142")],
            foreground=[("active", TEXT)],
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=CONTROL_ALT,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            lightcolor=CONTROL_ALT,
            darkcolor=CONTROL_ALT,
            gripcount=0,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=CONTROL_ALT,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            lightcolor=CONTROL_ALT,
            darkcolor=CONTROL_ALT,
            gripcount=0,
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[("active", "#243142"), ("pressed", SELECTION)],
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#243142"), ("pressed", SELECTION)],
        )
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.option_add("*Background", BG)
        self.root.option_add("*Foreground", TEXT)
        self.root.option_add("*Text.background", CONTROL)
        self.root.option_add("*Text.foreground", TEXT)
        self.root.option_add("*Text.insertBackground", TEXT)
        self.root.option_add("*Text.selectBackground", SELECTION)
        self.root.option_add("*Text.selectForeground", "#ffffff")

    def _create_surface(self, parent: tk.Misc, *, bg: str = PANEL, padding: int = 18, radius: int = 18) -> tuple[tk.Frame, tk.Frame]:
        surface = RoundedSurface(parent, bg_fill=bg, border_color=BORDER, padding=padding, radius=radius)
        return surface, surface.body

    def _create_panel(
        self,
        parent: tk.Misc,
        *,
        title: str,
        subtitle: str | None = None,
        bg: str = PANEL,
        padding: int = 18,
    ) -> tuple[tk.Frame, tk.Frame]:
        outer, body = self._create_surface(parent, bg=bg, padding=padding)
        header = tk.Frame(body, bg=bg)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text=title, bg=bg, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        if subtitle:
            tk.Label(header, text=subtitle, bg=bg, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))
        content = tk.Frame(body, bg=bg)
        content.pack(fill="both", expand=True)
        return outer, content

    def _create_metric_card(self, parent: tk.Misc, *, title: str, value_var: tk.StringVar) -> tk.Frame:
        outer, body = self._create_surface(parent, bg=PANEL, padding=18)
        tk.Label(body, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(body, textvariable=value_var, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 24)).pack(anchor="w", pady=(6, 0))
        return outer

    def _create_button(self, parent: tk.Misc, *, text: str, command, accent: bool = False) -> RoundedButton:
        return RoundedButton(parent, text=text, command=command, accent=accent)

    def _create_entry(self, parent: tk.Misc, *, textvariable: tk.StringVar, width: int | None = None) -> tk.Frame:
        outer, body = self._create_surface(parent, bg=CONTROL, padding=10, radius=12)
        entry = tk.Entry(
            body,
            textvariable=textvariable,
            bg=CONTROL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            width=width,
        )
        entry.pack(fill="x", expand=True)
        return outer

    def _create_detail_metric(
        self,
        parent: tk.Misc,
        *,
        row: int,
        column: int,
        title: str,
        value_var: tk.StringVar,
        columnspan: int = 1,
    ) -> None:
        cell = tk.Frame(parent, bg=PANEL)
        cell.grid(row=row, column=column, columnspan=columnspan, sticky="ew", pady=(0, 14))
        cell.columnconfigure(0, weight=1)
        tk.Label(cell, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        value_label = tk.Label(
            cell,
            textvariable=value_var,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 12),
            justify="left",
            anchor="w",
        )
        value_label.pack(anchor="w", fill="x", pady=(4, 0))

        def sync_wrap(_event=None) -> None:
            value_label.configure(wraplength=max(120, cell.winfo_width() - 2))

        cell.bind("<Configure>", sync_wrap, add="+")

    def _style_text_widget(self, widget: ScrolledText) -> None:
        widget.configure(
            background=CONTROL,
            foreground=TEXT,
            insertbackground=TEXT,
            selectbackground=SELECTION,
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10,
        )
        widget.vbar.configure(
            background=CONTROL_ALT,
            troughcolor=BG,
            activebackground="#243142",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )

    def _save_ui_state(self) -> None:
        selected_tab = self.selected_tab

        state = {
            "selected_tab": selected_tab,
            "mod_sort_column": self.mod_sort_column,
            "mod_sort_direction": self.mod_sort_direction,
            "version_sort_column": self.version_sort_column,
            "version_sort_direction": self.version_sort_direction,
        }
        try:
            UI_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _save_window_geometry(self) -> None:
        self._geometry_save_after_id = None
        if not self._geometry_save_enabled:
            return
        window_state = self.root.state()
        if window_state == "iconic":
            return
        if window_state == "normal":
            current_geometry = self.root.geometry()
            if self._looks_like_saved_maximized_geometry(current_geometry):
                window_state = "zoomed"
            elif self._is_valid_geometry(current_geometry):
                self._last_normal_geometry = current_geometry
        saved_state = {
            "normal_geometry": self._last_normal_geometry,
            "window_state": "zoomed" if window_state == "zoomed" else "normal",
        }
        try:
            WINDOW_GEOMETRY_FILE.write_text(json.dumps(saved_state, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _on_tab_changed(self, tab_name: str | None = None) -> None:
        if tab_name:
            self.selected_tab = self._normalize_tab_name(tab_name)
        self._save_ui_state()

    def _show_tab(self, tab_name: str) -> None:
        normalized = self._normalize_tab_name(tab_name)
        for name, frame in self.tab_frames.items():
            if name == normalized:
                frame.grid()
            else:
                frame.grid_remove()
        for name, button in self.tab_buttons.items():
            button.set_selected(name == normalized)
        self._on_tab_changed(normalized)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = tk.Frame(self.root, bg=BG, padx=18, pady=18)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        header = tk.Frame(shell, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)

        header_text = tk.Frame(header, bg=BG)
        header_text.grid(row=0, column=0, sticky="w")
        ttk.Label(header_text, text="CurseForge Discord Bot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header_text,
            text="Visual manager for release tracking, diagnostics, and bot control",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        header_actions = tk.Frame(header, bg=BG)
        header_actions.grid(row=0, column=1, sticky="e")
        self._create_button(header_actions, text="Open Log", command=self._open_log).pack(side="right")
        self._create_button(
            header_actions,
            text="Open Project Folder",
            command=self._open_project_folder,
            accent=True,
        ).pack(side="right", padx=(0, 10))

        metrics_row = tk.Frame(shell, bg=BG)
        metrics_row.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        for column in range(4):
            metrics_row.columnconfigure(column, weight=1)

        for index, (title, value_var) in enumerate(
            [
                ("Bot", self.status_text),
                ("Following", self.following_count_text),
                ("Stored releases", self.db_text),
                ("Last check", self.last_check_text),
            ]
        ):
            card = self._create_metric_card(metrics_row, title=title, value_var=value_var)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 14 if index < 3 else 0))

        body = tk.Frame(shell, bg=BG)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=360)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = tk.Frame(body, bg=BG)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=0)
        sidebar.rowconfigure(1, weight=0)
        sidebar.rowconfigure(2, weight=1)

        details_panel, details_content = self._create_panel(
            sidebar,
            title="Bot details",
            subtitle="Process state, environment, and latest activity",
            bg=PANEL,
        )
        details_panel.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        details_content.columnconfigure(0, weight=1)
        self._create_detail_metric(details_content, row=0, column=0, title="PID", value_var=self.pid_text)
        self._create_detail_metric(details_content, row=1, column=0, title="Environment", value_var=self.venv_text)
        self._create_detail_metric(details_content, row=2, column=0, title="Logs", value_var=self.log_text)
        self._create_detail_metric(details_content, row=3, column=0, title="Last release", value_var=self.last_release_text)
        self._create_detail_metric(details_content, row=4, column=0, title="Last error", value_var=self.last_error_text)
        self._create_detail_metric(details_content, row=5, column=0, title="Last action", value_var=self.notice_text)

        actions_panel, actions_content = self._create_panel(
            sidebar,
            title="Quick actions",
            subtitle="Launch, test, and control the Discord bot",
            bg=PANEL_ALT,
        )
        actions_panel.grid(row=1, column=0, sticky="ew")
        for column in range(2):
            actions_content.columnconfigure(column, weight=1)

        buttons = [
            ("Setup", self._setup_environment, False),
            ("Start", self._start_bot, True),
            ("Stop", self._stop_bot, False),
            ("Restart", self._restart_bot, False),
            ("Check Now", self._check_now, True),
            ("Restart App", self._restart_app, False),
            ("Test Debug", self._test_debug, False),
            ("Test Release", self._test_latest_release, False),
            ("Refresh", self._manual_refresh, False),
        ]
        for index, (label, command, accent) in enumerate(buttons):
            row = index // 2
            column = index % 2
            self._create_button(
                actions_content,
                text=label,
                command=command,
                accent=accent,
            ).grid(row=row, column=column, sticky="ew", padx=(0, 8 if column == 0 else 0), pady=(0, 8))

        workspace_panel, workspace_content = self._create_panel(
            body,
            title="Workspace",
            subtitle="Logs, releases, settings, and statistics",
            bg=PANEL,
        )
        workspace_panel.grid(row=0, column=1, sticky="nsew")
        workspace_content.columnconfigure(0, weight=1)
        workspace_content.rowconfigure(1, weight=1)

        tab_bar = tk.Frame(workspace_content, bg=PANEL)
        tab_bar.grid(row=0, column=0, sticky="w", pady=(0, 10))

        tab_container = tk.Frame(workspace_content, bg=PANEL, bd=0, highlightthickness=0)
        tab_container.grid(row=1, column=0, sticky="nsew")
        tab_container.columnconfigure(0, weight=1)
        tab_container.rowconfigure(0, weight=1)

        logs_tab = tk.Frame(tab_container, bg=PANEL)
        actions_tab = tk.Frame(tab_container, bg=PANEL)
        releases_tab = tk.Frame(tab_container, bg=PANEL)
        settings_tab = tk.Frame(tab_container, bg=PANEL)
        stats_tab = tk.Frame(tab_container, bg=PANEL)
        self.tab_frames = {
            "Logs": logs_tab,
            "Activity": actions_tab,
            "Releases": releases_tab,
            "Settings": settings_tab,
            "Stats": stats_tab,
        }
        for frame in self.tab_frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

        for index, tab_name in enumerate(["Logs", "Activity", "Releases", "Settings", "Stats"]):
            button = self._create_button(tab_bar, text=tab_name, command=lambda name=tab_name: self._show_tab(name))
            button.pack(side="left", padx=(0, 8 if index < 4 else 0))
            self.tab_buttons[tab_name] = button

        logs_tab.columnconfigure(0, weight=1)
        logs_tab.rowconfigure(0, weight=1)
        actions_tab.columnconfigure(0, weight=1)
        actions_tab.rowconfigure(0, weight=1)
        releases_tab.columnconfigure(0, weight=1)
        releases_tab.rowconfigure(0, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        stats_tab.columnconfigure(0, weight=1)
        stats_tab.rowconfigure(0, weight=1)

        logs_panel, logs_content = self._create_panel(
            logs_tab,
            title="Logs",
            subtitle="Live application output from the running bot",
            bg=CONTROL_ALT,
        )
        logs_panel.grid(row=0, column=0, sticky="nsew")
        logs_content.columnconfigure(0, weight=1)
        logs_content.rowconfigure(1, weight=1)
        logs_toolbar = tk.Frame(logs_content, bg=PANEL)
        logs_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Checkbutton(logs_toolbar, text="Follow logs", variable=self.follow_logs).pack(side="left")
        self._create_button(logs_toolbar, text="Clear view", command=self._clear_log_view).pack(side="left", padx=(10, 0))

        self.logs_view = ScrolledText(logs_content, wrap="word", font=("Consolas", 10))
        self.logs_view.grid(row=1, column=0, sticky="nsew")
        self._style_text_widget(self.logs_view)
        self.logs_view.configure(state="disabled")

        activity_panel, activity_content = self._create_panel(
            actions_tab,
            title="Activity",
            subtitle="Command output and background task results",
            bg=CONTROL_ALT,
        )
        activity_panel.grid(row=0, column=0, sticky="nsew")
        activity_content.columnconfigure(0, weight=1)
        activity_content.rowconfigure(0, weight=1)
        self.output_view = ScrolledText(activity_content, wrap="word", font=("Consolas", 10))
        self.output_view.grid(row=0, column=0, sticky="nsew")
        self._style_text_widget(self.output_view)
        self.output_view.configure(state="disabled")

        releases_panel, releases_content = self._create_panel(
            releases_tab,
            title="Releases",
            subtitle="Track mods, manage stored versions, and resend notifications",
            bg=CONTROL_ALT,
        )
        releases_panel.grid(row=0, column=0, sticky="nsew")
        releases_content.columnconfigure(0, weight=1)
        releases_content.rowconfigure(2, weight=1)

        releases_actions = tk.Frame(releases_content, bg=CONTROL_ALT)
        releases_actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._create_button(releases_actions, text="Refresh Releases", command=self._refresh_releases).pack(side="left")
        self._create_button(releases_actions, text="Send Latest To Release", command=self._send_selected_release).pack(side="left", padx=(8, 0))
        self._create_button(releases_actions, text="Send Latest To Debug", command=self._send_selected_release_to_debug).pack(side="left", padx=(8, 0))

        mod_editor = tk.Frame(releases_content, bg=CONTROL_ALT)
        mod_editor.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        mod_editor.columnconfigure(1, weight=1)
        mod_editor.columnconfigure(2, weight=0)
        mod_editor.columnconfigure(3, weight=0)
        ttk.Label(mod_editor, text="New MOD_ID", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self._create_entry(mod_editor, textvariable=self.new_mod_id, width=18).grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self._create_button(mod_editor, text="Add Mod", command=self._add_mod, accent=True).grid(row=0, column=2, sticky="ew")
        self._create_button(mod_editor, text="Remove Selected Mod", command=self._remove_selected_mod).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        tracked_outer, tracked_mods_pane = self._create_surface(releases_content, bg=PANEL_ALT, padding=18)
        tracked_outer.grid(row=2, column=0, sticky="nsew")
        tracked_mods_pane.columnconfigure(0, weight=1)
        tracked_mods_pane.columnconfigure(1, weight=0)
        tracked_mods_pane.rowconfigure(1, weight=1)

        tk.Label(tracked_mods_pane, text="Tracked mods", bg=PANEL_ALT, fg=TEXT, font=("Segoe UI Semibold", 18)).grid(row=0, column=0, sticky="nw")
        self.mods_tree = ttk.Treeview(
            tracked_mods_pane,
            columns=("following", "mod_name", "game_name", "mod_id", "download_count", "curseforge_updated_at", "latest_version", "latest_date"),
            show="headings",
            height=8,
        )
        self.mods_tree.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.mods_tree.heading("following", text="Following", command=lambda: self._sort_mods_by("following"))
        self.mods_tree.heading("mod_name", text="Mod", command=lambda: self._sort_mods_by("mod_name"))
        self.mods_tree.heading("game_name", text="Game", command=lambda: self._sort_mods_by("game_name"))
        self.mods_tree.heading("mod_id", text="MOD_ID", command=lambda: self._sort_mods_by("mod_id"))
        self.mods_tree.heading("download_count", text="Downloads", command=lambda: self._sort_mods_by("download_count"))
        self.mods_tree.heading("curseforge_updated_at", text="CurseForge Updated", command=lambda: self._sort_mods_by("curseforge_updated_at"))
        self.mods_tree.heading("latest_version", text="Latest Stored", command=lambda: self._sort_mods_by("latest_version"))
        self.mods_tree.heading("latest_date", text="Stored At", command=lambda: self._sort_mods_by("latest_date"))
        self.mods_tree.column("following", width=88, anchor="center")
        self.mods_tree.column("mod_name", width=240, anchor="w")
        self.mods_tree.column("game_name", width=170, anchor="w")
        self.mods_tree.column("mod_id", width=110, anchor="w")
        self.mods_tree.column("download_count", width=100, anchor="e")
        self.mods_tree.column("curseforge_updated_at", width=170, anchor="w")
        self.mods_tree.column("latest_version", width=120, anchor="w")
        self.mods_tree.column("latest_date", width=160, anchor="w")
        self.mods_tree.bind("<<TreeviewSelect>>", self._on_mod_selected)
        self.mods_tree.bind("<Button-1>", self._on_mod_tree_click, add="+")
        self.mods_tree.bind("<Button-3>", self._show_mod_context_menu)

        self.mods_tree_yscroll = ttk.Scrollbar(tracked_mods_pane, orient="vertical", command=self.mods_tree.yview)
        self.mods_tree.configure(yscrollcommand=self.mods_tree_yscroll.set)
        self.mods_tree_yscroll.grid(row=1, column=1, sticky="ns", pady=(8, 8), padx=(8, 0))
        self.mods_tree_xscroll = ttk.Scrollbar(tracked_mods_pane, orient="horizontal", command=self.mods_tree.xview)
        self.mods_tree.configure(xscrollcommand=self.mods_tree_xscroll.set)
        self.mods_tree_xscroll.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.mod_context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=CONTROL,
            fg=TEXT,
            activebackground=SELECTION,
            activeforeground=TEXT,
            relief="flat",
            borderwidth=0,
        )
        self.mod_context_menu.add_command(label="Copy MOD_ID", command=self._copy_selected_mod_id)
        self.mod_context_menu.add_command(label="Copy Release Channel ID", command=self._copy_selected_release_channel_id)
        self.mod_context_menu.add_separator()
        self.mod_context_menu.add_command(label="View Stored Versions", command=self._open_selected_versions_window)
        self.mod_context_menu.add_command(label="Forget Latest Stored Version", command=self._forget_latest_stored_version)
        self.mod_context_menu.add_separator()
        self.mod_context_menu.add_command(label="Set Specific Release Channel Override", command=self._set_selected_mod_release_channel_override)
        self.mod_context_menu.add_command(label="Clear Specific Release Channel Override", command=self._clear_selected_mod_release_channel_override)
        self.mod_context_menu.add_command(label="Set Specific Message Tag Override", command=self._set_selected_mod_message_tag_override)
        self.mod_context_menu.add_command(label="Clear Specific Message Tag Override", command=self._clear_selected_mod_message_tag_override)
        self.mod_context_menu.add_separator()
        self.mod_context_menu.add_command(label="Open CurseForge Page", command=self._open_selected_public_page)
        self.mod_context_menu.add_command(label="Open Author Files", command=self._open_selected_author_files_page)
        self.mod_context_menu.add_command(label="Open Comments", command=self._open_selected_comments_page)

        settings_panel, settings_content = self._create_panel(
            settings_tab,
            title="Settings",
            subtitle="Edit the most important runtime values stored in the environment file",
            bg=CONTROL_ALT,
        )
        settings_panel.grid(row=0, column=0, sticky="nsew")
        settings_content.columnconfigure(1, weight=1)
        ttk.Label(settings_content, text="Message Tag", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._create_entry(settings_content, textvariable=self.setting_message_tag).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(settings_content, text="Debug Channel ID", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))
        self._create_entry(settings_content, textvariable=self.setting_debug_channel_id).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(settings_content, text="Check Interval (minutes)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 8))
        self._create_entry(settings_content, textvariable=self.setting_check_interval_minutes).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(settings_content, text="Publish announcement messages", variable=self.setting_announce_messages).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Checkbutton(settings_content, text="Add reactions", variable=self.setting_add_reactions).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 12))
        tk.Label(
            settings_content,
            text="Per-game defaults",
            bg=CONTROL_ALT,
            fg=TEXT,
            font=("Segoe UI Semibold", 16),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(22, 10))
        self.game_defaults_frame = tk.Frame(settings_content, bg=CONTROL_ALT)
        self.game_defaults_frame.grid(row=6, column=0, columnspan=2, sticky="ew")
        self.game_defaults_frame.columnconfigure(1, weight=1)
        self.game_defaults_frame.columnconfigure(2, weight=1)
        self._create_button(settings_content, text="Save Settings", command=self._save_settings, accent=True).grid(row=7, column=0, sticky="w", pady=(16, 0))
        tk.Label(
            settings_content,
            text="Restart the bot after saving settings to apply them.",
            bg=CONTROL_ALT,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 0))

        stats_panel, stats_content = self._create_panel(
            stats_tab,
            title="Stats",
            subtitle="Track total downloads, likes, and quick access to mod pages",
            bg=CONTROL_ALT,
        )
        stats_panel.grid(row=0, column=0, sticky="nsew")
        stats_content.columnconfigure(0, weight=1)
        stats_content.rowconfigure(2, weight=1)
        stats_actions = tk.Frame(stats_content, bg=CONTROL_ALT)
        stats_actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._create_button(stats_actions, text="Refresh Stats", command=self._refresh_releases).pack(side="left")
        self._create_button(stats_actions, text="Open Downloads Statistics", command=self._open_author_dashboard, accent=True).pack(side="left", padx=(8, 0))

        self.stats_summary_text = tk.StringVar(value="Loading stats...")
        tk.Label(stats_content, textvariable=self.stats_summary_text, bg=CONTROL_ALT, fg=MUTED, font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.stats_tree = ttk.Treeview(
            stats_content,
            columns=("mod_name", "mod_id", "download_count", "likes", "comments_link"),
            show="headings",
            height=10,
        )
        self.stats_tree.grid(row=2, column=0, sticky="nsew")
        self.stats_tree.heading("mod_name", text="Mod")
        self.stats_tree.heading("mod_id", text="MOD_ID")
        self.stats_tree.heading("download_count", text="Downloads")
        self.stats_tree.heading("likes", text="Likes")
        self.stats_tree.heading("comments_link", text="Comments")
        self.stats_tree.column("mod_name", width=260, anchor="w")
        self.stats_tree.column("mod_id", width=100, anchor="w")
        self.stats_tree.column("download_count", width=120, anchor="e")
        self.stats_tree.column("likes", width=80, anchor="e")
        self.stats_tree.column("comments_link", width=130, anchor="center")
        self.stats_tree.bind("<Button-1>", self._on_stats_tree_click, add="+")
        self._update_mod_heading_labels()
        self._update_version_heading_labels()
        self._show_tab(self.selected_tab)

    def _apply_initial_pane_layouts(self) -> None:
        self.root.update_idletasks()

    def _manual_refresh(self) -> None:
        self._refresh_status()
        self._refresh_logs(force=True)
        self._refresh_releases()
        self._append_output("Status, logs, and releases refreshed manually.")

    def _schedule_refresh(self) -> None:
        self._refresh_status()
        self._refresh_logs()
        self.root.after(2000, self._schedule_refresh)

    def _refresh_releases(self) -> None:
        if self._release_refresh_in_progress:
            self._set_notice("Release refresh is already running.")
            return
        self._release_refresh_in_progress = True
        self._set_notice("Refreshing CurseForge release data...")
        thread = threading.Thread(target=self._refresh_releases_worker, daemon=True)
        thread.start()

    def _refresh_releases_worker(self) -> None:
        try:
            summaries = manager_service.list_tracked_releases()
        except Exception as exc:
            self.events.put(("release_error", str(exc)))
            return
        self.events.put(("release_summaries", summaries))

    def _apply_release_summaries(self, summaries: list[manager_service.ModReleaseSummary]) -> None:
        previous_mod = self._selected_mod_id()
        self.release_summaries = self._sorted_release_summaries(summaries)

        for item in self.mods_tree.get_children():
            self.mods_tree.delete(item)

        for summary in self.release_summaries:
            self.mods_tree.insert(
                "",
                tk.END,
                iid=f"mod:{summary.mod_id}",
                values=(
                    "\u2611" if summary.following else "\u2610",
                    summary.mod_name,
                    summary.game_name,
                    summary.mod_id,
                    summary.download_count,
                    self._format_curseforge_date(summary.curseforge_updated_at),
                    summary.latest_version,
                    summary.latest_date,
                ),
            )

        if previous_mod and any(summary.mod_id == previous_mod for summary in self.release_summaries):
            self.mods_tree.selection_set(f"mod:{previous_mod}")
        elif self.release_summaries:
            self.mods_tree.selection_set(f"mod:{self.release_summaries[0].mod_id}")

        self._render_game_defaults()
        self._refresh_stats_view()
        self._set_notice(f"Loaded {len(self.release_summaries)} tracked mods.")

    def _refresh_stats_view(self) -> None:
        tracked_mod_count = len(self.release_summaries)
        following_mod_count = sum(1 for summary in self.release_summaries if summary.following)
        total_downloads = sum(summary.download_count for summary in self.release_summaries)
        total_likes = sum(summary.thumbs_up_count for summary in self.release_summaries)
        self.stats_summary_text.set(
            f"Tracked mods: {tracked_mod_count} | Following: {following_mod_count} | "
            f"Total downloads: {total_downloads} | Total likes: {total_likes}"
        )

        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)

        for summary in self.release_summaries:
            self.stats_tree.insert(
                "",
                tk.END,
                iid=f"stats:{summary.mod_id}",
                values=(
                    summary.mod_name,
                    summary.mod_id,
                    summary.download_count,
                    summary.thumbs_up_count,
                    "Open comments",
                ),
            )

    def _on_mod_selected(self, _event=None) -> None:
        return

    def _render_game_defaults(self) -> None:
        if self.game_defaults_frame is None:
            return

        for child in self.game_defaults_frame.winfo_children():
            child.destroy()

        unique_games: dict[str, str] = {}
        for summary in self.release_summaries:
            if summary.game_id:
                unique_games[summary.game_id] = summary.game_name

        if not unique_games:
            tk.Label(
                self.game_defaults_frame,
                text="No games detected yet from tracked mods.",
                bg=CONTROL_ALT,
                fg=MUTED,
                font=("Segoe UI", 10),
            ).grid(row=0, column=0, sticky="w")
            return

        current_game_channels = manager_service.get_game_release_channel_ids()
        current_game_tags = manager_service.get_game_message_tags()

        for game_id, game_name in sorted(unique_games.items(), key=lambda item: item[1].lower()):
            self.game_name_by_id[game_id] = game_name
            if game_id not in self.game_release_channel_vars:
                self.game_release_channel_vars[game_id] = tk.StringVar(value=current_game_channels.get(game_id, ""))
            if game_id not in self.game_message_tag_vars:
                self.game_message_tag_vars[game_id] = tk.StringVar(value=current_game_tags.get(game_id, ""))

        active_game_ids = set(unique_games)
        self.game_release_channel_vars = {
            game_id: var for game_id, var in self.game_release_channel_vars.items() if game_id in active_game_ids
        }
        self.game_message_tag_vars = {
            game_id: var for game_id, var in self.game_message_tag_vars.items() if game_id in active_game_ids
        }

        tk.Label(
            self.game_defaults_frame,
            text="Game",
            bg=CONTROL_ALT,
            fg=MUTED,
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(
            self.game_defaults_frame,
            text="Release Channel ID",
            bg=CONTROL_ALT,
            fg=MUTED,
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=1, sticky="w", padx=(8, 18), pady=(0, 8))
        tk.Label(
            self.game_defaults_frame,
            text="Message Tag",
            bg=CONTROL_ALT,
            fg=MUTED,
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=2, sticky="w", padx=(0, 8), pady=(0, 8))

        for row, (game_id, game_name) in enumerate(sorted(unique_games.items(), key=lambda item: item[1].lower()), start=1):
            tk.Label(
                self.game_defaults_frame,
                text=f"{game_name} ({game_id})",
                bg=CONTROL_ALT,
                fg=TEXT,
                font=("Segoe UI Semibold", 10),
            ).grid(row=row, column=0, sticky="w", pady=(0, 8))
            self._create_entry(
                self.game_defaults_frame,
                textvariable=self.game_release_channel_vars[game_id],
                width=22,
            ).grid(row=row, column=1, sticky="ew", padx=(8, 18), pady=(0, 8))
            self._create_entry(
                self.game_defaults_frame,
                textvariable=self.game_message_tag_vars[game_id],
                width=28,
            ).grid(row=row, column=2, sticky="ew", padx=(0, 0), pady=(0, 8))

    def _on_mod_tree_click(self, event):
        row_id = self.mods_tree.identify_row(event.y)
        column_id = self.mods_tree.identify_column(event.x)
        if not row_id or column_id != "#1":
            return None

        self.mods_tree.selection_set(row_id)
        self.mods_tree.focus(row_id)
        self._toggle_selected_mod_following()
        return "break"

    def _on_stats_tree_click(self, event):
        row_id = self.stats_tree.identify_row(event.y)
        column_id = self.stats_tree.identify_column(event.x)
        if not row_id or column_id != "#5":
            return None

        self.stats_tree.selection_set(row_id)
        parts = row_id.split(":", 1)
        if len(parts) != 2:
            return None

        mod_id = parts[1]
        for summary in self.release_summaries:
            if summary.mod_id == mod_id:
                if summary.comments_url:
                    os.startfile(summary.comments_url)
                else:
                    self._append_output("No comments page is available for the selected mod.")
                break
        return "break"

    def _selected_mod_id(self) -> str | None:
        selection = self.mods_tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        if item_id.startswith("mod:"):
            return item_id.split(":", 1)[1]
        return None

    def _selected_summary(self) -> manager_service.ModReleaseSummary | None:
        selected_mod = self._selected_mod_id()
        if selected_mod is None:
            return None
        for summary in self.release_summaries:
            if summary.mod_id == selected_mod:
                return summary
        return None

    def _format_curseforge_date(self, value: str) -> str:
        if not value:
            return "-"
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value.replace("T", " ")[:16]

    def _shorten_log_line(self, line: str, max_length: int = 110) -> str:
        if not line:
            return "-"
        shortened = line.split(" - ", 2)[-1] if " - " in line else line
        return shortened if len(shortened) <= max_length else shortened[: max_length - 3] + "..."

    def _sort_key_curseforge_date(self, summary: manager_service.ModReleaseSummary):
        value = summary.curseforge_updated_at
        if not value:
            return datetime.min
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.min

    def _heading_text(self, base_label: str, active: bool, direction: str | None) -> str:
        if not active or direction is None:
            return base_label
        if direction == "asc":
            return f"{base_label}{SORT_ARROW_ASC}"
        return f"{base_label}{SORT_ARROW_DESC}"

    def _update_mod_heading_labels(self) -> None:
        for column, label in MOD_COLUMN_LABELS.items():
            self.mods_tree.heading(
                column,
                text=self._heading_text(label, self.mod_sort_column == column, self.mod_sort_direction),
            )

    def _update_version_heading_labels(self) -> None:
        return

    def _next_sort_direction(self, current_column: str | None, current_direction: str | None, column: str) -> tuple[str | None, str | None]:
        if current_column != column:
            return column, "asc"
        if current_direction == "asc":
            return column, "desc"
        if current_direction == "desc":
            return None, None
        return column, "asc"

    def _sorted_release_summaries(self, summaries: list[manager_service.ModReleaseSummary]) -> list[manager_service.ModReleaseSummary]:
        if self.mod_sort_column is None or self.mod_sort_direction is None:
            return list(summaries)

        def key(summary: manager_service.ModReleaseSummary):
            if self.mod_sort_column == "following":
                return 1 if summary.following else 0
            if self.mod_sort_column == "mod_name":
                return summary.mod_name.lower()
            if self.mod_sort_column == "game_name":
                return summary.game_name.lower()
            if self.mod_sort_column == "mod_id":
                return int(summary.mod_id) if summary.mod_id.isdigit() else summary.mod_id
            if self.mod_sort_column == "download_count":
                return summary.download_count
            if self.mod_sort_column == "curseforge_updated_at":
                return self._sort_key_curseforge_date(summary)
            if self.mod_sort_column == "latest_version":
                return int(summary.latest_version) if summary.latest_version.isdigit() else summary.latest_version
            if self.mod_sort_column == "latest_date":
                return summary.latest_date
            return summary.mod_name.lower()

        return sorted(summaries, key=key, reverse=self.mod_sort_direction == "desc")

    def _sort_mods_by(self, column: str) -> None:
        self.mod_sort_column, self.mod_sort_direction = self._next_sort_direction(
            self.mod_sort_column,
            self.mod_sort_direction,
            column,
        )
        self._update_mod_heading_labels()
        self._save_ui_state()
        self._apply_release_summaries(self.release_summaries)

    def _sorted_versions(self, versions: list[manager_service.ReleaseRecord]) -> list[manager_service.ReleaseRecord]:
        if self.version_sort_column is None or self.version_sort_direction is None:
            return list(versions)

        def key(record: manager_service.ReleaseRecord):
            if self.version_sort_column == "version":
                return int(record.version) if record.version.isdigit() else record.version
            return record.release_date

        return sorted(versions, key=key, reverse=self.version_sort_direction == "desc")

    def _sort_versions_by(self, column: str) -> None:
        self.version_sort_column, self.version_sort_direction = self._next_sort_direction(
            self.version_sort_column,
            self.version_sort_direction,
            column,
        )
        self._save_ui_state()

    def _confirm_once(self, key: str, message: str) -> bool:
        now = time.time()
        expires_at = self.pending_confirmations.get(key, 0.0)
        if expires_at > now:
            self.pending_confirmations.pop(key, None)
            return True
        self.pending_confirmations[key] = now + CONFIRMATION_WINDOW_SECONDS
        self._set_notice(f"{message} Click again within {int(CONFIRMATION_WINDOW_SECONDS)} seconds to confirm.")
        return False

    def _toggle_selected_mod_following(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return

        new_following_state = not summary.following

        def task() -> None:
            updated = manager_service.set_mod_following(summary.mod_id, new_following_state)
            if updated:
                state_label = "enabled" if new_following_state else "disabled"
                self.events.put(("output", f"Following {state_label} for {summary.mod_name} ({summary.mod_id})."))
                self.events.put(("toast", ("Releases", f"Following {state_label} for {summary.mod_name}. Restart the bot to apply it.")))
            else:
                raise RuntimeError("The selected mod is no longer configured.")

        self._run_action("Toggle Following", task)

    def _copy_to_clipboard(self, value: str) -> None:
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()

    def _copy_selected_mod_id(self) -> None:
        selected_mod = self._selected_mod_id()
        if not selected_mod:
            self._append_output("Select a mod first.")
            return
        self._copy_to_clipboard(selected_mod)
        self._set_notice(f"Copied MOD_ID: {selected_mod}")

    def _copy_selected_release_channel_id(self) -> None:
        summary = self._selected_summary()
        if summary is None or not summary.release_channel_id:
            self._append_output("No release channel ID is available for the selected mod.")
            return
        self._copy_to_clipboard(summary.release_channel_id)
        self._set_notice(f"Copied release channel ID: {summary.release_channel_id}")

    def _set_selected_mod_release_channel_override(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return

        value = simpledialog.askstring(
            "Specific Release Channel Override",
            f"Release channel override for {summary.mod_name} ({summary.mod_id}):",
            initialvalue=summary.release_channel_override or summary.release_channel_id,
            parent=self.root,
        )
        if value is None:
            return
        release_channel_id = value.strip()
        if not release_channel_id:
            self._append_output("Release channel override cannot be empty. Use clear override instead.")
            return

        def task() -> None:
            updated = manager_service.set_mod_release_channel_override(summary.mod_id, release_channel_id)
            if not updated:
                raise RuntimeError("The selected mod is no longer configured.")
            self.events.put(("output", f"Specific release channel override set for {summary.mod_name} ({summary.mod_id}) -> {release_channel_id}."))
            self.events.put(("toast", ("Releases", f"Specific release channel override saved for {summary.mod_name}. Restart the bot to apply it.")))

        self._run_action("Set Mod Release Channel Override", task)

    def _clear_selected_mod_release_channel_override(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return

        def task() -> None:
            updated = manager_service.clear_mod_release_channel_override(summary.mod_id)
            if not updated:
                raise RuntimeError("The selected mod is no longer configured.")
            self.events.put(("output", f"Specific release channel override cleared for {summary.mod_name} ({summary.mod_id})."))
            self.events.put(("toast", ("Releases", f"Specific release channel override cleared for {summary.mod_name}. Restart the bot to apply it.")))

        self._run_action("Clear Mod Release Channel Override", task)

    def _set_selected_mod_message_tag_override(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return

        value = simpledialog.askstring(
            "Specific Message Tag Override",
            f"Message tag override for {summary.mod_name} ({summary.mod_id}):",
            initialvalue=summary.message_tag_override or summary.message_tag,
            parent=self.root,
        )
        if value is None:
            return
        message_tag = value.strip()
        if not message_tag:
            self._append_output("Message tag override cannot be empty. Use clear override instead.")
            return

        def task() -> None:
            updated = manager_service.set_mod_message_tag(summary.mod_id, message_tag)
            if not updated:
                raise RuntimeError("The selected mod is no longer configured.")
            self.events.put(("output", f"Specific message tag override set for {summary.mod_name} ({summary.mod_id}) -> {message_tag}."))
            self.events.put(("toast", ("Releases", f"Specific message tag override saved for {summary.mod_name}. Restart the bot to apply it.")))

        self._run_action("Set Mod Message Tag Override", task)

    def _clear_selected_mod_message_tag_override(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return

        def task() -> None:
            updated = manager_service.set_mod_message_tag(summary.mod_id, "")
            if not updated:
                raise RuntimeError("The selected mod is no longer configured.")
            self.events.put(("output", f"Specific message tag override cleared for {summary.mod_name} ({summary.mod_id})."))
            self.events.put(("toast", ("Releases", f"Specific message tag override cleared for {summary.mod_name}. Restart the bot to apply it.")))

        self._run_action("Clear Mod Message Tag Override", task)

    def _use_selected_release_channel_id(self) -> None:
        summary = self._selected_summary()
        if summary is None or not summary.release_channel_id:
            self._append_output("No release channel ID is available for the selected mod.")
            return
        self.new_release_channel_id.set(summary.release_channel_id)
        self._set_notice(f"Filled release channel ID: {summary.release_channel_id}")

    def _open_selected_public_page(self) -> None:
        summary = self._selected_summary()
        if summary is None or not summary.public_url:
            self._append_output("No public CurseForge page is available for the selected mod.")
            return
        os.startfile(summary.public_url)

    def _open_selected_author_files_page(self) -> None:
        summary = self._selected_summary()
        if summary is None or not summary.author_files_url:
            self._append_output("No author files page is available for the selected mod.")
            return
        os.startfile(summary.author_files_url)

    def _open_selected_comments_page(self) -> None:
        summary = self._selected_summary()
        if summary is None or not summary.comments_url:
            self._append_output("No comments page is available for the selected mod.")
            return
        os.startfile(summary.comments_url)

    def _open_author_dashboard(self) -> None:
        os.startfile(AUTHOR_DASHBOARD_URL)

    def _show_mod_context_menu(self, event) -> None:
        row_id = self.mods_tree.identify_row(event.y)
        if not row_id:
            return
        self.mods_tree.selection_set(row_id)
        self.mods_tree.focus(row_id)
        try:
            self.mod_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.mod_context_menu.grab_release()

    def _open_selected_versions_window(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return
        if not summary.versions:
            self._append_output(f"No stored versions are available for {summary.mod_name}.")
            return

        window = tk.Toplevel(self.root)
        window.title(f"Stored versions - {summary.mod_name}")
        window.configure(bg=BG)
        window.transient(self.root)
        window.geometry("760x520")
        window.minsize(560, 360)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        outer, content = self._create_panel(
            window,
            title=f"Stored versions for {summary.mod_name}",
            subtitle="Review saved versions or forget one stored version",
            bg=CONTROL_ALT,
        )
        outer.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        actions = tk.Frame(content, bg=CONTROL_ALT)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        versions_tree = ttk.Treeview(
            content,
            columns=("version", "release_date"),
            show="headings",
            height=12,
        )
        versions_tree.grid(row=1, column=0, sticky="nsew")
        versions_tree.heading("version", text="Version")
        versions_tree.heading("release_date", text="Stored At")
        versions_tree.column("version", width=180, anchor="w")
        versions_tree.column("release_date", width=220, anchor="w")
        versions_xscroll = ttk.Scrollbar(content, orient="horizontal", command=versions_tree.xview)
        versions_tree.configure(xscrollcommand=versions_xscroll.set)
        versions_xscroll.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        for record in self._sorted_versions(summary.versions):
            versions_tree.insert("", tk.END, iid=f"version:{record.version}", values=(record.version, record.release_date))

        def forget_selected_from_window() -> None:
            selection = versions_tree.selection()
            if not selection:
                self._append_output("Select a stored version first.")
                return
            item_id = selection[0]
            selected_version = item_id.split(":", 1)[1]
            window.destroy()
            self._forget_release_for_mod_version(summary.mod_id, summary.mod_name, selected_version)

        self._create_button(actions, text="Forget Selected Version", command=forget_selected_from_window).pack(side="left")

    def _forget_release_for_mod_version(self, mod_id: str, mod_name: str, version: str) -> None:
        if not self._confirm_once("forget_release", f"Forget stored version {version} for mod {mod_id}?"):
            return

        def task() -> None:
            deleted = manager_service.forget_release(mod_id, version)
            if deleted:
                self.events.put(("output", f"Forgot stored version {version} for mod {mod_name} ({mod_id})."))
                self.events.put(("toast", ("Releases", f"Version {version} forgotten for mod {mod_name}.")))
            else:
                raise RuntimeError("The selected stored version was not found.")

        self._run_action("Forget Release", task)

    def _forget_latest_stored_version(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            self._append_output("Select a mod first.")
            return
        if not summary.versions:
            self._append_output(f"No stored versions are available for {summary.mod_name}.")
            return
        latest = self._sorted_versions(summary.versions)[0]
        self._forget_release_for_mod_version(summary.mod_id, summary.mod_name, latest.version)

    def _start_control_server(self) -> None:
        thread = threading.Thread(target=self._control_server_worker, daemon=True)
        thread.start()

    def _control_server_worker(self) -> None:
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((manager_service.MANAGER_CONTROL_HOST, manager_service.MANAGER_CONTROL_PORT))
            server.listen(1)
            server.settimeout(0.5)
            self._control_server_socket = server
        except OSError:
            return

        while not self._control_stop_event.is_set():
            try:
                connection, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with connection:
                try:
                    message = connection.recv(32).decode("utf-8", errors="ignore").strip().lower()
                except OSError:
                    message = ""
                if message == "exit":
                    self.root.after(0, self._close_from_remote_request)
                    break

        try:
            server.close()
        except OSError:
            pass

    def _close_from_remote_request(self) -> None:
        self._set_notice("Closing previous manager window because a new one was opened.")
        self._on_close()

    def _on_close(self) -> None:
        self._save_window_geometry()
        self._save_ui_state()
        self._control_stop_event.set()
        if self._control_server_socket is not None:
            try:
                self._control_server_socket.close()
            except OSError:
                pass
            self._control_server_socket = None
        self.root.destroy()

    def _refresh_status(self) -> None:
        status = manager_service.get_status()
        self.status_text.set("Running" if status.running else "Stopped")
        self.pid_text.set(str(status.pid) if status.pid is not None else "-")
        self.venv_text.set("Ready" if status.venv_ready else "Missing")
        self.log_text.set(f"Ready ({status.log_size} bytes)" if status.log_exists else "No log file")
        self.db_text.set("Present" if status.releases_db_exists else "Missing")
        self.following_count_text.set(f"{status.following_mod_count} / {status.tracked_mod_count}")
        self.last_check_text.set(status.last_check_completed or status.last_check_started or "-")
        self.last_release_text.set(self._shorten_log_line(status.last_release_sent))
        self.last_error_text.set(self._shorten_log_line(status.last_error))

    def _refresh_logs(self, force: bool = False) -> None:
        signature = (manager_service.LOG_FILE.exists(), manager_service.LOG_FILE.stat().st_size if manager_service.LOG_FILE.exists() else 0)
        if not force and signature == self.last_log_signature:
            return

        content = manager_service.read_log_tail()
        if not force and content == self.last_log_snapshot:
            self.last_log_signature = signature
            return

        previous_release_count = self.last_log_snapshot.count(RELEASE_SENT_MARKER)
        current_release_count = content.count(RELEASE_SENT_MARKER)
        self.last_log_signature = signature
        self.last_log_snapshot = content

        if force or self.follow_logs.get():
            self.logs_view.configure(state="normal")
            self.logs_view.delete("1.0", tk.END)
            self.logs_view.insert(tk.END, content or "No log file yet.")
            self.logs_view.see(tk.END)
            self.logs_view.configure(state="disabled")

        if current_release_count > previous_release_count:
            self._refresh_status()
            self._refresh_releases()

    def _clear_log_view(self) -> None:
        self.last_log_snapshot = ""
        self.logs_view.configure(state="normal")
        self.logs_view.delete("1.0", tk.END)
        self.logs_view.configure(state="disabled")

    def _append_output(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_view.configure(state="normal")
        self.output_view.insert(tk.END, f"[{timestamp}] {message}\n")
        self.output_view.see(tk.END)
        self.output_view.configure(state="disabled")

    def _set_notice(self, message: str) -> None:
        self.notice_text.set(message)

    def _run_action(self, title: str, action) -> None:
        if not self.action_lock.acquire(blocking=False):
            self._append_output("Another action is already running. Wait for it to finish.")
            return
        thread = threading.Thread(target=self._action_worker, args=(title, action), daemon=True)
        thread.start()

    def _action_worker(self, title: str, action) -> None:
        self.events.put(("output", f"{title} started."))
        try:
            action()
        except Exception as exc:
            self.events.put(("output", f"{title} failed: {exc}"))
            self.events.put(("toast", ("Error", f"{title} failed.\n{exc}")))
        finally:
            self.action_lock.release()
            self.events.put(("refresh", ""))

    def _process_events(self) -> None:
        while True:
            try:
                event_type, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "output":
                self._append_output(str(payload))
            elif event_type == "refresh":
                self._refresh_status()
                self._refresh_logs(force=True)
                self._refresh_releases()
            elif event_type == "release_summaries":
                self._release_refresh_in_progress = False
                self._apply_release_summaries(payload)  # type: ignore[arg-type]
            elif event_type == "release_error":
                self._release_refresh_in_progress = False
                message = str(payload)
                self._append_output(f"Release refresh failed: {message}")
                self._set_notice(f"Release refresh failed: {message}")
            elif event_type == "toast":
                title, message = payload  # type: ignore[misc]
                self._set_notice(f"{title}: {message}")
            elif event_type == "clear_add_inputs":
                self.new_mod_id.set("")

        self.root.after(200, self._process_events)

    def _setup_environment(self) -> None:
        def task() -> None:
            code = manager_service.setup_environment(lambda line: self.events.put(("output", line)))
            if code == 0:
                self.events.put(("output", "Setup completed successfully."))
                self.events.put(("toast", ("Setup", "Setup completed.")))
            else:
                raise RuntimeError(f"Setup returned exit code {code}.")

        self._run_action("Setup", task)

    def _start_bot(self) -> None:
        def task() -> None:
            pid = manager_service.start_bot()
            self.events.put(("output", f"Bot started with PID {pid}."))
            self.events.put(("toast", ("Bot", f"Bot started.\nPID: {pid}")))

        self._run_action("Start", task)

    def _stop_bot(self) -> None:
        def task() -> None:
            stopped = manager_service.stop_bot()
            message = "Bot stopped." if stopped else "Bot was already stopped."
            self.events.put(("output", message))
            self.events.put(("toast", ("Bot", message)))

        self._run_action("Stop", task)

    def _restart_bot(self) -> None:
        def task() -> None:
            pid = manager_service.restart_bot()
            self.events.put(("output", f"Bot restarted with PID {pid}."))
            self.events.put(("toast", ("Bot", f"Bot restarted.\nPID: {pid}")))

        self._run_action("Restart", task)

    def _check_now(self) -> None:
        def task() -> None:
            code = manager_service.run_update_check_once(lambda line: self.events.put(("output", line)))
            if code == 0:
                self.events.put(("output", "One-time update check completed successfully."))
                self.events.put(("toast", ("Bot", "One-time update check completed.")))
            else:
                raise RuntimeError(f"Check now returned exit code {code}.")

        self._run_action("Check Now", task)

    def _restart_app(self) -> None:
        launcher_path = manager_service.ROOT_DIR / "tools" / "bot-manager.bat"
        if not launcher_path.exists():
            self._append_output("App launcher was not found.")
            return

        try:
            os.startfile(str(launcher_path))
            self._set_notice("Restarting app...")
            self.root.after(150, self._on_close)
        except OSError as exc:
            self._append_output(f"Failed to restart app: {exc}")

    def _test_debug(self) -> None:
        def task() -> None:
            code = manager_service.send_debug_test(lambda line: self.events.put(("output", line)))
            if code == 0:
                self.events.put(("output", "Debug test sent successfully."))
                self.events.put(("toast", ("Debug Test", "Debug test sent.")))
            else:
                raise RuntimeError(f"Debug test returned exit code {code}.")

        self._run_action("Test Debug", task)

    def _test_latest_release(self) -> None:
        def task() -> None:
            code = manager_service.send_latest_release_test(lambda line: self.events.put(("output", line)))
            if code == 0:
                self.events.put(("output", "Latest release test sent successfully."))
                self.events.put(("toast", ("Test Release", "Test release sent.")))
            else:
                raise RuntimeError(f"Latest release test returned exit code {code}.")

        self._run_action("Test Release", task)

    def _save_settings(self) -> None:
        def task() -> None:
            manager_service.save_editable_settings(
                manager_service.EditableSettings(
                    message_tag=self.setting_message_tag.get().strip(),
                    debug_channel_id=self.setting_debug_channel_id.get().strip(),
                    announce_messages=self.setting_announce_messages.get(),
                    add_reactions=self.setting_add_reactions.get(),
                    check_interval_minutes=self.setting_check_interval_minutes.get().strip(),
                )
            )
            manager_service.save_game_defaults(
                {game_id: var.get().strip() for game_id, var in self.game_release_channel_vars.items()},
                {game_id: var.get().strip() for game_id, var in self.game_message_tag_vars.items()},
            )
            self.events.put(("output", "Settings saved."))
            self.events.put(("toast", ("Settings", "Settings saved. Restart the bot to apply them.")))

        self._run_action("Save Settings", task)

    def _add_mod(self) -> None:
        mod_id = self.new_mod_id.get().strip()
        if not mod_id:
            self._append_output("Enter a MOD_ID first.")
            return

        def task() -> None:
            mod_name = manager_service.add_tracked_mod(mod_id, None)
            self.events.put(("clear_add_inputs", ""))
            self.events.put(("output", f"Added mod {mod_name} ({mod_id})."))
            self.events.put(("toast", ("Releases", f"Added mod {mod_name} ({mod_id}). Restart the bot to apply it.")))

        self._run_action("Add Mod", task)

    def _remove_selected_mod(self) -> None:
        selected_mod = self._selected_mod_id()
        if not selected_mod:
            self._append_output("Select a mod first.")
            return

        summary = self._selected_summary()
        mod_label = summary.mod_name if summary is not None else selected_mod
        if not self._confirm_once("remove_mod", f"Remove {mod_label} ({selected_mod}) from tracking?"):
            return

        def task() -> None:
            removed = manager_service.remove_tracked_mod(selected_mod)
            if removed:
                self.events.put(("output", f"Removed mod {mod_label} ({selected_mod}) from tracking."))
                self.events.put(("toast", ("Releases", f"Removed mod {mod_label} ({selected_mod}). Restart the bot to apply it.")))
            else:
                raise RuntimeError("The selected mod is no longer configured.")

        self._run_action("Remove Mod", task)

    def _forget_selected_version(self) -> None:
        self._open_selected_versions_window()

    def _send_selected_release(self) -> None:
        self._send_selected_release_to("release")

    def _send_selected_release_to_debug(self) -> None:
        self._send_selected_release_to("debug")

    def _send_selected_release_to(self, target: str) -> None:
        selected_mod = self._selected_mod_id()
        if not selected_mod:
            self._append_output("Select a mod first.")
            return
        if target == "release" and not self._confirm_once(
            "send_release",
            f"Send the latest release again to the release channel for MOD_ID {selected_mod}?",
        ):
            return

        def task() -> None:
            code = manager_service.send_latest_release_for_mod(
                selected_mod,
                target,
                lambda line: self.events.put(("output", line)),
            )
            if code == 0:
                self.events.put(("output", f"Latest release for mod {selected_mod} sent to {target}."))
                self.events.put(("toast", ("Releases", f"Latest release sent to {target} for mod {selected_mod}.")))
            else:
                raise RuntimeError(f"Send latest release for mod {selected_mod} returned exit code {code}.")

        self._run_action(f"Send Latest {target.title()}", task)

    def _open_log(self) -> None:
        log_path = manager_service.LOG_FILE
        if not log_path.exists():
            self._append_output("No log file to open yet.")
            return

        os.startfile(str(log_path))

    def _open_project_folder(self) -> None:
        os.startfile(str(manager_service.ROOT_DIR))


def main() -> None:
    if manager_service.request_existing_manager_shutdown():
        time.sleep(0.6)

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass

    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "clam" in style.theme_names():
        style.theme_use("clam")

    BotManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

