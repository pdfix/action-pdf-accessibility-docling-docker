import json
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from ai import DoclingWrapper, InternalDocument
from constants import (
    PROGRESS_BAR_AUTOTAG_PART,
    PROGRESS_BAR_PROCESSING_PART,
    PROGRESS_BAR_SAVING_PART,
    PROGRESS_BAR_TEMPLATE_PART,
    PROGRESS_BAR_TOTAL,
)
from template_json import TemplateJsonCreator


class CreateTemplateJsonUsingDocling:
    """
    Class that takes care of creating layout template for PDFix SDK using Docling AI.
    """

    def __init__(
        self,
        license_name: Optional[str],
        license_key: Optional[str],
        input_path: str,
        output_path: str,
        do_formula_recognition: bool,
        do_image_description: bool,
        per_page: bool,
    ) -> None:
        """
        Initialize class for tagging pdf(s).

        Args:
            license_name (Optional[str]): Pdfix sdk license name (e-mail).
            license_key (Optional[str]): Pdfix sdk license key.
            input_path (str): Path to PDF document.
            output_path (str): Path where template JSON should be saved.
            do_formula_recognition (bool): Do also formula recognition.
            do_image_description (bool): Do also image desrciption.
            per_page (bool): Process PDF page by page.
        """
        self.license_name: Optional[str] = license_name
        self.license_key: Optional[str] = license_key
        self.input_path_str: str = input_path
        self.output_path_str: str = output_path
        self.do_formula_recognition: bool = do_formula_recognition
        self.do_image_description: bool = do_image_description
        self.per_page: bool = per_page

    def process_file(self) -> None:
        """
        Automatically creates template json.
        """
        with tqdm(total=PROGRESS_BAR_TOTAL) as progress_bar:
            progress_bar.set_description("Processing PDF document with docling")
            processing_units: int = PROGRESS_BAR_AUTOTAG_PART + PROGRESS_BAR_PROCESSING_PART
            wrapper: DoclingWrapper = DoclingWrapper(
                Path(self.input_path_str),
                self.do_formula_recognition,
                self.do_image_description,
                progress_bar,
                processing_units,
            )
            document: Optional[InternalDocument] = wrapper.process_pdf(self.per_page)

            if document is None:
                progress_bar.set_description("Done")
                progress_bar.n = PROGRESS_BAR_TOTAL
                progress_bar.refresh()
                return

            progress_bar.set_description("Creating layout template")
            progress_bar.n = processing_units
            progress_bar.refresh()

            creator: TemplateJsonCreator = TemplateJsonCreator(progress_bar, PROGRESS_BAR_TEMPLATE_PART)
            json_dict: dict = creator.process_document(document)

            progress_bar.set_description("Saving to file")
            progress_bar.n = processing_units + PROGRESS_BAR_TEMPLATE_PART
            progress_bar.refresh()

            with open(self.output_path_str, "w") as f:
                json.dump(json_dict, f, indent=2)

            progress_bar.set_description("Done")
            progress_bar.n = processing_units + PROGRESS_BAR_TEMPLATE_PART + PROGRESS_BAR_SAVING_PART
            progress_bar.refresh()
