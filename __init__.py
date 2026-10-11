# Berry Anki Add-on
# Main entry point for the add-on.

import os
import re
from typing import Dict
import copy
import colorsys

from aqt import mw, gui_hooks
from aqt.qt import QColor, QPalette

from . import utils, settings
from . import bento_integration
from .settings import DEFAULT_CONFIG

ADDON_PACKAGE = mw.addonManager.addonFromModule(__name__)
ADDON_PATH = os.path.dirname(__file__)

# --- Configuration Management ---
addon_config = {}

def load_config():
    """Load configuration, merging defaults with user's settings."""
    global addon_config
    config = copy.deepcopy(DEFAULT_CONFIG)
    user_config = mw.addonManager.getConfig(__name__) or {}

    # Recursively update the default config with user's settings
    def update_dict(d, u):
        for k, v in u.items():
            if isinstance(v, dict):
                r = d.get(k, {})
                if isinstance(r, dict):
                    d[k] = update_dict(r, v)
                else:
                    d[k] = v 
            else:
                d[k] = v
        return d
    
    addon_config = update_dict(config, user_config)

# Initial load of the configuration
load_config()


def get_icons() -> Dict[str, str]:
    """Loads all SVG icons from the 'icons' folder."""
    icons_dir = os.path.join(ADDON_PATH, "icons")
    icons = {}
    if not os.path.isdir(icons_dir):
        return {}
        
    for filename in os.listdir(icons_dir):
        if filename.endswith(".svg"):
            icon_name = os.path.splitext(filename)[0]
            try:
                with open(os.path.join(icons_dir, filename), 'r', encoding='utf-8') as f:
                    icons[icon_name] = f.read()
            except Exception as e:
                print(f"Berry: Error loading icon '{filename}': {e}")
    return icons

def hex_to_rgba(hex_color: str, alpha_percent: int) -> str:
    """Converts a hex color string to an rgba string with a given opacity."""
    hex_color = hex_color.lstrip('#')
    if not re.match(r"^[0-9a-fA-F]{6}$", hex_color):
        return "rgba(0,0,0,0.85)" # Return a default if hex is invalid
    
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha_percent / 100:.2f})"


def darken_color(color_str: str, factor: float = 0.7) -> str:
    """Returns a darker version of a hex or rgba color string.
    factor < 1 darkens, factor > 1 lightens."""
    # Parse the color to RGB components
    r, g, b = 0, 0, 0
    if color_str.startswith("rgba"):
        try:
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            return "#000000"
    elif color_str.startswith("#"):
        hex_c = color_str.lstrip('#')
        if re.match(r"^[0-9a-fA-F]{6}$", hex_c):
            r, g, b = (int(hex_c[i:i+2], 16) for i in (0, 2, 4))
        else:
            return "#000000"
    else:
        return "#000000"

    # Convert to HLS, reduce lightness, convert back
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = max(0, l * factor)
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(nr * 255):02x}{int(ng * 255):02x}{int(nb * 255):02x}"


def resolve_is_dark_mode(theme_setting: str) -> bool:
    """Resolves the "theme" config value (system/light/dark) to an actual
    dark/light bool, following the real Anki theme for "system"."""
    if theme_setting == "system":
        try:
            return mw.style().is_dark()
        except AttributeError:
            return mw.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
    return theme_setting == "dark"


def generate_css(is_dark: bool, config=None) -> str:
    """Builds the widget's CSS (color variables + widget.css + sizing) for
    the given theme/config. Used by both the real deck-browser render and
    the settings-dialog live preview, so the two can never visually drift
    apart.
    """
    if config is None:
        config = addon_config
    current_theme = "dark" if is_dark else "light"
    theme_colors = config.get("colors", {}).get(current_theme, {})

    try:
        with open(os.path.join(ADDON_PATH, "widget.css"), "r", encoding="utf-8") as f:
            css_content = f.read()
    except FileNotFoundError:
        css_content = ""

    bg_color = theme_colors.get("background", "#ffffff")
    bg_opacity = config.get("background_opacity_percent", 85)
    settings_icon_color = darken_color(bg_color, 0.65)

    if bg_color.startswith("rgba"):
        final_bg_color = bg_color
    else:
        final_bg_color = hex_to_rgba(bg_color, bg_opacity)

    css_variables = f"""
        :root {{
            --Berry-bg-color: {final_bg_color};
            --Berry-title-color: {theme_colors.get("title", "#000000")};
            --Berry-item-bg-color: {theme_colors.get("item_background", "rgba(0,0,0,0.1)")};
            --Berry-item-text-color: {theme_colors.get("item_text", "#000000")};
            --Berry-icon-color: {theme_colors.get("icon", "#333333")};
            --Berry-empty-text-color: {theme_colors.get("empty_text", "#888888")};
            --Berry-settings-icon-color: {settings_icon_color};
        }}
    """

    css = f"{css_variables}\n{css_content}"
    css += bento_integration.sizing_css("#Berry-widget-container", "#Berry-widget-container", config)
    return css


def generate_html(devices, config=None, is_dark: bool = False) -> str:
    """Builds the widget's inner HTML for a given device list/config/theme."""
    if config is None:
        config = addon_config
    icons = get_icons()
    settings_svg = icons.get("settings", "")
    current_theme = "dark" if is_dark else "light"

    if devices:
        device_items_html = ""
        for device in devices:
            name = device.get("name", "Unknown Device")
            dev_type = device.get("type", "bluetooth")
            icon_svg = icons.get(dev_type, icons.get("bluetooth", ""))
            device_items_html += f"""
                <div class="Berry-device-item">
                    <div class="Berry-device-icon">{icon_svg}</div>
                    <span>{name}</span>
                </div>
            """
    else:
        device_items_html = "<div class='Berry-device-item-empty'>No devices connected</div>"

    return f"""
        <div id="Berry-widget-container" class="{current_theme}-theme">
          <h2 id="Berry-title">{config.get("widget_title", "Bluetooth Devices")}</h2>
          <div id="Berry-device-list">
            {device_items_html}
          </div>
        </div>
    """


def add_Berry_widget(deck_browser, content):
    """Callback hook to add the widget to the deck browser screen."""
    config = addon_config
    devices = utils.get_connected_devices()
    is_dark_mode = resolve_is_dark_mode(config.get("theme", "system"))

    css = generate_css(is_dark_mode, config)
    html_content = generate_html(devices, config, is_dark=is_dark_mode)
    content.stats += f"<style>{css}</style>{html_content}"


_is_settings_open = False
def debounce_settings(func):
    def wrapper(*args, **kwargs):
        global _is_settings_open
        if _is_settings_open:
            return
        _is_settings_open = True
        try:
            return func()
        finally:
            _is_settings_open = False
    return wrapper

@debounce_settings
def show_settings_dialog():
    """Opens the custom settings dialog and refreshes the deck browser on save."""
    dialog = settings.BerrySettingsDialog(mw, addon_package=ADDON_PACKAGE, config=addon_config)
    if dialog.exec():
        # The dialog has updated the addon_config object.
        # Refresh the deck browser to see changes.
        mw.deckBrowser.show()

def on_pycmd(handled, message, context):
    """Handle pycmd messages from the widget."""
    if message == "Berry::open_settings":
        show_settings_dialog()
        return (True, None)
    return handled

# --- Add-on Setup ---
gui_hooks.deck_browser_will_render_content.append(add_Berry_widget)
gui_hooks.webview_did_receive_js_message.append(on_pycmd)
bento_integration.register_widget("Berry", settings_callback=show_settings_dialog)
bento_integration.add_menu_action("Berry Settings", show_settings_dialog)
