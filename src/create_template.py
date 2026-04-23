import json
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from ai import DoclingWrapper, InternalDocument
from constants import (
    PROGRESS_FIRST_STEP,
    PROGRESS_FOURTH_STEP,
    PROGRESS_SECOND_STEP,
    PROGRESS_THIRD_STEP,
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
        reading_order: str,
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
            reading_order (str): Reading order for the document.
        """
        self.license_name: Optional[str] = license_name
        self.license_key: Optional[str] = license_key
        self.input_path_str: str = input_path
        self.output_path_str: str = output_path
        self.do_formula_recognition: bool = do_formula_recognition
        self.do_image_description: bool = do_image_description
        self.per_page: bool = per_page
        self.reading_order: str = reading_order

    def process_file(self) -> None:
        """
        Automatically creates template json.
        """
        total_progress_count: int = (
            PROGRESS_FIRST_STEP + PROGRESS_SECOND_STEP + PROGRESS_THIRD_STEP + PROGRESS_FOURTH_STEP
        )
        with tqdm(total=total_progress_count) as progress_bar:
            progress_bar.set_description("Initializing")

            wrapper: DoclingWrapper = DoclingWrapper(
                Path(self.input_path_str),
                self.do_formula_recognition,
                self.do_image_description,
                self.reading_order,
                progress_bar,
                PROGRESS_SECOND_STEP,
            )

            progress_bar.update(PROGRESS_FIRST_STEP)
            text: str = "Processing pages" if self.per_page else "Processing document"
            progress_bar.set_description(text)

            document: Optional[InternalDocument] = wrapper.process_pdf(self.per_page)

            if document is None:
                return

            progress_bar.n = PROGRESS_FIRST_STEP + PROGRESS_SECOND_STEP
            progress_bar.set_description("Creating template")
            progress_bar.refresh()

            creator: TemplateJsonCreator = TemplateJsonCreator(
                self.input_path_str, self.reading_order, progress_bar, PROGRESS_THIRD_STEP
            )
            json_dict: dict = creator.process_document(document)

            progress_bar.n = PROGRESS_FIRST_STEP + PROGRESS_SECOND_STEP + PROGRESS_THIRD_STEP
            progress_bar.set_description("Saving template")
            progress_bar.refresh()

            with open(self.output_path_str, "w") as f:
                json.dump(json_dict, f, indent=2)

            progress_bar.n = total_progress_count
            progress_bar.set_description("Done")
            progress_bar.refresh()
