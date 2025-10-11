# settings_dialog.py
# Defines the Qt Dialog for Berry settings.

import copy
import os
from functools import partial

from aqt import mw
from aqt.qt import (
    QColor,
    QColorDialog,
    QDesktopServices,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    Qt,
    QButtonGroup,
    QFormLayout,
    QPixmap,
    QUrl,
)

# --- Helper function to create colored square buttons ---
def create_color_button(initial_color: str, parent: QWidget) -> QPushButton:
    """Creates a small, square QPushButton with a specific background color."""
    button = QPushButton(parent)
    button.setFixedSize(24, 24)
    button.setStyleSheet(f"background-color: {initial_color}; border: 1px solid #555; border-radius: 4px;")
    return button

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "widget_title": "Bluetooth Devices",
    "background_opacity_percent": 100, # Default is now 100%
    "theme": "system",
    "colors": {
        "light": {
            "background": "#e8e8ed",
            "title": "#1d1d1f",
            "item_background": "rgba(0, 0, 0, 0.05)",
            "item_text": "#1d1d1f",
            "icon": "#6e6e73",
            "empty_text": "#86868b",
        },
        "dark": {
            "background": "#2c2d30",
            "title": "#f5f5f7",
            "item_background": "rgba(255, 255, 255, 0.1)",
            "item_text": "#f5f5f7",
            "icon": "#f5f5f7",
            "empty_text": "#a1a1a6",
        },
    },
}

class BerrySettingsDialog(QDialog):
    def __init__(self, parent=None, addon_package=None, config=None):
        super().__init__(parent)
        self.addon_package = addon_package
        self.setWindowTitle("Berry Settings")
        self.setMinimumWidth(450)

        # --- Config Management ---
        # Keep a reference to the original config object to update it on save
        self.source_config = config
        # Work on a deep copy, so changes are isolated until saved
        self.config = copy.deepcopy(self.source_config)

        # --- UI Setup ---
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Builds the user interface for the dialog."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # --- Logo ---
        logo_label = QLabel()
        # Assumes "berry_logo.png" is in the same directory as this script
        logo_path = os.path.join(os.path.dirname(__file__), "berry_logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            logo_label.setPixmap(pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        # --- Support & Bug Reports ---
        support_layout = QHBoxLayout()
        self.donate_button = QPushButton("Donate")
        self.report_button = QPushButton("Report Bug")

        self.donate_button.clicked.connect(self.on_donate)
        self.report_button.clicked.connect(self.on_report_bug)
        
        support_layout.addStretch()
        support_layout.addWidget(self.donate_button)
        support_layout.addWidget(self.report_button)
        support_layout.addStretch()

        layout.addLayout(support_layout)

        # --- Theme Selection ---
        theme_group = QGroupBox("Appearance Theme")
        theme_buttons_layout = QHBoxLayout()
        self.theme_button_group = QButtonGroup(self)
        
        self.radio_system = QPushButton("System")
        self.radio_light = QPushButton("Light")
        self.radio_dark = QPushButton("Dark")

        for btn in [self.radio_system, self.radio_light, self.radio_dark]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            theme_buttons_layout.addWidget(btn)
            self.theme_button_group.addButton(btn)
        theme_group.setLayout(theme_buttons_layout)
        
        # --- Opacity Slider ---
        opacity_group = QGroupBox("Background Opacity")
        opacity_layout = QVBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_group.setLayout(opacity_layout)
        
        # --- Color Customization ---
        colors_group = QGroupBox("Color Customization")
        colors_form_layout = QFormLayout()
        colors_form_layout.setSpacing(10)
        colors_form_layout.setContentsMargins(10, 15, 10, 15)

        # Create color buttons for light and dark themes
        self.color_buttons = {"light": {}, "dark": {}}
        color_keys = ["background", "title", "item_background", "item_text", "icon", "empty_text"]
        
        # Light Theme Colors
        colors_form_layout.addRow(QLabel("<b>Light Theme</b>"))
        for key in color_keys:
            btn = create_color_button(self.config["colors"]["light"][key], self)
            btn.clicked.connect(partial(self.pick_color, btn, "light", key))
            self.color_buttons["light"][key] = btn
            colors_form_layout.addRow(f"{key.replace('_', ' ').title()}:", btn)

        # Add a separator
        separator = QWidget()
        separator.setMinimumHeight(10)
        colors_form_layout.addRow(separator)

        # Dark Theme Colors
        colors_form_layout.addRow(QLabel("<b>Dark Theme</b>"))
        for key in color_keys:
            btn = create_color_button(self.config["colors"]["dark"][key], self)
            btn.clicked.connect(partial(self.pick_color, btn, "dark", key))
            self.color_buttons["dark"][key] = btn
            colors_form_layout.addRow(f"{key.replace('_', ' ').title()}:", btn)
        
        colors_group.setLayout(colors_form_layout)

        # --- Layout Assembly ---
        layout.addWidget(theme_group)
        layout.addWidget(opacity_group)
        layout.addWidget(colors_group)
        layout.addStretch()

        # --- Save/Cancel/Restore Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.restore_button = QPushButton("Restore Defaults")
        button_box.addButton(self.restore_button, QDialogButtonBox.ButtonRole.ResetRole)

        button_box.accepted.connect(self.save_and_close)
        button_box.rejected.connect(self.reject)
        self.restore_button.clicked.connect(self.on_restore_defaults)
        
        layout.addWidget(button_box)
        
        self.setStyleSheet(self.get_stylesheet())

    def on_donate(self):
        """Opens the donation link in a web browser."""
        url = QUrl("https://buymeacoffee.com/peacemonk")
        QDesktopServices.openUrl(url)

    def on_report_bug(self):
        """Opens the bug report link in a web browser."""
        url = QUrl("https://github.com/thepeacemonk/Berry")
        QDesktopServices.openUrl(url)

    def load_settings(self):
        """Loads settings from config and updates the UI elements."""
        # Theme
        theme = self.config.get("theme", "system")
        if theme == "light": self.radio_light.setChecked(True)
        elif theme == "dark": self.radio_dark.setChecked(True)
        else: self.radio_system.setChecked(True)

        # Opacity
        self.opacity_slider.setValue(self.config.get("background_opacity_percent", 100))

        # Colors
        for theme_mode, buttons in self.color_buttons.items():
            for key, button in buttons.items():
                color_str = self.config["colors"][theme_mode][key]
                button.setStyleSheet(f"background-color: {color_str}; border: 1px solid #555; border-radius: 4px;")

    def pick_color(self, button: QPushButton, mode: str, key: str):
        """Opens a color dialog and updates the button style and config."""
        current_color_str = self.config["colors"][mode][key]
        
        initial_color = QColor()
        if "rgba" in current_color_str:
            try:
                parts = current_color_str.replace("rgba(", "").replace(")", "").split(",")
                initial_color.setRgb(int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
            except (ValueError, IndexError):
                initial_color.setNamedColor("#000000") # Fallback
        else:
            initial_color.setNamedColor(current_color_str)

        color = QColorDialog.getColor(initial_color, self, f"Choose {mode.title()} {key.replace('_', ' ')}", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        
        if color.isValid():
            if color.alpha() == 255:
                new_color_str = color.name()
            else:
                new_color_str = f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF():.2f})"
            
            self.config["colors"][mode][key] = new_color_str
            button.setStyleSheet(f"background-color: {new_color_str}; border: 1px solid #555; border-radius: 4px;")

    def on_restore_defaults(self):
        """Resets the configuration to defaults and reloads the UI."""
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.load_settings()

    def save_and_close(self):
        """Saves the current settings to the config file."""
        # Get theme and opacity from UI elements
        if self.radio_light.isChecked(): self.config["theme"] = "light"
        elif self.radio_dark.isChecked(): self.config["theme"] = "dark"
        else: self.config["theme"] = "system"

        self.config["background_opacity_percent"] = self.opacity_slider.value()
        
        # Update the original config object with our changes
        self.source_config.clear()
        self.source_config.update(self.config)

        # Write the updated config to the file
        mw.addonManager.writeConfig(self.addon_package, self.source_config)
        self.accept()

    def get_stylesheet(self) -> str:
        """Returns the QSS stylesheet for the dialog."""
        return """
            QDialog {
                background-color: #2c2c2e;
                color: #e5e5e7;
            }
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 1px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
            }
            QLabel {
                font-size: 14px;
            }
            QLabel[text="<b>Light Theme</b>"], QLabel[text="<b>Dark Theme</b>"] {
                font-size: 15px;
                color: #e5e5e7;
            }
            #themeToggleButton {
                background-color: #3a3a3c;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 14px;
            }
            #themeToggleButton:checked {
                background-color: #555557;
            }
            QPushButton[text="Donate"],
            QPushButton[text="Report Bug"] {
                background-color: #3a3a3c;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 14px;
                margin-bottom: 10px;
            }
            QPushButton[text="Donate"]:hover,
            QPushButton[text="Report Bug"]:hover {
                background-color: #4a4a4c;
            }
            QSlider::groove:horizontal {
                background: #3a3a3c; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white; width: 20px; height: 20px;
                margin: -7px 0; border-radius: 10px;
            }
            QSlider::sub-page:horizontal {
                background: #BD87FA; height: 6px; border-radius: 3px;
            }
            QDialogButtonBox QPushButton {
                background-color: #3a3a3c;
                padding: 8px 16px;
                border-radius: 8px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #4a4a4c;
            }
            /* Style for the Save button specifically */
            QDialogButtonBox QPushButton[text="Save"] {
                background-color: #BD87FA;
                color: #ffffff;
            }
            QDialogButtonBox QPushButton[text="Save"]:hover {
                background-color: #d1a3fa;
            }
        """

