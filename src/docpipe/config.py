"""Central configuration. All secrets/endpoints come from environment variables
(never hard-coded). In Azure, secrets should be loaded from Key Vault."""
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional
    pass


@dataclass
class Settings:
    mode: str = "local"
    data_dir: Path = Path("./data")
    confidence_threshold: float = 0.85
    max_retries: int = 3
    di_endpoint: str = ""
    di_key: str = ""
    di_model_id: str = "prebuilt-invoice"
    blob_account_url: str = ""
    blob_container: str = "raw-landing"
    servicebus_namespace: str = ""
    servicebus_queue: str = "dead-letter-docs"
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_mailbox: str = ""
    graph_site_id: str = ""
    graph_drive_id: str = ""
    graph_folder: str = "Incoming"

    @property
    def is_azure(self) -> bool:
        return self.mode == "azure"

    @property
    def inbox_dir(self) -> Path: return self.data_dir / "inbox"
    @property
    def landing_dir(self) -> Path: return self.data_dir / "landing"
    @property
    def output_dir(self) -> Path: return self.data_dir / "output"
    @property
    def dead_letter_dir(self) -> Path: return self.data_dir / "dead_letter"
    @property
    def db_path(self) -> Path: return self.data_dir / "pipeline.db"


def load_settings() -> Settings:
    g = os.getenv
    return Settings(
        mode=g("PIPELINE_MODE", "local").lower(),
        data_dir=Path(g("DATA_DIR", "./data")),
        confidence_threshold=float(g("CONFIDENCE_THRESHOLD", "0.85")),
        max_retries=int(g("MAX_RETRIES", "3")),
        di_endpoint=g("DI_ENDPOINT", ""),
        di_key=g("DI_KEY", ""),
        di_model_id=g("DI_MODEL_ID", "prebuilt-invoice"),
        blob_account_url=g("BLOB_ACCOUNT_URL", ""),
        blob_container=g("BLOB_CONTAINER", "raw-landing"),
        servicebus_namespace=g("SERVICEBUS_NAMESPACE", ""),
        servicebus_queue=g("SERVICEBUS_QUEUE", "dead-letter-docs"),
        graph_tenant_id=g("GRAPH_TENANT_ID", ""),
        graph_client_id=g("GRAPH_CLIENT_ID", ""),
        graph_client_secret=g("GRAPH_CLIENT_SECRET", ""),
        graph_mailbox=g("GRAPH_MAILBOX", ""),
        graph_site_id=g("GRAPH_SITE_ID", ""),
        graph_drive_id=g("GRAPH_DRIVE_ID", ""),
        graph_folder=g("GRAPH_FOLDER", "Incoming"),
    )
