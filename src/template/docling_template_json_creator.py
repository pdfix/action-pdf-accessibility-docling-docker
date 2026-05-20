from typing import Optional

import tqdm
from pdfixsdk import GetPdfix, PdfDoc, Pdfix, PdfPage, PdfPageView

from constants import ZOOM
from exceptions import PdfixFailedToOpenException, PdfixFailedToTagException, PdfixInitializeException
from internal_classes import InternalDocument
from template.abstract_template_json_creator import AbstractTemplateJsonCreator


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
        return self._build_template_dict(document, chapter_list)

    def _build_chapter_element_create(self, document: InternalDocument) -> list:
        if len(document.ordered_elements) == 0:
            self.progress_bar.update(self.total_progress_units)
            return []

        pdfix: Optional[Pdfix] = GetPdfix()
        if pdfix is None:
            raise PdfixInitializeException()

        try:
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
                        if page_number not in page_cache:
                            pdf_page: Optional[PdfPage] = doc.AcquirePage(page_number - 1)
                            if pdf_page is None:
                                raise PdfixFailedToTagException(pdfix, "Failed to acquire the page")
                            page_view: Optional[PdfPageView] = pdf_page.AcquirePageView(ZOOM, 0)
                            if page_view is None:
                                pdf_page.Release()
                                raise PdfixFailedToTagException(pdfix, "Failed to acquire the page view")
                            page_height: float = pdf_page.height
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
        finally:
            pdfix.Release()
