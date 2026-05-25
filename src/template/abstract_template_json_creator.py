import logging
import re
from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from docling_core.types.doc import (
    BoundingBox,
    CodeItem,
    DescriptionAnnotation,
    DocItem,
    DocItemLabel,
    FloatingItem,
    FormItem,
    FormulaItem,
    GroupItem,
    GroupLabel,
    InlineGroup,
    KeyValueItem,
    ListGroup,
    ListItem,
    NodeItem,
    PictureItem,
    ProvenanceItem,
    SectionHeaderItem,
    TableCell,
    TableData,
    TableItem,
    TextItem,
    TitleItem,
)
from pdfixsdk import PdfPageView, PdfRect, __version__
from pydantic import AnyUrl
from tqdm import tqdm

from constants import DOCKER_IMAGE
from internal_classes import InternalDocument, InternalElement
from logger import get_logger
from utils import convert_latex_to_mathml, convert_to_base64, get_current_version
from utils_sdk import convert_bbox_to_pdfrect

logger: logging.Logger = get_logger()


class Placement(Enum):
    UNDER = "under"  # default
    BEFORE = "before"
    AFTER = "after"


class AbstractTemplateJsonCreator(ABC):
    """
    Abstract base with shared template JSON building blocks (element dicts, metadata, pagemap).
    """

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        """
        Initialize shared template JSON state and pagemap defaults.

        Args:
            input_path_str (str): Path to PDF document to create template for.
            bbox_overlap (float): How much bounding box from docling must overlap with PDF element area.
            progress_bar (tqdm): Progress bar to update about processing.
            total_progress_units (int): Total number of units for progress bar for processing.
        """
        self.input_path_str = input_path_str
        self.add_rd_indexes: bool = False
        self.progress_bar: tqdm = progress_bar
        self.total_progress_units: int = total_progress_units

        self.page_map_settings: list[dict[str, str]] = [
            {
                "graphic_table_detect": "0",
                "statement": "$if",
                "text_table_detect": "0",
                "label_image_detect": "0",
                "label_word_detect": "0",
                "initial_element_only": "1",
                "artifact_untagged": "1",
                "initial_elements_keep_empty": "0",
                "initial_element_overlap": str(bbox_overlap),
                "rd_sort": "0",
            }
        ]

    @abstractmethod
    def process_document(self, document: InternalDocument) -> dict:
        """
        Prepare PDFix SDK json template for whole document.

        Args:
            document (InternalDocument): Internal representation of PDF document with Docling data.

        Returns:
            Template json for whole document.
        """
        pass

    def _build_template_dict(self, document: InternalDocument, element_create: list) -> dict:
        """
        Build main template dictionary for template JSON.

        Args:
            document (InternalDocument): Internal representation of PDF document with Docling data.
            element_create (list): List of element create blocks.

        Returns:
            Template dictionary for template JSON.
        """
        return {
            "metadata": self._create_metadata(document),
            "template": {
                "element_create": element_create,
                "pagemap": self.page_map_settings,
            },
        }

    def _create_metadata(self, document: InternalDocument) -> dict:
        """
        Create metadata for template JSON.

        Args:
            document (InternalDocument): Internal representation of PDF document with Docling data.

        Returns:
            Metadata for template JSON.
        """
        created_date: str = date.today().strftime("%Y-%m-%d")
        docker_image: str = f"{DOCKER_IMAGE}:{get_current_version()}"

        return {
            "author": "Generated using Docling Project AI",
            "created": created_date,
            "modified": created_date,
            "notes": f"Created using Docling Project {document.docling_version} inside {docker_image}",
            "sdk_version": __version__,
            "version": "1",
        }

    def _create_elements(
        self, element: InternalElement, page_view: PdfPageView, page_height: float, include_parent_key: bool
    ) -> list[dict]:
        """
        Create elements recursivelyfor template JSON.

        Args:
            element (InternalElement): Internal element to create elements for.
            page_view (PdfPageView): PDFix page view to create elements for.
            page_height (float): Height of the page to create elements for.
            include_parent_key (bool): Whether to include parent key in the elements.

        Returns:
            List of elements for template JSON.
        """
        results: list[dict] = []
        result: dict = {}
        results.append(result)

        # Basic element data like name, bbox, comment, parent, etc.
        item: NodeItem = element.item
        element_ref: str = element.id()
        result["name"] = element_ref
        flag_list: list[str] = []
        if element.continuous_element is not None:
            flag_list.append("continuous")
        bbox_list: Optional[list[str]] = self._get_template_bbox(element, page_view, page_height)
        if bbox_list is not None:
            result["bbox"] = bbox_list
        label: str = self._get_label(element)
        result["comment"] = f"{element_ref} {label}"
        if element.parent is not None and include_parent_key:
            result["parent"] = element.parent.id()

        # Children of element (resursivity)
        children: list[dict] = []

        for child in element.children:
            place_element: Placement = Placement.UNDER
            if isinstance(child.item, TextItem) and child.item.label == DocItemLabel.CAPTION:
                # remove parent from captions and use "caption" tag instead
                place_element = Placement.BEFORE
                if "parent" in result:
                    result.pop("parent", None)
                result["caption"] = child.id()
            if isinstance(item, TableItem):
                # Do not add anything under table
                place_element = Placement.AFTER
            if isinstance(item, PictureItem):
                # Under picture should not be any footnotes
                if isinstance(child.item, TextItem) and child.item.label == DocItemLabel.FOOTNOTE:
                    place_element = Placement.AFTER

            # Create children elements
            children_result: list[dict] = self._create_elements(child, page_view, page_height, False)

            # Place them properly
            if place_element == Placement.UNDER:
                children.extend(children_result)
            elif place_element == Placement.BEFORE:
                for child_result in reversed(children_result):
                    results.insert(0, child_result)
            elif place_element == Placement.AFTER:
                results.extend(children_result)

        # Add children node to template
        if len(children) > 0:
            result["element_template"] = {
                "template": {
                    "element_create": [{"elements": children, "statement": "$if"}],
                    "pagemap": self.page_map_settings,
                },
            }

        # Add note to comment about hyperlinks
        if isinstance(item, TextItem):
            hyperlink: Optional[Union[AnyUrl, Path]] = item.hyperlink
            if isinstance(hyperlink, AnyUrl):
                result["comment"] = f"{result['comment']} Hyperlink: {hyperlink}"
            elif isinstance(hyperlink, Path):
                result["comment"] = f"{result['comment']} Hyperlink: {hyperlink}"
            if item.text:
                result["text"] = item.text

        # Add note to comment about footnotes and captions
        if isinstance(item, FloatingItem):
            if len(item.footnotes) > 0:
                footnotes: str = ", ".join([footnote.cref for footnote in item.footnotes])
                result["comment"] = f"{result['comment']} Footnotes: {footnotes}"
            if len(item.captions) > 0:
                captions: str = ", ".join([caption.cref for caption in item.captions])
                result["comment"] = f"{result['comment']} Captions: {captions}"

        # Add default flags to element
        flag_list.append("no_join")
        flag_list.append("no_split")
        flag_list.append("no_expand")

        # Process element according to its type
        if isinstance(item, TitleItem):
            result["tag"] = "Title"
            result["type"] = "pde_text"
        elif isinstance(item, SectionHeaderItem):
            level: int = item.level
            result["comment"] = result["comment"].replace(label, f"{label} {level}")
            result["heading"] = f"h{level}"
            result["type"] = "pde_text"
        elif isinstance(item, ListItem):
            list_type: str = self._get_list_type(item)
            if list_type != "None":
                result["numbering"] = list_type
            if item.marker:
                result["label_text"] = item.marker
            result["label"] = "label_list"
            result["type"] = "pde_text"
        elif isinstance(item, CodeItem):
            language: str = item.code_language
            result["comment"] = f"{result['comment']} Lang: {language}"
            result["type"] = "pde_text"
        elif isinstance(item, FormulaItem):
            result["tag"] = "Formula"
            if item.text:
                latex_formula: str = item.text
                result["alt"] = latex_formula
                result["mathml"] = convert_to_base64(convert_latex_to_mathml(latex_formula))
            result["type"] = "pde_image"
        elif isinstance(item, TextItem):
            match item.label:
                case DocItemLabel.CAPTION:
                    result["tag"] = "Caption"
                case DocItemLabel.CHECKBOX_SELECTED:
                    pass
                case DocItemLabel.CHECKBOX_UNSELECTED:
                    pass
                case DocItemLabel.FOOTNOTE:
                    result["tag"] = "Note"
                case DocItemLabel.PAGE_FOOTER:
                    flag_list.append("footer")
                    flag_list.append("artifact")
                case DocItemLabel.PAGE_HEADER:
                    flag_list.append("header")
                    flag_list.append("artifact")
                case DocItemLabel.PARAGRAPH:
                    pass
                case DocItemLabel.REFERENCE:
                    result["tag"] = "Reference"
                case DocItemLabel.TEXT:
                    pass
                case DocItemLabel.EMPTY_VALUE:
                    pass
            result["type"] = "pde_text"
        elif isinstance(item, PictureItem):
            if "no_join" in flag_list:
                flag_list.remove("no_join")
            if "no_split" in flag_list:
                flag_list.remove("no_split")
            if (
                len(item.annotations) > 0
                and isinstance(item.annotations[0], DescriptionAnnotation)
                and item.annotations[0].text
            ):
                alt_text: str = item.annotations[0].text
                result["alt"] = alt_text
            result["type"] = "pde_image"
        elif isinstance(item, TableItem):
            table_data: TableData = item.data
            table_pdfrect: PdfRect = self._get_table_pdfrect(element, page_view, page_height)
            cells: list = self._create_cells(table_pdfrect, table_data, page_view, page_height, element_ref)
            if "element_template" not in result:
                result["element_template"] = {
                    "template": {
                        "element_create": [{"elements": cells, "statement": "$if"}],
                        "pagemap": self.page_map_settings,
                    },
                }
            else:
                nested_elements: list[dict] = result["element_template"]["template"]["element_create"][0]["elements"]
                nested_elements.extend(cells)
            if len(cells) == table_data.num_rows * table_data.num_cols:
                result["row_num"] = table_data.num_rows
                result["col_num"] = table_data.num_cols
            else:
                grid_size: str = f"table grid size: {table_data.num_rows}x{table_data.num_cols}"
                warning_message: str = f"Warning: cells: {len(cells)} do not match {grid_size}"
                result["comment"] = f"{result['comment']} {warning_message}"
            result["type"] = "pde_table"
        elif isinstance(item, KeyValueItem):
            result["type"] = "pde_text"
        elif isinstance(item, FormItem):
            result["type"] = "pde_text"
        elif isinstance(item, ListGroup):
            result["type"] = "pde_list"
        elif isinstance(item, InlineGroup):
            result["type"] = "pde_container"
        elif isinstance(item, GroupItem):
            match item.label:
                case GroupLabel.CHAPTER:
                    result["tag"] = "Sect"
                case GroupLabel.SECTION:
                    result["tag"] = "Part"
                case _:
                    result["tag"] = "NonStruct"
            result["type"] = "pde_container"
        elif isinstance(item, FloatingItem):
            result["type"] = "pde_container"
        elif isinstance(item, DocItem):
            result["type"] = "pde_container"
        elif isinstance(item, NodeItem):
            result["type"] = "pde_container"

        # Write final flag to template json for element
        if len(flag_list) > 0:
            result["flag"] = "|".join(flag_list)

        return results

    def _get_template_bbox(
        self, element: InternalElement, page_view: PdfPageView, page_height: float
    ) -> Optional[list[str]]:
        """
        Get bounding box for template JSON.

        Args:
            element (InternalElement): Internal element to get bounding box for.
            page_view (PdfPageView): PDFix page view to get bounding box for.
            page_height (float): Height of the page to get bounding box for.

        Returns:
            Bounding box for template JSON as list of strings or None.
        """
        item: NodeItem = element.item

        if isinstance(item, DocItem):
            provenance: ProvenanceItem = item.prov[element.provenance_index]
            pdf_rect: PdfRect = convert_bbox_to_pdfrect(provenance.bbox, page_view, page_height)
            return self._convert_pdfrect_to_list_str(pdf_rect)

        return None

    def _convert_pdfrect_to_list_str(self, pdf_rect: PdfRect) -> list[str]:
        """
        Convert PDF rectangle to list of strings.

        Args:
            pdf_rect (PdfRect): PDF rectangle to convert.

        Returns:
            List of strings representing the PDF rectangle.
        """
        return [str(pdf_rect.left), str(pdf_rect.bottom), str(pdf_rect.right), str(pdf_rect.top)]

    def _get_label(self, element: InternalElement) -> str:
        """
        Get label for template JSON.

        Args:
            element (InternalElement): Internal element to get label for.

        Returns:
            Label for template JSON.
        """
        item: NodeItem = element.item

        if isinstance(item, DocItem):
            return str(item.label)

        if isinstance(item, GroupItem):
            return str(item.label)

        return ""

    def _get_table_pdfrect(self, table_element: InternalElement, page_view: PdfPageView, page_height: float) -> PdfRect:
        """
        Get PDF rectangle for table.

        Args:
            table_element (InternalElement): Internal element to get PDF rectangle for.
            page_view (PdfPageView): PDFix page view to get PDF rectangle for.
            page_height (float): Height of the page to get PDF rectangle for.

        Returns:
            PDF rectangle for table.
        """
        item: NodeItem = table_element.item

        if isinstance(item, DocItem):
            provenance: ProvenanceItem = item.prov[table_element.provenance_index]
            return convert_bbox_to_pdfrect(provenance.bbox, page_view, page_height)

        logger.error("We should never get here as table element should have bounding box from Docling.")
        return PdfRect()

    def _create_cells(
        self, table_pdfrect: PdfRect, table: TableData, page_view: PdfPageView, page_height: float, table_ref: str
    ) -> list:
        """
        Create cells for table.

        Args:
            table_pdfrect (PdfRect): Table's PDF rectangle.
            table (TableData): Table data to create cells for.
            page_view (PdfPageView): PDFix page view to create cells for.
            page_height (float): Height of the page to create cells for.
            table_ref (str): Table unique identifier.

        Returns:
            List of cells for table.
        """
        cells: list = []
        table_cells: list[list[TableCell]] = table.grid

        for row_index, row in enumerate(table_cells):
            for col_index, cell in enumerate(row):
                regular_cell: bool = row_index == cell.start_row_offset_idx and col_index == cell.start_col_offset_idx
                cell_column: int = col_index + 1
                cell_row: int = row_index + 1
                cell_scope: str = self._get_cell_scope(cell)
                cell_dict: dict = {
                    "cell_column": str(cell_column),
                    "cell_column_span": str(cell.col_span),
                    "cell_row": str(cell_row),
                    "cell_row_span": str(cell.row_span),
                    "comment": f"Cell Pos: [{cell_row}, {cell_column}]",
                    "type": "pde_cell",
                }

                if regular_cell:
                    if cell.bbox:
                        pdf_rect: PdfRect = convert_bbox_to_pdfrect(cell.bbox, page_view, page_height)
                        cell_dict["bbox"] = self._convert_pdfrect_to_list_str(pdf_rect)

                    cell_dict["cell_header"] = self._convert_bool_to_str(cell.row_header or cell.column_header)

                    if cell_scope:
                        cell_dict["cell_scope"] = cell_scope

                    if cell.text:
                        cell_dict["text"] = cell.text
                else:
                    cell_dict["cell_column_span"] = 0
                    cell_dict["cell_row_span"] = 0

                cells.append(cell_dict)

        return cells

    def _get_cell_scope(self, cell: TableCell) -> str:
        """
        Convert cell data into cell scope string.

        Args:
            cell (TableCell): Table cell to get scope for.

        Returns:
            Cell scope for table.
        """
        if cell.column_header and cell.row_header:
            return "both"

        elif cell.column_header:
            return "column"

        elif cell.row_header:
            return "row"

        return ""

    def _convert_bool_to_str(self, value: bool) -> str:
        """
        Convert boolean value to string.

        Args:
            value (bool): Boolean value to convert.

        Returns:
            String representation of the boolean value.
        """
        return "true" if value else "false"

    def _get_list_type(self, item: ListItem) -> str:
        """
        Convert list item data into list type string.

        Args:
            item (ListItem): List item to convert.

        Returns:
            List type string.
        """
        marker: str = item.marker.strip()
        stripped_marker: str = marker.lstrip("([").rstrip(")].:")

        if item.enumerated:
            if re.fullmatch(r"\d+", stripped_marker):
                return "Decimal"

            if re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", stripped_marker):
                return "UpperRoman"

            if re.fullmatch(r"m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})", stripped_marker):
                return "LowerRoman"

            if re.fullmatch(r"[A-Z]", stripped_marker):
                return "UpperAlpha"

            if re.fullmatch(r"[a-z]", stripped_marker):
                return "LowerAlpha"

            if len(marker) > 1:
                return "Description"

            return "Ordered"

        else:
            disc_markers: list[str] = ["•", "●", "◉", "◌", "◍", "◎", "○", "·", "˚", "°", "∙"]
            square_markers: list[str] = ["▪", "▫", "■", "□", "▣", "▤", "▥", "▦", "▧", "▨", "▩"]
            arrows: list[str] = ["→", "⇒", "➔", "➙", "➛", "➜", "➝", "➞", "➟", "➠", "➡", "►", "▶", "▸", "‣", "➤", "➢"]
            check_markers: list[str] = ["✓", "✔", "✗", "✘", "☑", "☒", "☓"]
            rest: list[str] = ["-", "*", "+", "⁃", "−", "–"]

            if marker == "":
                return "None"

            if marker in disc_markers:
                return "Disc"

            if marker in square_markers:
                return "Square"

            if len(marker) > 1:
                return "Description"

            if marker in arrows or marker in check_markers or marker in rest:
                return "Unordered"

        return "None"

    def _calculate_bbox_from_children(
        self, children: list[InternalElement], page_view: PdfPageView, page_height: float
    ) -> list[str]:
        """
        Calculate bounding box from children.

        Args:
            children (list[InternalElement]): List of internal elements to calculate bounding box from.
            page_view (PdfPageView): PDFix page view to calculate bounding box from.
            page_height (float): Height of the page to calculate bounding box from.

        Returns:
            Bounding box for template JSON as list of strings.
        """
        if len(children) == 0:
            return ["0", "0", "0", "0"]

        result: Optional[PdfRect] = None

        for child in children:
            if isinstance(child.item, DocItem) and len(child.item.prov) > 0:
                provenance: ProvenanceItem = child.item.prov[0]
                bbox: BoundingBox = provenance.bbox
                pdf_rect: PdfRect = convert_bbox_to_pdfrect(bbox, page_view, page_height)

                if result is None:
                    result = pdf_rect
                else:
                    if pdf_rect.left < result.left:
                        result.left = pdf_rect.left
                    if pdf_rect.bottom < result.bottom:
                        result.bottom = pdf_rect.bottom
                    if pdf_rect.right > result.right:
                        result.right = pdf_rect.right
                    if pdf_rect.top > result.top:
                        result.top = pdf_rect.top

        if result is None:
            return ["0", "0", "0", "0"]

        return self._convert_pdfrect_to_list_str(result)

    def _postprocess_template_block(self, template_block: dict) -> dict:
        """
        If requested add rd_index to elements to keep existing reading order.

        Args:
            template_block (dict): Template block to postprocess.

        Returns:
            Postprocessed template block.
        """
        if self.add_rd_indexes:
            return self._add_rd_indexes(template_block)

        return template_block

    def _add_rd_indexes(self, template_block: dict) -> dict:
        """
        Add rd_index to elements to keep existing reading order and do it recursively.

        Args:
            template_block (dict): Template block to add rd_index to.

        Returns:
            Template block with rd_index added to elements.
        """

        def walk(node: Any) -> None:
            """
            Walk through the template block and add rd_index to elements.

            Args:
                node (Any): Node to walk through.
            """
            if isinstance(node, dict):
                elements = node.get("elements")
                if isinstance(elements, list):
                    for list_index, member in enumerate(elements):
                        if isinstance(member, dict):
                            member["rd_index"] = list_index

                        walk(member)
                for key, value in node.items():
                    if key == "elements":
                        continue

                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(template_block)
        return template_block
