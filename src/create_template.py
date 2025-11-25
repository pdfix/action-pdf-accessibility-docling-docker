import json
from pathlib import Path
from typing import Optional

from ai import InternalDocument, process_pdf
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
        zoom: float,
        threshold: float,
    ) -> None:
        """
        Initialize class for tagging pdf(s).

        Args:
            license_name (Optional[str]): Pdfix sdk license name (e-mail).
            license_key (Optional[str]): Pdfix sdk license key.
            input_path (str): Path to PDF document.
            output_path (str): Path where template JSON should be saved.
            zoom (float): Zoom level for rendering the page.
            threshold (float): Threshold under which results from AI are ignored.
        """
        self.license_name: Optional[str] = license_name
        self.license_key: Optional[str] = license_key
        self.input_path_str: str = input_path
        self.output_path_str: str = output_path
        self.zoom: float = zoom
        self.threshold: float = threshold

    def process_file(self) -> None:
        """
        Automatically creates template json.
        """
        document: Optional[InternalDocument] = process_pdf(Path(self.input_path_str))

        if document is None:
            return

        creator: TemplateJsonCreator = TemplateJsonCreator()
        json_dict: dict = creator.process_document(document)

        with open(self.output_path_str, "w") as f:
            json.dump(json_dict, f, indent=2)
