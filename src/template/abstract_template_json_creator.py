import logging
import re
from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from docling_core.types.doc import (
    AnyTableCell,
    BoundingBox,
    CodeItem,
    DescriptionAnnotation,
    DocItem,
    DocItemLabel,
    FieldHeadingItem,
    FieldItem,
    FieldRegionItem,
    FieldValueItem,
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
    RichTableCell,
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
from internal_classes import InternalDocument, InternalElement, InternalElementGroup
from logger import get_logger
from utils import clean_image_alternate_text_end, convert_latex_to_mathml, convert_to_base64, get_current_version
from utils_sdk import convert_bbox_to_pdfrect

logger: logging.Logger = get_logger()


class Placement(Enum):
    UNDER = "under"  # default behaviour (children are put under the parent)
    BEFORE = "before"
    AFTER = "after"
    SKIP = "skip"
    TABLE = "table"  # Content of rich table cell, placed into its cell by _create_cells


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
        Create elements recursively for template JSON.

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
        if element.is_continuous or element.continuous_element is not None:
            flag_list.append("continuous")
        bbox_list: Optional[list[str]] = self._get_template_bbox(element, page_view, page_height)
        if bbox_list is not None:
            result["bbox"] = bbox_list
        label: str = self._get_label(element)
        result["comment"] = f"{element_ref} {label}"
        if element.parent is not None and include_parent_key:
            result["parent"] = element.parent.id()

        # Rich table cells reference their content (group) which docling puts under the table
        rich_cell_refs: set[str] = set()
        if isinstance(item, TableItem):
            rich_cell_refs = {cell.ref.cref for cell in item.data.table_cells if isinstance(cell, RichTableCell)}
        table_rich_cells: dict[str, InternalElement] = {}

        # Children of element (recursivity)
        children: list[dict] = []

        for child in element.children:
            # First set default behaviour
            place_element: Placement = Placement.UNDER

            if isinstance(child.item, TextItem) and child.item.label == DocItemLabel.CAPTION:
                place_element = (
                    Placement.AFTER
                    if self._is_caption_after(child, element, page_view, page_height)
                    else Placement.BEFORE
                )
                if place_element == Placement.BEFORE:
                    result["caption"] = child.id()
            elif isinstance(item, TableItem):
                if child.item.self_ref in rich_cell_refs:
                    place_element = Placement.TABLE
                else:
                    # Do not add anything under table
                    place_element = Placement.AFTER
                    # Sanity check that anything under table in Docling is either used in rich cells or is caption
                    if not isinstance(child.item, TextItem):
                        logger.warning(f"Table {element_ref} child {child.id()} is not content of any rich cell.")
            elif isinstance(item, PictureItem):
                # Under picture should not be any footnotes
                if isinstance(child.item, TextItem) and child.item.label == DocItemLabel.FOOTNOTE:
                    place_element = Placement.AFTER
                else:
                    # Other texts under picture are mostly its labels (chart axes, legend, ...). There is a small chance
                    # they are useful, but mostly they are not and only mess up the whole autotagging. They are part
                    # of the picture which is described by its alternate text.
                    place_element = Placement.SKIP
            elif isinstance(item, FieldItem):
                # Fillable value is the widget itself (same bbox). SDK tags every widget as Form with OBJR on its own
                # and puts it into the element whose bbox covers it, so the widget lands in this field item.
                if isinstance(child.item, FieldValueItem) and child.item.kind == "fillable":
                    place_element = Placement.SKIP
            elif isinstance(item, ListItem) and isinstance(child.item, FieldItem):
                # SDK does not allow container under list item (pde_text). List item gets bbox of the field instead, so
                # SDK puts the field key text and the widget into it. Field info is in list item comment.
                place_element = Placement.SKIP

            # We do not want this child in template JSON
            if place_element == Placement.SKIP:
                continue

            # Rich table cell content is created later inside its cell
            if place_element == Placement.TABLE:
                table_rich_cells[child.item.self_ref] = child
                continue

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
            result["element_template"] = self._create_element_template(children)

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

        # Add default flags to regular elements. Furniture groups are page-level artifacts and keep only that flag.
        if element.group == InternalElementGroup.NONE:
            flag_list.append("no_join")
            flag_list.append("no_split")
            flag_list.append("no_expand")

        # Process element according to its type
        if element.group == InternalElementGroup.HEADER:
            flag_list.append("artifact")
            result["type"] = "pde_header"
        elif element.group == InternalElementGroup.FOOTER:
            flag_list.append("artifact")
            result["type"] = "pde_footer"
        elif isinstance(item, TitleItem):
            result["tag"] = "Title"
            result["type"] = "pde_text"
        elif isinstance(item, (SectionHeaderItem, FieldHeadingItem)):
            level: int = element.heading_level if element.heading_level is not None else item.level
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
            for child in element.children:
                if isinstance(child.item, FieldItem):
                    result["comment"] = f"{result['comment']} {self._get_field_info(child)}"
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
                    # TODO(SDK): printed checkbox should be Form with PrintField attribute (Role=cb, Checked=on)
                    result["actual_text"] = self._get_checkbox_actual_text(item.text, True)
                case DocItemLabel.CHECKBOX_UNSELECTED:
                    # TODO(SDK): printed checkbox should be Form with PrintField attribute (Role=cb, Checked=off)
                    result["actual_text"] = self._get_checkbox_actual_text(item.text, False)
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
                alt_text = clean_image_alternate_text_end(alt_text)
                result["alt"] = alt_text
            result["type"] = "pde_image"
        elif isinstance(item, TableItem):
            table_data: TableData = item.data
            table_pdfrect: PdfRect = self._get_table_pdfrect(element, page_view, page_height)
            cells: list = self._create_cells(
                table_pdfrect, table_data, page_view, page_height, element_ref, table_rich_cells
            )
            if "element_template" not in result:
                result["element_template"] = self._create_element_template(cells)
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
        elif isinstance(item, FieldRegionItem):
            # Form area with interactive form fields, SDK tags their widgets on its own. SDK makes Figure from graphics
            # inside container (field box borders), but without container it creates its own form tables.
            result["type"] = "pde_container"
        elif isinstance(item, FieldItem):
            # One interactive form field: its key and hint as P and the widget tagged by SDK as Form. SDK fills widget
            # /TU (tooltip read by screen readers) only from text within 4 points, Docling knowledge (key, value, hint)
            # is in the comment for now.
            result["comment"] = f"{result['comment']} {self._get_field_info(element)}"
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

    def _is_caption_after(
        self,
        caption: InternalElement,
        parent: InternalElement,
        page_view: PdfPageView,
        page_height: float,
    ) -> bool:
        """
        True only when caption bbox is clearly below parent bbox (PDF Y). Missing/overlap → False.

        Args:
            caption (InternalElement): Caption child.
            parent (InternalElement): Table/picture (or other) that owns the caption.
            page_view (PdfPageView): PDFix page view for bbox conversion.
            page_height (float): Page height for bbox conversion.

        Returns:
            True if caption is after (below) parent; False otherwise (use BEFORE default).
        """
        parent_bbox: Optional[list[str]] = self._get_template_bbox(parent, page_view, page_height)
        caption_bbox: Optional[list[str]] = self._get_template_bbox(caption, page_view, page_height)
        if parent_bbox is None or caption_bbox is None:
            return False

        # Template bbox: [left, bottom, right, top] in PDF coords (Y up). Below → smaller Y.
        parent_bottom: float = float(parent_bbox[1])
        caption_top: float = float(caption_bbox[3])
        return caption_top <= parent_bottom

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

        if isinstance(item, DocItem) and len(item.prov) > 0:
            provenance: ProvenanceItem = item.prov[element.provenance_index]
            pdf_rect: PdfRect = convert_bbox_to_pdfrect(provenance.bbox, page_view, page_height)
            # Form area from layout can be narrower than widgets of its fields, SDK does not tag widget sticking out
            if isinstance(item, FieldRegionItem):
                self._extend_pdfrect(pdf_rect, self._get_descendants_with_provenance(element), page_view, page_height)
            return self._convert_pdfrect_to_list_str(pdf_rect)

        # Form field item has no provenance, its bbox has to cover the widget so SDK puts the widget into it. Other
        # items without provenance inside form area (e.g. list item holding field item and its list) need bbox too,
        # because SDK skips element without bbox under parent with bbox (form area) together with its content.
        if isinstance(item, FieldItem) or self._is_in_field_region(element):
            descendants: list[InternalElement] = self._get_descendants_with_provenance(element)
            if len(descendants) > 0:
                return self._calculate_bbox_from_children(descendants, page_view, page_height)

        return None

    def _is_in_field_region(self, element: InternalElement) -> bool:
        """
        Check if element is inside form area.

        Args:
            element (InternalElement): Internal element to check.

        Returns:
            True if any ancestor of element is form area (field region).
        """
        parent: Optional[InternalElement] = element.parent
        while parent is not None:
            if isinstance(parent.item, FieldRegionItem):
                return True
            parent = parent.parent
        return False

    def _get_descendants_with_provenance(self, element: InternalElement) -> list[InternalElement]:
        """
        Get closest descendants that have provenance (their bboxes cover all deeper descendants).

        Args:
            element (InternalElement): Internal element to search descendants of.

        Returns:
            List of descendants with provenance.
        """
        descendants: list[InternalElement] = []
        for child in element.children:
            if isinstance(child.item, DocItem) and len(child.item.prov) > 0:
                descendants.append(child)
            else:
                descendants.extend(self._get_descendants_with_provenance(child))
        return descendants

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
        self,
        table_pdfrect: PdfRect,
        table: TableData,
        page_view: PdfPageView,
        page_height: float,
        table_ref: str,
        table_rich_cells: dict[str, InternalElement],
    ) -> list:
        """
        Create cells for table.

        Args:
            table_pdfrect (PdfRect): Table's PDF rectangle.
            table (TableData): Table data to create cells for.
            page_view (PdfPageView): PDFix page view to create cells for.
            page_height (float): Height of the page to create cells for.
            table_ref (str): Table unique identifier.
            table_rich_cells (dict[str, InternalElement]): Content of rich cells by its Docling reference.

        Returns:
            List of cells for table.
        """
        cells: list = []
        table_cells: list[list[AnyTableCell]] = table.grid

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

                    if isinstance(cell, RichTableCell):
                        cell_name: str = f"Table {table_ref} cell [{cell_row}, {cell_column}]"
                        rich_cell: Optional[InternalElement] = table_rich_cells.get(cell.ref.cref)
                        if rich_cell is None:
                            logger.warning(f"{cell_name}: content {cell.ref.cref} of rich cell is not under table.")
                        else:
                            cell_elements: list[dict] = self._create_rich_cell_elements(
                                rich_cell, page_view, page_height, cell_name
                            )
                            if len(cell_elements) > 0:
                                cell_dict["element_template"] = self._create_element_template(cell_elements)
                else:
                    cell_dict["cell_column_span"] = 0
                    cell_dict["cell_row_span"] = 0

                cells.append(cell_dict)

        return cells

    def _create_rich_cell_elements(
        self, rich_cell: InternalElement, page_view: PdfPageView, page_height: float, cell_name: str
    ) -> list[dict]:
        """
        Create elements for content of rich table cell. Docling wraps the content into a group which is dropped and its
        children go directly under the cell. Only these direct children are checked whether they can be under TD.

        Args:
            rich_cell (InternalElement): Content of rich cell referenced by the cell (group or form field).
            page_view (PdfPageView): PDFix page view to create elements for.
            page_height (float): Height of the page to create elements for.
            cell_name (str): Table and cell position for log messages.

        Returns:
            List of elements for template JSON of the cell.
        """
        contents: list[InternalElement] = rich_cell.children if isinstance(rich_cell.item, GroupItem) else [rich_cell]
        results: list[dict] = []

        for content in contents:
            # Create element for layout template and go through each record what can stay
            for result in self._create_elements(content, page_view, page_height, False):
                comment: str = result["comment"]
                element_type: str = result["type"]
                tag: str = result.get("tag", "")
                flags: str = result.get("flag", "")

                # Children of table cell (TD/TH) according to ISO/TS 32005 Table 5 (PDF 1.7 and PDF 2.0 namespaces,
                # checked by veraPDF). ISO 32000-1 has no such rules (its Annex L are colour plates) and PDF/UA-1
                # does not check TD content.
                # Forbidden: TR, TD, TH, THead, TBody, TFoot, LI, LBody, Document, DocumentFragment, Part, Title,
                # Caption, BlockQuote, Aside, Sub, TOC, TOCI, RB, RT, RP, WT, WP.

                # These are forbidden under TD but as P they can be present.
                if tag in {"Caption", "Title"}:
                    # Converted to P by removing specifying tag
                    result.pop("tag")
                # Furniture (header, footer not allowed under TD)
                elif element_type in {"pde_header", "pde_footer"} or (
                    element_type == "pde_text" and ("header" in flags or "footer" in flags)
                ):
                    logger.warning(f"{cell_name}: skipped element {comment}, it can not be under pde_cell.")
                    # Not added
                    continue
                # PDFix SDK allows only pde_text under pde_cell, other types fail whole tagging with error 70 (template
                # node has an invalid or missing parent) even when PDF specification allows them under TD. Until it is
                # fixed in SDK these elements are disabled and SDK puts their content into the cell itself
                # (images become Figure, texts become P).
                elif element_type in {"pde_container", "pde_image", "pde_list", "pde_table"}:
                    # Added as disabled atm
                    result["disable"] = True

                # Allowed: P, H (at most one), H1-H6, L, Lbl, Div, Sect, Art, Table (complete Table -> TR -> TD),
                # Figure, Formula, Form, Note (PDF 1.7) / FENote (PDF 2.0), Index, BibEntry, Reference, Code, Span,
                # Link, Annot, Quote, Em, Strong, Ruby, Warichu.

                results.append(result)

        return results

    def _create_element_template(self, elements: list[dict]) -> dict:
        """
        Create nested template with elements under its parent element.

        Args:
            elements (list[dict]): Elements under parent element.

        Returns:
            Element template for template JSON.
        """
        return {
            "template": {
                "element_create": [{"elements": elements, "statement": "$if"}],
                "pagemap": self.page_map_settings,
            },
        }

    def _get_checkbox_actual_text(self, label: str, checked: bool) -> str:
        """
        Create actual text for printed checkbox the same way as screen readers announce interactive checkbox (label,
        role, state). Box symbols are dropped, screen readers do not read empty box symbol reliably.

        Args:
            label (str): Text of the checkbox from Docling.
            checked (bool): Whether the checkbox is checked.

        Returns:
            Actual text for the checkbox.
        """
        state: str = "checked" if checked else "not checked"
        label = " ".join(label.split()).strip("\u2610\u2611\u2612 ")
        if label:
            return f"{label}, check box, {state}"
        return f"check box, {state}"

    def _get_field_info(self, element: InternalElement) -> str:
        """
        Describe form field from Docling data for template comment (keys, value, checkbox state and hints).

        Args:
            element (InternalElement): Internal element of form field item.

        Returns:
            Form field description.
        """
        info: list[str] = []
        for child in element.children:
            child_item: NodeItem = child.item
            if not isinstance(child_item, TextItem):
                continue
            if isinstance(child_item, FieldValueItem):
                info.append(f"Value ({child_item.kind}): '{child_item.orig}'")
            elif child_item.label == DocItemLabel.FIELD_KEY:
                info.append(f"Key: '{child_item.text}'")
            elif child_item.label == DocItemLabel.FIELD_HINT:
                info.append(f"Hint: '{child_item.text}'")
        return " ".join(info)

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
                if result is None:
                    provenance: ProvenanceItem = child.item.prov[0]
                    bbox: BoundingBox = provenance.bbox
                    result = convert_bbox_to_pdfrect(bbox, page_view, page_height)
                else:
                    self._extend_pdfrect(result, [child], page_view, page_height)

        if result is None:
            return ["0", "0", "0", "0"]

        return self._convert_pdfrect_to_list_str(result)

    def _extend_pdfrect(
        self, result: PdfRect, elements: list[InternalElement], page_view: PdfPageView, page_height: float
    ) -> None:
        """
        Extend rectangle so it covers bounding boxes of elements.

        Args:
            result (PdfRect): Rectangle to extend in place.
            elements (list[InternalElement]): Internal elements whose bounding boxes have to be covered.
            page_view (PdfPageView): PDFix page view to convert bounding boxes.
            page_height (float): Height of the page to convert bounding boxes.
        """
        for element in elements:
            if isinstance(element.item, DocItem) and len(element.item.prov) > 0:
                provenance: ProvenanceItem = element.item.prov[0]
                pdf_rect: PdfRect = convert_bbox_to_pdfrect(provenance.bbox, page_view, page_height)
                if pdf_rect.left < result.left:
                    result.left = pdf_rect.left
                if pdf_rect.bottom < result.bottom:
                    result.bottom = pdf_rect.bottom
                if pdf_rect.right > result.right:
                    result.right = pdf_rect.right
                if pdf_rect.top > result.top:
                    result.top = pdf_rect.top

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
