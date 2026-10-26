import logging
import os


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if conn:  # Observability: ship logs/traces to Application Insights
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
            configure_azure_monitor(connection_string=conn)
        except ImportError:
            logging.getLogger(__name__).warning(
                "azure-monitor-opentelemetry not installed; skipping App Insights")
