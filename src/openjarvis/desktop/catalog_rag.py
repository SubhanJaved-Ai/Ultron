"""Ultron Lightweight In-Memory System Catalog RAG.

Provides sub-millisecond local indexing and fuzzy retrieval for:
- Desktop & Start Menu shortcuts (.lnk)
- All Chrome Profiles (mapped from Chrome Local State)
- Drive volumes (C:, D:, E:, F:) and Windows Shell Folders
- Videos and media libraries
- Registered Windows applications and registry App Paths
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


STOP_WORDS = {
    "and", "the", "or", "in", "on", "at", "to", "for", "of", "a", "an", "is", "it",
    "my", "this", "there", "here", "with", "from", "by", "about", "as", "into",
    "through", "during", "before", "after", "above", "below", "up", "down", "in", "out"
}


@dataclass
class SystemItem:
    id: str
    name: str
    item_type: str  # "chrome_profile" | "app" | "shortcut" | "drive" | "shell_folder" | "video"
    target_path: str
    arguments: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)

    def matches(self, query: str) -> float:
        """Calculate a relevance score between 0.0 and 1.0 for a query string."""
        q = query.lower().strip()
        if not q:
            return 0.0

        n = self.name.lower()
        # 1. Exact match
        if q == n:
            return 1.0

        # Filter out common stop words
        all_q_words = re.findall(r"[a-z0-9]+", q)
        q_words = [w for w in all_q_words if w not in STOP_WORDS and len(w) > 1]
        if not q_words:
            return 0.0

        # 2. All query words present in item name
        n_words = set(re.findall(r"[a-z0-9]+", n))
        if all(qw in n_words for qw in q_words):
            score = 0.85 + (0.1 if n.startswith(q) else 0.0)
            return min(score, 0.99)

        # 3. Whole-word keyword matching
        matched_kw = 0
        for kw in self.keywords:
            kw_words = set(re.findall(r"[a-z0-9]+", kw.lower()))
            if any(qw in kw_words for qw in q_words):
                matched_kw += 1

        if matched_kw > 0:
            return min(0.5 + (0.15 * matched_kw), 0.95)

        # Substring in target path or id (only for specific query words of length >= 4)
        for qw in q_words:
            if len(qw) >= 4 and (qw in self.id.lower() or qw in self.target_path.lower()):
                return 0.45

        return 0.0


class SystemCatalogRAG:
    """In-memory lightweight local system knowledge catalog."""

    def __init__(self, cache_ttl_seconds: float = 300.0) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self._last_refresh: float = 0.0
        self._items: Dict[str, SystemItem] = {}

    def ensure_indexed(self, force: bool = False) -> None:
        """Refresh index if cache expired or forced."""
        now = time.time()
        if force or (now - self._last_refresh > self.cache_ttl_seconds) or not self._items:
            self._build_index()
            self._last_refresh = now

    def _build_index(self) -> None:
        """Scan and populate all catalog items."""
        items: Dict[str, SystemItem] = {}

        # 1. Index Chrome Profiles
        self._index_chrome_profiles(items)

        # 2. Index Drive Volumes & Special Shell Folders
        self._index_drives_and_folders(items)

        # 3. Index Desktop & Start Menu Shortcuts (.lnk)
        self._index_shortcuts(items)

        # 4. Index Registered Apps (App Paths & Common Tools)
        self._index_applications(items)

        # 5. Index Media & Video Library
        self._index_videos(items)

        self._items = items

    def _index_chrome_profiles(self, items: Dict[str, SystemItem]) -> None:
        """Parse Chrome Local State info_cache to index all profiles."""
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            user_profile = os.environ.get("USERPROFILE", "")
            if user_profile:
                local_app_data = str(Path(user_profile) / "AppData" / "Local")

        if not local_app_data:
            return

        local_state_file = Path(local_app_data) / "Google" / "Chrome" / "User Data" / "Local State"
        chrome_exe = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if not Path(chrome_exe).exists():
            chrome_exe = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"

        if local_state_file.exists():
            try:
                data = json.loads(local_state_file.read_text(encoding="utf-8"))
                info_cache = data.get("profile", {}).get("info_cache", {})
                for pdir, pdata in info_cache.items():
                    name = pdata.get("name", pdir)
                    gaia_name = pdata.get("gaia_name", "")
                    user_name = pdata.get("user_name", "")
                    keywords = [
                        name.lower(),
                        pdir.lower(),
                        "chrome",
                        "browser profile",
                        "google chrome",
                    ]
                    if gaia_name:
                        keywords.append(gaia_name.lower())
                    if user_name:
                        keywords.append(user_name.lower())
                        # Add user email prefix
                        if "@" in user_name:
                            keywords.append(user_name.split("@")[0].lower())

                    # Known aliases
                    if name.lower() == "airluc":
                        keywords.extend(["airluc", "air luc", "airluck", "airluc official", "airlucofficial"])
                    elif name.lower() == "your chrome":
                        keywords.extend(["default", "your chrome", "main chrome", "my chrome", "subhan ai"])

                    item_id = f"chrome_profile:{pdir}"
                    items[item_id] = SystemItem(
                        id=item_id,
                        name=name,
                        item_type="chrome_profile",
                        target_path=chrome_exe,
                        arguments=f'--profile-directory="{pdir}"',
                        metadata={
                            "profile_directory": pdir,
                            "display_name": name,
                            "gaia_name": gaia_name,
                            "email": user_name,
                        },
                        keywords=keywords,
                    )
            except Exception:
                pass

    def _index_drives_and_folders(self, items: Dict[str, SystemItem]) -> None:
        """Index all mounted filesystem drive letters and standard shell folders."""
        # Active drives
        for letter in ["C", "D", "E", "F", "G", "H"]:
            drive_root = f"{letter}:\\"
            if Path(drive_root).exists():
                item_id = f"drive:{letter.lower()}"
                items[item_id] = SystemItem(
                    id=item_id,
                    name=f"{letter} Drive",
                    item_type="drive",
                    target_path=drive_root,
                    keywords=[f"{letter.lower()} drive", f"{letter.lower()}:", f"drive {letter.lower()}", "drive", "volume", "storage"],
                )

        # Standard Windows Shell Folders
        home = Path.home()
        special_folders = [
            ("This PC", "shell:MyComputerFolder", ["my computer", "this pc", "computer", "pc", "all drives", "explorer"]),
            ("Downloads", str(home / "Downloads"), ["downloads", "download folder", "save folder", "saves"]),
            ("Documents", str(home / "Documents"), ["documents", "docs", "my documents"]),
            ("Desktop", str(self._get_real_desktop_path()), ["desktop", "desktop view", "desktop folder"]),
            ("Videos", str(home / "Videos"), ["videos", "my videos", "video folder", "captures"]),
            ("Pictures", str(home / "Pictures"), ["pictures", "photos", "images"]),
            ("Music", str(home / "Music"), ["music", "songs", "audio"]),
        ]

        # Check for Ultron workspace folder
        ultron_dir = Path("D:/Ultron")
        if ultron_dir.exists():
            special_folders.append(("Ultron Workspace", str(ultron_dir), ["ultron", "ultron folder", "workspace", "project"]))

        for name, target, kw in special_folders:
            item_id = f"shell_folder:{name.lower().replace(' ', '_')}"
            items[item_id] = SystemItem(
                id=item_id,
                name=name,
                item_type="shell_folder",
                target_path=target,
                keywords=kw,
            )

    def _get_real_desktop_path(self) -> Path:
        """Return the real active desktop path (accounting for OneDrive redirection)."""
        home = Path.home()
        onedrive_desktop = home / "OneDrive" / "Desktop"
        if onedrive_desktop.exists():
            return onedrive_desktop
        std_desktop = home / "Desktop"
        if std_desktop.exists():
            return std_desktop
        return home

    def _index_shortcuts(self, items: Dict[str, SystemItem]) -> None:
        """Scan desktop and start menu shortcuts (.lnk)."""
        search_dirs = [
            self._get_real_desktop_path(),
            Path("C:/Users/Public/Desktop"),
        ]

        appdata = os.environ.get("APPDATA", "")
        if appdata:
            search_dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        programdata = os.environ.get("PROGRAMDATA", "")
        if programdata:
            search_dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        for sdir in search_dirs:
            if not sdir.exists():
                continue
            try:
                for sc in sdir.glob("**/*.lnk"):
                    stem = sc.stem
                    clean_name = re.sub(r"\s*-\s*Chrome$", "", stem, flags=re.IGNORECASE).strip()
                    item_id = f"shortcut:{clean_name.lower().replace(' ', '_')}"

                    keywords = [
                        clean_name.lower(),
                        stem.lower(),
                        "app",
                        "shortcut",
                        "desktop app",
                    ]
                    # Tag common tools
                    if "capcut" in stem.lower():
                        keywords.extend(["capcut", "video editor", "cap cut"])
                    elif "chrome" in stem.lower():
                        keywords.extend(["chrome", "browser"])
                    elif "code" in stem.lower() or "visual studio" in stem.lower():
                        keywords.extend(["vs code", "vscode", "visual studio code", "code editor"])
                    elif "obs" in stem.lower():
                        keywords.extend(["obs", "obs studio", "screen recorder", "streaming"])
                    elif "vlc" in stem.lower():
                        keywords.extend(["vlc", "vlc media player", "media player", "video player"])
                    elif "antigravity" in stem.lower():
                        keywords.extend(["antigravity", "antigravity ide", "ide"])
                    elif "wispr" in stem.lower():
                        keywords.extend(["wispr", "wispr flow", "voice typing"])

                    if item_id not in items:
                        items[item_id] = SystemItem(
                            id=item_id,
                            name=clean_name,
                            item_type="shortcut",
                            target_path=str(sc),
                            keywords=keywords,
                        )
            except Exception:
                pass

    def _index_applications(self, items: Dict[str, SystemItem]) -> None:
        """Index well-known applications and registry App Paths."""
        # Built-in Windows utilities
        built_in = [
            ("Notepad", "notepad.exe", ["notepad", "text editor", "notes"]),
            ("Calculator", "calc.exe", ["calculator", "calc", "math"]),
            ("Paint", "mspaint.exe", ["paint", "drawing", "mspaint"]),
            ("Task Manager", "taskmgr.exe", ["task manager", "taskmgr", "processes"]),
            ("Command Prompt", "cmd.exe", ["cmd", "command prompt", "terminal"]),
            ("PowerShell", "powershell.exe", ["powershell", "posh", "shell"]),
        ]
        for name, target, kw in built_in:
            item_id = f"app:{name.lower().replace(' ', '_')}"
            if item_id not in items:
                items[item_id] = SystemItem(
                    id=item_id,
                    name=name,
                    item_type="app",
                    target_path=target,
                    keywords=kw,
                )

        # Standard program locations
        user_profile = os.environ.get("USERPROFILE", "C:\\Users\\DELL")
        program_candidates = [
            ("Visual Studio Code", Path(user_profile) / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "Code.exe", ["vs code", "vscode", "visual studio code", "code"]),
            ("Antigravity IDE", Path(user_profile) / "AppData" / "Local" / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe", ["antigravity", "antigravity ide"]),
            ("Wispr Flow", Path(user_profile) / "AppData" / "Local" / "WisprFlow" / "Wispr Flow.exe", ["wispr", "wispr flow"]),
            ("OBS Studio", Path("C:/Program Files/obs-studio/bin/64bit/obs64.exe"), ["obs", "obs studio"]),
            ("VLC media player", Path("C:/Program Files/VideoLAN/VLC/vlc.exe"), ["vlc", "vlc media player", "video player"]),
            ("Google Chrome", Path("C:/Program Files/Google/Chrome/Application/chrome.exe"), ["chrome", "google chrome", "browser"]),
            # CapCut check
            ("CapCut", Path(user_profile) / "AppData" / "Local" / "CapCut" / "CapCut.exe", ["capcut", "video editor", "cap cut"]),
            ("CapCut Installer", Path(user_profile) / "Downloads" / "capcut-9-1-0-3879.exe", ["capcut", "capcut installer", "cap cut"]),
        ]

        for name, path_obj, kw in program_candidates:
            if path_obj.exists():
                item_id = f"app:{name.lower().replace(' ', '_')}"
                items[item_id] = SystemItem(
                    id=item_id,
                    name=name,
                    item_type="app",
                    target_path=str(path_obj),
                    keywords=kw,
                )

    def _index_videos(self, items: Dict[str, SystemItem]) -> None:
        """Scan standard video directories for user videos (.mp4, .mkv, .mov)."""
        video_dirs = [
            Path.home() / "Videos",
            Path("D:/"),
            Path("E:/"),
        ]
        video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

        count = 0
        for vdir in video_dirs:
            if not vdir.exists():
                continue
            try:
                # Fast limited scan (depth 3, max 60 videos to avoid disk thrashing)
                for root, dirs, files in os.walk(str(vdir)):
                    depth = len(Path(root).relative_to(vdir).parts)
                    if depth > 3:
                        dirs.clear()
                        continue

                    # Skip heavy build/system directories
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in {"node_modules", ".git", "__pycache__", "venv", ".venv", "windows"}]

                    for file in files:
                        p = Path(root) / file
                        if p.suffix.lower() in video_exts:
                            item_id = f"video:{p.stem.lower()}"
                            keywords = [
                                p.stem.lower(),
                                file.lower(),
                                "video",
                                "movie",
                                "media",
                                "clip",
                            ]
                            items[item_id] = SystemItem(
                                id=item_id,
                                name=file,
                                item_type="video",
                                target_path=str(p),
                                metadata={"size_bytes": p.stat().st_size if p.exists() else 0},
                                keywords=keywords,
                            )
                            count += 1
                            if count >= 60:
                                break
                    if count >= 60:
                        break
            except Exception:
                pass

    def search(
        self,
        query: str,
        item_types: Optional[List[str]] = None,
        min_score: float = 0.35,
        top_k: int = 5,
    ) -> List[Tuple[SystemItem, float]]:
        """Search the indexed catalog using semantic fuzzy scoring."""
        self.ensure_indexed()
        scored: List[Tuple[SystemItem, float]] = []

        for item in self._items.values():
            if item_types and item.item_type not in item_types:
                continue
            score = item.matches(query)
            if score >= min_score:
                scored.append((item, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def find_chrome_profile(self, name_or_query: str) -> Optional[SystemItem]:
        """Find the best-matching Chrome Profile."""
        self.ensure_indexed()
        q = name_or_query.lower().strip()
        # Direct check for airluc
        if "airluc" in q:
            for item in self._items.values():
                if item.item_type == "chrome_profile" and "airluc" in item.name.lower():
                    return item

        results = self.search(name_or_query, item_types=["chrome_profile"], min_score=0.3, top_k=1)
        if results:
            return results[0][0]
        return None

    def find_app_or_shortcut(self, name_or_query: str) -> Optional[SystemItem]:
        """Find an application or desktop shortcut."""
        self.ensure_indexed()
        results = self.search(name_or_query, item_types=["app", "shortcut"], min_score=0.4, top_k=1)
        if results:
            return results[0][0]
        return None

    def find_folder_or_drive(self, name_or_query: str) -> Optional[SystemItem]:
        """Find a drive volume or special shell folder."""
        self.ensure_indexed()
        results = self.search(name_or_query, item_types=["drive", "shell_folder"], min_score=0.35, top_k=1)
        if results:
            return results[0][0]
        return None

    def find_video(self, name_or_query: str) -> Optional[SystemItem]:
        """Find a video file by name or substring."""
        self.ensure_indexed()
        results = self.search(name_or_query, item_types=["video"], min_score=0.35, top_k=1)
        if results:
            return results[0][0]
        return None


# Global singleton instance
_GLOBAL_CATALOG = SystemCatalogRAG()


def get_system_catalog() -> SystemCatalogRAG:
    """Return the global SystemCatalogRAG instance."""
    return _GLOBAL_CATALOG
