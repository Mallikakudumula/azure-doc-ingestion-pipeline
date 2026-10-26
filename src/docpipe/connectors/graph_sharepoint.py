"""SharePoint / document-library intake via Microsoft Graph.
Needs app permission Sites.Read.All (or Sites.Selected for least privilege)."""
import logging
from typing import Iterator

from ..models import RawDocument
from .base import Connector
from .graph_client import GRAPH, GraphClient

log = logging.getLogger(__name__)


class GraphSharePointConnector(Connector):
    name = "sharepoint"

    def __init__(self, client: GraphClient, drive_id: str, folder: str):
        self.client, self.drive_id, self.folder = client, drive_id, folder

    def fetch(self) -> Iterator[RawDocument]:
        url = f"{GRAPH}/drives/{self.drive_id}/root:/{self.folder}:/children"
        for item in self.client.get_paged(url):
            if "file" not in item:   # skip sub-folders
                continue
            content = self.client.get(
                f"{GRAPH}/drives/{self.drive_id}/items/{item['id']}/content", raw=True)
            yield RawDocument(
                filename=item["name"], content=content, source_channel="sharepoint",
                source_ref=item["id"], received_at=item.get("lastModifiedDateTime", ""),
                metadata={"web_url": item.get("webUrl"), "etag": item.get("eTag")})
