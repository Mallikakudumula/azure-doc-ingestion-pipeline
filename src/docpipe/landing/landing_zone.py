"""Secure landing zone for RAW documents. Raw files are never modified: they are
written once under a content-hash name, so they can always be reprocessed or audited.

Azure: Blob Storage is encrypted at rest by default (Microsoft-managed or
customer-managed keys). Access is via Managed Identity + the RBAC role
'Storage Blob Data Contributor' -> no account keys in code."""
import logging
import os
import stat
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from ..models import RawDocument

log = logging.getLogger(__name__)


def _relative_key(doc: RawDocument, file_hash: str) -> str:
    d = datetime.now(timezone.utc)
    safe = Path(doc.filename).name.replace(" ", "_")
    return f"{d:%Y/%m/%d}/{doc.source_channel}/{file_hash[:12]}_{safe}"


class LandingZone(ABC):
    @abstractmethod
    def store(self, doc: RawDocument, file_hash: str) -> str: ...


class LocalLandingZone(LandingZone):
    def __init__(self, root: Path):
        self.root = root

    def store(self, doc: RawDocument, file_hash: str) -> str:
        path = self.root / _relative_key(doc, file_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(doc.content)
            os.chmod(path, stat.S_IREAD)   # read-only raw copy
        return str(path)


class BlobLandingZone(LandingZone):
    def __init__(self, account_url: str, container: str):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        svc = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self.container = svc.get_container_client(container)

    def store(self, doc: RawDocument, file_hash: str) -> str:
        from azure.core.exceptions import ResourceExistsError
        key = _relative_key(doc, file_hash)
        try:
            self.container.upload_blob(key, doc.content, overwrite=False,
                                       metadata={"sha256": file_hash,
                                                 "source_channel": doc.source_channel})
        except ResourceExistsError:
            log.info("Blob already staged: %s", key)
        return f"{self.container.url}/{key}"
