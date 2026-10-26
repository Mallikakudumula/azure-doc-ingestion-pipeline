"""Email intake: reads attachments from a shared mailbox via Microsoft Graph.
Needs app permission Mail.Read. Written against the Graph v1.0 docs;
test it against your own Microsoft 365 developer tenant."""
import base64
import logging
from typing import Iterator

from ..models import RawDocument
from .base import Connector
from .graph_client import GRAPH, GraphClient

log = logging.getLogger(__name__)


class GraphEmailConnector(Connector):
    name = "email"

    def __init__(self, client: GraphClient, mailbox: str):
        self.client, self.mailbox = client, mailbox

    def fetch(self) -> Iterator[RawDocument]:
        url = f"{GRAPH}/users/{self.mailbox}/mailFolders/inbox/messages"
        params = {"$filter": "hasAttachments eq true", "$top": 25,
                  "$select": "id,subject,from,receivedDateTime"}
        for msg in self.client.get_paged(url, params):
            att_url = f"{GRAPH}/users/{self.mailbox}/messages/{msg['id']}/attachments"
            for att in self.client.get_paged(att_url):
                if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                    continue  # skip inline items / nested emails
                yield RawDocument(
                    filename=att["name"],
                    content=base64.b64decode(att["contentBytes"]),
                    source_channel="email",
                    source_ref=f"{msg['id']}/{att['id']}",
                    received_at=msg.get("receivedDateTime", ""),
                    metadata={"subject": msg.get("subject"),
                              "sender": msg.get("from", {}).get("emailAddress", {}).get("address")})
