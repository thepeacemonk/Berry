# settings_dialog.py
# Defines the Qt Dialog for Berry settings — Onigiri-style horizontal layout.

import copy
import os
import re
import importlib
from functools import partial

from aqt import mw
from aqt.qt import (
    QColor,
    QColorDialog,
    QDesktopServices,
    QDialog,
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
    QScrollArea,
    QApplication,
    QFrame,
    QSizePolicy,
    QAbstractButton,
    QSpinBox,
    QTimer,
)
try:
    from PyQt6.QtCore import pyqtProperty, QPointF, QParallelAnimationGroup
    from PyQt6.QtGui import QPainter, QPen, QColor as QColor2, QPainterPath, QFont
    from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QRectF
    from PyQt6.QtWidgets import QStyleOption, QStyle
except ImportError:
    from PyQt5.QtCore import pyqtProperty, QPointF, QParallelAnimationGroup
    from PyQt5.QtGui import QPainter, QPen, QColor as QColor2, QPainterPath, QFont
    from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QRectF
    from PyQt5.QtWidgets import QStyleOption, QStyle
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView
from . import bento_integration

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "widget_title": "Bluetooth Devices",
    "background_opacity_percent": 100,
    "theme": "system",
    "manual_widget_width": 200,
    "manual_widget_height": 200,
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

# ─── UI Components ───────────────────────────────────────────────────────────

class AnimatedToggleButton(QAbstractButton):
    """iOS-style animated toggle switch, matching Onigiri's design."""
    def __init__(self, parent=None, accent_color="#BD87FA"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accent_color = QColor(accent_color)
        self.track_color_off = QColor("#cccccc") if not theme_manager.night_mode else QColor("#555555")
        self.thumb_color = QColor("#ffffff")
        self.setFixedSize(38, 20)
        self._thumb_x_pos = 3.0
        self.animation = QPropertyAnimation(self, b"thumb_x_pos", self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._start_animation)

    @pyqtProperty(float)
    def thumb_x_pos(self):
        return self._thumb_x_pos

    @thumb_x_pos.setter
    def thumb_x_pos(self, value):
        self._thumb_x_pos = value
        self.update()

    def _start_animation(self, checked):
        end_pos = self.width() - self.height() + 3 if checked else 3
        self.animation.setStartValue(self.thumb_x_pos)
        self.animation.setEndValue(end_pos)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        height = self.height()
        radius = height / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        track_color = self.accent_color if self.isChecked() else self.track_color_off
        painter.setBrush(track_color)
        painter.drawRoundedRect(self.rect(), radius, radius)
        thumb_radius = radius - 3
        painter.setBrush(self.thumb_color)
        thumb_y = radius
        painter.drawEllipse(QPointF(self._thumb_x_pos + thumb_radius, thumb_y), thumb_radius, thumb_radius)

    def showEvent(self, event):
        super().showEvent(event)
        self._thumb_x_pos = self.width() - self.height() + 3 if self.isChecked() else 3
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._thumb_x_pos = self.width() - self.height() + 3 if self.isChecked() else 3
        self.update()


class GooeySegmentedControl(QWidget):
    """Segmented control container with a gooey sliding pill animation."""
    def __init__(self, accent_color="#BD87FA", parent=None, bg_color="#f2f2f2", border_color="#dcdde1"):
        super().__init__(parent)
        self.setObjectName("themeToggleContainer")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._accent_color = QColor(accent_color)
        self._bg_color = QColor(bg_color)
        self._border_color = QColor(border_color)

        self._indicator_rect = QRectF(4, 4, 0, 0)
        
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_x = QPropertyAnimation(self, b"indicator_x")
        self.anim_width = QPropertyAnimation(self, b"indicator_width")
        self.anim_group.addAnimation(self.anim_x)
        self.anim_group.addAnimation(self.anim_width)
        
        self.anim_x.setEasingCurve(QEasingCurve.Type.InOutBack)
        self.anim_width.setEasingCurve(QEasingCurve.Type.InOutBack)
        
        self.anim_x.setDuration(400)
        self.anim_width.setDuration(400)

        self.button_group = QButtonGroup(self)
        self.button_group.buttonClicked.connect(self.animate_to)

    @pyqtProperty(float)
    def indicator_x(self):
        return self._indicator_rect.x()

    @indicator_x.setter
    def indicator_x(self, value):
        self._indicator_rect.setX(value)
        self.update()

    @pyqtProperty(float)
    def indicator_width(self):
        return self._indicator_rect.width()

    @indicator_width.setter
    def indicator_width(self, value):
        self._indicator_rect.setWidth(value)
        self.update()

    def set_accent_color(self, color_str):
        self._accent_color = QColor(color_str)
        self.update()

    def add_button(self, btn):
        self._layout.addWidget(btn)
        self.button_group.addButton(btn)

    def animate_to(self, btn):
        if not btn: return
        target_rect = btn.geometry()
        if target_rect.width() == 0:
            return
            
        self.anim_x.setStartValue(self.indicator_x)
        self.anim_x.setEndValue(float(target_rect.x()))
        
        self.anim_width.setStartValue(self.indicator_width)
        self.anim_width.setEndValue(float(target_rect.width()))
        
        self.anim_group.start()

    def update_indicator_no_animation(self):
        checked_btn = self.button_group.checkedButton()
        if checked_btn and checked_btn.geometry().width() > 0:
            r = checked_btn.geometry()
            self._indicator_rect.setX(r.x())
            self._indicator_rect.setWidth(r.width())
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_indicator_no_animation()

    def showEvent(self, event):
        super().showEvent(event)
        # Delay the initial setup slightly to let layout finish
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self.update_indicator_no_animation)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the pill track ourselves (radius = actual height / 2) instead
        # of relying on QSS border-radius, which doesn't clamp large values
        # the way CSS does and can render as a barely-rounded rectangle.
        track_radius = self.height() / 2.0
        track_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        track_path = QPainterPath()
        track_path.addRoundedRect(track_rect, track_radius, track_radius)
        p.setPen(QPen(self._border_color, 1))
        p.setBrush(self._bg_color)
        p.drawPath(track_path)

        if self._indicator_rect.width() > 0:
            # The InOutBack easing on the slide animation overshoots past its
            # target (that's what gives it the "gooey" bounce), which can push
            # the indicator's rounded corner past x=0 mid-animation. Clipping
            # to the track's own rounded path (rather than the widget's plain
            # rectangular bounds) means any overshoot gets bounded by the
            # pill's curve instead of being sliced off into a flat edge.
            p.setClipPath(track_path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent_color)

            checked_btn = self.button_group.checkedButton()
            h = checked_btn.geometry().height() if checked_btn else 28
            y = checked_btn.geometry().y() if checked_btn else 4

            rect = QRectF(self._indicator_rect.x(), float(y), self._indicator_rect.width(), float(h))
            radius = h / 2.0
            p.drawRoundedRect(rect, radius, radius)

class ModernSlider(QSlider):
    def __init__(self, accent_color="#BD87FA", parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.accent_color = QColor(accent_color)
        self.setMinimumHeight(24)

    def _theme_tokens(self):
        curr = self.parent()
        while curr:
            if hasattr(curr, "_theme_tokens"):
                return curr._theme_tokens()
            curr = curr.parent()
        return {
            "border": "#d1d5db" if not theme_manager.night_mode else "#444444",
            "surface": "#eaeaea" if not theme_manager.night_mode else "#2d2d2d",
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        enabled = self.isEnabled()
        w = self.width()
        h = self.height()

        # Track parameters
        track_h = 18
        track_y = (h - track_h) // 2
        track_rx = track_h // 2

        min_val = self.minimum()
        max_val = self.maximum()
        val = self.value()

        range_val = max_val - min_val
        if range_val <= 0:
            range_val = 1

        handle_d = 12
        padding_x = 9

        x_min = padding_x
        x_max = w - padding_x
        pct = (val - min_val) / range_val
        handle_cx = x_min + pct * (x_max - x_min)

        # Get background color from tokens
        tokens = self._theme_tokens()
        bg_color_hex = tokens.get("surface", "#eaeaea")
        bg_color = QColor(bg_color_hex)

        if enabled:
            active_color = self.accent_color
        else:
            active_color = QColor(self.accent_color.red(), self.accent_color.green(), self.accent_color.blue(), 76)
            bg_color.setAlpha(76)

        # Draw background track
        track_rect = QRectF(0, track_y, w, track_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(track_rect, track_rx, track_rx)

        # Draw active track
        active_right = handle_cx + 10
        if active_right > w:
            active_right = w
        if active_right < track_rx * 2:
            active_right = track_rx * 2

        active_rect = QRectF(0, track_y, active_right, track_h)
        painter.setBrush(active_color)
        painter.drawRoundedRect(active_rect, track_rx, track_rx)

        # Draw handle (white circle centered at handle_cx)
        handle_cy = track_y + track_h / 2
        handle_color = QColor("#ffffff") if enabled else QColor(255, 255, 255, 120)
        painter.setBrush(handle_color)
        painter.drawEllipse(QPointF(handle_cx, handle_cy), 6, 6)

class SectionGroup(QWidget):
    """Onigiri-style section container with bold title and rounded inner card."""
    def __init__(self, title="", parent=None, description=""):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 5, 0, 0)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 17px; margin-bottom: 2px;")
        main_layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("font-size: 11px; color: #888; margin-bottom: 5px;")
            desc_label.setWordWrap(True)
            main_layout.addWidget(desc_label)

        self.content_area = QWidget()
        self.content_area.setObjectName("innerGroup")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(15, 15, 15, 15)
        self.content_layout.setSpacing(10)
        main_layout.addWidget(self.content_area)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


# ─── Live Preview Widget ─────────────────────────────────────────────────────

def _parse_color(color_str):
    """Parse a hex or rgba color string into a QColor."""
    if not color_str:
        return QColor("#000000")
    if "rgba" in color_str:
        try:
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
            a = int(float(parts[3].strip()) * 255)
            return QColor(r, g, b, a)
        except (ValueError, IndexError):
            return QColor("#000000")
    else:
        c = QColor(color_str)
        return c if c.isValid() else QColor("#000000")


# ─── Live Preview ────────────────────────────────────────────────────────────

# #Berry-widget-container is a fixed 200x200 square with `margin: 20px auto`
# baked into widget.css, so — like Global/Sticky/Hours/Power — there's a
# single fixed natural footprint, not a per-view-mode dict.
_NATURAL_W, _NATURAL_H = 200, 240

_PREVIEW_DEVICE_SETS = {
    "devices": [
        {"name": "AirPods Pro", "type": "headphone"},
        {"name": "Magic Keyboard", "type": "keyboard"},
    ],
    "empty": [],
}


class BerryPreviewWidget(QWidget):
    """Renders a live HTML preview of the Berry widget using sample device data."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._variant = "devices"

        self.preview_layout = QVBoxLayout(self)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)

        self.webview = None

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.refresh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(120)

    def cleanup(self):
        """Release the embedded AnkiWebView before this widget is destroyed.

        AnkiWebView wraps a QWebEngineView; if it is left to be torn down
        implicitly during Python interpreter finalization (Anki quitting),
        Qt dereferences already-freed child widgets and segfaults. Cleaning
        it up explicitly on dialog close avoids that.
        """
        if getattr(self, "_resize_timer", None) is not None:
            self._resize_timer.stop()
        if getattr(self, "webview", None) is not None:
            if getattr(self, "webview", None):
                self.webview.cleanup()
            self.webview = None

    def set_variant(self, variant):
        if variant == self._variant:
            return
        self._variant = variant
        self.refresh()

    def _resolve_theme_is_dark(self):
        theme = self.config.get("theme", "system")
        if theme == "system":
            return theme_manager.night_mode
        return theme == "dark"


    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "webview", None) is None:
            self.webview = AnkiWebView(title="berry_preview", parent=self)
            
            self.webview.setMinimumSize(260, 300)
            self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.webview.disable_zoom()
            page = self.webview.page()
            page.setBackgroundColor(QColor(0, 0, 0, 0))
            self.preview_layout.addWidget(self.webview)
            self.refresh()

    def refresh(self):
        if not getattr(self, "webview", None):
            return
        addon_module = importlib.import_module(__package__)
        system_is_dark = theme_manager.night_mode
        widget_is_dark = self._resolve_theme_is_dark()

        devices = _PREVIEW_DEVICE_SETS.get(self._variant, _PREVIEW_DEVICE_SETS["devices"])
        css = addon_module.generate_css(widget_is_dark, self.config)
        html_content = addon_module.generate_html(devices, self.config, is_dark=widget_is_dark)

        # Behind the widget: Onigiri's actual deck-browser wallpaper when the
        # integration is active, otherwise the same flat color as this dialog.
        settings_bg = "#181818" if system_is_dark else "#f7f7f7"
        wallpaper = None
        if bento_integration.is_onigiri_detected():
            wallpaper = bento_integration.main_menu_wallpaper(system_is_dark)
        if not wallpaper:
            wallpaper = {"kind": "color", "color": settings_bg}

        if wallpaper["kind"] == "image":
            bg_layer_css = f"""
                background-color: {wallpaper['color']};
                background-image: url('{wallpaper['url']}');
                background-size: cover; background-position: center; background-repeat: no-repeat;
                filter: blur({wallpaper['blur_px']}px);
                opacity: {wallpaper['opacity']};
            """
        else:
            bg_layer_css = f"background-color: {wallpaper['color']}; opacity: 1;"

        panel_w = self.webview.width()
        panel_h = self.webview.height()
        if panel_w < 100 or panel_h < 100:
            panel_w, panel_h = 320, 400

        avail_w = panel_w - 40
        avail_h = panel_h - 40
        factor = min(1.0, avail_w / _NATURAL_W, avail_h / _NATURAL_H) * 0.94
        final_w = _NATURAL_W * factor + 2
        final_h = _NATURAL_H * factor + 2

        full_html = f"""
        <html><head><style>
            html, body {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: transparent; }}
            body {{
                position: relative;
                display: flex; align-items: center; justify-content: center;
                background: transparent;
            }}
            #onigiri-bg-container {{
                position: absolute; inset: 10px; z-index: 0;
                border-radius: 20px; overflow: hidden;
                transform: translateZ(0);
            }}
            #onigiri-bg-layer {{
                position: absolute; inset: -50px;
                {bg_layer_css}
            }}
            #scale-wrapper {{
                position: relative; z-index: 1;
                width: {final_w}px; height: {final_h}px;
                flex-shrink: 0;
            }}
            #berry-preview-inner {{
                position: absolute; top: 0; left: 0;
                transform: scale({factor}); transform-origin: top left;
            }}
        </style>
        <style>{css}</style>
        </head>
        <body>
            <div id="onigiri-bg-container">
                <div id="onigiri-bg-layer"></div>
            </div>
            <div id="scale-wrapper">
                <div id="berry-preview-inner">{html_content}</div>
            </div>
        </body></html>
        """
        self.webview.setHtml(full_html)


# ─── Helper to create color buttons ──────────────────────────────────────────

def _contrast_text_color(hex_color: str) -> str:
    """Returns a suitable contrasting text color (black or white) for a given hex background."""
    a = 1.0
    if hex_color.startswith("rgba"):
        try:
            parts = hex_color.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts) >= 4:
                a = float(parts[3])
        except Exception:
            r, g, b = 255, 255, 255
    else:
        c = hex_color.lstrip('#')
        if len(c) in (6, 8):
            r, g, b = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
            if len(c) == 8:
                a = int(c[6:8], 16) / 255.0
        else:
            r, g, b = 255, 255, 255
            
    is_dark = False
    try:
        from aqt.theme import theme_manager
        is_dark = theme_manager.night_mode
    except ImportError:
        pass
        
    bg_r, bg_g, bg_b = (48, 48, 48) if is_dark else (242, 242, 242)
    
    eff_r = r * a + bg_r * (1.0 - a)
    eff_g = g * a + bg_g * (1.0 - a)
    eff_b = b * a + bg_b * (1.0 - a)

    luminance = (0.2126 * eff_r + 0.7152 * eff_g + 0.0722 * eff_b) / 255.0
    return "#111111" if luminance > 0.56 else "#ffffff"


def _format_as_hex(color_str: str) -> str:
    a = 1.0
    r, g, b = 255, 255, 255
    if color_str.startswith("rgba"):
        try:
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts) >= 4:
                a = float(parts[3])
        except Exception:
            pass
    else:
        c = color_str.lstrip('#')
        if len(c) in (6, 8):
            r, g, b = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
            if len(c) == 8:
                a = int(c[6:8], 16) / 255.0

    if a >= 1.0:
        return f"#{r:02X}{g:02X}{b:02X}"

    is_dark = False
    try:
        from aqt.theme import theme_manager
        is_dark = theme_manager.night_mode
    except ImportError:
        pass

    bg_r, bg_g, bg_b = (36, 36, 36) if is_dark else (255, 255, 255)
    
    eff_r = int(r * a + bg_r * (1.0 - a))
    eff_g = int(g * a + bg_g * (1.0 - a))
    eff_b = int(b * a + bg_b * (1.0 - a))
    return f"#{eff_r:02X}{eff_g:02X}{eff_b:02X}"


def create_color_button(initial_color: str, parent: QWidget) -> QPushButton:
    """Creates a small, square QPushButton with a specific background color."""
    button = QPushButton(parent)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setObjectName("colorSwatchButton")
    _apply_swatch_style(button, initial_color)
    return button


def _apply_swatch_style(button, color_str):
    text_color = _contrast_text_color(color_str)
    hex_display = _format_as_hex(color_str)
    button.setText(hex_display)
    button.setStyleSheet(
        f"QPushButton#colorSwatchButton {{"
        f"  background-color: {hex_display};"
        f"  color: {text_color};"
        f"  font-weight: bold;"
        f"  font-size: 13px;"
        f"  border: 1px solid rgba(0,0,0,0.15);"
        f"  border-radius: 12px;"
        f"  padding: 6px 16px;"
        f"}}"
        f"QPushButton#colorSwatchButton:hover {{"
        f"  border: 1px solid rgba(0,0,0,0.35);"
        f"}}"
    )


# ─── Main Settings Dialog ────────────────────────────────────────────────────

class BerrySettingsDialog(QDialog):
    def __init__(self, parent=None, addon_package=None, config=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.addon_package = addon_package
        self.setWindowTitle("Berry Settings")

        # Screen-proportional sizing
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.resize(int(avail.width() * 0.42), int(avail.height() * 0.50))
        else:
            self.resize(720, 500)
        self.setMinimumSize(780, 400)
        
        # Config management
        self.source_config = config
        self.config = copy.deepcopy(self.source_config)

        self.setup_ui()
        self.load_settings()

        # Tear down the embedded AnkiWebView and schedule the dialog for
        # deletion when it closes, so it does not linger as a child of the
        # main window with a live QWebEngineView (which segfaults during
        # interpreter shutdown). deleteLater() is used instead of
        # WA_DeleteOnClose because this dialog is shown with exec(): a
        # WA_DeleteOnClose delete happens inside the modal loop and frees the
        # dialog while exec() is still unwinding, which itself crashes.
        self.finished.connect(self._cleanup_on_close)

    def _cleanup_on_close(self, *args):
        preview = getattr(self, "preview_widget", None)
        if preview is not None:
            preview.cleanup()
        self.deleteLater()

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geo = self.frameGeometry()
            geo.moveCenter(screen.availableGeometry().center())
            self.move(geo.topLeft())

    # ── Theme tokens (Onigiri pattern) ────────────────────────────────────

    def _theme_tokens(self):
        is_dark = theme_manager.night_mode
        accent = "#BD87FA"
        if is_dark:
            return {
                "bg": "#181818",
                "panel": "#242424",
                "surface": "#303030",
                "fg": "#f4f4f5",
                "muted": "#c4c4c4",
                "border": "#454545",
                "accent": accent,
            }
        return {
            "bg": "#f7f7f7",
            "panel": "#ffffff",
            "surface": "#f2f2f2",
            "fg": "#202124",
            "muted": "#6f7177",
            "border": "#dcdde1",
            "accent": accent,
        }

    # ── UI Setup ──────────────────────────────────────────────────────────

    def setup_ui(self):
        tokens = self._theme_tokens()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        content_h_layout = QHBoxLayout()
        content_h_layout.setSpacing(0)
        content_h_layout.setContentsMargins(0, 0, 0, 0)

        # ── Right: Preview panel ─────────────────────────────────────────
        preview_wrapper = QWidget()
        preview_wrapper.setObjectName("previewWrapper")
        preview_wrapper_layout = QVBoxLayout(preview_wrapper)
        preview_wrapper_layout.setContentsMargins(20, 24, 10, 20)
        preview_wrapper_layout.setSpacing(12)

        preview_header_row = QWidget()
        preview_header_layout = QHBoxLayout(preview_header_row)
        preview_header_layout.setContentsMargins(0, 0, 0, 0)

        preview_title = QLabel("Preview")
        preview_title.setStyleSheet(f"font-size: 12px; font-weight: 700; letter-spacing: 0.6px; color: {tokens['muted']};")
        preview_header_layout.addWidget(preview_title)
        preview_header_layout.addStretch()

        self.preview_variant_toggle = GooeySegmentedControl(tokens["accent"], self, bg_color=tokens["surface"], border_color=tokens["border"])
        self.radio_preview_devices = QPushButton("Devices")
        self.radio_preview_empty = QPushButton("Empty")
        for btn in [self.radio_preview_devices, self.radio_preview_empty]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            self.preview_variant_toggle.add_button(btn)
        self.radio_preview_devices.setChecked(True)
        self.preview_variant_toggle.button_group.buttonClicked.connect(self._on_preview_variant_changed)
        preview_header_layout.addWidget(self.preview_variant_toggle)

        preview_wrapper_layout.addWidget(preview_header_row)

        self.preview_widget = BerryPreviewWidget(self.config, self)
        preview_wrapper_layout.addWidget(self.preview_widget, 1)

        # Support buttons initialization
        self.donate_button = QPushButton("Donate")
        self.donate_button.setObjectName("cancelButton")
        self.donate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.report_button = QPushButton("Report Bug")
        self.report_button.setObjectName("cancelButton")
        self.report_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.donate_button.clicked.connect(self.on_donate)
        self.report_button.clicked.connect(self.on_report_bug)

        # ── Right: Controls panel (rounded shell) ────────────────────────
        controls_outer = QWidget()
        controls_outer.setObjectName("controlsOuter")
        controls_outer_layout = QVBoxLayout(controls_outer)
        controls_outer_layout.setContentsMargins(8, 10, 8, 0)
        controls_outer_layout.setSpacing(0)

        controls_container = QFrame()
        controls_container.setObjectName("controlsContainer")
        controls_container.setFrameShape(QFrame.Shape.NoFrame)
        controls_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        controls_container_layout = QVBoxLayout(controls_container)
        controls_container_layout.setContentsMargins(0, 0, 0, 0)
        controls_container_layout.setSpacing(0)

        # Scroll area for controls
        scroll = QScrollArea()
        scroll.setObjectName("controlsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(28, 24, 28, 20)
        scroll_layout.setSpacing(20)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Appearance Section ───────────────────────────────────────
        appearance_group = SectionGroup("Appearance", self)

        # Theme row
        theme_row = QWidget()
        theme_row_layout = QHBoxLayout(theme_row)
        theme_row_layout.setContentsMargins(0, 0, 0, 0)
        theme_row_layout.addWidget(QLabel("Theme"))
        theme_row_layout.addStretch()

        theme_toggle_container = GooeySegmentedControl(tokens["accent"], self, bg_color=tokens["surface"], border_color=tokens["border"])

        self.theme_button_group = theme_toggle_container.button_group
        self.radio_system = QPushButton("System")
        self.radio_light = QPushButton("Light")
        self.radio_dark = QPushButton("Dark")

        for btn in [self.radio_system, self.radio_light, self.radio_dark]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            theme_toggle_container.add_button(btn)

        theme_row_layout.addWidget(theme_toggle_container)

        appearance_group.add_widget(theme_row)

        # Opacity row
        opacity_row = QWidget()
        opacity_row_layout = QHBoxLayout(opacity_row)
        opacity_row_layout.setContentsMargins(0, 0, 0, 0)
        opacity_row_layout.addWidget(QLabel("Opacity"))
        self.opacity_slider = ModernSlider(tokens["accent"], self)
        self.opacity_slider.setObjectName("berrySlider")
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setMinimumWidth(120)
        self.opacity_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        opacity_row_layout.addWidget(self.opacity_slider, 1)
        self.opacity_value_label = QLabel("100%")
        self.opacity_value_label.setFixedWidth(38)
        opacity_row_layout.addWidget(self.opacity_value_label)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)

        appearance_group.add_widget(opacity_row)
        scroll_layout.addWidget(appearance_group)

        # ── Colors Section ───────────────────────────────────────────
        colors_group = SectionGroup("Colors", self)

        self.color_buttons = {"light": {}, "dark": {}}
        color_keys = ["background", "title", "item_background", "item_text", "icon", "empty_text"]
        friendly_names = {
            "background": "Background",
            "title": "Title",
            "item_background": "Item Background",
            "item_text": "Item Text",
            "icon": "Icon",
            "empty_text": "Empty Text",
        }

        # Light colors header
        light_header = QLabel("Light Theme")
        light_header.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {tokens['muted']};")
        colors_group.add_widget(light_header)

        for key in color_keys:
            row = self._create_color_row(
                friendly_names[key],
                self.config["colors"]["light"][key],
                "light", key,
            )
            colors_group.add_widget(row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {tokens['border']};")
        sep.setFixedHeight(1)
        colors_group.add_widget(sep)

        # Dark colors header
        dark_header = QLabel("Dark Theme")
        dark_header.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {tokens['muted']};")
        colors_group.add_widget(dark_header)

        for key in color_keys:
            row = self._create_color_row(
                friendly_names[key],
                self.config["colors"]["dark"][key],
                "dark", key,
            )
            colors_group.add_widget(row)

        scroll_layout.addWidget(colors_group)

        # ── Onigiri Integration Section ──────────────────────────────
        integration_group, self.bento_width_spin, self.bento_height_spin = bento_integration.create_settings_group(self.config)
        scroll_layout.addWidget(integration_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        scroll.viewport().setAutoFillBackground(False)
        scroll_content.setAutoFillBackground(False)
        controls_container.setAutoFillBackground(False)
        controls_container_layout.addWidget(scroll)

        # ── Buttons logic initialized here but moved to bottom bar ──────────────────────────────────────────────
        self.restore_button = QPushButton("Restore Defaults")
        self.restore_button.setObjectName("cancelButton")
        self.restore_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_button.setAutoDefault(False)
        self.restore_button.clicked.connect(self.on_restore_defaults)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setAutoDefault(False)
        self.save_button.clicked.connect(self.save_and_close)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)

        controls_outer_layout.addWidget(controls_container)
        content_h_layout.addWidget(controls_outer, 1)
        content_h_layout.addWidget(preview_wrapper)

        root_layout.addLayout(content_h_layout, 1)

        # ── Bottom Pill Bar ──────────────────────────────────────────────
        bottom_container = QWidget()
        bottom_container.setObjectName("bottomContainer")
        bottom_container_layout = QVBoxLayout(bottom_container)
        bottom_container_layout.setContentsMargins(20, 8, 20, 20)
        
        bottom_bar = QWidget()
        bottom_bar.setObjectName("bottomPillBar")
        bottom_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(10, 10, 10, 10)
        bottom_bar_layout.setSpacing(8)

        logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), "berry_logo.svg")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(200, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setFixedSize(scaled_pixmap.size())
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bottom_bar_layout.addWidget(logo_label)

        bottom_bar_layout.addSpacing(8)
        bottom_bar_layout.addWidget(self.donate_button)
        bottom_bar_layout.addWidget(self.report_button)
        bottom_bar_layout.addWidget(self.restore_button)

        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.cancel_button)
        bottom_bar_layout.addWidget(self.save_button)

        bottom_container_layout.addWidget(bottom_bar)
        root_layout.addWidget(bottom_container)
        self._apply_stylesheet()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _create_color_row(self, label_text, initial_color, mode, key):
        row = QFrame()
        row.setObjectName("colorRow")
        
        is_dark = theme_manager.night_mode
        bg_color = "#242424" if is_dark else "#FFFFFF"
        border_color = "#454545" if is_dark else "#DCDDE1"
        text_color = "#f4f4f5" if is_dark else "#1d1d1f"
        
        row.setStyleSheet(f"""
            QFrame#colorRow {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
        """)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 10, 16, 10)

        label = QLabel(label_text)
        label.setStyleSheet(
            f"font-weight: 700; font-size: 14px; border: none; "
            f"background: transparent; color: {text_color};"
        )
        layout.addWidget(label)
        layout.addStretch()

        btn = create_color_button(initial_color, self)
        btn.clicked.connect(partial(self.pick_color, btn, mode, key))
        self.color_buttons[mode][key] = btn
        layout.addWidget(btn)

        return row

    def _on_opacity_changed(self, value):
        self.opacity_value_label.setText(f"{value}%")
        self.config["background_opacity_percent"] = value
        self._refresh_preview()

    def _refresh_preview(self):
        self.preview_widget.config = self.config
        self.preview_widget.refresh()

    def _on_preview_variant_changed(self, btn):
        self.preview_widget.set_variant("empty" if btn is self.radio_preview_empty else "devices")

    # ── Load / Save / Restore ─────────────────────────────────────────────

    def load_settings(self):
        theme = self.config.get("theme", "system")
        if theme == "light":
            self.radio_light.setChecked(True)
        elif theme == "dark":
            self.radio_dark.setChecked(True)
        else:
            self.radio_system.setChecked(True)

        opacity = self.config.get("background_opacity_percent", 100)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(opacity)
        self.opacity_slider.blockSignals(False)
        self.opacity_value_label.setText(f"{opacity}%")

        for theme_mode, buttons in self.color_buttons.items():
            for key, button in buttons.items():
                color_str = self.config["colors"][theme_mode][key]
                _apply_swatch_style(button, color_str)

        # Connect theme button signals after loading to avoid spurious updates
        self.theme_button_group.buttonClicked.connect(self._on_theme_changed)
        QTimer.singleShot(0, self._refresh_preview)

    def _on_theme_changed(self, btn):
        if btn is self.radio_light:
            self.config["theme"] = "light"
        elif btn is self.radio_dark:
            self.config["theme"] = "dark"
        else:
            self.config["theme"] = "system"
        self._refresh_preview()

    def pick_color(self, button, mode, key):
        current_color_str = self.config["colors"][mode][key]

        try:
            import importlib
            onigiri_color_picker = importlib.import_module("1011095603.onigiri_color_picker")
            OnigiriColorDialog = onigiri_color_picker.OnigiriColorDialog
            
            initial_hex = current_color_str
            if initial_hex.startswith("rgba"):
                try:
                    parts = initial_hex.replace("rgba(", "").replace(")", "").split(",")
                    r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                    initial_hex = f"#{r:02x}{g:02x}{b:02x}"
                except Exception:
                    initial_hex = "#FFFFFF"
            
            new_color_hex, ok = OnigiriColorDialog.getColor(initial_hex, self, anchor=button)
            if ok:
                self.config["colors"][mode][key] = new_color_hex
                _apply_swatch_style(button, new_color_hex)
                self._refresh_preview()
            return
        except Exception as e:
            print(f"Failed to load OnigiriColorDialog: {e}")
            initial_color = _parse_color(current_color_str)

            color = QColorDialog.getColor(
                initial_color, self,
                f"Choose {mode.title()} {key.replace('_', ' ')}",
                QColorDialog.ColorDialogOption.ShowAlphaChannel
                | QColorDialog.ColorDialogOption.DontUseNativeDialog,
            )

            if color.isValid():
                if color.alpha() == 255:
                    new_color_str = color.name().upper()
                else:
                    new_color_str = f"#{color.red():02X}{color.green():02X}{color.blue():02X}{color.alpha():02X}"

                self.config["colors"][mode][key] = new_color_str
                _apply_swatch_style(button, new_color_str)
                self._refresh_preview()

    def on_restore_defaults(self):
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.load_settings()

    def save_and_close(self):
        if self.radio_light.isChecked():
            self.config["theme"] = "light"
        elif self.radio_dark.isChecked():
            self.config["theme"] = "dark"
        else:
            self.config["theme"] = "system"

        self.config["background_opacity_percent"] = self.opacity_slider.value()
        bento_integration.save_settings_group(self.config, self.bento_width_spin, self.bento_height_spin)

        self.source_config.clear()
        self.source_config.update(self.config)
        mw.addonManager.writeConfig(self.addon_package, self.source_config)
        self.accept()

    def on_donate(self):
        QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/peacemonk"))

    def on_report_bug(self):
        QDesktopServices.openUrl(QUrl("https://github.com/thepeacemonk/Berry"))

    # ── Stylesheet (Onigiri pattern) ──────────────────────────────────────

    def _apply_stylesheet(self):
        t = self._theme_tokens()
        bg = t["bg"]
        panel = t["panel"]
        fg = t["fg"]
        muted = t["muted"]
        surface = t["surface"]
        border = t["border"]
        accent = t["accent"]

        accent_hex = accent.lstrip("#")
        accent_rgb = tuple(int(accent_hex[i:i+2], 16) for i in (0, 2, 4))
        scrollbar_thumb = f"rgba({accent_rgb[0]}, {accent_rgb[1]}, {accent_rgb[2]}, 0.45)"
        scrollbar_thumb_hover = f"rgba({accent_rgb[0]}, {accent_rgb[1]}, {accent_rgb[2]}, 0.75)"

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {fg}; }}

            QWidget#previewWrapper {{
                background-color: transparent;
                border: none;
            }}

            /* Rounded content shell (right panel) */
            QFrame#controlsContainer {{
                background-color: transparent;
                border: none;
                border-top-left-radius: 28px;
                border-top-right-radius: 28px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QWidget#controlsOuter {{
                background-color: transparent;
            }}

            QScrollArea#controlsScroll {{
                background: transparent;
                border: none;
            }}
            QScrollArea#controlsScroll > QWidget {{
                background: transparent;
            }}

            /* Inner groups (rounded cards) */
            QWidget#innerGroup {{
                background-color: transparent;
                border: none;
                border-radius: 12px;
            }}

            /* Labels */
            QLabel {{ color: {fg}; font-size: 13px; }}

            /* Theme toggle pills */
            #themeToggleButton {{
                background-color: transparent;
                border: none;
                border-radius: 14px;
                padding: 4px 16px;
                font-size: 13px;
                font-weight: 600;
                color: {muted};
            }}
            #themeToggleButton:checked {{
                color: #ffffff;
            }}
            #themeToggleButton:hover:!checked {{
                color: {fg};
            }}

            /* Sliders */
            QSlider#berrySlider::groove:horizontal {{
                height: 18px;
                border-radius: 9px;
                background-color: {surface};
            }}
            QSlider#berrySlider::sub-page:horizontal {{
                background-color: {accent};
                border-radius: 9px;
            }}
            QSlider#berrySlider::handle:horizontal {{
                background-color: #ffffff;
                width: 12px;
                height: 12px;
                margin: 3px 3px;
                border-radius: 6px;
            }}

            /* General fallbacks */
            QPushButton {{
                background-color: {surface};
                color: {fg};
                border: 1px solid {border};
                padding: 6px 12px;
                margin: 0px;
                border-radius: 14px;
            }}
            QPushButton:hover {{ background-color: {border}; }}

            /* Support buttons */
            QPushButton#supportButton {{
                background-color: {surface};
                color: {fg};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 4px 12px;
                margin: 0px;
                font-size: 11px;
            }}
            QPushButton#supportButton:hover {{
                background-color: {border};
            }}

            /* Save / Cancel / Restore pills */
            QPushButton#saveButton {{
                background-color: {accent};
                color: #ffffff;
                border: none;
                border-radius: 18px;
                min-height: 36px;
                max-height: 36px;
                padding: 0px 14px;
                margin: 0px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#saveButton:hover {{ background-color: {accent}; }}

            QPushButton#cancelButton {{
                background-color: {surface};
                color: {fg};
                border: 1px solid {border};
                border-radius: 18px;
                min-height: 36px;
                max-height: 36px;
                padding: 0px 14px;
                margin: 0px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#cancelButton:hover {{ background-color: {border}; }}

            QWidget#bottomContainer {{
                background-color: transparent;
            }}

            QWidget#bottomPillBar {{
                background-color: {panel};
                border-radius: 28px;
                border: 1px solid {border};
            }}

            QGroupBox {{
                font-size: 15px;
                font-weight: bold;
                border: 1px solid {border};
                border-radius: 12px;
                margin-top: 10px;
                padding: 15px;
                color: {fg};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
            }}

            QSpinBox {{
                background-color: {panel};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 5px;
            }}

            /* Scrollbar */
            QScrollArea#controlsScroll QScrollBar:vertical {{
                background: {surface};
                width: 8px;
                margin: 0px;
                border: none;
            }}
            QScrollArea#controlsScroll QScrollBar::handle:vertical {{
                background: {scrollbar_thumb};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollArea#controlsScroll QScrollBar::handle:vertical:hover {{
                background: {scrollbar_thumb_hover};
            }}
            QScrollArea#controlsScroll QScrollBar::add-line:vertical,
            QScrollArea#controlsScroll QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollArea#controlsScroll QScrollBar::add-page:vertical,
            QScrollArea#controlsScroll QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
# ── Bento WebUI settings -----------------------------------------------------
# Keep the legacy Qt implementation above as a compatibility fallback when
# Onigiri is not installed.  When the Bento host is available this class name
# is intentionally replaced by the shared production-preview WebUI surface.
try:
    if getattr(mw, "onigiri_api", {}).get("id") != "1011095603":
        raise ImportError("Onigiri Bento API is not active")
    _bws = importlib.import_module("1011095603.api.widget_settings")
except Exception:
    _bws = None

if _bws is not None:
    class BerrySettingsDialog(_bws.BentoSettingsDialog):
        def __init__(self, parent=None, addon_package=None, config=None):
            package = addon_package or mw.addonManager.addonFromModule(__name__)
            source = config if isinstance(config, dict) else (mw.addonManager.getConfig(package) or {})

            def save(updated):
                source.clear()
                source.update(copy.deepcopy(updated))
                mw.addonManager.writeConfig(package, source)
                addon = importlib.import_module(__package__)
                if isinstance(getattr(addon, "addon_config", None), dict):
                    addon.addon_config.clear()
                    addon.addon_config.update(copy.deepcopy(updated))
                if getattr(mw, "state", "") == "deckBrowser":
                    mw.deckBrowser.refresh()

            def preview(updated, variant, theme):
                addon = importlib.import_module(__package__)
                devices = _PREVIEW_DEVICE_SETS.get(variant, _PREVIEW_DEVICE_SETS["devices"])
                dark = theme == "dark"
                css = addon.generate_css(dark, updated)
                body = addon.generate_html(devices, updated, is_dark=dark)
                wallpaper = bento_integration.main_menu_wallpaper(dark)
                return _bws.preview_document(body, css, dark=dark, wallpaper=wallpaper)

            color_fields = []
            labels = {
                "background": "Background", "title": "Title",
                "item_background": "Item background", "item_text": "Item text",
                "icon": "Icon", "empty_text": "Empty-state text",
            }
            for mode in ("light", "dark"):
                for key, label in labels.items():
                    color_fields.append(_bws.field(
                        f"colors.{mode}.{key}", f"{mode.title()} · {label}", "color",
                        default=DEFAULT_CONFIG["colors"][mode][key],
                    ))

            pages = [
                _bws.page("appearance", "Appearance", [
                    _bws.section("Widget surface", [
                        _bws.field("widget_title", "Title", default="Bluetooth Devices"),
                        _bws.field("theme", "Theme", "select", default="system", options=[
                            {"value": "system", "label": "System"},
                            {"value": "light", "label": "Light"},
                            {"value": "dark", "label": "Dark"},
                        ]),
                        _bws.field("background_opacity_percent", "Background opacity", "range", default=100, minimum=0, maximum=100, unit="%"),
                    ]),
                    _bws.section("Light and dark colors", color_fields,
                                 "The preview uses Berry's production CSS and device markup."),
                ], "Colors and behavior for the Bluetooth device card.", "B"),
            ]
            super().__init__(
                parent, title="Berry", subtitle="Bluetooth devices at a glance",
                accent="#BD87FA", pages=pages, config=source, defaults=DEFAULT_CONFIG,
                save_callback=save, preview_callback=preview,
                logo_path=os.path.join(os.path.dirname(__file__), "berry_logo.svg"),
                mini_logo_path=os.path.join(os.path.dirname(__file__), "berry_mini_logo.svg"),
                preview_variants=[{"value": "devices", "label": "Devices"}, {"value": "empty", "label": "Empty"}],
                bugs_url="https://github.com/thepeacemonk/Berry",
            )
