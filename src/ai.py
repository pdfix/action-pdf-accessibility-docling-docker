import json
import logging
from pathlib import Path
from typing import Optional

import torch
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument
from tqdm import tqdm
from transformers.utils import logging as transformers_logging

from constants import PERCENT_AI, PERCENT_CONVERT, PERCENT_RENDER
from docling_converter import DoclingConverter
from internal_classes import InternalDocument
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

            self.progress_bar.update(docling_step_units)
        except Exception as e:
            logger.error("Error during docling conversion:")
            logger.exception(e)
            return None

        # Convert Docling data into internal document
        internal_converter: DoclingConverter = DoclingConverter(
            result, self.reading_order, self.progress_bar, convert_step_units
        )
        internal_document: InternalDocument = internal_converter.convert()
        document: DoclingDocument = result.document

        # Save Docling data about document into JSON file
        outputs_folder: Path = Path(__file__).parent.parent.joinpath("outputs")
        outputs_folder.mkdir(exist_ok=True)
        docling_json_path: Path = outputs_folder.joinpath(f"{self.path.stem}_{self.reading_order}_output.json")

        with open(docling_json_path, "w") as f:
            json.dump(document.export_to_dict(), f, indent=4)

        # Return internal document
        return internal_document
