from tqdm import tqdm

from constants import RD_DOCLING, RD_PDF, RD_PDFIX, RD_XY
from internal_classes import InternalDocument
from template.abstract_template_json_creator import AbstractTemplateJsonCreator, Placement
from template.docling_template_json_creator import DoclingTemplateJsonCreator
from template.pdf_template_json_creator import PdfTemplateJsonCreator
from template.pdfix_template_json_creator import PdfixTemplateJsonCreator
from template.xy_template_json_creator import XYTemplateJsonCreator

__all__ = ["Placement", "TemplateJsonCreator"]


class TemplateJsonCreator:
    """
    Facade that selects the reading-order-specific template builder and delegates processing.
    """

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        reading_order: str,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        """
        Create the template builder for the given reading order.

        Args:
            input_path_str (str): Path to the source PDF.
            bbox_overlap (float): Overlap threshold for matching Docling boxes to PDF elements.
            reading_order (str): Reading order mode (pdfix_rd, docling_rd, pdf_rd, or x_y_rd).
            progress_bar (tqdm): Progress bar for template creation.
            total_progress_units (int): Progress units allocated to template creation.
        """
        self._creator: AbstractTemplateJsonCreator = self._create_implementation(
            input_path_str,
            bbox_overlap,
            reading_order,
            progress_bar,
            total_progress_units,
        )

    def process_document(self, document: InternalDocument) -> dict:
        """
        Convert an internal document into PDFix layout template JSON.

        Args:
            document (InternalDocument): Docling layout data to convert.

        Returns:
            Complete template JSON dict ready for PDFix SDK tagging.
        """
        return self._creator.process_document(document)

    @staticmethod
    def _create_implementation(
        input_path_str: str,
        bbox_overlap: float,
        reading_order: str,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> AbstractTemplateJsonCreator:
        if reading_order == RD_PDFIX:
            return PdfixTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        if reading_order == RD_DOCLING:
            return DoclingTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        if reading_order == RD_PDF:
            return PdfTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        if reading_order == RD_XY:
            return XYTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        return PdfixTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
