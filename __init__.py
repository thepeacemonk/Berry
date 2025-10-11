# Berry Anki Add-on
# Main entry point for the add-on.

import os
import re
from typing import Dict
import copy

from aqt import mw, gui_hooks
from aqt.qt import QAction, QColor, QPalette

from . import utils, settings
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


def add_Berry_widget(deck_browser, content):
    """Callback hook to add the widget to the deck browser screen."""
    config = addon_config
    
    # --- 1. Get Device & Icon Data ---
    devices = utils.get_connected_devices()
    icons = get_icons()

    # --- 2. Determine Theme ---
    theme_setting = config.get("theme", "system")
    
    if theme_setting == "system":
        try:
            is_dark_mode = mw.style().is_dark()
        except AttributeError:
            is_dark_mode = mw.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
    elif theme_setting == "light":
        is_dark_mode = False
    else:  # "dark"
        is_dark_mode = True

    current_theme = "dark" if is_dark_mode else "light"
    theme_colors = config.get("colors", {}).get(current_theme, {})
    
    # --- 3. Load CSS ---
    try:
        with open(os.path.join(ADDON_PATH, "widget.css"), "r", encoding="utf-8") as f:
            css_content = f.read()
    except FileNotFoundError:
        css_content = ""

    # --- 4. Prepare CSS Variables ---
    bg_color = theme_colors.get("background", "#ffffff")
    bg_opacity = config.get("background_opacity_percent", 85)
    
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
        }}
    """
    
    css_style_block = f"<style>{css_variables}\n{css_content}</style>"

    # --- 5. Generate HTML for Device List ---
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

    # --- 6. Assemble Final Widget HTML ---
    widget_html = f"""
        {css_style_block}
        <div id="Berry-widget-container" class="{current_theme}-theme">
          <h2 id="Berry-title">{config.get("widget_title", "Bluetooth Devices")}</h2>
          <div id="Berry-device-list">
            {device_items_html}
          </div>
        </div>
    """
    content.stats += widget_html

def show_settings_dialog():
    """Opens the custom settings dialog and refreshes the deck browser on save."""
    dialog = settings.BerrySettingsDialog(mw, addon_package=ADDON_PACKAGE, config=addon_config)
    if dialog.exec():
        # The dialog has updated the addon_config object.
        # Refresh the deck browser to see changes.
        mw.deckBrowser.show()

# --- Add-on Setup ---
gui_hooks.deck_browser_will_render_content.append(add_Berry_widget)
action = QAction("Berry Settings", mw)
action.triggered.connect(show_settings_dialog)
mw.form.menuTools.addAction(action)
