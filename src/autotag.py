import json
from pathlib import Path
from typing import Optional

from pdfixsdk import (
    GetPdfix,
    PdfDoc,
    PdfDocTemplate,
    Pdfix,
    PdfTagsParams,
    PsMemoryStream,
    kDataFormatJson,
    kSaveFull,
)
from tqdm import tqdm

from ai import DoclingWrapper, InternalDocument
from constants import (
    PROGRESS_FIRST_STEP,
    PROGRESS_FOURTH_STEP,
    PROGRESS_SECOND_STEP,
    PROGRESS_THIRD_STEP,
)
from exceptions import (
    PdfixFailedToOpenException,
    PdfixFailedToSaveException,
    PdfixFailedToTagException,
    PdfixInitializeException,
)
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
        do_formula_recognition: bool,
        do_image_description: bool,
        per_page: bool,
    ) -> None:
        """
        Initialize class for tagging pdf.

        Args:
            license_name (Optional[str]): Pdfix SDK license name (e-mail).
            license_key (Optional[str]): Pdfix SDK license key.
            input_path (str): Path to PDF document.
            output_path (str): Path where tagged PDF should be saved.
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
        Automatically tags a PDF document.
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

            creator: TemplateJsonCreator = TemplateJsonCreator(progress_bar, PROGRESS_THIRD_STEP)
            template_json_dict: dict = creator.process_document(document)

            # Save template to file
            output_directory: Path = Path(__file__).parent.parent.joinpath("output").resolve()
            output_directory.mkdir()
            id: str = Path(self.input_path_str).stem
            template_path: Path = output_directory.joinpath(f"{id}-template_json.json")

            with open(template_path, "w") as file:
                file.write(json.dumps(template_json_dict, indent=2))

            progress_bar.n = PROGRESS_FIRST_STEP + PROGRESS_SECOND_STEP + PROGRESS_THIRD_STEP
            progress_bar.set_description("Autotagging")
            progress_bar.refresh()

            # Initialize PDFix SDK
            pdfix: Optional[Pdfix] = GetPdfix()
            if pdfix is None:
                raise PdfixInitializeException()

            # Try to authorize PDFix SDK
            authorize_sdk(pdfix, self.license_name, self.license_key)

            # Open the document
            doc: Optional[PdfDoc] = pdfix.OpenDoc(self.input_path_str, "")
            if doc is None:
                raise PdfixFailedToOpenException(pdfix, self.input_path_str)

            # Autotag document
            self._autotag_using_template(doc, template_json_dict, pdfix)

            # Save the processed document
            if not doc.Save(self.output_path_str, kSaveFull):
                raise PdfixFailedToSaveException(pdfix, self.output_path_str)

            progress_bar.n = total_progress_count
            progress_bar.set_description("Done")
            progress_bar.refresh()

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
