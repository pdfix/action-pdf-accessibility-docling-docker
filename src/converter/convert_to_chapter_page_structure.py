import logging

from docling_core.types.doc import DocItem, DoclingDocument
from hierarchical.postprocessor import ResultPostprocessor

from converter.convert_to_chapter_structure import ConvertToChapterStructure
from internal_classes import InternalDocument, InternalElement
from logger import get_logger

logger: logging.Logger = get_logger()


class ConvertToChapterPageStructure(ConvertToChapterStructure):
    """
    Converts DoclingDocument into InternalDocument that keeps the chapter/section hierarchy of the Docling
    post-processing reading order, but places that hierarchy back under pages.

    Elements spanning several pages are duplicated per page: every clone keeps only the children that belong to
    its page and clones after the first one reference the first clone as their continuous element.
    """

    def convert(self) -> InternalDocument:
        """
        Convert DoclingDocument into InternalDocument with chapter hierarchy split into pages.

        Returns:
            InternalDocument with pages, each holding chapter/section hierarchy of that page.
        """
        # The postprocessor modifies the result.document in place.
        ResultPostprocessor(self.result).process()
        document: DoclingDocument = self.result.document

        bar_budget: int = 4 + len(document.pages)
        bar_step: float = self.convert_step_units / bar_budget
        self.progress_bar.update(bar_step)

        # Return object
        internal_document: InternalDocument = InternalDocument()
        internal_document.docling_version = document.version
        internal_document.pages = self._create_pages(document, bar_step)

        # Transform Docling data into internal data structure
        elements: list[InternalElement] = self._create_root_list(document)
        self.progress_bar.update(bar_step)

        internal_document.ordered_elements = elements
        self._dump_docling_hierarchy(internal_document)
        internal_document.ordered_elements = []

        # Filter out elements without page number and join continuous elements together in the whole tree, so each
        # Docling item is present exactly once before it is split by pages again
        joined_elements: list[InternalElement] = self._join_and_filter_tree(elements)
        self.progress_bar.update(bar_step)

        # Add chapters and sections groups to elements
        chapter_and_section_groups: list[InternalElement] = self._add_chapters_and_sections_groups(joined_elements)
        self.progress_bar.update(bar_step)

        # Split the hierarchy back into pages
        self._distribute_elements_to_pages(chapter_and_section_groups, internal_document)

        return internal_document

    def _join_and_filter_tree(self, elements: list[InternalElement]) -> list[InternalElement]:
        """
        Join continuous elements together and filter out elements without page number in the whole tree.

        Args:
            elements (list[InternalElement]): Elements to join and filter.

        Returns:
            List of joined and filtered elements with joined and filtered children.
        """
        result: list[InternalElement] = self._join_and_filter_elements(elements)

        for element in result:
            if len(element.children) > 0:
                element.children = self._join_and_filter_tree(element.children)

        return result

    def _distribute_elements_to_pages(
        self, elements: list[InternalElement], internal_document: InternalDocument
    ) -> None:
        """
        Split elements by pages and add them to pages of internal document.

        Args:
            elements (list[InternalElement]): Elements in Docling reading order to distribute.
            internal_document (InternalDocument): Internal document to add elements to.
        """
        for element in elements:
            for page_element in self._split_element_by_pages(element):
                page_index: int = page_element.page_number - 1

                if 0 <= page_index < len(internal_document.pages):
                    internal_document.pages[page_index].ordered_elements.append(page_element)
                else:
                    logger.error(f"Cannot add element: {page_element.id()} to page_index: {page_index}")

    def _split_element_by_pages(self, element: InternalElement) -> list[InternalElement]:
        """
        Create one copy of element for each page the element occupies. Children are split the same way and each copy
        gets only children of its page. Copies after the first one point to the first one as continuous element.
        Parent of returned copies is left unset, caller is responsible for it.

        Args:
            element (InternalElement): Element to split by pages.

        Returns:
            List of created copies sorted by page number. Empty when element cannot be placed on any page.
        """
        children_by_page: dict[int, list[InternalElement]] = {}
        for child in element.children:
            for child_copy in self._split_element_by_pages(child):
                children_by_page.setdefault(child_copy.page_number, []).append(child_copy)

        provenance_pages: dict[int, int] = self._provenance_pages(element)

        # Element with bounding box but without usable provenance cannot be placed on any page, so it is dropped and
        # its children are used instead of it
        if isinstance(element.item, DocItem) and len(provenance_pages) == 0:
            logger.warning(f"No provenance for element: '{element.id()}' dropping it and keeping its children...")
            return [child_copy for page in sorted(children_by_page) for child_copy in children_by_page[page]]

        page_numbers: list[int] = sorted(set(provenance_pages) | set(children_by_page))
        if len(page_numbers) == 0:
            logger.warning(f"No page for element: '{element.id()}' skipping it...")
            return []

        copies: list[InternalElement] = []

        for page_number in page_numbers:
            element_copy: InternalElement = InternalElement(element.item, None)
            element_copy.page_number = page_number
            element_copy.provenance_index = self._provenance_index_for_page(provenance_pages, page_number)

            for child_copy in children_by_page.get(page_number, []):
                child_copy.parent = element_copy
                element_copy.children.append(child_copy)

            if len(copies) > 0:
                element_copy.continuous_element = copies[0]
                element_copy.is_continuous = True
                copies[0].is_continuous = True

            copies.append(element_copy)

        return copies

    def _provenance_pages(self, element: InternalElement) -> dict[int, int]:
        """
        Collect pages the element itself is placed on together with provenance index to use for each of them.

        Args:
            element (InternalElement): Element to collect pages for.

        Returns:
            Page number to provenance index mapping. Empty for groups that have no bounding box.
        """
        if not isinstance(element.item, DocItem):
            return {}

        # Element created for one specific provenance stands only for that provenance
        if element.continuous_element is not None:
            if element.page_number < 1:
                return {}
            return {element.page_number: element.provenance_index}

        pages: dict[int, int] = {}

        for index, provenance in enumerate(element.item.prov):
            page_number: int = provenance.page_no
            if page_number >= 1 and page_number not in pages:
                pages[page_number] = index

        return pages

    def _provenance_index_for_page(self, provenance_pages: dict[int, int], page_number: int) -> int:
        """
        Get provenance index to use for copy of element created for given page.

        Args:
            provenance_pages (dict[int, int]): Page number to provenance index mapping of the element.
            page_number (int): Page the copy of element is created for.

        Returns:
            Provenance index or -1 for groups that have no bounding box.
        """
        if len(provenance_pages) == 0:
            return -1

        if page_number in provenance_pages:
            return provenance_pages[page_number]

        # Copy created only because a child spilled to this page, so reuse the closest preceding bounding box
        previous_pages: list[int] = [page for page in provenance_pages if page < page_number]
        if len(previous_pages) > 0:
            return provenance_pages[max(previous_pages)]

        return provenance_pages[min(provenance_pages)]
