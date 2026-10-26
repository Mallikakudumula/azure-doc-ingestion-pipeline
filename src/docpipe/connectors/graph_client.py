"""Thin Microsoft Graph client: app-only auth (client credentials) via MSAL,
plus handling of throttling (HTTP 429 / Retry-After) and paging."""
import logging
import time

import requests

log = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        import msal  # imported lazily so local mode needs no msal
        self._app = msal.ConfidentialClientApplication(
            client_id, authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret)

    def _headers(self) -> dict:
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"Graph auth failed: {result.get('error_description')}")
        return {"Authorization": f"Bearer {result['access_token']}"}

    def get(self, url: str, params: dict | None = None, raw: bool = False):
        for attempt in range(5):
            resp = requests.get(url, headers=self._headers(), params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("Graph %s; retrying in %ss", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content if raw else resp.json()
        resp.raise_for_status()

    def get_paged(self, url: str, params: dict | None = None):
        while url:
            data = self.get(url, params)
            yield from data.get("value", [])
            url, params = data.get("@odata.nextLink"), None
