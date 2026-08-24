import json
import logging
from pathlib import Path
from typing import Optional

from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.settings import settings
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument
from tqdm import tqdm

from constants import PERCENT_AI, PERCENT_CONVERT, PERCENT_RENDER
from docling_converter import DoclingConverter
from internal_classes import InternalDocument
from logger import get_logger
from utils import disable_additional_logging

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

        # Disable unwanted log messages
        disable_additional_logging()

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
            pipeline_options.artifacts_path = settings.cache_dir.joinpath("models")

            if self.do_image_description:
                # Overwrite default 0.05 value for 5% of the page area
                pipeline_options.picture_description_options.picture_area_threshold = 0.0

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
            result, self.reading_order, self.path, self.progress_bar, convert_step_units
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
