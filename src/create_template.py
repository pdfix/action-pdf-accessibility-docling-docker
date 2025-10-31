import json
import tempfile
from typing import BinaryIO, Optional, cast

from pdfixsdk import (
    GetPdfix,
    PdfDoc,
    Pdfix,
    PdfPage,
    PdfPageView,
    kRotate0,
)
from tqdm import tqdm

from ai import Region, process_page
from exceptions import PdfixFailedToCreateTemplateException, PdfixFailedToOpenException, PdfixInitializeException
from page_renderer import render_page
from template_json import TemplateJsonCreator
from utils_sdk import authorize_sdk


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
        pdfix: Optional[Pdfix] = GetPdfix()
        if pdfix is None:
            raise PdfixInitializeException()

        # Try to authorize PDFix SDK
        authorize_sdk(pdfix, self.license_name, self.license_key)

        # Open the document
        doc: Optional[PdfDoc] = pdfix.OpenDoc(self.input_path_str, "")
        if doc is None:
            raise PdfixFailedToOpenException(pdfix, self.input_path_str)

        # Process images of each page
        num_pages: int = doc.GetNumPages()
        template_json_creator: TemplateJsonCreator = TemplateJsonCreator()

        for page_index in tqdm(range(0, num_pages), desc="Processing pages"):
            # Acquire the page
            page: Optional[PdfPage] = doc.AcquirePage(page_index)
            if page is None:
                raise PdfixFailedToCreateTemplateException(pdfix, "Unable to acquire the page")

            try:
                self._process_pdf_file_page(pdfix, page, page_index, template_json_creator)
            except Exception:
                raise
            finally:
                if page:
                    page.Release()

        # Create template for whole document
        template_json_dict: dict = template_json_creator.create_json_dict_for_document(self.zoom)
        output_data: dict = template_json_dict

        # Save template json
        with open(self.output_path_str, "w") as file:
            file.write(json.dumps(output_data, indent=2))

    def _process_pdf_file_page(
        self,
        pdfix: Pdfix,
        page: PdfPage,
        page_index: int,
        templateJsonCreator: TemplateJsonCreator,
    ) -> None:
        """
        Create template json for current PDF document page.

        Args:
            pdfix (Pdfix): Pdfix SDK.
            page (PdfPage): The PDF document page to process.
            page_index (int): PDF file page index.
            templateJsonCreator (TemplateJsonCreator): Template JSON creator.
        """
        page_number: int = page_index + 1

        # Define rotation for rendering the page
        page_view: Optional[PdfPageView] = page.AcquirePageView(self.zoom, kRotate0)
        if page_view is None:
            raise PdfixFailedToCreateTemplateException(pdfix, "Unable to acquire page view")

        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_file:
                # Render the page as an image
                render_page(pdfix, page, page_view, cast(BinaryIO, temp_file))
                temp_image_path: str = temp_file.name

                # Run layout analysis
                result: list[Region] = process_page(temp_image_path, self.threshold)

                # Process the results
                templateJsonCreator.process_page(result, page_number, page_view)
        except Exception:
            raise
        finally:
            # Release resources
            page_view.Release()
