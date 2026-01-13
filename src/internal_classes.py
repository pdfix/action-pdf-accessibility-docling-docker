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
        # page_id: str = str(self.page_number)
        # provenance_id: str = str(self.provenance_index) if self.provenance_index >= 0 else "x"
        # return f"{node_id}-{page_id}-{provenance_id}"

    def debug_info(self) -> str:
        """
        Debug function to print information if NodeItem is DocItem or GroupItem as they differ.

        Returns:
            Printable string containing parent type, id, current type.
        """
        if isinstance(self.item, DocItem):
            self.item.self_ref
            return f"DocItem {self.item.self_ref} ({type(self.item)})"
        if isinstance(self.item, GroupItem):
            return f"GroupItem {self.item.self_ref} ({type(self.item)})"
        return f"Unkown {type(self.item)}"


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


class InternalDocument:
    """
    Class to represent whole PDF document with list of pages and used Docling version.
    """

    def __init__(self) -> None:
        """
        Constructor.
        """
        self.pages: list[InternalPage] = []
        self.docling_version: str = ""
