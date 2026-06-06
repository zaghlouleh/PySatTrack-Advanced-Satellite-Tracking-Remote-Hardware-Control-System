#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import random
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QStackedLayout, QSizePolicy, QGraphicsOpacityEffect)
from PyQt5.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from src.utils.logger import logger

script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class BackgroundManager:
    """Manages background images and videos for dialogs with proper transparency effects"""
    
    def __init__(self):
        self.photo_path = os.path.join(script_dir, "Photo")
        self.video_path = os.path.join(script_dir, "video")
        self.html_video_path = os.path.join(script_dir, "assets", "video", "background_video.html")
        self.current_dialog = None
        
        self.image_files = []
        self.video_files = []
        
        self.current_image_index = 0
        self.slideshow_timer = None
        self.slideshow_delay = 5000

        self.background_mode = None
        self.cached_video_widget = None
        
        self._load_background_files()
        self._select_background_mode()
        
        # Verify if video file targets exist in the video directory
        if self.background_mode == 'video' and self.video_files:
            logger.info("Pre-creating QWebEngineView for video background.")
            self.cached_video_widget = self._create_video_background()

        logger.info(f"Background mode determined: '{self.background_mode}'")
    
    def _load_background_files(self):
        self.image_files = []
        self.video_files = []
        
        if os.path.exists(self.photo_path):
            for file in sorted(os.listdir(self.photo_path)):
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    self.image_files.append(os.path.join(self.photo_path, file))
        
        # if os.path.exists(self.video_path):
        #     for file in sorted(os.listdir(self.video_path)):
        #         if file.lower().endswith(('.mp4', '.avi', '.mov', '.wmv', '.mkv')):
        #             self.video_files.append(os.path.join(self.video_path, file))

    def _select_background_mode(self):
        available_modes = []
        if self.image_files:
            available_modes.append('image')
        if self.video_files:
            available_modes.append('video')

        self.background_mode = random.choice(available_modes) if available_modes else None

    def setup_dialog_background(self, dialog, force_mode=None):
        try:
            self.current_dialog = dialog
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
            dialog.setAttribute(Qt.WA_TranslucentBackground, False)
            
            if hasattr(dialog, 'service_display_name'):
                # Login-specific sizing (keep TLE source selection unchanged)
                initial_width, initial_height = 600, 500
            else:
                initial_width, initial_height = 950, 650
            x = (screen_geometry.width() - initial_width) // 2
            y = (screen_geometry.height() - initial_height) // 2
            dialog.setGeometry(x, y, initial_width, initial_height)
            dialog.setMinimumSize(300, 200)
            
            main_layout = QVBoxLayout(dialog)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            
            background_container = QWidget()
            background_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            background_container.setStyleSheet("border-radius: 15px;")
            background_container.setAutoFillBackground(False)

            bg_layout = QStackedLayout(background_container)
            bg_layout.setStackingMode(QStackedLayout.StackAll)
            
            background_widget = None
            if self.background_mode == 'image' and self.image_files:
                initial_image_path = random.choice(self.image_files)
                background_widget = self._create_image_background(initial_image_path, dialog.size())
                self._start_slideshow(dialog)
            elif self.background_mode == 'video' and self.cached_video_widget:
                logger.info("Using pre-cached video widget.")
                background_widget = self.cached_video_widget
                # Inject video source
                if self.video_files:
                    video_url = QUrl.fromLocalFile(random.choice(self.video_files))
                    js = f"document.getElementById('bgvid').src = '{video_url.toString()}'; document.getElementById('bgvid').muted = true; document.getElementById('bgvid').loop = true; document.getElementById('bgvid').load(); document.getElementById('bgvid').play();"
                    background_widget.loadFinished.connect(lambda: background_widget.page().runJavaScript(js))

            if background_widget:
                bg_layout.addWidget(background_widget)
            else:
                logger.warning("No background media found.")

            # Content overlay
            content_overlay = QWidget()
            content_overlay.setAttribute(Qt.WA_TranslucentBackground)
            content_overlay.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            overlay_layout = QVBoxLayout(content_overlay)
            overlay_layout.setContentsMargins(0, 0, 0, 0)
            overlay_layout.addStretch()
            
            content_container = QWidget()
            content_container.setObjectName("contentContainer")
            if hasattr(dialog, 'service_display_name'):
                # Keep login compact; do not affect larger dialogs (e.g. TLE source selection)
                content_container.setMinimumSize(500, 400)
            else:
                content_container.setMinimumSize(700, 600)
            self._apply_dialog_styling(content_container)
            
            content_layout = QVBoxLayout(content_container)
            content_layout.setContentsMargins(30, 30, 30, 30)
            overlay_layout.addWidget(content_container, 0, Qt.AlignCenter)
            overlay_layout.addStretch()
            
            final_stacked_layout = QStackedLayout()
            final_stacked_layout.setStackingMode(QStackedLayout.StackAll)
            final_stacked_layout.addWidget(background_container)
            final_stacked_layout.addWidget(content_overlay)
            
            container = QWidget()
            container.setLayout(final_stacked_layout)
            main_layout.addWidget(container)
            
            dialog.content_layout = content_layout
            dialog.content_container = content_container
            dialog.background_container = background_container
            dialog._bg_manager = self
            
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            logger.info("Dialog background setup completed.")
            return True
            
        except Exception as e:
            logger.error(f"Background setup error: {e}")
            return self._setup_fallback_dialog(dialog)

    def _start_slideshow(self, dialog):
        if len(self.image_files) <= 1:
            return
        if self.slideshow_timer:
            self.slideshow_timer.stop()
            self.slideshow_timer.deleteLater()
        self.slideshow_timer = QTimer(dialog)
        self.slideshow_timer.timeout.connect(lambda: self._next_background(dialog))
        self.slideshow_timer.start(self.slideshow_delay)

    def _next_background(self, dialog):
        if not self.image_files or not hasattr(dialog, 'background_container'):
            return
        bg_layout = dialog.background_container.layout()
        if not isinstance(bg_layout, QStackedLayout):
            return
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
        image_path = self.image_files[self.current_image_index]
        if os.path.exists(image_path):
            new_background = self._create_image_background(image_path, dialog.size())
            if new_background:
                opacity_effect = QGraphicsOpacityEffect()
                new_background.setGraphicsEffect(opacity_effect)
                opacity_effect.setOpacity(0.0)
                old_background = bg_layout.currentWidget()
                bg_layout.addWidget(new_background)
                bg_layout.setCurrentWidget(new_background)
                fade_animation = QPropertyAnimation(opacity_effect, b"opacity")
                fade_animation.setDuration(3000)
                fade_animation.setStartValue(0.0)
                fade_animation.setEndValue(1.0)
                fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
                new_background.animation = fade_animation
                if old_background:
                    fade_animation.finished.connect(old_background.deleteLater)
                fade_animation.start(QPropertyAnimation.DeleteWhenStopped)

    def _create_image_background(self, image_path, container_size):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None
        background_label = QLabel()
        scaled_pixmap = pixmap.scaled(container_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        background_label.setPixmap(scaled_pixmap)
        background_label.setAlignment(Qt.AlignCenter)
        return background_label

    def _create_video_background(self):
        try:
            web_view = QWebEngineView()
            web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # if not os.path.exists(self.html_video_path):
            #     logger.error(f"HTML not found: {self.html_video_path}")
            #     return None
            settings = web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
            settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, False)
            web_view.setContextMenuPolicy(Qt.NoContextMenu)
            web_view.page().javaScriptConsoleMessage.connect(lambda msg, line, source: logger.debug(f"VideoConsole [{source}:{line}]: {msg}"))
            # web_view.load(QUrl.fromLocalFile(self.html_video_path))
            return web_view
        except Exception as e:
            logger.error(f"Video background creation error: {e}")
            return None

    def _apply_dialog_styling(self, content_container):
        content_container.setStyleSheet("""
            QWidget#contentContainer {
                background: transparent;
                border: none;
            }
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            QGroupBox {
                background: rgba(25, 25, 35, 0.85);
                border: 1px solid rgba(100, 181, 246, 0.5);
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 15px;
                color: #E0E0E0;
                font-weight: bold;
                font-size: 11pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                padding: 2px 8px;
                background: rgba(40, 40, 50, 0.95);
                border: 1px solid rgba(100, 181, 246, 0.4);
                border-radius: 6px;
                color: #64B5F6;
                font-weight: bold;
            }
            QLabel { background: transparent; color: #FFFFFF; font-weight: normal; }
            QLabel#loginHeaderTitle { color: #64B5F6; background: transparent; }
            QLabel#loginHeaderSubtitle { color: #B0BEC5; background: transparent; }
            QCheckBox { background: transparent; color: #FFFFFF; spacing: 8px; }


            QCheckBox::indicator {
                width: 16px; height: 16px; border: 2px solid #64B5F6; border-radius: 3px;
                background: rgba(40, 40, 50, 0.8);
            }
            QCheckBox::indicator:checked { background: #64B5F6; border: 2px solid #64B5F6; }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(100, 181, 246, 0.8), stop:1 rgba(66, 133, 244, 0.8));
                border: 1px solid rgba(100, 181, 246, 0.6); border-radius: 8px;
                padding: 10px 20px; color: white; font-weight: bold; font-size: 10pt;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(120, 201, 255, 0.9), stop:1 rgba(86, 153, 255, 0.9));
                border: 1px solid rgba(120, 201, 255, 0.8);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(80, 161, 226, 0.9), stop:1 rgba(56, 123, 224, 0.9));
            }
            QLineEdit, QComboBox, QListWidget {
                background: rgba(30, 30, 40, 0.9); border: 2px solid rgba(100, 181, 246, 0.3);
                border-radius: 6px; padding: 8px 12px; color: #FFFFFF; font-size: 10pt;
                selection-background-color: rgba(100, 181, 246, 0.5);
            }
            QLineEdit:focus, QComboBox:focus { border: 2px solid rgba(100, 181, 246, 0.8); }
            QScrollBar:vertical { background: rgba(40, 40, 50, 0.8); width: 12px; margin: 0; border-radius: 6px; }
            QScrollBar::handle:vertical { background: rgba(100, 181, 246, 0.6); border-radius: 6px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: rgba(100, 181, 246, 0.8); }
        """)

    def _setup_fallback_dialog(self, dialog):
        dialog.setWindowFlags(Qt.Dialog)
        dialog.setAttribute(Qt.WA_TranslucentBackground, False)
        if hasattr(dialog, 'service_display_name'):
            dialog.setMinimumSize(500, 400)
            dialog.resize(500, 400)
        else:
            dialog.setMinimumSize(700, 600)
            dialog.resize(700, 600)
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = (screen_geometry.width() - dialog.width()) // 2
        y = (screen_geometry.height() - dialog.height()) // 2
        dialog.move(x, y)
        dialog.setStyleSheet("""
            QDialog { background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #1a237e, stop: 0.5 #311b92, stop: 1 #4a148c); border-radius: 20px; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        dialog.content_layout = layout
        return True
