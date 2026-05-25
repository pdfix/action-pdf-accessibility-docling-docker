import logging
from abc import ABC, abstractmethod
from typing import Optional

from docling.datamodel.document import ConversionResult
from docling_core.types.doc import (
    DocItem,
    DoclingDocument,
    GroupItem,
    NodeItem,
    ProvenanceItem,
)
from tqdm import tqdm

from internal_classes import InternalDocument, InternalElement
from logger import get_logger

logger: logging.Logger = get_logger()


class AbstractInternalDocumentConverter(ABC):
    """
    Converts a DoclingDocument into this project's InternalDocument representation.
    """

    def __init__(
        self,
        result: ConversionResult,
        progress_bar: tqdm,
        convert_step_units: float,
    ) -> None:
        """
        Args:
            result (ConversionResult): Result from Docling conversion.
            progress_bar (tqdm): Progress bar to update during conversion.
            convert_step_units (float): Total progress units allocated to conversion.
        """
        self.result: ConversionResult = result
        self.progress_bar: tqdm = progress_bar
        self.convert_step_units: float = convert_step_units

    @abstractmethod
    def convert(self) -> InternalDocument:
        """
        Convert DoclingDocument into InternalDocument.

        Returns:
            Internal representation of the PDF document.
        """
        pass

    def _create_elements(
        self, document: DoclingDocument, item: NodeItem, parent: Optional[InternalElement]
    ) -> list[InternalElement]:
        """
        Creates element(s) from provided document and item. Some NodeItem can result in many elements.
        Either NodeItem has multiple ProvenanceItems or children of NodeItem are on multiple pages.
        Creates also children recursively.

        Args:
            document (DoclingDocument): Processed document by Docling.
            item (NodeItem): Structure element that is processed according to its data.
            parent (Optional[InternalElement]): Already created parent or None.

        Returns:
            List of created elements for item.
        """
        internal_elements: list[InternalElement] = []

        if isinstance(item, DocItem):
            provenances: list[ProvenanceItem] = item.prov
            for index in range(len(provenances)):
                internal_element: InternalElement = InternalElement(item, parent)
                internal_element.provenance_index = index
                internal_element.page_number = provenances[index].page_no
                if index > 0:
                    internal_element.continuous_element = internal_elements[0]
                internal_elements.append(internal_element)
            internal_element = internal_elements[0]
        elif isinstance(item, GroupItem):
            internal_element = InternalElement(item, parent)
            internal_element.provenance_index = -1
            internal_elements.append(internal_element)
        else:
            logger.error("Unsupported descendant NodeItem type")
            return internal_elements

        children: list[InternalElement] = []

        if len(item.children) > 0:
            for child_ref in item.children:
                child_item: Optional[NodeItem] = self._get_item(document, child_ref.cref)
                if child_item is None:
                    continue
                child_elements: list[InternalElement] = self._create_elements(document, child_item, internal_element)
                children.extend(child_elements)

            page_children: dict[int, list[InternalElement]] = {}
            for child in children:
                page_number: int = child.page_number
                if page_number not in page_children:
                    page_children[page_number] = []
                page_children[page_number].append(child)

            first: bool = True
            for page_number, child_list in page_children.items():
                if first:
                    internal_element.page_number = page_number
                    internal_element.children.extend(child_list)
                    first = False
                else:
                    new_element = InternalElement(item, parent)
                    new_element.provenance_index = internal_element.provenance_index
                    new_element.page_number = page_number
                    new_element.children.extend(child_list)
                    new_element.continuous_element = internal_element
                    internal_elements.append(new_element)

        return internal_elements

    def _get_item(self, document: DoclingDocument, reference: str) -> Optional[NodeItem]:
        """
        Retrieves NodeItem from DoclingDocument according to its Docling identifier.

        Args:
            document (DoclingDocument): Processed document by Docling.
            reference (str): Docling type of unique identifier.

        Returns:
            Found NodeItem or None.
        """
        for group in document.groups:
            if group.self_ref == reference:
                return group
        for text in document.texts:
            if text.self_ref == reference:
                return text
        for picture in document.pictures:
            if picture.self_ref == reference:
                return picture
        for table in document.tables:
            if table.self_ref == reference:
                return table
        for key_value_item in document.key_value_items:
            if key_value_item.self_ref == reference:
                return key_value_item
        for form_item in document.form_items:
            if form_item.self_ref == reference:
                return form_item
        return None
