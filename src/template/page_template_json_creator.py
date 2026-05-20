from typing import Optional

from pdfixsdk import GetPdfix, PdfDoc, Pdfix, PdfPage, PdfPageView

from constants import ZOOM
from exceptions import PdfixFailedToOpenException, PdfixFailedToTagException, PdfixInitializeException
from internal_classes import InternalDocument, InternalElement, InternalPage
from template.abstract_template_json_creator import AbstractTemplateJsonCreator


class PageTemplateJsonCreator(AbstractTemplateJsonCreator):
    """
    Template JSON built from per-page blocks (element_create entries with $page_num query).
    """

    def process_document(self, document: InternalDocument) -> dict:
        """
        Build a PDFix template JSON with one element_create block per page.

        Args:
            document (InternalDocument): Internal representation of the PDF with Docling layout data.

        Returns:
            Complete template JSON dict (metadata and template with per-page element_create entries).
        """
        page_list: list = self._build_page_element_create(document)
        return self._build_template_dict(document, page_list)

    def _build_page_element_create(self, document: InternalDocument) -> list:
        if len(document.pages) == 0:
            self.progress_bar.update(self.total_progress_units)
            return []

        pdfix: Optional[Pdfix] = GetPdfix()
        if pdfix is None:
            raise PdfixInitializeException()

        doc: Optional[PdfDoc] = pdfix.OpenDoc(self.input_path_str, "")
        if doc is None:
            raise PdfixFailedToOpenException(pdfix, self.input_path_str)

        step: float = self.total_progress_units / len(document.pages)
        template_json_pages: list = []

        for index, page in enumerate(document.pages):
            pdf_page: Optional[PdfPage] = doc.AcquirePage(index)
            if pdf_page is None:
                raise PdfixFailedToTagException(pdfix, "Failed to acquire the page")

            try:
                page_view: Optional[PdfPageView] = pdf_page.AcquirePageView(ZOOM, 0)
                if page_view is None:
                    raise PdfixFailedToTagException(pdfix, "Failed to acquire the page view")

                try:
                    page_dict: dict = self._process_page(page, page_view)
                    page_dict = self._postprocess_template_block(page_dict)
                    template_json_pages.append(page_dict)
                    self.progress_bar.update(step)
                finally:
                    page_view.Release()
            finally:
                pdf_page.Release()

        return template_json_pages

    def _process_page(self, page: InternalPage, page_view: PdfPageView) -> dict:
        page_elements: list = self._create_page(page, page_view)

        return {
            "comment": f"Page {page.number}",
            "elements": page_elements,
            "query": {
                "$and": [{"$page_num": page.number}],
            },
            "statement": "$if",
        }

    def _create_page(self, page: InternalPage, page_view: PdfPageView) -> list:
        results: list = []
        page_h: float = page.height

        for element in self._get_page_elements(page):
            results.extend(self._create_elements(element, page_view, page_h, False))

        return results

    def _get_page_elements(self, page: InternalPage) -> list[InternalElement]:
        return page.ordered_elements
