#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "watchdog>=4.0.0",
# ]
# ///
"""
Watch ~/Downloads for any file starting with "CME".
When one arrives, delete ~/Downloads/data.csv (if present) and rename the CME file to data.csv.

Run:
  uv run --no-project watch_downloads.py
"""

import logging
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

DOWNLOADS = Path.home() / "Downloads"
DATA_CSV  = DOWNLOADS / "data.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def handle_cme_file(src: Path) -> None:
    if DATA_CSV.exists():
        DATA_CSV.unlink()
        log.info("Deleted existing data.csv")
    src.rename(DATA_CSV)
    log.info("Renamed %s -> data.csv", src.name)


class DownloadsHandler(FileSystemEventHandler):
    def _check(self, path_str: str) -> None:
        p = Path(path_str)
        # skip macOS partial-download temp files (.crdownload, .part, .download)
        if p.suffix in {".crdownload", ".part", ".download"}:
            return
        if p.parent == DOWNLOADS and p.name.startswith("CME") and p.name != "data.csv":
            if not p.exists():
                return  # already handled by a sibling event
            log.info("Detected CME file: %s", p.name)
            try:
                handle_cme_file(p)
            except Exception as exc:
                log.error("Failed to rename %s: %s", p.name, exc)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._check(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        # browsers often write to a temp name then move to the final name
        if not event.is_directory:
            self._check(event.dest_path)


def main() -> None:
    if not DOWNLOADS.exists():
        log.error("Downloads folder not found: %s", DOWNLOADS)
        sys.exit(1)

    log.info("Watching %s for CME*.* files ...", DOWNLOADS)
    observer = Observer()
    observer.schedule(DownloadsHandler(), str(DOWNLOADS), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping watcher")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
