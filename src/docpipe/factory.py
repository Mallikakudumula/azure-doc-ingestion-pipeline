"""Builds the right components for local vs azure mode."""
from .config import Settings
from .connectors.local_folder import LocalFolderConnector
from .extraction.mock_extractor import MockExtractor
from .landing.landing_zone import LocalLandingZone
from .pipeline import Pipeline
from .resilience.dead_letter import LocalDeadLetter
from .storage.database import connect
from .storage.repository import Repository


def build_pipeline(s: Settings) -> Pipeline:
    repo = Repository(connect(s.db_path))
    if s.is_azure:
        from .extraction.di_extractor import DocumentIntelligenceExtractor
        from .landing.landing_zone import BlobLandingZone
        from .resilience.dead_letter import ServiceBusDeadLetter
        return Pipeline(s, repo, BlobLandingZone(s.blob_account_url, s.blob_container),
                        DocumentIntelligenceExtractor(s.di_endpoint, s.di_key, s.di_model_id),
                        ServiceBusDeadLetter(s.servicebus_namespace, s.servicebus_queue))
    return Pipeline(s, repo, LocalLandingZone(s.landing_dir), MockExtractor(),
                    LocalDeadLetter(s.dead_letter_dir))


def build_connectors(s: Settings, source: str):
    connectors = []
    if source in ("local", "all") or not s.is_azure:
        connectors.append(LocalFolderConnector(s.inbox_dir))
    if s.is_azure and source in ("email", "sharepoint", "all"):
        from .connectors.graph_client import GraphClient
        client = GraphClient(s.graph_tenant_id, s.graph_client_id, s.graph_client_secret)
        if source in ("email", "all"):
            from .connectors.graph_email import GraphEmailConnector
            connectors.append(GraphEmailConnector(client, s.graph_mailbox))
        if source in ("sharepoint", "all"):
            from .connectors.graph_sharepoint import GraphSharePointConnector
            connectors.append(GraphSharePointConnector(client, s.graph_drive_id, s.graph_folder))
    return connectors
