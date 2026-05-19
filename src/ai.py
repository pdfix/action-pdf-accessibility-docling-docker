import json
import logging
from pathlib import Path
from typing import Optional

import torch
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
from hierarchical.postprocessor import ResultPostprocessor
from tqdm import tqdm
from transformers.utils import logging as transformers_logging

from constants import PERCENT_AI, PERCENT_CONVERT, PERCENT_RENDER, RD_DOCLING
from internal_classes import InternalDocument, InternalElement, InternalPage
from logger import get_logger

logger: logging.Logger = get_logger()


class DoclingWrapper:
    """
    Wrapper class for Docling processing.
    """

    def __init__(
        self,
        path: Path,
        do_formula_recognition: bool,
        do_image_description: bool,
        reading_order: str,
        progress_bar: tqdm,
        progress_units_total: int,
    ) -> None:
        """
        Constructor.

        Args:
            path (Path): Path to PDF document.
            do_formula_recognition (bool): If formulas are post-processed by Docling to create LaTeX representations.
            do_image_description (bool): If pictures are post-processed by Docling to create image descriptions.
            reading_order (str): Reading order for the document.
            progress_bar (tqdm): Progress bar to update during processing.
            progress_units_total (int): Total number of units for progress bar for processing.
        """
        self.path: Path = path
        self.do_formula_recognition: bool = do_formula_recognition
        self.do_image_description: bool = do_image_description
        self.reading_order: str = reading_order
        self.progress_bar: tqdm = progress_bar
        self.progress_units_total: int = progress_units_total

        # Disable warnings about NNPACK unsupported hardware when running in docker image
        torch.backends.nnpack.set_flags(False)

        # Disable RapidOCR logging
        logging.getLogger("RapidOCR").disabled = True

        # Docling pulls in Hugging Face deps (transformers / huggingface_hub) which can emit their own tqdm bars
        # (notably: "Loading weights"). Disable those so only our own progress bar is shown.
        transformers_logging.disable_progress_bar()

    def process_pdf(self) -> Optional[InternalDocument]:
        """
        Process PDF document with Docling. The docling structure is converted into an internal representation so each
        item is on the correct page; some items are split between pages or across columns on the same page.

        Returns:
            Internal representation of PDF document with Docling Data. Or None if some error happens.
        """
        docling_step_units: float = self.progress_units_total * (PERCENT_RENDER + PERCENT_AI)
        convert_step_units: float = self.progress_units_total * PERCENT_CONVERT

        # Run docling
        try:
            pipeline_options: PdfPipelineOptions = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True

            pipeline_options.do_formula_enrichment = self.do_formula_recognition
            pipeline_options.do_picture_description = self.do_image_description

            converter: DocumentConverter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
            result: ConversionResult = converter.convert(self.path)
            if self.reading_order == RD_DOCLING:
                # The postprocessor modifies the result.document in place.
                ResultPostprocessor(result).process()

            self.progress_bar.update(docling_step_units)
        except Exception as e:
            logger.error("Error during docling conversion:")
            logger.exception(e)
            return None

        # Get Docling internal result
        document: DoclingDocument = result.document

        bar_budget: int = 1 + len(document.pages) + len(document.body.children)
        bar_step: float = convert_step_units / bar_budget

        # Save docling result as json to file
        outputs_folder: Path = Path(__file__).parent.parent.joinpath("outputs")
        outputs_folder.mkdir(exist_ok=True)
        docling_json_path: Path = outputs_folder.joinpath(f"{self.path.stem}_{self.reading_order}_output.json")

        with open(docling_json_path, "w") as f:
            json.dump(document.export_to_dict(), f, indent=4)

        # Convert docling internal document into this project internal structure
        internal_document: InternalDocument = InternalDocument()
        internal_document.docling_version = document.version

        self.progress_bar.update(bar_step)

        for page in document.pages.values():
            internal_page: InternalPage = InternalPage()
            internal_page.number = page.page_no
            internal_page.height = page.size.height
            internal_page.width = page.size.width
            internal_document.pages.append(internal_page)

            self.progress_bar.update(bar_step)

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

            self.progress_bar.update(bar_step)

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
            new_elements: list[InternalElement] = []
            for element in page.ordered_elements:
                new_elements.append(element)
            page.ordered_elements = new_elements
        return internal_document
