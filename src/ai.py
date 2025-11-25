import json
import logging
import traceback
from pathlib import Path
from typing import Optional

from docling.datamodel.document import ConversionResult
from docling.document_converter import DocumentConverter
from docling_core.types.doc import (
    DocItem,
    DoclingDocument,
    GroupItem,
    NodeItem,
    ProvenanceItem,
)

from logger import get_logger

logger: logging.Logger = get_logger()


class InternalElement:
    def __init__(self, item: NodeItem) -> None:
        self.item: NodeItem = item
        self.provenance_index: int = 0
        self.children: list["InternalElement"] = []

    def debug_info(self) -> str:
        if isinstance(self.item, DocItem):
            self.item.self_ref
            return f"DocItem {self.item.self_ref} ({type(self.item)})"
        if isinstance(self.item, GroupItem):
            return f"GroupItem {self.item.self_ref} ({type(self.item)})"
        return f"Unkown {type(self.item)}"


class InternalPage:
    def __init__(self) -> None:
        self.number: int = 0
        self.height: float = 0
        self.width: float = 0
        self.ordered_elements: list[InternalElement] = []


class InternalDocument:
    def __init__(self) -> None:
        self.pages: list[InternalPage] = []
        self.docling_version: str = ""


def get_item(document: DoclingDocument, reference: str) -> Optional[NodeItem]:
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


def create_elements(document: DoclingDocument, item: NodeItem) -> list[InternalElement]:
    internal_elements: list[InternalElement] = []

    # Create element(s) according to provenances
    if isinstance(item, DocItem):
        provenances: list[ProvenanceItem] = item.prov
        for index in range(len(provenances)):
            internal_element: InternalElement = InternalElement(item)
            internal_element.provenance_index = index
            internal_elements.append(internal_element)
    elif isinstance(item, GroupItem):
        internal_element = InternalElement(item)
        internal_element.provenance_index = -1
        internal_elements.append(internal_element)
    else:
        print("Unsupported descendant NodeItem type")

    # Recursively create children
    if len(internal_elements) > 0:
        for child_ref in item.children:
            child_item: Optional[NodeItem] = get_item(document, child_ref.cref)
            if child_item is None:
                continue
            child_elements: list[InternalElement] = create_elements(document, child_item)
            internal_elements[0].children.extend(child_elements)

    return internal_elements


def get_start_page_number(elements: list[InternalElement]) -> int:
    # Find page number in DocItems
    for element in elements:
        if isinstance(element.item, DocItem):
            return element.item.prov[0].page_no
    # Find page number in GroupItems
    for element in elements:
        if isinstance(element.item, GroupItem):
            number: int = get_start_page_number(element.children)
            if number > 0:
                return number
    # Not found
    return -1


def process_pdf(path: Path) -> Optional[InternalDocument]:
    try:
        converter: DocumentConverter = DocumentConverter()
        result: ConversionResult = converter.convert(path)
    except Exception as e:
        red: str = "\033[31m"
        reset: str = "\033[0m"
        print(f"{red}Error during docling conversion:\n{e}{reset}")
        traceback.print_stack()
        return None
    document: DoclingDocument = result.document
    outputs_folder: Path = Path(__file__).parent.parent.joinpath("outputs")
    outputs_folder.mkdir(exist_ok=True)
    docling_json_path: Path = outputs_folder.joinpath(f"{path.stem}_output.json")
    with open(docling_json_path, "w") as f:
        json.dump(document.export_to_dict(), f, indent=4)
    internal_document: InternalDocument = InternalDocument()
    internal_document.docling_version = document.version

    for page in document.pages.values():
        internal_page: InternalPage = InternalPage()
        internal_page.number = page.page_no
        internal_page.height = page.size.height
        internal_page.width = page.size.width
        internal_document.pages.append(internal_page)

    for reference in document.body.children:
        # Get the item for the reference
        item: Optional[NodeItem] = get_item(document, reference.cref)
        if item is None:
            continue

        # Get first page that element appears in
        elements: list[InternalElement] = create_elements(document, item)
        page_number: int = get_start_page_number(elements)
        page_index: int = page_number - 1

        if 0 <= page_index < len(internal_document.pages):
            internal_document.pages[page_index].ordered_elements.extend(elements)

    return internal_document
