import json
import logging

# import tempfile
import traceback
from pathlib import Path
from typing import Optional  # BinaryIO, Optional, cast

# from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    # BoundingBox,
    # CoordOrigin,
    DocItem,
    DoclingDocument,
    GroupItem,
    NodeItem,
    ProvenanceItem,
    # TableItem,
)

# from pdfixsdk import (
#     GetPdfix,
#     PdfDoc,
#     Pdfix,
#     PdfPage,
#     PdfPageView,
#     kRotate0,
# )
# from cell_processor import CellProcessor
# from exceptions import PdfixFailedToOpenException, PdfixFailedToRenderException, PdfixInitializeException
from internal_classes import InternalDocument, InternalElement, InternalPage
from logger import get_logger

# from page_renderer import crop_image, render_page

logger: logging.Logger = get_logger()


class DoclingWrapper:
    """
    Wrapper class for Docling processing.
    """

    def __init__(self, path: Path, do_formula_recognition: bool, do_image_description: bool) -> None:
        """
        Constructor.

        Args:
            path (Path): Path to PDF document.
            do_formula_recognition (bool): If formulas are post-processed by Docling to create LaTeX representations.
            do_image_description (bool): If pictures are post-processed by Docling to create image descriptions.
        """
        self.path: Path = path
        self.do_formula_recognition: bool = do_formula_recognition
        self.do_image_description: bool = do_image_description
        # self.cell_processor: CellProcessor = CellProcessor()
        # self.cached_page_images: dict[int, Path] = {}
        # self.pdfix: Optional[Pdfix] = None
        # self.doc: Optional[PdfDoc] = None
        # self.cell_images: list[Path] = []

    def process_pdf(self) -> Optional[InternalDocument]:
        """
        Processed PDF document. First docling runs to create docling structure. That this structure is used to create
        internal representation of PDF document so each item is on correct page some items are split either between
        pages or for multiple columns inside same page.

        Returns:
            Internal representation of PDF document with Docling Data. Or None if some error happens.
        """
        try:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            # pipeline_options.table_structure_options.do_cell_matching = True

            # # Docling Parse with EasyOCR (CPU only) # not installed by default
            # # from docling.datamodel.pipeline_options import EasyOcrOptions
            # pipeline_options.ocr_options = EasyOcrOptions()
            # pipeline_options.ocr_options.use_gpu = False  # <-- set this.
            # # pipeline_options.ocr_options.lang = ["en"]

            # # Docling Parse with Rapid OCR
            # # from docling.datamodel.pipeline_options import RapidOcrOptions
            # pipeline_options.ocr_options = RapidOcrOptions()

            # # Docling Parse with Tesseract CLI # not installed by default
            # # Ensure Tesseract CLI (or library) is installed and on PATH.
            # # from docling.datamodel.pipeline_options import TesseractCliOcrOptions
            # pipeline_options.ocr_options = TesseractCliOcrOptions()
            # pipeline_options.ocr_options.force_full_page_ocr = True
            # # Language packs must be installed; set TESSDATA_PREFIX if Tesseract cannot find language data. Using
            # # lang=["auto"] requires traineddata that supports script/language detection on your system.
            # pipeline_options.ocr_options.lang = ["auto"]

            # # Docling Parse with ocrmac (macOS only) # default in Mac environment
            # # from docling.datamodel.pipeline_options import OcrMacOptions
            # pipeline_options.ocr_options = OcrMacOptions()

            pipeline_options.do_formula_enrichment = self.do_formula_recognition
            pipeline_options.do_picture_description = self.do_image_description

            # GPU:
            # pipeline_options.accelerator_options = AcceleratorOptions(
            #     num_threads=4, device=AcceleratorDevice.AUTO
            # )

            # CPU only
            # pass

            converter: DocumentConverter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
            result: ConversionResult = converter.convert(self.path)
        except Exception as e:
            logger.error(f"Error during docling conversion:\n{e}")
            traceback.print_stack()
            return None
        document: DoclingDocument = result.document
        outputs_folder: Path = Path(__file__).parent.parent.joinpath("outputs")
        outputs_folder.mkdir(exist_ok=True)
        docling_json_path: Path = outputs_folder.joinpath(f"{self.path.stem}_output.json")
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
            item: Optional[NodeItem] = self._get_item(document, reference.cref)
            if item is None:
                continue

            # Get first page that element appears in
            elements: list[InternalElement] = self._create_elements(document, item, None)
            for element in elements:
                page_index: int = element.page_number - 1

                if 0 <= page_index < len(internal_document.pages):
                    internal_document.pages[page_index].ordered_elements.append(element)
                else:
                    logger.error(f"Cannot add element: {element.id()} to page_index: {page_index}")

        # # Post-process docling data to include table cell contents
        # internal_document = self._post_process_docling_data(internal_document)

        # # clean up files
        # for page_image in self.cached_page_images.values():
        #     try:
        #         page_image.unlink()
        #     except Exception as e:
        #         logger.warning(f"Cannot delete cached page image {page_image.as_posix()}: {e}")

        # for cell_image in self.cell_images:
        #     try:
        #         cell_image.unlink()
        #     except Exception as e:
        #         logger.warning(f"Cannot delete cached cell image {cell_image.as_posix()}: {e}")

        return internal_document

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
                child_item: Optional[NodeItem] = self._get_item(document, child_ref.cref)
                if child_item is None:
                    continue
                # More children are expected for GroupItem -> there will be just one internal_element
                # For DocItem currently all provenances points to the same page and thus any children will also be from
                # the same page
                # With this we can safely assume that internal_element (always first create element for NodeItem)
                # is parent for their page
                child_elements: list[InternalElement] = self._create_elements(document, child_item, internal_element)
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

    def _get_item(self, document: DoclingDocument, reference: str) -> Optional[NodeItem]:
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

    def _post_process_docling_data(self, internal_document: InternalDocument) -> InternalDocument:
        """
        Post process data from docling to include contents of table cells.

        Args:
            internal_document (InternalDocument): Internal representation of PDF document with Docling Data.

        Returns:
            Updated InternalDocument with table cell contents included.
        """
        for page in internal_document.pages:
            # page_height: float = page.height
            new_elements: list[InternalElement] = []
            for element in page.ordered_elements:
                # After a lot of testing (running docling on cell, running VLM on cell) post-processing of table cells
                # does not work currently (we are unable to detect images in cells or any other structure).
                # if isinstance(element.item, TableItem):
                #     table: TableItem = element.item
                #     cell_elements: list[InternalElement] = self._post_process_table(table, page_height)
                #     new_elements.extend(cell_elements)
                new_elements.append(element)
            page.ordered_elements = new_elements
        return internal_document

    # def _post_process_table(self, table: TableItem, page_height: float) -> list[InternalElement]:
    #     """
    #     Post-process table cells to create InternalElements inside cells.

    #     Args:
    #         table (TableItem): Table item from Docling.
    #         page_height (float): Height of the page where table is located.

    #     Returns:
    #         List of InternalElements inside table cells.
    #     """
    #     internal_elements: list[InternalElement] = []

    #     # Table data
    #     # Only first provenance is usefull as all provenances are inside the same page
    #     provenance: ProvenanceItem = table.prov[0]
    #     page_number: int = provenance.page_no
    #     bbox: BoundingBox = provenance.bbox
    #     if bbox.coord_origin == CoordOrigin.TOPLEFT:
    #         bbox = bbox.to_bottom_left_origin(page_height)
    #     table_id: str = table.self_ref.replace("#", "").replace("/", "")

    #     # Walk through cells
    #     for row in table.data.grid:
    #         for cell in row:
    #             cell_row: int = cell.start_row_offset_idx + 1
    #             cell_column: int = cell.start_col_offset_idx + 1
    #             cell_id: str = f"{table_id}_cell_{cell_row}_{cell_column}"
    #             cell_bbox: Optional[BoundingBox] = cell.bbox
    #             if cell_bbox is None:
    #                 # usually skipping empty cells as they do not have bbox
    #                 continue
    #             if cell_bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
    #                 cell_bbox = cell_bbox.to_top_left_origin(page_height)

    #             cell_image_path: Path = self._create_image_of_cell(page_number, cell_bbox, cell_id)

    #             # elements: list[InternalElement] = self.cell_processor.process_cell_vlm(
    #             #     cell_image_path, page_number, cell_bbox, cell_id
    #             # )

    #             # elements: list[InternalElement] = self.cell_processor.process_cell_docling(
    #             #     cell_image_path, page_number, cell_bbox, cell_id
    #             # )

    #             elements: list[InternalElement] = []

    #             internal_elements.extend(elements)

    #     return internal_elements

    # def _create_image_of_cell(self, page_number: int, cell_bbox: BoundingBox, cell_id: str) -> Path:
    #     """
    #     Creates image of cell from PDF document.

    #     Args:
    #         page_number (int): Page number where cell is located.
    #         cell_bbox (BoundingBox): Bounding box of the cell in top-left origin (PIL Image.crop needs it that way).
    #         cell_id (str): ID of the cell for temporary image file.

    #     Returns:
    #         Path to image of the cell.
    #     """
    #     page_image_path: Path = self._render_page_to_image(page_number)

    #     with tempfile.NamedTemporaryFile(prefix=f"{cell_id}-", suffix=".jpg", delete=False) as temp_file:
    #         crop_image(page_image_path, cell_bbox, cast(BinaryIO, temp_file))

    #         cell_image_path: Path = Path(temp_file.name)
    #         self.cell_images.append(cell_image_path)
    #         return cell_image_path

    # def _render_page_to_image(self, page_number: int) -> Path:
    #     """
    #     Render PDF page to image or return already rendered image from cache.

    #     Args:
    #         page_number (int): Page number to render.

    #     Returns:
    #         Path to rendered image.
    #     """
    #     if page_number in self.cached_page_images:
    #         return self.cached_page_images[page_number]

    #     if self.pdfix is None:
    #         self.pdfix = GetPdfix()
    #         if self.pdfix is None:
    #             raise PdfixInitializeException()

    #     if self.doc is None:
    #         string_path: str = self.path.as_posix()
    #         self.doc = self.pdfix.OpenDoc(string_path, "")
    #         if self.doc is None:
    #             raise PdfixFailedToOpenException(self.pdfix, string_path)

    #     page_index: int = page_number - 1
    #     page: Optional[PdfPage] = self.doc.AcquirePage(page_index)
    #     if page is None:
    #         raise PdfixFailedToRenderException(self.pdfix, "Failed to acquire the page")

    #     page_view: Optional[PdfPageView] = page.AcquirePageView(1.0, kRotate0)
    #     if page_view is None:
    #         raise PdfixFailedToRenderException(self.pdfix, "Failed to acquire the page view")

    #     with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
    #         render_page(self.pdfix, page, page_view, cast(BinaryIO, temp_file))

    #         self.cached_page_images[page_number] = Path(temp_file.name)
    #         return self.cached_page_images[page_number]
