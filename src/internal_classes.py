from typing import Optional

from docling_core.types.doc import (
    DocItem,
    GroupItem,
    NodeItem,
)


class InternalElement:
    """
    Class to represent one Structure inside PDF document.
    Contains reference to parent and references to children so you can crawl both ways.
    Contains information which BBOX inside Docling Data is for this element.
    Contains also information if this is continuous structure and has reference to first structure.
    """

    def __init__(self, item: NodeItem, parent: Optional["InternalElement"]) -> None:
        """
        Constructor.

        Args:
            item (NodeItem): Reference to Docling Data.
            parent (Optional[InternalElement]): None or already created element.
        """
        self.item: NodeItem = item
        self.provenance_index: int = -1
        self.children: list["InternalElement"] = []
        self.page_number: int = -1
        self.parent: Optional["InternalElement"] = parent
        self.continuous_element: Optional["InternalElement"] = None

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
        if isinstance(self.item, DocItem):
            type_str = str(self.item.label)
        elif isinstance(self.item, GroupItem):
            type_str = str(self.item.label)
        item_str: str = f"Item '{self.id()}' ({type_str})"  # [{str(self.item.content_layer)}]"
        parent_str: str = f"Parent '{self.parent.id()}'" if self.parent is not None else "'No parent'"
        continuous_str: str = (
            f"Continuous '{self.continuous_element.id()}'" if self.continuous_element is not None else "'No continuous'"
        )
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
