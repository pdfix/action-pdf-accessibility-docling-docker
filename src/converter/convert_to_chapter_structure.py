import logging
from typing import Optional

from docling_core.types.doc import DoclingDocument, NodeItem
from docling_core.types.doc.document import ContentLayer, GroupItem, GroupLabel, SectionHeaderItem
from hierarchical.postprocessor import ResultPostprocessor

from converter.abstract_internal_document_converter import AbstractInternalDocumentConverter
from internal_classes import InternalDocument, InternalElement
from logger import get_logger

logger: logging.Logger = get_logger()


class ConvertToChapterStructure(AbstractInternalDocumentConverter):
    """
    Converts DoclingDocument into InternalDocument organized by chapter structure (docling reading order).
    """

    def convert(self) -> InternalDocument:
        """
        Convert DoclingDocument into InternalDocument organized by chapter structure (docling reading order).

        Returns:
            InternalDocument organized by chapter structure.
        """
        bar_budget: int = 1 + 3
        bar_step: float = self.convert_step_units / bar_budget

        # The postprocessor modifies the result.document in place.
        ResultPostprocessor(self.result).process()
        document: DoclingDocument = self.result.document
        self.progress_bar.update(bar_step)

        # Return object
        internal_document: InternalDocument = InternalDocument()
        internal_document.docling_version = document.version

        # Transform Docling data into internal data structure
        elements: list[InternalElement] = self._create_root_list(document)
        self.progress_bar.update(bar_step)

        # Filter out elements without page number and join continuous elements together
        filtered_elements: list[InternalElement] = self._join_and_filter_elements(elements)
        self.progress_bar.update(bar_step)

        # Add chapters and sections groups to elements
        chapter_and_section_groups: list[InternalElement] = self._add_chapters_and_sections_groups(filtered_elements)
        self.progress_bar.update(bar_step)

        internal_document.ordered_elements = chapter_and_section_groups

        return internal_document

    def _create_root_list(self, document: DoclingDocument) -> list[InternalElement]:
        """
        Create list of elements that is directly in body of document.

        Args:
            document (DoclingDocument): Document structure from docling containing all data.

        Returns:
            List of root elements.
        """
        root_list: list[InternalElement] = []

        for reference in document.body.children:
            item: Optional[NodeItem] = self._get_item(document, reference.cref)
            if item is None:
                continue

            elements: list[InternalElement] = self._create_elements(document, item, None)
            root_list.extend(elements)

        return root_list

    def _join_and_filter_elements(self, elements: list[InternalElement]) -> list[InternalElement]:
        """
        Join continuous elements togetherand filter out elements without page number.

        Args:
            elements (list[InternalElement]): Elements to join and filter.

        Returns:
            List of joined and filtered elements.
        """
        result: list[InternalElement] = []

        for element in elements:
            id: str = element.id()

            # Page -1 hierarchy -> problem in docling post-process -> skip it
            if element.page_number < 1:
                logger.warning(f"Page number is less than 1 for element: '{id}' skipping it...")
                continue

            # Page header/footer just directly copy it
            if element.item.content_layer == ContentLayer.FURNITURE:
                result.append(element)
                continue

            # Joining groups together
            if element.continuous_element is not None:
                continuous_element_id: str = element.continuous_element.id()
                continuous_element: Optional[InternalElement] = None
                for result_element in result:
                    if result_element.id() == continuous_element_id:
                        continuous_element = result_element
                        break

                if continuous_element is not None:
                    self._join_elements(element, continuous_element)
                    continue
            else:
                result.append(element)

        return result

    def _join_elements(self, element_to_add: InternalElement, existing_element: InternalElement) -> None:
        """
        Join new element to existing element in place.

        Args:
            element_to_add (InternalElement): Element to add to existing element.
            existing_element (InternalElement): Existing element to join to.
        """
        for child in element_to_add.children:
            if child.continuous_element is None:
                existing_element.children.append(child)
            else:
                continuous_element_id: str = child.continuous_element.id()
                continuous_element: Optional[InternalElement] = None
                for result_element in existing_element.children:
                    if result_element.id() == continuous_element_id:
                        continuous_element = result_element
                        break

                if continuous_element is None:
                    logger.error("Did not find element in existing elements that is pointed by continuous element")
                    existing_element.children.append(child)
                else:
                    self._join_elements(child, continuous_element)

    def _add_chapters_and_sections_groups(self, elements: list[InternalElement]) -> list[InternalElement]:
        """
        Add chapters and sections groups to elements.

        Args:
            elements (list[InternalElement]): Elements to add chapters and sections groups to.

        Returns:
            List of elements with chapters and sections groups added.
        """
        result: list[InternalElement] = []

        for element in elements:
            if element.item.content_layer == ContentLayer.FURNITURE:
                result.append(element)
                continue

            new_element: InternalElement = element
            added_chapter: bool = False

            if isinstance(element.item, SectionHeaderItem):
                # Create chapter group with proper parent
                chapter_item: GroupItem = GroupItem(
                    label=GroupLabel.CHAPTER, self_ref=element.item.self_ref.replace("texts", "chaptergroup")
                )
                chapter_element: InternalElement = InternalElement(chapter_item, None)

                # Add chapter header as first child and then rest of chapter header children
                chapter_element.children.append(element)
                chapter_element.children.extend(element.children)

                # Reparent chapter header without children
                element.parent = chapter_element
                element.children = []

                # Add new group element and mark to skip chapter header
                new_element = chapter_element
                added_chapter = True

            result.append(new_element)
            self._process_children_chapters_and_sections(new_element, added_chapter)

        return result

    def _process_children_chapters_and_sections(self, source_element: InternalElement, skip_first_child: bool) -> None:
        """
        Process children of chapters and sections groups in place and add section groups.

        Args:
            source_element (InternalElement): Source element to process children of.
            skip_first_child (bool): Whether to skip the first child as it was already processed.
        """
        result: list[InternalElement] = []

        for child in source_element.children:
            new_child: InternalElement = child

            if skip_first_child:
                result.append(new_child)
                skip_first_child = False
                continue

            added_section: bool = False

            if isinstance(child.item, SectionHeaderItem):
                # Create section group with proper parent
                section_item: GroupItem = GroupItem(
                    label=GroupLabel.SECTION, self_ref=child.item.self_ref.replace("texts", "sectiongroup")
                )
                section_element: InternalElement = InternalElement(section_item, source_element)

                # Add section header as first child and then rest of section header children
                section_element.children.append(child)
                section_element.children.extend(child.children)

                # Reparent section header without children
                child.parent = section_element
                child.children = []

                # Add new group element and mark to skip section header
                new_child = section_element
                added_section = True

            result.append(new_child)
            self._process_children_chapters_and_sections(new_child, added_section)

        source_element.children = result
