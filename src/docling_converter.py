import logging
from pathlib import Path

from docling.datamodel.document import ConversionResult
from tqdm import tqdm

from converter.abstract_internal_document_converter import AbstractInternalDocumentConverter
from converter.convert_to_chapter_structure import ConvertToChapterStructure
from converter.convert_to_page_structure import ConvertToPageStructure
from internal_classes import InternalDocument
from logger import get_logger

__all__ = ["DoclingConverter"]

logger: logging.Logger = get_logger()


class DoclingConverter:
    """
    Facade that selects the Docling converter (with or without chapters) and delegates conversion.
    """

    def __init__(
        self,
        result: ConversionResult,
        chapters: bool,
        path: Path,
        progress_bar: tqdm,
        convert_step_units: float,
    ) -> None:
        """
        Create the converter with or without chapters.

        Args:
            result (ConversionResult): Result from Docling conversion.
            chapters (bool): Group content under headings into chapters and sections.
            path: Path to the PDF file.
            progress_bar (tqdm): Progress bar to update during conversion.
            convert_step_units (float): Total progress units allocated to conversion.
        """
        self._converter: AbstractInternalDocumentConverter = self._create_implementation(
            result,
            chapters,
            path,
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
        document.group_page_headers_and_footers()
        document.normalize_heading_levels()
        logger.info(document.debug_info())
        return document

    @staticmethod
    def _create_implementation(
        result: ConversionResult,
        chapters: bool,
        path: Path,
        progress_bar: tqdm,
        convert_step_units: float,
    ) -> AbstractInternalDocumentConverter:
        """
        Create the implementation with or without chapters.

        Args:
            result (ConversionResult): Result from Docling conversion.
            chapters (bool): Group content under headings into chapters and sections.
            path: Path to the PDF file.
            progress_bar (tqdm): Progress bar to update during conversion.
            convert_step_units (float): Total progress units allocated to conversion.
        """
        if chapters:
            return ConvertToChapterStructure(result, path, progress_bar, convert_step_units)

        return ConvertToPageStructure(result, path, progress_bar, convert_step_units)
