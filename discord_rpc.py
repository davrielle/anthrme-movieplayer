import time
from pypresence import Presence

try:
    from pypresence.types import ActivityType
except ImportError:  # pypresence versi lama
    ActivityType = None

CLIENT_ID = "1571028295959576626"   # <- ganti
LARGE_IMAGE = "anthrmemp"              # key art asset, atau URL gambar
APP_NAME = "anthrme-MOVIEPLAYER"


class DiscordRPC:
    def __init__(self):
        self.rpc = None
        self.connected = False
        self.last_try = 0       # terakhir coba connect
        self.last_update = 0    # terakhir kirim update
        self.last_key = None    # (judul, paused) terakhir
        self.last_start = None  # patokan buat deteksi seek
        self.active = False     # presence lagi tampil atau nggak

    def connect(self):
        self.last_try = time.time()
        try:
            self.rpc = Presence(CLIENT_ID)
            self.rpc.connect()
            self.connected = True
        except Exception as e:
            print("Discord belum kedeteksi:", e)
            self.connected = False

    def update(self, title, paused, position, duration):
        now = time.time()

        # Kalau belum nyambung, coba lagi tiap 15 detik
        if not self.connected:
            if now - self.last_try > 15:
                self.connect()
            return

        key = (title, paused)
        start = now - position
        changed = key != self.last_key

        # Deteksi lompatan (user geser seek bar)
        if not paused and self.last_start is not None:
            if abs(start - self.last_start) > 3:
                changed = True

        # Kirim hanya kalau ada perubahan, dan jangan terlalu sering
        if not changed or now - self.last_update < 3:
            return

        data = dict(
            details=title[:128],
            large_image=LARGE_IMAGE,
            large_text=APP_NAME,
        )
        if ActivityType is not None:
            data["activity_type"] = ActivityType.WATCHING

        if paused:
            data["state"] = "Paused"
        else:
            data["state"] = "watching"
            data["start"] = int(start)
            if duration:
                data["end"] = int(now + (duration - position))

        try:
            self.rpc.update(**data)
            self.last_update = now
            self.last_key = key
            self.last_start = start
            self.active = True
        except Exception as e:
            print("Gagal update presence:", e)
            self.connected = False

    def clear(self):
        if self.connected and self.active:
            try:
                self.rpc.clear()
            except Exception:
                pass
        self.active = False
        self.last_key = None
        self.last_start = None

    def close(self):
        self.clear()
        if self.connected:
            try:
                self.rpc.close()
            except Exception:
                pass
        self.connected = False