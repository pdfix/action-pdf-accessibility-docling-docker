import logging

from docling.datamodel.document import ConversionResult
from tqdm import tqdm

from constants import RD_DOCLING
from converter.abstract_internal_document_converter import AbstractInternalDocumentConverter
from converter.convert_to_chapter_structure import ConvertToChapterStructure
from converter.convert_to_page_structure import ConvertToPageStructure
from internal_classes import InternalDocument
from logger import get_logger

__all__ = ["DoclingConverter"]

logger: logging.Logger = get_logger()


class DoclingConverter:
    """
    Facade that selects the reading-order-specific Docling converter and delegates conversion.
    """

    def __init__(
        self,
        result: ConversionResult,
        reading_order: str,
        progress_bar: tqdm,
        convert_step_units: float,
    ) -> None:
        """
        Create the converter for the given reading order.

        Args:
            result (ConversionResult): Result from Docling conversion.
            reading_order (str): Reading order mode (docling_rd or other page-based modes).
            progress_bar (tqdm): Progress bar to update during conversion.
            convert_step_units (float): Total progress units allocated to conversion.
        """
        self._converter: AbstractInternalDocumentConverter = self._create_implementation(
            result,
            reading_order,
            progress_bar,
            convert_step_units,
        )

    def convert(self) -> InternalDocument:
        """
        Convert Docling conversion result into InternalDocument.

        Returns:
            Internal representation of the PDF document.
        """
        document: InternalDocument = self._converter.convert()
        logger.info(document.debug_info())
        return document

    @staticmethod
    def _create_implementation(
        result: ConversionResult,
        reading_order: str,
        progress_bar: tqdm,
        convert_step_units: float,
    ) -> AbstractInternalDocumentConverter:
        """
        Create the implementation for the given reading order.

        Args:
            result (ConversionResult): Result from Docling conversion.
            reading_order (str): Reading order mode (docling_rd or other page-based modes).
            progress_bar (tqdm): Progress bar to update during conversion.
            convert_step_units (float): Total progress units allocated to conversion.
        """
        if reading_order == RD_DOCLING:
            return ConvertToChapterStructure(result, progress_bar, convert_step_units)

        return ConvertToPageStructure(result, progress_bar, convert_step_units)
