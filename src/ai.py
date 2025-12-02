import json
import logging
import traceback
from pathlib import Path
from typing import Optional

# from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
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
        self.pages: list[InternalPage] = []
        self.docling_version: str = ""


def get_item(document: DoclingDocument, reference: str) -> Optional[NodeItem]:
    """
    Retrieves NodeItem from DoclingDocument according to its Docling indentificator.

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


def create_elements(
    document: DoclingDocument, item: NodeItem, parent: Optional[InternalElement]
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

    # Create element(s) according to provenances
    if isinstance(item, DocItem):
        provenances: list[ProvenanceItem] = item.prov
        for index in range(len(provenances)):
            internal_element: InternalElement = InternalElement(item, parent)
            internal_element.provenance_index = index
            internal_element.page_number = provenances[index].page_no
            if index > 0:
                # Points to first element (first Provenance) for NodeItem
                internal_element.continuous_element = internal_elements[0]
            internal_elements.append(internal_element)
        # Keep internal_element pointing to first element
        internal_element = internal_elements[0]
    elif isinstance(item, GroupItem):
        internal_element = InternalElement(item, parent)
        internal_element.provenance_index = -1
        internal_elements.append(internal_element)
    else:
        logger.error("Unsupported descendant NodeItem type")
        return internal_elements

    # Recursively create children
    children: list[InternalElement] = []

    if len(item.children) > 0:
        # Convert children
        for child_ref in item.children:
            child_item: Optional[NodeItem] = get_item(document, child_ref.cref)
            if child_item is None:
                continue
            # More children are expected for GroupItem -> there will be just one internal_element
            # For DocItem currently all provenances points to the same page and thus any children will also be from
            # the same page
            # With this we can safely assume that internal_element (always first create element for NodeItem) is parent
            # for their page
            child_elements: list[InternalElement] = create_elements(document, child_item, internal_element)
            children.extend(child_elements)

        # Sort children into page numbers
        page_children: dict[int, list[InternalElement]] = {}
        for child in children:
            page_number: int = child.page_number
            if page_number not in page_children:
                page_children[page_number] = []
            page_children[page_number].append(child)

        # Create more elements if children are on more pages
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
                # Points to first element (usually GroupItem with first page number) for NodeItem
                new_element.continuous_element = internal_element
                internal_elements.append(new_element)

    return internal_elements


def process_pdf(path: Path, do_formula_recognition: bool, do_image_description: bool) -> Optional[InternalDocument]:
    """
    Processed PDF document. First docling runs to create docling structure. That this structure is used to create
    internal representation of PDF document so each item is on correct page some items are split either between pages
    or for multiple columns inside same page.

    Args:
        path (Path): Path to PDF document.
        do_formula_recognition (bool): If formulas are post-processed by Docling to create LaTeX representation of them.
        do_image_description (bool): If pictures are post-processed by Docling to create description for image.

    Returns:
        Internal representation of PDF document with Docling Data. Or None if some error happens.
    """
    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        # pipeline_options.ocr_options.lang = ["en"]
        pipeline_options.do_formula_enrichment = do_formula_recognition
        pipeline_options.do_picture_description = do_image_description
        # GPU:
        # pipeline_options.accelerator_options = AcceleratorOptions(
        #     num_threads=4, device=AcceleratorDevice.AUTO
        # )
        # CPU only
        # pass

        converter: DocumentConverter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result: ConversionResult = converter.convert(path)
    except Exception as e:
        logger.error(f"Error during docling conversion:\n{e}")
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
        elements: list[InternalElement] = create_elements(document, item, None)
        for element in elements:
            page_index: int = element.page_number - 1

            if 0 <= page_index < len(internal_document.pages):
                internal_document.pages[page_index].ordered_elements.append(element)
            else:
                logger.error(f"Cannot add element: {element.id()} to page_index: {page_index}")

    return internal_document
