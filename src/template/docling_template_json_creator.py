import logging
from typing import Optional

import tqdm
from pdfixsdk import GetPdfix, PdfDoc, Pdfix, PdfPage, PdfPageView

from constants import ZOOM
from exceptions import PdfixFailedToOpenException, PdfixFailedToTagException, PdfixInitializeException
from internal_classes import InternalDocument, InternalElement
from logger import get_logger
from template.abstract_template_json_creator import AbstractTemplateJsonCreator

logger: logging.Logger = get_logger()


class DoclingTemplateJsonCreator(AbstractTemplateJsonCreator):
    """
    Docling chapter reading order: rd_sort 3, rd_index on elements.
    Builds element_create from document.ordered_elements (no per-page blocks).
    """

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        super().__init__(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        self.page_map_settings[0]["rd_sort"] = "3"
        self.add_rd_indexes = True

    def process_document(self, document: InternalDocument) -> dict:
        """
        Build a PDFix template JSON from document-level reading order (chapter structure).

        Args:
            document (InternalDocument): Internal representation with ordered_elements in Docling reading order.

        Returns:
            Complete template JSON dict (metadata and template with a single element_create block).
        """
        chapter_list: list = self._build_chapter_element_create(document)
        whole_template: dict = self._build_template_dict(document, chapter_list)
        self._add_pages_to_elements(whole_template, document)
        return whole_template

    def _build_chapter_element_create(self, document: InternalDocument) -> list:
        if len(document.ordered_elements) == 0:
            self.progress_bar.update(self.total_progress_units)
            return []

        pdfix: Optional[Pdfix] = GetPdfix()
        if pdfix is None:
            raise PdfixInitializeException()

        doc: Optional[PdfDoc] = pdfix.OpenDoc(self.input_path_str, "")
        if doc is None:
            raise PdfixFailedToOpenException(pdfix, self.input_path_str)

        try:
            step: float = self.total_progress_units / len(document.ordered_elements)
            page_cache: dict[int, tuple[PdfPage, PdfPageView, int]] = {}
            elements: list[dict] = []

            try:
                for element in document.ordered_elements:
                    page_number: int = element.page_number
                    if page_number < 1:
                        logger.error(f"Page {page_number} does not exists, using first page instead")
                        page_number = 1
                    if page_number not in page_cache:
                        pdf_page: Optional[PdfPage] = doc.AcquirePage(page_number - 1)
                        if pdf_page is None:
                            raise PdfixFailedToTagException(pdfix, "Failed to acquire the page")
                        page_view: Optional[PdfPageView] = pdf_page.AcquirePageView(ZOOM, 0)
                        if page_view is None:
                            pdf_page.Release()
                            raise PdfixFailedToTagException(pdfix, "Failed to acquire the page view")
                        page_height: int = page_view.GetDeviceHeight()
                        page_cache[page_number] = (pdf_page, page_view, page_height)

                    _, page_view, page_height = page_cache[page_number]
                    elements.extend(self._create_elements(element, page_view, float(page_height), False))
                    self.progress_bar.update(step)
            finally:
                for pdf_page, page_view, _ in page_cache.values():
                    if page_view is not None:
                        page_view.Release()
                    if pdf_page is not None:
                        pdf_page.Release()

            post_processed_elements: list = [self._postprocess_template_block(element) for element in elements]
            return post_processed_elements
        finally:
            doc.Close()

    def _add_pages_to_elements(self, whole_template: dict, document: InternalDocument) -> None:
        """
        Add pages to elements where it makes sense.

        Args:
            whole_template (dict): Whole template dictionary.
            document (InternalDocument): Internal document.
        """
        template: dict = whole_template["template"]
        self._process_elements(template, document)

    def _process_elements(self, template: dict, document: InternalDocument) -> None:
        """
        Process elements and add pages to them where it makes sense.

        Args:
            template (dict): Template definition.
            document (InternalDocument): Internal document.
        """
        element_create: list = template["element_create"]

        for element in element_create:
            if "bbox" in element:
                element_id: str = element["name"]
                internal_element: Optional[InternalElement] = self._find_internal_element(
                    element_id, document.ordered_elements
                )
                if internal_element is None:
                    logger.error(f"Internal element {element_id} not found in document")
                else:
                    page_number: int = internal_element.page_number
                    template["query"] = {
                        "$and": [{"$page_num": page_number}],
                    }
                # Do not go deaper for elements with bbox (page is already set)
            elif "element_template" in element and "template" in element["element_template"]:
                child_template: dict = element["element_template"]["template"]
                self._process_elements(child_template, document)

    def _find_internal_element(self, element_id: str, elements: list[InternalElement]) -> Optional[InternalElement]:
        """
        Find internal element by its id.

        Args:
            element_id (str): Id of the element to find.
            document (InternalDocument): Internal document.

        Returns:
            Internal element or None if not found.
        """
        for element in elements:
            if element.id() == element_id:
                return element

            if element.children:
                result: Optional[InternalElement] = self._find_internal_element(element_id, element.children)
                if result is not None:
                    return result

        return None
