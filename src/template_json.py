from tqdm import tqdm

from internal_classes import InternalDocument
from template.abstract_template_json_creator import AbstractTemplateJsonCreator, Placement
from template.chapter_template_json_creator import ChapterTemplateJsonCreator
from template.page_template_json_creator import PageTemplateJsonCreator

__all__ = ["Placement", "TemplateJsonCreator"]


class TemplateJsonCreator:
    """
    Facade that selects the template builder (with or without chapters) and delegates processing.
    """

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        chapters: bool,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        """
        Create the template builder with or without chapters.

        Args:
            input_path_str (str): Path to the source PDF.
            bbox_overlap (float): Overlap threshold for matching Docling boxes to PDF elements.
            chapters (bool): Structure the document into chapters and sections, otherwise by pages.
            progress_bar (tqdm): Progress bar for template creation.
            total_progress_units (int): Progress units allocated to template creation.
        """
        self._creator: AbstractTemplateJsonCreator = self._create_implementation(
            input_path_str,
            bbox_overlap,
            chapters,
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
        chapters: bool,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> AbstractTemplateJsonCreator:
        """
        Create the implementation with or without chapters.

        Args:
            input_path_str (str): Path to the source PDF.
            bbox_overlap (float): Overlap threshold for matching Docling boxes to PDF elements.
            chapters (bool): Structure the document into chapters and sections, otherwise by pages.
            progress_bar (tqdm): Progress bar for template creation.
            total_progress_units (int): Progress units allocated to template creation.
        """
        if chapters:
            return ChapterTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)

        return PageTemplateJsonCreator(input_path_str, bbox_overlap, progress_bar, total_progress_units)
