"""Azure Document Intelligence extractor (prebuilt-invoice by default).

- Scanned PDFs / images: sent to Document Intelligence (OCR + extraction).
- Text-based files (docx/csv/json/xlsx/native pdf): extracted from normalized text,
  so we don't pay for OCR we don't need.
NOTE: written against azure-ai-documentintelligence 1.0.x; verify against your
installed SDK version and your Azure resource."""
import logging

from ..models import ExtractedField, ExtractionResult, NormalizedDocument, TransientError
from .mock_extractor import MockExtractor

log = logging.getLogger(__name__)

# Document Intelligence invoice field -> our canonical field
DI_FIELD_MAP = {"InvoiceId": "document_number", "VendorName": "counterparty",
                "InvoiceDate": "document_date", "InvoiceTotal": "amount"}


class DocumentIntelligenceExtractor:
    def __init__(self, endpoint: str, key: str, model_id: str):
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        if key:
            from azure.core.credentials import AzureKeyCredential
            cred = AzureKeyCredential(key)
        else:   # Managed Identity / az login: no secret needed
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
        self.client = DocumentIntelligenceClient(endpoint, cred)
        self.model_id = model_id
        self.model_version = "api-2024-11-30"
        self._text_extractor = MockExtractor()   # rule-based path for text files

    def extract(self, filename: str, content: bytes, doc: NormalizedDocument) -> ExtractionResult:
        if not doc.needs_ocr and doc.file_format != "pdf":
            result = self._text_extractor.extract(filename, content, doc)
            return ExtractionResult(result.fields, "rule-based-text", "1.0")
        return self._analyze(content)

    def _analyze(self, content: bytes) -> ExtractionResult:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.exceptions import HttpResponseError, ServiceRequestError
        try:
            poller = self.client.begin_analyze_document(
                self.model_id, AnalyzeDocumentRequest(bytes_source=content))
            analysis = poller.result()
        except ServiceRequestError as exc:           # network problem -> retry
            raise TransientError(str(exc)) from exc
        except HttpResponseError as exc:
            if exc.status_code in (408, 429, 500, 502, 503, 504):
                raise TransientError(f"HTTP {exc.status_code}") from exc
            raise
        fields: list[ExtractedField] = []
        if analysis.documents:
            doc = analysis.documents[0]
            for di_name, ours in DI_FIELD_MAP.items():
                f = (doc.fields or {}).get(di_name)
                if f is None:
                    continue
                value = f.value_currency.amount if (di_name == "InvoiceTotal"
                                                    and getattr(f, "value_currency", None)) else f.content
                page = f.bounding_regions[0].page_number if f.bounding_regions else 1
                fields.append(ExtractedField(ours, value, float(f.confidence or 0.0), page))
                if di_name == "InvoiceTotal" and getattr(f, "value_currency", None):
                    fields.append(ExtractedField("currency", f.value_currency.currency_code,
                                                 float(f.confidence or 0.0), page))
        return ExtractionResult(fields, self.model_id, self.model_version)
