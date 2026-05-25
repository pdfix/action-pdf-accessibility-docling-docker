import logging
from typing import Optional

from docling_core.types.doc import DoclingDocument, NodeItem

from converter.abstract_internal_document_converter import AbstractInternalDocumentConverter
from internal_classes import InternalDocument, InternalElement, InternalPage
from logger import get_logger

logger: logging.Logger = get_logger()


class ConvertToPageStructure(AbstractInternalDocumentConverter):
    """
    Converts DoclingDocument into InternalDocument with pages and ordered elements per page.
    """

    def convert(self) -> InternalDocument:
        """
        Convert DoclingDocument into InternalDocument with pages and ordered elements per page.

        Returns:
            InternalDocument with pages and ordered elements per page.
        """
        document: DoclingDocument = self.result.document
        progress_bar_budget: int = 1 + len(document.pages) + len(document.body.children)
        progress_step: float = self.convert_step_units / progress_bar_budget

        # Create return object
        internal_document: InternalDocument = InternalDocument()
        internal_document.docling_version = document.version
        self.progress_bar.update(progress_step)

        # Add pages
        internal_document.pages = self._create_pages(document, progress_step)

        # Add elements
        self._add_elements(document, internal_document, progress_step)

        return internal_document

    def _create_pages(self, document: DoclingDocument, progress_step: float) -> list[InternalPage]:
        """
        Create pages from DoclingDocument.

        Args:
            document (DoclingDocument): Document to create pages from.
            bar_step (float): Step to update progress bar.

        Returns:
            List of created pages.
        """
        pages: list[InternalPage] = []

        for page in document.pages.values():
            internal_page: InternalPage = InternalPage()
            internal_page.number = page.page_no
            internal_page.height = page.size.height
            internal_page.width = page.size.width
            pages.append(internal_page)

            self.progress_bar.update(progress_step)

        return pages

    def _add_elements(
        self, document: DoclingDocument, internal_document: InternalDocument, progress_step: float
    ) -> None:
        """
        Add elements to pages.

        Args:
            document (DoclingDocument): Document to add elements to.
            internal_document (InternalDocument): Internal document to add elements to.
            progress_step (float): Step to update progress bar.
        """
        for reference in document.body.children:
            item: Optional[NodeItem] = self._get_item(document, reference.cref)
            if item is None:
                continue

            elements: list[InternalElement] = self._create_elements(document, item, None)
            for element in elements:
                page_index: int = element.page_number - 1

                if 0 <= page_index < len(internal_document.pages):
                    internal_document.pages[page_index].ordered_elements.append(element)
                else:
                    logger.error(f"Cannot add element: {element.id()} to page_index: {page_index}")

            self.progress_bar.update(progress_step)
