from enum import Enum
from typing import Optional

from docling_core.types.doc import (
    DocItem,
    DocItemLabel,
    GroupItem,
    GroupLabel,
    NodeItem,
    TextItem,
)


class InternalElementGroup(Enum):
    """
    Semantic group created by this project rather than supplied by Docling.
    """

    NONE = "none"
    HEADER = "header"
    FOOTER = "footer"


class InternalElement:
    """
    Class to represent one Structure inside PDF document.
    Contains reference to parent and references to children so you can crawl both ways.
    Contains information which BBOX inside Docling Data is for this element.
    Contains also information if this is continuous structure and has reference to first structure.
    """

    def __init__(
        self,
        item: NodeItem,
        parent: Optional["InternalElement"],
        group: InternalElementGroup = InternalElementGroup.NONE,
    ) -> None:
        """
        Constructor.

        Args:
            item (NodeItem): Reference to Docling Data.
            parent (Optional[InternalElement]): None or already created element.
            group (InternalElementGroup): Project-created semantic group, if any.
        """
        self.item: NodeItem = item
        self.provenance_index: int = -1
        self.children: list["InternalElement"] = []
        self.page_number: int = -1
        self.parent: Optional["InternalElement"] = parent
        self.group: InternalElementGroup = group
        self.continuous_element: Optional["InternalElement"] = None
        # True also for the first element of a continuous chain, which has no continuous_element reference
        self.is_continuous: bool = False

    def id(self) -> str:
        """
        Unique identificator through whole PDF document received from Docling data.

        Returns:
            Unique identifier as string.
        """
        node_id: str = self.item.self_ref.replace("#", "").replace("/", "")
        return node_id

    def debug_info(self, level: int) -> str:
        """
        Debug function to print information about the element.

        Args:
            level (int): Level of indentation.

        Returns:
            Printable string containing information about the element.
        """
        offset: str = "    " * level
        type_str: str = "Unknown"
        if self.group != InternalElementGroup.NONE:
            type_str = self.group.value
        elif isinstance(self.item, DocItem):
            type_str = str(self.item.label)
        elif isinstance(self.item, GroupItem):
            type_str = str(self.item.label)
        item_str: str = f"Item '{self.id()}' ({type_str})"  # [{str(self.item.content_layer)}]"
        parent_str: str = f"Parent '{self.parent.id()}'" if self.parent is not None else "'No parent'"
        if self.continuous_element is not None:
            continuous_str: str = f"Continuous '{self.continuous_element.id()}'"
        elif self.is_continuous:
            continuous_str = "'Continuous first'"
        else:
            continuous_str = "'No continuous'"
        data_str: str = f"{offset}{item_str} {parent_str} {continuous_str} Provenance Index: {self.provenance_index}"
        data_str += f" Page: {self.page_number}"
        if len(self.children) > 0:
            data_str += " Children:"
            for child in self.children:
                data_str += "\n" + child.debug_info(level + 1)
        else:
            data_str += " 'No children'"
        return data_str


class InternalPage:
    """
    Class to represent one page of PDF document with list of elements that are in order Docling provided.
    """

    def __init__(self) -> None:
        """
        Constructor.
        """
        self.number: int = 0
        self.height: float = 0
        self.width: float = 0
        self.ordered_elements: list[InternalElement] = []

    def debug_info(self, level: int) -> str:
        """
        Debug function to print information about page.

        Args:
            level (int): Level of indentation.

        Returns:
            Printable string containing information about the page.
        """
        offset: str = "    " * level
        data_str: str = f"{offset}Page {self.number} Height: {self.height} Width: {self.width} Elements:"
        for element in self.ordered_elements:
            data_str += "\n" + element.debug_info(level + 1)
        return data_str

    def group_headers_and_footers(self) -> None:
        """
        Move every page header and footer out of the page hierarchy and into one semantic group per type.

        The header group is placed first and the footer group last. Relative order among extracted elements and
        among body elements is preserved.
        """
        headers: list[InternalElement] = []
        footers: list[InternalElement] = []

        body_elements: list[InternalElement] = self._extract_group_elements(
            self.ordered_elements,
            InternalElementGroup.HEADER,
            DocItemLabel.PAGE_HEADER,
            headers,
        )
        body_elements = self._extract_group_elements(
            body_elements,
            InternalElementGroup.FOOTER,
            DocItemLabel.PAGE_FOOTER,
            footers,
        )

        grouped_elements: list[InternalElement] = []
        if len(headers) > 0:
            grouped_elements.append(self._create_furniture_group(InternalElementGroup.HEADER, headers))

        grouped_elements.extend(body_elements)

        if len(footers) > 0:
            grouped_elements.append(self._create_furniture_group(InternalElementGroup.FOOTER, footers))

        self.ordered_elements = grouped_elements

    def _extract_group_elements(
        self,
        elements: list[InternalElement],
        group: InternalElementGroup,
        label: DocItemLabel,
        extracted: list[InternalElement],
    ) -> list[InternalElement]:
        """
        Remove matching elements recursively and append them to extracted in reading order.
        """
        remaining: list[InternalElement] = []

        for element in elements:
            if element.group == group:
                extracted.extend(element.children)
                continue

            if isinstance(element.item, TextItem) and element.item.label == label:
                extracted.append(element)
                continue

            element.children = self._extract_group_elements(element.children, group, label, extracted)
            remaining.append(element)

        return remaining

    def _create_furniture_group(self, group: InternalElementGroup, children: list[InternalElement]) -> InternalElement:
        """
        Create a project-owned header or footer group with the extracted elements as children.
        """
        group_item: GroupItem = GroupItem(
            label=GroupLabel.UNSPECIFIED,
            name=f"page_{group.value}",
            self_ref=f"#/page-{group.value}-group-{self.number}",
        )
        group_element: InternalElement = InternalElement(group_item, None, group)

        for child in children:
            child.parent = group_element
            group_element.children.append(child)

        return group_element


class InternalDocument:
    """
    Class to represent whole PDF document with list of pages and used Docling version.
    """

    def __init__(self) -> None:
        """
        Constructor.
        """
        self.pages: list[InternalPage] = []
        # For docling reading order (does not have page by page structure)
        self.ordered_elements: list[InternalElement] = []
        self.docling_version: str = ""

    def debug_info(self) -> str:
        """
        Debug function to print information about document.

        Returns:
            Printable string containing information about the document.
        """
        data_str: str = f"Docling Version: {self.docling_version}\n"
        data_str += "Pages:\n"
        for page in self.pages:
            data_str += page.debug_info(1) + "\n"
        data_str += "Ordered Elements:\n"
        for element in self.ordered_elements:
            data_str += element.debug_info(1) + "\n"
        return data_str

    def group_page_headers_and_footers(self) -> None:
        """
        Group and position headers and footers independently on every page.
        """
        for page in self.pages:
            page.group_headers_and_footers()
