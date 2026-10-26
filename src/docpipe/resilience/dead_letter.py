"""Dead-letter sinks: where files go when they can't be processed.
Local = JSON files in data/dead_letter. Azure = Service Bus queue."""
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

log = logging.getLogger(__name__)


class DeadLetterSink(ABC):
    @abstractmethod
    def send(self, file_hash: str, filename: str, reason: str, source_channel: str) -> None: ...


class LocalDeadLetter(DeadLetterSink):
    def __init__(self, folder: Path):
        self.folder = folder

    def send(self, file_hash, filename, reason, source_channel):
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = {"file_hash": file_hash, "filename": filename,
                   "reason": reason, "source_channel": source_channel}
        (self.folder / f"{file_hash[:12]}.json").write_text(json.dumps(payload, indent=2))
        log.error("DEAD-LETTERED %s: %s", filename, reason)


class ServiceBusDeadLetter(DeadLetterSink):
    def __init__(self, namespace: str, queue: str):
        from azure.identity import DefaultAzureCredential
        from azure.servicebus import ServiceBusClient
        self.client = ServiceBusClient(namespace, DefaultAzureCredential())
        self.queue = queue

    def send(self, file_hash, filename, reason, source_channel):
        from azure.servicebus import ServiceBusMessage
        body = json.dumps({"file_hash": file_hash, "filename": filename,
                           "reason": reason, "source_channel": source_channel})
        with self.client.get_queue_sender(self.queue) as sender:
            sender.send_messages(ServiceBusMessage(body))
        log.error("DEAD-LETTERED to Service Bus: %s (%s)", filename, reason)
