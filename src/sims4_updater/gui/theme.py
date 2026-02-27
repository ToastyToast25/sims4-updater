"""
Theme constants for the Sims 4 Updater GUI.
"""

# Color palette
COLORS = {
    "bg_dark": "#1a1a2e",
    "bg_sidebar": "#16213e",
    "bg_card": "#0f3460",
    "bg_card_alt": "#0a2a50",
    "accent": "#e94560",
    "accent_hover": "#ff6b81",
    "text": "#eaeaea",
    "text_muted": "#a0a0b0",
    "success": "#2ed573",
    "warning": "#ffa502",
    "error": "#ff4757",
    "border": "#2a2a4a",
    "separator": "#1a3a6a",
    # Depth levels
    "bg_deeper": "#0d1526",
    "bg_surface": "#1a2744",
    # Accent variants
    "accent_glow": "#e94560",
    "accent_subtle": "#2a1a2e",
    # Hover states
    "card_hover": "#143a6e",
    "sidebar_hover": "#1a3050",
    "text_dim": "#6a6a8a",
    # Gradient endpoints
    "gradient_start": "#0f3460",
    "gradient_end": "#1a1a2e",
    # Toast backgrounds
    "toast_success": "#1a3d2a",
    "toast_warning": "#3d2a1a",
    "toast_error": "#3d1a1a",
    "toast_info": "#1a2a3d",
    # Pack type colors
    "pack_expansion": "#e94560",
    "pack_game": "#ffa502",
    "pack_stuff": "#2ed573",
    "pack_kit": "#a0a0b0",
    "pack_free": "#70a1ff",
    "pack_other": "#6a6a8a",
    # Button hover variants
    "hover_success": "#3ae882",
    "hover_warning": "#cc8400",
    "hover_error": "#cc3944",
    "hover_cancel": "#ff6b6b",
    # Status extras
    "status_ready": "#5b9bd5",
    "status_ready_bg": "#1a2a3d",
    # Bright text / button foregrounds
    "text_bright": "#ffffff",
    "btn_white": "#ffffff",
    "btn_white_hover": "#e0e0e0",
    # Progress bar
    "progress_track": "#4a1a2a",
    # Steam-branded
    "steam_bg": "#1b2838",
    "steam_hover": "#2a475e",
    "steam_text": "#c7d5e0",
    # Skeleton loading
    "skeleton_base": "#1a2744",
    "skeleton_shimmer": "#243556",
}

# Button style presets — unpack into CTkButton(..., **BUTTON_STYLES["primary"])
BUTTON_STYLES = {
    "primary": {"fg_color": COLORS["accent"], "hover_color": COLORS["accent_hover"]},
    "success": {
        "fg_color": COLORS["success"],
        "hover_color": COLORS["hover_success"],
        "text_color": COLORS["bg_dark"],
    },
    "danger": {"fg_color": COLORS["error"], "hover_color": COLORS["hover_error"]},
    "warning": {"fg_color": COLORS["warning"], "hover_color": COLORS["hover_warning"]},
    "ghost": {
        "fg_color": "transparent",
        "hover_color": COLORS["card_hover"],
        "border_width": 1,
        "border_color": COLORS["border"],
    },
    "secondary": {
        "fg_color": COLORS["bg_card_alt"],
        "hover_color": COLORS["card_hover"],
    },
    "steam": {
        "fg_color": COLORS["steam_bg"],
        "hover_color": COLORS["steam_hover"],
        "text_color": COLORS["steam_text"],
    },
}

# Sidebar
SIDEBAR_WIDTH = 180
SIDEBAR_BTN_HEIGHT = 38

# Standardized sizing
CORNER_RADIUS = 10
CORNER_RADIUS_SMALL = 6
BUTTON_HEIGHT = 38
BUTTON_HEIGHT_SMALL = 30
CARD_PAD_X = 18
CARD_PAD_Y = 14
CARD_ROW_PAD = 6
SECTION_PAD = 30
SECTION_GAP = 15

# Spacing scale (4px base)
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 30

# Fonts (family, size, weight)
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_HEADING = ("Segoe UI", 15, "bold")
FONT_BODY = ("Segoe UI", 12)
FONT_BODY_BOLD = ("Segoe UI", 12, "bold")
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 10)

# Navigation icons (Unicode)
NAV_ICONS = {
    "home": "\u2302",  # ⌂
    "dlc": "\u25a6",  # ▦
    "downloader": "\u2913",  # ⤓
    "unlocker": "\u26bf",  # ⚿
    "language": "\u2637",  # ☷
    "events": "\u2605",  # ★
    "settings": "\u2699",  # ⚙
    "packer": "\u2750",  # ❐
    "greenluma": "\u2618",  # ☘
    "mods": "\u2692",  # ⚒
    "diagnostics": "\u2695",  # ⚕
    "progress": "\u21bb",  # ↻
}

# Animation timing (ms)
ANIM_FAST = 150
ANIM_NORMAL = 250
ANIM_SLOW = 400
ANIM_STAGGER = 80
TOAST_DURATION = 3000
TOAST_SLIDE_MS = 300

# Window
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 600
MIN_WIDTH = 750
MIN_HEIGHT = 500
