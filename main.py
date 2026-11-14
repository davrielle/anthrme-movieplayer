import json
import os
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
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QSlider, QLabel, QListWidget,
)

from discord_rpc import DiscordRPC

APP_TITLE = "anthrme-MOVIEPLAYER"
VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v")
FILE_FILTER = "Video (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v);;Semua file (*.*)"
DATA_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "anthrme-MOVIEPLAYER")
os.makedirs(DATA_DIR, exist_ok=True)
RESUME_FILE = os.path.join(DATA_DIR, "resume.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")

SKIP_SECONDS = 5          # lompat maju/mundur berapa detik
BAR_HIDE_DELAY = 3        # detik: bar fullscreen ngilang kalau mouse diem

ACCENT = "#7FDB5A"   # hijau logo lu, ganti kode warna ini buat ngubah aksen

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

QFrame#fsbar {{
    background-color: #0f1115;
    border: 1px solid #2a2f3a;
    border-radius: 12px;
}}
"""


def format_time(seconds):
    """Ubah detik jadi format mm:ss atau hh:mm:ss."""
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Player(QMainWindow):
    # Signal dipakai karena tombol mpv dipanggil dari thread lain,
    # sedangkan UI Qt cuma boleh diubah dari thread utama
    fullscreen_toggled = Signal()
    fullscreen_exited = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1200, 640)
        self.setAcceptDrops(True)

        # ---------- State ----------
        self.playlist = []          # daftar path video
        self.index = -1             # urutan video yang lagi diputar
        self.current_path = None
        self.current_title = None
        self.was_playing = False    # dipakai buat deteksi video selesai
        self.last_save = 0
        self.panel_visible = True
        self.last_cursor_pos = QCursor.pos()
        self.last_cursor_move = 0
        self.resume = self.load_resume()

        # ---------- Area video ----------
        self.video = QWidget()
        self.video.setAttribute(Qt.WA_NativeWindow)
        self.video.setStyleSheet("background-color: black;")

        # ---------- Tombol kontrol (mode biasa) ----------
        self.btn_open = QPushButton("Open")
        self.btn_prev = QPushButton("⏮")
        self.btn_back = QPushButton(f"« {SKIP_SECONDS}s")
        self.btn_play = QPushButton("▶")
        self.btn_fwd = QPushButton(f"{SKIP_SECONDS}s »")
        self.btn_next = QPushButton("⏭")
        self.btn_list = QPushButton("Playlist")
        self.btn_full = QPushButton("⛶ Fullscreen")

        self.btn_play.setObjectName("primary")

        self.btn_open.clicked.connect(self.open_files)
        self.btn_prev.clicked.connect(self.play_prev)
        self.btn_back.clicked.connect(lambda: self.skip(-SKIP_SECONDS))
        self.btn_play.clicked.connect(self.toggle_pause)
        self.btn_fwd.clicked.connect(lambda: self.skip(SKIP_SECONDS))
        self.btn_next.clicked.connect(self.play_next)
        self.btn_list.clicked.connect(self.toggle_panel)
        self.btn_full.clicked.connect(self.toggle_fullscreen)

        # Seek bar + waktu
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(lambda: self.on_seek(self.seek))
        self.time_label = QLabel("00:00 / 00:00")

        # Volume
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(110)
        self.volume.valueChanged.connect(self.on_volume)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.btn_open)
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_back)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_fwd)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.seek, stretch=1)
        controls.addWidget(self.time_label)
        controls.addWidget(QLabel("Vol"))
        controls.addWidget(self.volume)
        controls.addWidget(self.btn_list)
        controls.addWidget(self.btn_full)

        self.controls_bar = QWidget()
        self.controls_bar.setLayout(controls)

        # ---------- Panel playlist (kanan) ----------
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

        # ---------- Susunan utama ----------
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self.video, stretch=1)
        left.addWidget(self.controls_bar)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left, stretch=1)
        main_layout.addWidget(self.side_panel)

        central = QWidget()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # ---------- Bar kontrol fullscreen (jendela terpisah, selalu di atas) ----------
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
        self.fs_exit = QPushButton("✕ Exit")
        self.fs_play.setObjectName("primary")
        for b in (self.fs_prev, self.fs_back, self.fs_play,
                  self.fs_fwd, self.fs_next, self.fs_exit):
            b.setFocusPolicy(Qt.NoFocus)

        self.fs_prev.clicked.connect(self.play_prev)
        self.fs_back.clicked.connect(lambda: self.skip(-SKIP_SECONDS))
        self.fs_play.clicked.connect(self.toggle_pause)
        self.fs_fwd.clicked.connect(lambda: self.skip(SKIP_SECONDS))
        self.fs_next.clicked.connect(self.play_next)
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
        fs_layout.addWidget(self.fs_prev)
        fs_layout.addWidget(self.fs_back)
        fs_layout.addWidget(self.fs_play)
        fs_layout.addWidget(self.fs_fwd)
        fs_layout.addWidget(self.fs_next)
        fs_layout.addWidget(self.fs_seek, stretch=1)
        fs_layout.addWidget(self.fs_time)
        fs_layout.addWidget(QLabel("Vol"))
        fs_layout.addWidget(self.fs_volume)
        fs_layout.addWidget(self.fs_exit)

        # ---------- Mesin mpv ----------
        self.player = mpv.MPV(
            wid=str(int(self.video.winId())),
            input_default_bindings=True,
            input_vo_keyboard=True,
            sub_auto="fuzzy",   # subtitle otomatis kalau namanya mirip video
            idle=True,          # mpv tetap hidup pas video selesai
        )
        self.player.volume = self.volume.value()

        # Tombol keyboard F, Esc, dan double click
        self.fullscreen_toggled.connect(self.toggle_fullscreen)
        self.fullscreen_exited.connect(self.exit_fullscreen)
        self.player.register_key_binding("f", self._on_key_f)
        self.player.register_key_binding("ESC", self._on_key_esc)
        self.player.register_key_binding("MBTN_LEFT_DBL", self._on_key_f)

        # Timer buat ngecek gerakan kursor tiap 0.1 detik (munculin/sembunyiin bar fullscreen)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self.check_cursor)
        self.cursor_timer.start(100)

        # ---------- Discord Rich Presence ----------
        self.rpc = DiscordRPC()
        self.rpc.connect()

        # ---------- Timer utama ----------
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

    # ================= Resume =================
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
        """Catat posisi video yang lagi diputar."""
        if not self.current_path:
            return
        pos = self.player.time_pos
        dur = self.player.duration
        if pos is None or not dur:
            return
        # Terlalu awal atau hampir habis: gak usah diingat
        if pos < 10 or pos > dur - 10:
            self.resume.pop(self.current_path, None)
        else:
            self.resume[self.current_path] = int(pos)
        self.save_resume_file()

    # ================= Playlist =================
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

        # Langsung putar kalau belum ada yang main (atau daftar diganti)
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

        self.remember_position()  # simpan posisi video sebelumnya

        path = self.playlist[index]
        self.index = index
        self.current_path = path
        self.current_title = os.path.splitext(os.path.basename(path))[0]
        self.setWindowTitle(f"{self.current_title} - {APP_TITLE}")
        self.was_playing = False

        # Lanjut dari posisi terakhir kalau ada
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
        # Lewat 5 detik: ulang dari awal. Kalau belum: ke video sebelumnya
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
        """Dipanggil pas video habis."""
        self.resume.pop(self.current_path, None)  # udah tamat, hapus resume-nya
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

    # ================= Keyboard dari mpv =================
    def _on_key_f(self, state, name, char):
        if state[0] in ("d", "p"):
            self.fullscreen_toggled.emit()

    def _on_key_esc(self, state, name, char):
        if state[0] in ("d", "p"):
            self.fullscreen_exited.emit()

    # ================= Drag & drop =================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.add_files(sorted(paths))

    # ================= Kontrol =================
    def toggle_pause(self):
        self.player.pause = not self.player.pause

    def skip(self, seconds):
        """Maju (+) atau mundur (-) beberapa detik."""
        if self.current_path:
            self.player.seek(seconds, reference="relative")

    def on_volume(self, value):
        self.player.volume = value
        # Samain slider volume di mode biasa dan di bar fullscreen
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

    # ================= Panel & fullscreen =================
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
            # Tampilkan bar sebentar pas baru masuk fullscreen
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
        """Munculin bar kontrol di bawah tengah layar."""
        geo = self.screen().geometry()
        width = min(geo.width() - 80, 1150)
        self.fs_bar.setFixedWidth(width)
        self.fs_bar.adjustSize()
        x = geo.left() + (geo.width() - width) // 2
        y = geo.bottom() - self.fs_bar.height() - 40
        self.fs_bar.move(x, y)
        self.fs_bar.show()
        self.fs_bar.raise_()

    def check_cursor(self):
        """Munculin bar pas mouse gerak, sembunyiin pas mouse diem (cuma di fullscreen)."""
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

    # ================= Update UI & Discord =================
    def update_ui(self):
        pos = self.player.time_pos
        dur = self.player.duration

        # Deteksi video selesai -> lanjut ke berikutnya
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

        # Simpan posisi tiap 5 detik
        if pos is not None and time.time() - self.last_save > 5:
            self.last_save = time.time()
            self.remember_position()

        # Kirim status ke Discord
        if self.current_title and pos is not None:
            self.rpc.update(self.current_title, bool(self.player.pause), pos, dur)
        else:
            self.rpc.clear()

    def closeEvent(self, event):
        self.fs_bar.close()
        self.cursor_timer.stop()
        self.timer.stop()
        self.remember_position()
        self.rpc.close()
        self.player.terminate()
        event.accept()


if __name__ == "__main__":
    # Biar icon di taskbar Windows pakai icon app lu, bukan icon Python
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "anthrme.movieplayer"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyleSheet(THEME)
    app.setWindowIcon(QIcon(ICON_PATH))
    locale.setlocale(locale.LC_NUMERIC, "C")

    window = Player()
    window.show()
    sys.exit(app.exec())