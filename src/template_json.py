import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from pdfixsdk import PdfDevRect, PdfPageView, PdfRect, __version__

from ai import Region
from constants import CONFIG_FILE
from logger import get_logger
from process_bboxes import PostProcessingBBoxes

logger: logging.Logger = get_logger()


class TemplateJsonCreator:
    """
    Class that prepares each page and in the end creates whole template json file for PDFix-SDK
    """

    def __init__(self) -> None:
        """
        Initializes pdfix sdk template json creation by preparing list for each page.
        """
        self.template_json_pages: list = []

    def create_json_dict_for_document(self, zoom: float) -> dict:
        """
        Prepare PDFix SDK json template for whole document.

        Args:
            zoom (float): Zoom level that page was rendered with.

        Returns:
            Template json for whole document
        """
        created_date: str = date.today().strftime("%Y-%m-%d")
        image_info: str = f"transforms in this docker image of version: {self._get_current_version()}"
        metadata: dict = {
            "author": "Generated using Docling layout",
            "created": created_date,
            "modified": created_date,
            "notes": f"Created using Docling layout, PDFix SDK and {image_info} with zoom: {zoom}",
            "sdk_version": __version__,
            # we are creating first one always so it is always "1"
            "version": "1",
        }
        page_map: list = [
            {
                "graphic_table_detect": "0",
                "statement": "$if",
                "text_table_detect": "0",
                "label_image_detect": "0",
                "label_word_detect": "0",
            }
        ]

        return {
            "metadata": metadata,
            "template": {
                "element_create": self.template_json_pages,
                "pagemap": page_map,
            },
        }

    def process_page(self, results: list[Region], page_number: int, page_view: PdfPageView) -> None:
        """
        Prepare json template for PDFix SDK for one page and save it internally to use later in
        create_json_dict_for_document.

        Args:
            results (list[Region]): List of all regions on page.
            page_number (int): PDF file page number.
            page_view (PdfPageView): The view of the PDF page used for coordinate conversion.
            zoom (float): Zoom level that page was rendered with.
        """
        elements: list = self._create_json_for_elements(results, page_view)

        json_for_page = {
            "comment": f"Page {page_number}",
            "elements": elements,
            "query": {
                "$and": [{"$page_num": page_number}],
            },
            "statement": "$if",
        }
        self.template_json_pages.append(json_for_page)

    def _get_current_version(self) -> str:
        """
        Read the current version from config.json.

        Returns:
            The current version of the Docker image.
        """
        config_path: Path = Path(__file__).parent.joinpath(f"../{CONFIG_FILE}").resolve()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("version", "unknown")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error reading {CONFIG_FILE}: {e}")
            return "unknown"

    def _create_json_for_elements(self, results: list[Region], page_view: PdfPageView) -> list:
        """
        Prepare initial structural elements for the template based on
        detected regions.

        Args:
            results (list[Region]): List of all regions on page.
            page_view (PdfPageView): The view of the PDF page used for coordinate conversion.

        Returns:
            List of elements with parameters.
        """
        elements: list = []

        # TODO For now highest score object wins. In future prioritise Table object.
        post_processor: PostProcessingBBoxes = PostProcessingBBoxes(results)
        regions: list[Region] = post_processor.get_list_of_regions()
        # regions: list[Region] = results

        for region in regions:
            element: dict[str, Any] = {}

            rect: PdfDevRect = PdfDevRect()
            offset: int = 2
            rect.left = int(region.box[0] - offset)
            rect.top = int(region.box[1] - offset)
            rect.right = int(region.box[2] + offset)
            rect.bottom = int(region.box[3] + offset)

            bbox: PdfRect = page_view.RectToPage(rect)
            element["bbox"] = [str(bbox.left), str(bbox.bottom), str(bbox.right), str(bbox.top)]
            logger.debug(f"FROM : {region.box} CREATED: {element['bbox']}")
            label = region.label.lower()
            element["comment"] = f"{label} {round(region.score * 100)}%"

            # List of types:
            match region.label:
                case "Caption":
                    element["tag"] = "Caption"
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Checkbox-Selected":  # For now text is ok
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Checkbox-Unselected":  # For now text is ok
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Code":
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Document Index":  # NO IDEA - For now text is ok
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Footnote":
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Form":  # TODO For now ignore it
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Formula":
                    element["tag"] = "Formula"
                    element["flag"] = "no_join|no_split"
                    element["type"] = "pde_image"

                case "Key-Value Region":  # NO IDEA - For now text is ok
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Picture":
                    element["flag"] = "no_join|no_split"
                    element["type"] = "pde_image"

                case "Page-footer":
                    element["flag"] = "footer|artifact|no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Page-header":
                    element["flag"] = "header|artifact|no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "List-item":
                    # Only text included so we cannot mark bullets/numbers as:
                    # element["label"] = "label"
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"
                    continue

                case "Section-header":
                    element["heading"] = "h1"
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Table":  # TODO In future add TableFormer and observer output and what can be done with it
                    # No information about table size
                    # element["row_num"] = row_count
                    # element["col_num"] = column_count
                    # No information about cells
                    # element["element_template"] = {
                    #    "template": {
                    #         "element_create": [{"elements": cell_elements, "query": {}, "statement": "$if"}],
                    #    },
                    # }
                    # CELL INFO
                    # cell_info: dict = {
                    #     "cell_column": str(column),
                    #     "cell_column_span": str(column_span),
                    #     "cell_row": str(row),
                    #     "cell_row_span": str(row_span),
                    #     "cell_header": "false",
                    #     "cell_scope": "column",
                    #     "comment": f"Cell Pos: {cell_position} Span: {cell_span}",
                    #     "type": "pde_cell",
                    # }
                    element["flag"] = "no_join|no_split"
                    element["type"] = "pde_table"

                case "Text":
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case "Title":
                    element["tag"] = "Title"
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

                case _:
                    logger.warning(f"No case for {region.label}")
                    element["flag"] = "no_join|no_split"
                    element["text_flag"] = "no_new_line"
                    element["type"] = "pde_text"

            elements.append(element)

        # Currently we are sorting BBoxes from top to bottom, left to right
        # for other types of sorting (or keeping original Docling order) another sorting is needed)
        elements = sorted(elements, key=lambda x: (float(x["bbox"][1]), 1000.0 - float(x["bbox"][0])), reverse=True)

        return elements
