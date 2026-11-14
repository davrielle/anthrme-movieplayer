import json
import os
import re
import sys
import time
import locale

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = BASE_DIR + os.pathsep + os.environ["PATH"]

import mpv
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QSlider, QLabel, QListWidget, QMenu, QMessageBox,
)

from discord_rpc import DiscordRPC

"== Konstanta =="
APP_TITLE = "anthrme-MOVIEPLAYER"
VIDEO_EXT = (
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
    ".ts", ".mts", ".m2ts", ".mpg", ".mpeg", ".3gp", ".ogv",
)
FILE_FILTER = "Video (" + " ".join("*" + e for e in VIDEO_EXT) + ");;Semua file (*.*)"
DATA_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "anthrme-MOVIEPLAYER")
os.makedirs(DATA_DIR, exist_ok=True)
RESUME_FILE = os.path.join(DATA_DIR, "resume.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")
SHOT_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "anthrme-MOVIEPLAYER")
SERVER_NAME = "anthrme-movieplayer-instance"

SKIP_SECONDS = 5
BAR_HIDE_DELAY = 3
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

ACCENT = "#7FDB5A"

"== Tema =="
THEME = f"""
QMainWindow, QWidget {{
    background-color: #0f1115;
    color: #e6e6e6;
    font-family: "Segoe UI";
    font-size: 13px;
}}
QLabel {{ background: transparent; }}

QPushButton {{
    background-color: #1a1d24;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background-color: {ACCENT}; color: #0f1115; }}
QPushButton::menu-indicator {{ image: none; width: 0px; }}

QPushButton#primary {{
    background-color: {ACCENT};
    color: #0f1115;
    border: none;
    font-weight: bold;
    min-width: 44px;
}}
QPushButton#primary:hover {{ background-color: #9be87b; color: #0f1115; }}

QSlider::groove:horizontal {{
    height: 6px; background: #2a2f3a; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT}; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: white; width: 14px; height: 14px;
    margin: -4px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}

QListWidget {{
    background-color: #151820;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background-color: #1f2430; }}
QListWidget::item:selected {{ background-color: {ACCENT}; color: #0f1115; }}

QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{
    background: #2a2f3a; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QMenu {{
    background-color: #151820;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 26px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: {ACCENT}; color: #0f1115; }}
QMenu::separator {{ height: 1px; background: #2a2f3a; margin: 6px 4px; }}

QToolTip {{
    background-color: #151820;
    color: #e6e6e6;
    border: 1px solid #2a2f3a;
    padding: 4px 8px;
}}

QFrame#fsbar {{
    background-color: #0f1115;
    border: 1px solid #2a2f3a;
    border-radius: 12px;
}}
"""


"== Fungsi bantu =="
def format_time(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def track_label(track):
    parts = []
    lang = track.get("lang")
    if lang:
        parts.append(str(lang).upper())
    title = track.get("title")
    if title:
        parts.append(str(title))
    codec = track.get("codec")
    if codec:
        parts.append(str(codec))
    text = " · ".join(parts) if parts else "Track"
    return f"{track.get('id')}. {text}"


"== Registrasi Open with di Windows =="
def registry_delete_tree(root, path):
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub = winreg.EnumKey(key, 0)
                except OSError:
                    break
                registry_delete_tree(root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def registry_register(exe_path):
    import ctypes
    import winreg
    app_key = "Software\\Classes\\Applications\\" + os.path.basename(exe_path)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app_key) as key:
        winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, APP_TITLE)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app_key + "\\DefaultIcon") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app_key + "\\shell\\open\\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app_key + "\\SupportedTypes") as key:
        for ext in VIDEO_EXT:
            winreg.SetValueEx(key, ext, 0, winreg.REG_SZ, "")
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def registry_unregister(exe_path):
    import ctypes
    import winreg
    app_key = "Software\\Classes\\Applications\\" + os.path.basename(exe_path)
    registry_delete_tree(winreg.HKEY_CURRENT_USER, app_key)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


"== Satu instance: kirim file ke app yang sudah jalan =="
def forward_to_running_instance(paths):
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write("\n".join(paths).encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


"== Notifikasi kecil =="
class Toast(QLabel):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel { background-color: rgba(15, 17, 21, 235); color: white;"
            " border: 1px solid #2a2f3a; border-radius: 10px;"
            " padding: 10px 22px; font-size: 14px; }"
        )
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def popup(self, text, area):
        self.setText(text)
        self.adjustSize()
        x = area.left() + (area.width() - self.width()) // 2
        y = area.top() + 40
        self.move(x, y)
        self.show()
        self.raise_()
        self.hide_timer.start(1800)


class Player(QMainWindow):
    fullscreen_toggled = Signal()
    fullscreen_exited = Signal()
    speed_up_req = Signal()
    speed_down_req = Signal()
    shot_req = Signal()

    def __init__(self, server=None):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1320, 720)
        self.setAcceptDrops(True)

        "== State =="
        self.server = server
        self.playlist = []
        self.index = -1
        self.current_path = None
        self.current_title = None
        self.was_playing = False
        self.last_save = 0
        self.last_remote = 0
        self.speed_index = SPEEDS.index(1.0)
        self.panel_visible = True
        self.last_cursor_pos = QCursor.pos()
        self.last_cursor_move = 0
        self.resume = self.load_resume()
        self.toast = Toast()

        "== Area video =="
        self.video = QWidget()
        self.video.setAttribute(Qt.WA_NativeWindow)
        self.video.setStyleSheet("background-color: black;")

        "== Tombol kontrol =="
        self.btn_open = QPushButton("Open")
        self.btn_prev = QPushButton("⏮")
        self.btn_back = QPushButton(f"« {SKIP_SECONDS}s")
        self.btn_play = QPushButton("▶")
        self.btn_fwd = QPushButton(f"{SKIP_SECONDS}s »")
        self.btn_next = QPushButton("⏭")
        self.btn_speed = QPushButton("1x")
        self.btn_audio = QPushButton("Audio")
        self.btn_sub = QPushButton("Sub")
        self.btn_shot = QPushButton("📷")
        self.btn_more = QPushButton("⋯")
        self.btn_list = QPushButton("☰")
        self.btn_full = QPushButton("⛶")

        self.btn_play.setObjectName("primary")
        self.btn_speed.setToolTip("Kecepatan putar ( [ dan ] )")
        self.btn_audio.setToolTip("Pilih audio track")
        self.btn_sub.setToolTip("Pilih subtitle")
        self.btn_shot.setToolTip("Screenshot (S)")
        self.btn_more.setToolTip("Menu lainnya")
        self.btn_list.setToolTip("Tampilkan / sembunyikan playlist")
        self.btn_full.setToolTip("Fullscreen (F)")

        self.btn_open.clicked.connect(self.open_files)
        self.btn_prev.clicked.connect(self.play_prev)
        self.btn_back.clicked.connect(lambda: self.skip(-SKIP_SECONDS))
        self.btn_play.clicked.connect(self.toggle_pause)
        self.btn_fwd.clicked.connect(lambda: self.skip(SKIP_SECONDS))
        self.btn_next.clicked.connect(self.play_next)
        self.btn_speed.clicked.connect(self.cycle_speed)
        self.btn_shot.clicked.connect(self.take_screenshot)
        self.btn_list.clicked.connect(self.toggle_panel)
        self.btn_full.clicked.connect(self.toggle_fullscreen)

        "== Menu audio, subtitle, lainnya =="
        self.audio_menu = QMenu(self)
        self.audio_menu.aboutToShow.connect(self.fill_audio_menu)
        self.btn_audio.setMenu(self.audio_menu)

        self.sub_menu = QMenu(self)
        self.sub_menu.aboutToShow.connect(self.fill_sub_menu)
        self.btn_sub.setMenu(self.sub_menu)

        self.more_menu = QMenu(self)
        register_action = self.more_menu.addAction("Daftarkan ke menu 'Open with' Windows")
        register_action.triggered.connect(self.register_open_with)
        unregister_action = self.more_menu.addAction("Hapus dari menu 'Open with'")
        unregister_action.triggered.connect(self.unregister_open_with)
        self.more_menu.addSeparator()
        folder_action = self.more_menu.addAction("Buka folder screenshot")
        folder_action.triggered.connect(self.open_shot_folder)
        self.btn_more.setMenu(self.more_menu)

        "== Seek bar, waktu, volume =="
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(lambda: self.on_seek(self.seek))
        self.time_label = QLabel("00:00 / 00:00")

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(110)
        self.volume.valueChanged.connect(self.on_volume)

        "== Susunan bar kontrol (2 baris) =="
        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        seek_row.addWidget(self.seek, stretch=1)
        seek_row.addWidget(self.time_label)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        for widget in (self.btn_open, self.btn_prev, self.btn_back,
                       self.btn_play, self.btn_fwd, self.btn_next):
            buttons_row.addWidget(widget)
        buttons_row.addStretch(1)
        buttons_row.addWidget(QLabel("Vol"))
        buttons_row.addWidget(self.volume)
        for widget in (self.btn_speed, self.btn_audio, self.btn_sub, self.btn_shot,
                       self.btn_more, self.btn_list, self.btn_full):
            buttons_row.addWidget(widget)

        self.controls_bar = QWidget()
        controls = QVBoxLayout(self.controls_bar)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addLayout(seek_row)
        controls.addLayout(buttons_row)

        "== Panel playlist =="
        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(
            lambda item: self.play_index(self.playlist_widget.row(item))
        )
        self.btn_add = QPushButton("Add")
        self.btn_clear = QPushButton("Clear")
        self.btn_add.clicked.connect(self.add_files_dialog)
        self.btn_clear.clicked.connect(self.clear_playlist)

        self.side_panel = QWidget()
        side = QVBoxLayout(self.side_panel)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(QLabel("Playlist (double click buat putar)"))
        side.addWidget(self.playlist_widget, stretch=1)
        side_buttons = QHBoxLayout()
        side_buttons.addWidget(self.btn_add)
        side_buttons.addWidget(self.btn_clear)
        side.addLayout(side_buttons)
        self.side_panel.setFixedWidth(260)

        "== Susunan utama =="
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self.video, stretch=1)
        left.addWidget(self.controls_bar)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left, stretch=1)
        main_layout.addWidget(self.side_panel)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        "== Bar kontrol fullscreen =="
        self.fs_bar = QFrame()
        self.fs_bar.setObjectName("fsbar")
        self.fs_bar.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.fs_bar.setAttribute(Qt.WA_ShowWithoutActivating)

        self.fs_prev = QPushButton("⏮")
        self.fs_back = QPushButton(f"« {SKIP_SECONDS}s")
        self.fs_play = QPushButton("▶")
        self.fs_fwd = QPushButton(f"{SKIP_SECONDS}s »")
        self.fs_next = QPushButton("⏭")
        self.fs_speed = QPushButton("1x")
        self.fs_shot = QPushButton("📷")
        self.fs_exit = QPushButton("✕ Exit")
        self.fs_play.setObjectName("primary")
        for button in (self.fs_prev, self.fs_back, self.fs_play, self.fs_fwd,
                       self.fs_next, self.fs_speed, self.fs_shot, self.fs_exit):
            button.setFocusPolicy(Qt.NoFocus)

        self.fs_prev.clicked.connect(self.play_prev)
        self.fs_back.clicked.connect(lambda: self.skip(-SKIP_SECONDS))
        self.fs_play.clicked.connect(self.toggle_pause)
        self.fs_fwd.clicked.connect(lambda: self.skip(SKIP_SECONDS))
        self.fs_next.clicked.connect(self.play_next)
        self.fs_speed.clicked.connect(self.cycle_speed)
        self.fs_shot.clicked.connect(self.take_screenshot)
        self.fs_exit.clicked.connect(self.exit_fullscreen)

        self.fs_seek = QSlider(Qt.Horizontal)
        self.fs_seek.setRange(0, 1000)
        self.fs_seek.sliderReleased.connect(lambda: self.on_seek(self.fs_seek))
        self.fs_time = QLabel("00:00 / 00:00")

        self.fs_volume = QSlider(Qt.Horizontal)
        self.fs_volume.setRange(0, 100)
        self.fs_volume.setValue(self.volume.value())
        self.fs_volume.setFixedWidth(100)
        self.fs_volume.valueChanged.connect(self.on_volume)

        fs_layout = QHBoxLayout(self.fs_bar)
        fs_layout.setContentsMargins(14, 10, 14, 10)
        fs_layout.setSpacing(8)
        for widget in (self.fs_prev, self.fs_back, self.fs_play, self.fs_fwd,
                       self.fs_next, self.fs_speed, self.fs_shot):
            fs_layout.addWidget(widget)
        fs_layout.addWidget(self.fs_seek, stretch=1)
        fs_layout.addWidget(self.fs_time)
        fs_layout.addWidget(QLabel("Vol"))
        fs_layout.addWidget(self.fs_volume)
        fs_layout.addWidget(self.fs_exit)

        "== Mesin mpv =="
        self.player = mpv.MPV(
            wid=str(int(self.video.winId())),
            input_default_bindings=True,
            input_vo_keyboard=True,
            sub_auto="fuzzy",
            idle=True,
            screenshot_format="png",
        )
        self.player.volume = self.volume.value()

        "== Shortcut keyboard dari mpv =="
        self.fullscreen_toggled.connect(self.toggle_fullscreen)
        self.fullscreen_exited.connect(self.exit_fullscreen)
        self.speed_up_req.connect(self.speed_up)
        self.speed_down_req.connect(self.speed_down)
        self.shot_req.connect(self.take_screenshot)
        self.player.register_key_binding("f", self._on_key_f)
        self.player.register_key_binding("ESC", self._on_key_esc)
        self.player.register_key_binding("MBTN_LEFT_DBL", self._on_key_f)
        self.player.register_key_binding("]", self._on_key_speed_up)
        self.player.register_key_binding("[", self._on_key_speed_down)
        self.player.register_key_binding("s", self._on_key_shot)

        "== Server satu instance =="
        if self.server is not None:
            self.server.newConnection.connect(self.on_remote_connection)

        "== Timer kursor =="
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self.check_cursor)
        self.cursor_timer.start(100)

        "== Discord Rich Presence =="
        self.rpc = DiscordRPC()
        self.rpc.connect()

        "== Timer utama =="
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

    "== Resume =="
    def load_resume(self):
        try:
            with open(RESUME_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_resume_file(self):
        try:
            with open(RESUME_FILE, "w", encoding="utf-8") as f:
                json.dump(self.resume, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Gagal simpan resume:", e)

    def remember_position(self):
        if not self.current_path:
            return
        pos = self.player.time_pos
        dur = self.player.duration
        if pos is None or not dur:
            return
        if pos < 10 or pos > dur - 10:
            self.resume.pop(self.current_path, None)
        else:
            self.resume[self.current_path] = int(pos)
        self.save_resume_file()

    "== Open with dan satu instance =="
    def open_initial(self, paths):
        self.last_remote = time.time()
        QTimer.singleShot(300, lambda: self.add_files(paths, replace=True))

    def on_remote_connection(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.disconnected.connect(conn.deleteLater)
        conn.waitForReadyRead(500)
        raw = bytes(conn.readAll()).decode("utf-8", errors="ignore")
        conn.disconnectFromServer()
        paths = [p for p in raw.split("\n") if p]
        if not paths:
            return
        now = time.time()
        replace = now - self.last_remote > 1.5
        self.last_remote = now
        self.add_files(sorted(paths), replace=replace)
        self.bring_to_front()

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def register_open_with(self):
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self, APP_TITLE, "Fitur ini cuma jalan di versi .exe hasil build."
            )
            return
        try:
            registry_register(sys.executable)
            QMessageBox.information(
                self,
                APP_TITLE,
                "Berhasil didaftarkan.\n\nKlik kanan video, pilih Open with, lalu "
                "Choose another app, pilih anthrme-MOVIEPLAYER, dan centang "
                "Always kalau mau dijadikan default.",
            )
        except Exception as e:
            QMessageBox.warning(self, APP_TITLE, f"Gagal mendaftarkan: {e}")

    def unregister_open_with(self):
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self, APP_TITLE, "Fitur ini cuma jalan di versi .exe hasil build."
            )
            return
        try:
            registry_unregister(sys.executable)
            QMessageBox.information(self, APP_TITLE, "Sudah dihapus dari menu Open with.")
        except Exception as e:
            QMessageBox.warning(self, APP_TITLE, f"Gagal menghapus: {e}")

    "== Playlist =="
    def add_files(self, paths, replace=False):
        paths = [p for p in paths if p.lower().endswith(VIDEO_EXT)]
        if not paths:
            return

        if replace:
            self.playlist.clear()
            self.playlist_widget.clear()

        first_new = len(self.playlist)
        for p in paths:
            self.playlist.append(p)
            self.playlist_widget.addItem(os.path.basename(p))

        if replace or self.current_path is None:
            self.play_index(first_new)

    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Pilih video", "", FILE_FILTER)
        if paths:
            self.add_files(paths, replace=True)

    def add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Tambah ke playlist", "", FILE_FILTER)
        if paths:
            self.add_files(paths)

    def play_index(self, index):
        if not (0 <= index < len(self.playlist)):
            return

        self.remember_position()

        path = self.playlist[index]
        self.index = index
        self.current_path = path
        self.current_title = os.path.splitext(os.path.basename(path))[0]
        self.setWindowTitle(f"{self.current_title} - {APP_TITLE}")
        self.was_playing = False

        start = self.resume.get(path)
        try:
            self.player["start"] = str(int(start)) if start else "none"
        except Exception:
            pass

        self.player.play(path)
        self.playlist_widget.setCurrentRow(index)

    def play_next(self):
        if self.index + 1 < len(self.playlist):
            self.play_index(self.index + 1)

    def play_prev(self):
        pos = self.player.time_pos or 0
        if pos > 5 or self.index <= 0:
            if self.current_path:
                self.player.seek(0, reference="absolute")
        else:
            self.play_index(self.index - 1)

    def clear_playlist(self):
        self.remember_position()
        self.player.stop()
        self.playlist.clear()
        self.playlist_widget.clear()
        self.index = -1
        self.current_path = None
        self.current_title = None
        self.was_playing = False
        self.setWindowTitle(APP_TITLE)

    def on_file_finished(self):
        self.resume.pop(self.current_path, None)
        self.save_resume_file()

        if self.index + 1 < len(self.playlist):
            self.play_index(self.index + 1)
        else:
            self.current_path = None
            self.current_title = None
            self.was_playing = False
            self.setWindowTitle(APP_TITLE)
            self.seek.setValue(0)
            self.fs_seek.setValue(0)
            self.time_label.setText("00:00 / 00:00")
            self.fs_time.setText("00:00 / 00:00")

    "== Keyboard dari mpv =="
    def _on_key_f(self, state, name, char):
        if state[0] in ("d", "p"):
            self.fullscreen_toggled.emit()

    def _on_key_esc(self, state, name, char):
        if state[0] in ("d", "p"):
            self.fullscreen_exited.emit()

    def _on_key_speed_up(self, state, name, char):
        if state[0] in ("d", "p"):
            self.speed_up_req.emit()

    def _on_key_speed_down(self, state, name, char):
        if state[0] in ("d", "p"):
            self.speed_down_req.emit()

    def _on_key_shot(self, state, name, char):
        if state[0] in ("d", "p"):
            self.shot_req.emit()

    "== Drag and drop =="
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.add_files(sorted(paths))

    "== Kontrol dasar =="
    def toggle_pause(self):
        self.player.pause = not self.player.pause

    def skip(self, seconds):
        if self.current_path:
            self.player.seek(seconds, reference="relative")

    def on_volume(self, value):
        self.player.volume = value
        for slider in (self.volume, self.fs_volume):
            if slider.value() != value:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)

    def on_seek(self, slider):
        duration = self.player.duration
        if duration:
            target = slider.value() / 1000 * duration
            self.player.seek(target, reference="absolute")

    "== Kecepatan putar =="
    def apply_speed(self, index):
        index = max(0, min(len(SPEEDS) - 1, index))
        self.speed_index = index
        value = SPEEDS[index]
        self.player.speed = value
        text = f"{value:g}x"
        self.btn_speed.setText(text)
        self.fs_speed.setText(text)
        self.show_toast(f"Kecepatan {text}")

    def cycle_speed(self):
        self.apply_speed((self.speed_index + 1) % len(SPEEDS))

    def speed_up(self):
        self.apply_speed(self.speed_index + 1)

    def speed_down(self):
        self.apply_speed(self.speed_index - 1)

    "== Screenshot =="
    def take_screenshot(self):
        if not self.current_path:
            self.show_toast("Belum ada video")
            return
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            name = re.sub(r'[\\/:*?"<>|]', "_", f"{self.current_title}_{stamp}.png")
            path = os.path.join(SHOT_DIR, name)
            self.player.screenshot_to_file(path, includes="subtitles")
            self.show_toast("Screenshot tersimpan")
        except Exception as e:
            self.show_toast("Screenshot gagal")
            print("Screenshot gagal:", e)

    def open_shot_folder(self):
        os.makedirs(SHOT_DIR, exist_ok=True)
        os.startfile(SHOT_DIR)

    "== Audio dan subtitle =="
    def fill_audio_menu(self):
        self.fill_track_menu(self.audio_menu, "audio", "aid")

    def fill_sub_menu(self):
        self.fill_track_menu(self.sub_menu, "sub", "sid")
        self.sub_menu.addSeparator()
        load_action = self.sub_menu.addAction("Muat subtitle dari file...")
        load_action.triggered.connect(self.load_subtitle_file)

    def fill_track_menu(self, menu, kind, prop):
        menu.clear()
        try:
            all_tracks = self.player.track_list or []
        except Exception:
            all_tracks = []
        tracks = [t for t in all_tracks if t.get("type") == kind]

        off_action = menu.addAction("Mati")
        off_action.setCheckable(True)
        off_action.setChecked(not any(t.get("selected") for t in tracks))
        off_action.triggered.connect(
            lambda checked=False, p=prop: setattr(self.player, p, "no")
        )

        for track in tracks:
            action = menu.addAction(track_label(track))
            action.setCheckable(True)
            action.setChecked(bool(track.get("selected")))
            action.triggered.connect(
                lambda checked=False, p=prop, tid=track["id"]: setattr(self.player, p, tid)
            )

    def load_subtitle_file(self):
        if not self.current_path:
            self.show_toast("Belum ada video")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih subtitle",
            "",
            "Subtitle (*.srt *.ass *.ssa *.vtt *.sub);;Semua file (*.*)",
        )
        if path:
            try:
                self.player.command("sub-add", path)
                self.show_toast("Subtitle dimuat")
            except Exception as e:
                self.show_toast("Subtitle gagal dimuat")
                print("Subtitle gagal:", e)

    "== Notifikasi =="
    def show_toast(self, text):
        area = self.screen().geometry() if self.isFullScreen() else self.geometry()
        self.toast.popup(text, area)

    "== Panel dan fullscreen =="
    def toggle_panel(self):
        self.panel_visible = not self.panel_visible
        self.side_panel.setVisible(self.panel_visible)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.controls_bar.hide()
            self.side_panel.hide()
            self.showFullScreen()
            self.last_cursor_pos = QCursor.pos()
            self.last_cursor_move = time.time()
            self.show_fs_bar()

    def exit_fullscreen(self):
        self.fs_bar.hide()
        if self.isFullScreen():
            self.showNormal()
            self.controls_bar.show()
            self.side_panel.setVisible(self.panel_visible)

    def show_fs_bar(self):
        geo = self.screen().geometry()
        width = min(geo.width() - 80, 1250)
        self.fs_bar.setFixedWidth(width)
        self.fs_bar.adjustSize()
        x = geo.left() + (geo.width() - width) // 2
        y = geo.bottom() - self.fs_bar.height() - 40
        self.fs_bar.move(x, y)
        self.fs_bar.show()
        self.fs_bar.raise_()

    def check_cursor(self):
        if not self.isFullScreen():
            if self.fs_bar.isVisible():
                self.fs_bar.hide()
            return

        pos = QCursor.pos()
        now = time.time()

        if pos != self.last_cursor_pos:
            self.last_cursor_pos = pos
            self.last_cursor_move = now
            if not self.fs_bar.isVisible():
                self.show_fs_bar()
        elif self.fs_bar.isVisible():
            over_bar = self.fs_bar.geometry().contains(pos)
            busy = self.fs_seek.isSliderDown() or self.fs_volume.isSliderDown()
            if now - self.last_cursor_move > BAR_HIDE_DELAY and not over_bar and not busy:
                self.fs_bar.hide()

    "== Update UI dan Discord =="
    def update_ui(self):
        pos = self.player.time_pos
        dur = self.player.duration

        if pos is not None:
            self.was_playing = True
        elif self.current_path and self.was_playing and self.player.idle_active:
            self.on_file_finished()
            return

        value = int(pos / dur * 1000) if (pos is not None and dur) else None
        if value is not None and not self.seek.isSliderDown():
            self.seek.setValue(value)
        if value is not None and not self.fs_seek.isSliderDown():
            self.fs_seek.setValue(value)

        text = f"{format_time(pos)} / {format_time(dur)}"
        self.time_label.setText(text)
        self.fs_time.setText(text)

        playing = pos is not None and not self.player.pause
        icon = "⏸" if playing else "▶"
        self.btn_play.setText(icon)
        self.fs_play.setText(icon)

        if pos is not None and time.time() - self.last_save > 5:
            self.last_save = time.time()
            self.remember_position()

        if self.current_title and pos is not None:
            self.rpc.update(self.current_title, bool(self.player.pause), pos, dur)
        else:
            self.rpc.clear()

    def closeEvent(self, event):
        self.toast.close()
        self.fs_bar.close()
        self.cursor_timer.stop()
        self.timer.stop()
        self.remember_position()
        self.rpc.close()
        if self.server is not None:
            self.server.close()
        self.player.terminate()
        event.accept()


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "anthrme.movieplayer"
        )
    except Exception:
        pass

    paths = sorted(os.path.abspath(a) for a in sys.argv[1:] if os.path.isfile(a))

    app = QApplication(sys.argv)
    if paths and forward_to_running_instance(paths):
        sys.exit(0)

    app.setStyleSheet(THEME)
    app.setWindowIcon(QIcon(ICON_PATH))
    locale.setlocale(locale.LC_NUMERIC, "C")

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    window = Player(server)
    window.show()
    if paths:
        window.open_initial(paths)
    sys.exit(app.exec())