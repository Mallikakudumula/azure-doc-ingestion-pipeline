"""Simulates the intake channels on a laptop: sub-folders of data/inbox/
(email, portal, sharepoint, shared_drive) stand in for the real channels."""
import logging
from pathlib import Path
from typing import Iterator

from ..models import RawDocument
from .base import Connector

log = logging.getLogger(__name__)
CHANNELS = {"email", "portal", "sharepoint", "shared_drive"}


class LocalFolderConnector(Connector):
    name = "local"

    def __init__(self, inbox: Path):
        self.inbox = inbox

    def fetch(self) -> Iterator[RawDocument]:
        for path in sorted(self.inbox.rglob("*")):
            if not path.is_file():
                continue
            channel = path.parent.name if path.parent.name in CHANNELS else "shared_drive"
            log.info("Found %s (channel=%s)", path.name, channel)
            yield RawDocument(filename=path.name, content=path.read_bytes(),
                              source_channel=channel, source_ref=str(path))
