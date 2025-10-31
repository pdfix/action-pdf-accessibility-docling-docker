import json
import tempfile
from pathlib import Path
from typing import BinaryIO, Optional, cast

from pdfixsdk import (
    GetPdfix,
    PdfDoc,
    PdfDocTemplate,
    Pdfix,
    PdfPage,
    PdfPageView,
    PdfTagsParams,
    PsMemoryStream,
    kDataFormatJson,
    kRotate0,
    kSaveFull,
)
from tqdm import tqdm

from ai import Region, process_page
from exceptions import (
    PdfixFailedToOpenException,
    PdfixFailedToSaveException,
    PdfixFailedToTagException,
    PdfixInitializeException,
)
from page_renderer import render_page
from template_json import TemplateJsonCreator
from utils_sdk import authorize_sdk, json_to_raw_data


class AutotagUsingDoclingLayoutRecognition:
    """
    Class that takes care of Autotagging provided PDF document using Docling AI.
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
        Initialize class for tagging pdf.

        Args:
            license_name (Optional[str]): Pdfix SDK license name (e-mail).
            license_key (Optional[str]): Pdfix SDK license key.
            input_path (str): Path to PDF document.
            output_path (str): Path where tagged PDF should be saved.
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
        Automatically tags a PDF document.
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

        # Process each page
        num_pages: int = doc.GetNumPages()
        template_json_creator: TemplateJsonCreator = TemplateJsonCreator()

        for page_index in tqdm(range(0, num_pages), desc="Processing pages"):
            # Acquire the page
            page: Optional[PdfPage] = doc.AcquirePage(page_index)
            if page is None:
                raise PdfixFailedToTagException(pdfix, "Failed to acquire the page")

            try:
                self._process_pdf_file_page(pdfix, page, page_index, template_json_creator)
            except Exception:
                raise
            finally:
                page.Release()

        # Create template for whole document
        template_json_dict: dict = template_json_creator.create_json_dict_for_document(self.zoom)

        # Save template to file
        template_path: Path = Path(__file__).parent.joinpath("../output/{id}-template_json.json").resolve()
        with open(template_path, "w") as file:
            file.write(json.dumps(template_json_dict, indent=2))

        # Autotag document
        self._autotag_using_template(doc, template_json_dict, pdfix)

        # Save the processed document
        if not doc.Save(self.output_path_str, kSaveFull):
            raise PdfixFailedToSaveException(pdfix, self.output_path_str)

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

        # Define zoom level and rotation for rendering the page
        page_view: Optional[PdfPageView] = page.AcquirePageView(self.zoom, kRotate0)
        if page_view is None:
            raise PdfixFailedToTagException(pdfix, "Failed to acquire the page view")

        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_file:
                # Render the page as an image
                render_page(pdfix, page, page_view, cast(BinaryIO, temp_file))
                temp_image_path: str = temp_file.name

                # Run layout analysis
                results: list[Region] = process_page(temp_image_path, self.threshold)

                # Process the results
                templateJsonCreator.process_page(results, page_number, page_view)
        except Exception:
            raise
        finally:
            page_view.Release()

    def _autotag_using_template(self, doc: PdfDoc, template_json_dict: dict, pdfix: Pdfix) -> None:
        """
        Autotag opened document using template and remove previous tags and structures.

        Args:
            doc (PdfDoc): Opened document to tag.
            template_json_dict (dict): Template for tagging.
            pdfix (Pdfix): Pdfix SDK.
        """
        # Remove old structure and prepare an empty structure tree
        if not doc.RemoveTags():
            raise PdfixFailedToTagException(pdfix, "Failed to remove tags from document")
        if not doc.RemoveStructTree():
            raise PdfixFailedToTagException(pdfix, "Failed to remove structure tree from document")

        # Convert template json to memory stream
        memory_stream: Optional[PsMemoryStream] = pdfix.CreateMemStream()
        if memory_stream is None:
            raise PdfixFailedToTagException(pdfix, "Failed to create memory stream")

        try:
            raw_data, raw_data_size = json_to_raw_data(template_json_dict)
            if not memory_stream.Write(0, raw_data, raw_data_size):
                raise PdfixFailedToTagException(pdfix, "Failed to write template data into memory")

            doc_template: PdfDocTemplate = doc.GetTemplate()
            if not doc_template.LoadFromStream(memory_stream, kDataFormatJson):
                raise PdfixFailedToTagException(pdfix, "Failed to save template into document")
        except Exception:
            raise
        finally:
            memory_stream.Destroy()

        # Autotag document
        tagsParams: PdfTagsParams = PdfTagsParams()
        if not doc.AddTags(tagsParams):
            raise PdfixFailedToTagException(pdfix, "Failed to tag document")
