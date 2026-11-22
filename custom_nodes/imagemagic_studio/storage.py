"""Per-installation session catalog. PNGs and their edit history live on disk."""
import re
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from ntpath import isreserved
from pathlib import Path


SESSION_ID = re.compile(r"[0-9a-f]{32}")
IMAGE_NAME = re.compile(r"[0-9a-f]{32}_\d+_\.png")
CUSTOM_MARKER = ".imagemagic-session"


class FolderUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class Session:
    id: str
    name: str
    folder: Path
    custom: bool

    @property
    def marker(self):
        return self.folder / (CUSTOM_MARKER if self.custom else "name.txt")

    def available(self):
        try:
            if self.folder.resolve(strict=True) != self.folder:
                return False
            if self.id == "previous":
                return True
            if self.marker.resolve(strict=True) != self.marker:
                return False
            if self.custom:
                return self.marker.read_text(encoding="utf-8") == self.id
            return self.marker.is_file()
        except (OSError, RuntimeError, UnicodeError):
            return False

    def require_folder(self):
        if not self.available():
            raise FolderUnavailable(f"Folder unavailable: {self.folder}. Reconnect it and try again.")
        return self.folder


class Catalog:
    def __init__(self, root):
        self.root = root.resolve()

    @contextmanager
    def connect(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.root / "imagemagic.sqlite3", timeout=10)) as db:
            version, = db.execute("PRAGMA user_version").fetchone()
            if version == 0:
                # Serialize first use by the web server and ComfyUI worker.
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    version, = db.execute("PRAGMA user_version").fetchone()
                    if version == 0:
                        db.execute("""CREATE TABLE sessions (
                            id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL,
                            created_at REAL NOT NULL, custom_folder TEXT COLLATE NOCASE UNIQUE
                        )""")
                        for marker in self.root.glob("*/name.txt"):
                            sid = marker.parent.name
                            if SESSION_ID.fullmatch(sid) and marker.resolve() == marker:
                                db.execute("INSERT INTO sessions (id, name, created_at) VALUES (?, ?, ?)",
                                           (sid, marker.read_text(encoding="utf-8"), marker.stat().st_mtime))
                        db.execute("PRAGMA user_version = 1")
                        version = 1
            if version != 1:
                raise RuntimeError("This ImageMagic catalog requires a newer version of the studio.")
            with db:
                yield db

    def _session(self, row):
        sid, name, custom = row
        return Session(sid, name, Path(custom) if custom else self.root / sid, custom is not None)

    def sessions(self):
        with self.connect() as db:
            rows = db.execute("SELECT id, name, custom_folder FROM sessions ORDER BY created_at DESC, id")
            return [self._session(row) for row in rows]

    def suggest(self, parent, name):
        # A disconnected or moved session can still own a location in the catalog.
        with self.connect() as db:
            registered = {Path(row[0]) for row in db.execute(
                "SELECT custom_folder FROM sessions WHERE custom_folder IS NOT NULL")}
        parent = parent.resolve(strict=True)
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "Session"
        if isreserved(stem):
            stem = "_" + stem
        folder = parent / stem
        number = 2
        while folder in registered or folder.exists() or folder.is_symlink():
            folder = parent / f"{stem} ({number})"
            number += 1
        return folder

    def get(self, sid):
        if sid == "previous":
            return Session(sid, "Previous images", self.root, False)
        if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
            raise KeyError("Unknown session")
        with self.connect() as db:
            row = db.execute("SELECT id, name, custom_folder FROM sessions WHERE id = ?", (sid,)).fetchone()
        if row is None:
            raise KeyError("Unknown session")
        return self._session(row)

    def create(self, name, destination=None):
        sid = uuid.uuid4().hex
        folder = self.root / sid
        if destination is not None:
            folder = Path(destination)
            if not folder.is_absolute() or folder.name in {"", ".", ".."} or isreserved(folder.name):
                raise ValueError("Choose an absolute session folder.")
            folder = folder.parent.resolve(strict=True) / folder.name
            if any(part.lower() == ".trash" for part in folder.parts):
                raise ValueError("Choose a session folder outside the trash.")
        session = Session(sid, name, folder, destination is not None)
        made_folder = False
        try:
            with self.connect() as db:
                try:
                    db.execute("INSERT INTO sessions (id, name, created_at, custom_folder) VALUES (?, ?, ?, ?)",
                               (sid, name, time.time(), str(folder) if session.custom else None))
                except sqlite3.IntegrityError as error:
                    raise FileExistsError("This session location is already registered.") from error
                folder.mkdir()
                made_folder = True
                session.marker.write_text(sid if session.custom else name, encoding="utf-8")
        except Exception:
            if made_folder:
                session.marker.unlink(missing_ok=True)
                folder.rmdir()
            raise
        return session

    def remove(self, session):
        """Called after deleting this session's confirmed images; retain unrelated files."""
        if session.id == "previous":
            return
        folder = session.require_folder()
        marker = session.marker.read_bytes()
        removed_marker = False
        try:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
                session.marker.unlink()
                removed_marker = True
                if not any(folder.iterdir()):
                    folder.rmdir()
        except Exception:
            if removed_marker:
                folder.mkdir(exist_ok=True)
                session.marker.write_bytes(marker)
            raise
