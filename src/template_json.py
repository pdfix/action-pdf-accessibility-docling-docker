import re
from datetime import date
from pathlib import Path
from typing import Optional, Union

from docling_core.types.doc import (
    BoundingBox,
    CodeItem,
    CoordOrigin,
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
from pdfixsdk import GetPdfix, PdfDevRect, PdfDoc, Pdfix, PdfPage, PdfPageView, PdfRect, __version__
from pydantic import AnyUrl
from tqdm import tqdm

from ai import InternalDocument, InternalElement, InternalPage
from constants import DOCKER_IMAGE, ZOOM
from exceptions import PdfixFailedToOpenException, PdfixFailedToTagException, PdfixInitializeException
from utils import convert_latex_to_mathml, convert_to_base64, get_current_version


class TemplateJsonCreator:
    """
    Class that prepares each page and in the end creates whole template json file for PDFix-SDK
    """

    # Constants
    CONFIG_FILE = "config.json"
    PAGE_MAP_SETTINGS: list = [
        {
            "graphic_table_detect": "0",
            "statement": "$if",
            "text_table_detect": "0",
            "label_image_detect": "0",
            "label_word_detect": "0",
            "initial_element_only": "1",
            "artifact_untagged": "1",
            "initial_elements_keep_empty": "0",
        }
    ]

    def __init__(self, input_path_str: str, progress_bar: tqdm, total_progress_units: int) -> None:
        """
        Initializes pdfix sdk template json creation by preparing list for each page.

        Args:
            input_path_str (str): Path to PDF document to create template for.
            progress_bar (tqdm): Progress bar to update about processing.
            total_progress_units (int): Total number of units for progress bar for processing.
        """
        self.input_path_str = input_path_str
        self.template_json_pages: list = []
        self.progress_bar: tqdm = progress_bar
        self.total_progress_units: int = total_progress_units

    def process_document(self, document: InternalDocument) -> dict:
        """
        Prepare PDFix SDK json template for whole document.

        Args:
            document (InternalDocument): Internal representatio of PDF document with Docling data.

        Returns:
            Template json for whole document
        """
        created_date: str = date.today().strftime("%Y-%m-%d")
        docker_image: str = f"{DOCKER_IMAGE}:{get_current_version()}"
        metadata: dict = {
            "author": "Generated using Docling Project AI",
            "created": created_date,
            "modified": created_date,
            "notes": f"Created using Docling Project {document.docling_version} inside {docker_image}",
            "sdk_version": __version__,
            # we are creating first one always so it is always "1"
            "version": "1",
        }

        if len(document.pages) == 0:
            self.progress_bar.update(self.total_progress_units)
        else:
            pdfix: Optional[Pdfix] = GetPdfix()
            if pdfix is None:
                raise PdfixInitializeException()

            # Open the document
            doc: Optional[PdfDoc] = pdfix.OpenDoc(self.input_path_str, "")
            if doc is None:
                raise PdfixFailedToOpenException(pdfix, self.input_path_str)

            step: float = self.total_progress_units / len(document.pages)

            for index, page in enumerate(document.pages):
                pdf_page: Optional[PdfPage] = doc.AcquirePage(index)
                if pdf_page is None:
                    raise PdfixFailedToTagException(pdfix, "Failed to acquire the page")

                try:
                    page_view: Optional[PdfPageView] = pdf_page.AcquirePageView(ZOOM, 0)
                    if page_view is None:
                        raise PdfixFailedToTagException(pdfix, "Failed to acquire the page view")

                    try:
                        page_dict: dict = self.process_page(page, page_view)
                        self.template_json_pages.append(page_dict)
                        self.progress_bar.update(step)
                    except Exception:
                        raise
                    finally:
                        page_view.Release()
                except Exception:
                    raise
                finally:
                    pdf_page.Release()

        return {
            "metadata": metadata,
            "template": {
                "element_create": self.template_json_pages,
                "pagemap": self.PAGE_MAP_SETTINGS,
            },
        }

    def process_page(self, page: InternalPage, page_view: PdfPageView) -> dict:
        """
        Prepare json template for PDFix SDK for one page and save it internally to use later in
        create_json_dict_for_document.

        Args:
            page (InternalPage): Results from docling about page.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.

        Returns:
            Json dict for one page.
        """
        page_elements: list = self._create_page(page, page_view)

        json_for_page = {
            "comment": f"Page {page.number}",
            "elements": page_elements,
            "query": {
                "$and": [{"$page_num": page.number}],
            },
            "statement": "$if",
        }
        return json_for_page

    def _create_page(self, page: InternalPage, page_view: PdfPageView) -> list:
        """
        Prepare initial structural elements for the template based on
        detected regions.

        Args:
            page (InternalPage): Results from docling about page.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.

        Returns:
            List of elements with parameters.
        """
        results: list = []

        page_h: float = page.height

        for element in page.ordered_elements:
            result: list[dict] = self._create_elements(element, page_view, page_h, False)

            results.extend(result)

        return results

    def _create_elements(
        self, element: InternalElement, page_view: PdfPageView, page_height: float, include_parent_key: bool
    ) -> list[dict]:
        """
        Create element dict for json as pdfix template expects. Some items can result in multiple dict.

        Args:
            element (InternalElement): Element to create dict for.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.
            page_height (float): Height of the page to convert bbox.

        Returns:
            List of elements dict for json.
        """
        results: list[dict] = []
        result: dict = {}
        results.append(result)

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
        # layer: str = self._get_content_layer(element)
        result["comment"] = f"{element_ref} {label}"
        # Keep parent key only if child is not under it
        if element.parent is not None and include_parent_key:
            result["parent"] = element.parent.id()

        # If any elment has language added in future add result["lang"] = "en" or other language code

        children: list[dict] = []
        # For now put everything where Docling returns it
        append_children_instead_of_including_them: bool = False  # isinstance(item, TableItem)

        for child in element.children:
            child_result: list[dict] = self._create_elements(
                child, page_view, page_height, append_children_instead_of_including_them
            )
            children.extend(child_result)

        if len(children) > 0:
            if append_children_instead_of_including_them:
                for child_dict in children:
                    # Caption and Footnotes under Table are put after Table
                    results.append(child_dict)
            else:
                result["element_template"] = {
                    "template": {
                        "element_create": [{"elements": children, "statement": "$if"}],
                        "pagemap": self.PAGE_MAP_SETTINGS,
                    },
                }
            # if bbox_list is None:
            #     result["bbox"] = self._calculate_bbox_from_children(element.children, page_view, page_height)

        if isinstance(item, TextItem):
            hyperlink: Optional[Union[AnyUrl, Path]] = item.hyperlink
            if isinstance(hyperlink, AnyUrl):
                result["comment"] = f"{result['comment']} Hyperlink: {hyperlink}"
            elif isinstance(hyperlink, Path):
                result["comment"] = f"{result['comment']} Hyperlink: {hyperlink}"
            if item.text:
                result["text"] = item.text

        if isinstance(item, FloatingItem):
            if len(item.footnotes) > 0:
                footnotes: str = ", ".join([footnote.cref for footnote in item.footnotes])
                result["comment"] = f"{result['comment']} Footnotes: {footnotes}"
            if len(item.captions) > 0:
                captions: str = ", ".join([caption.cref for caption in item.captions])
                result["comment"] = f"{result['comment']} Captions: {captions}"

        # For all
        flag_list.append("no_join")
        flag_list.append("no_split")
        flag_list.append("no_expand")

        if isinstance(item, TitleItem):
            result["tag"] = "Title"
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, SectionHeaderItem):
            level: int = item.level
            result["comment"] = result["comment"].replace(label, f"{label} {level}")
            result["heading"] = "h"  # Instead of f"h{level}" use generic to force PDFix SDK to run algorithm
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, ListItem):
            result["numbering"] = self._get_list_type(item)
            result["label_text"] = item.marker
            result["label"] = "label_list"  # if we know nesting use "li_1", "li_2" etc. for different levels
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, CodeItem):
            language: str = item.code_language
            result["comment"] = f"{result['comment']} Lang: {language}"
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, FormulaItem):
            result["tag"] = "Formula"
            if item.text:
                # Formula MathML
                latex_formula: str = item.text
                result["alt"] = latex_formula
                # base64 mathml
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
            # result["text_flag"] = "no_new_line"
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
                # Figure alt text
                alt_text: str = item.annotations[0].text
                result["alt"] = alt_text
            result["type"] = "pde_image"
        elif isinstance(item, TableItem):
            table_data: TableData = item.data
            cells: list = self._create_cells(table_data, page_view, page_height, element_ref)
            if "element_template" not in result:
                result["element_template"] = {
                    "template": {
                        "element_create": [{"elements": cells, "statement": "$if"}],
                        "pagemap": self.PAGE_MAP_SETTINGS,
                    },
                }
            else:
                elements: list[dict] = result["element_template"]["template"]["element_create"][0]["elements"]
                elements.extend(cells)
            result["row_num"] = table_data.num_rows
            result["col_num"] = table_data.num_cols
            result["type"] = "pde_table"
        elif isinstance(item, KeyValueItem):
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, FormItem):
            # result["text_flag"] = "no_new_line"
            result["type"] = "pde_text"
        elif isinstance(item, ListGroup):
            result["type"] = "pde_list"
        elif isinstance(item, InlineGroup):
            # Default - should not get here
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
            # Default - should not get here
            result["type"] = "pde_container"
        elif isinstance(item, DocItem):
            # Default - should not get here
            result["type"] = "pde_container"
        elif isinstance(item, NodeItem):
            # Default - should not get here
            result["type"] = "pde_container"

        # Create flag
        if len(flag_list) > 0:
            result["flag"] = "|".join(flag_list)

        return results

    def _get_template_bbox(
        self, element: InternalElement, page_view: PdfPageView, page_height: float
    ) -> Optional[list[str]]:
        """
        Get bounding box for json as pdfix template expects.

        Args:
            element (InternalElement): Element to get bbox for.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.
            page_height (float): Height of the page to convert bbox.

        Returns:
            List of strings representing bbox for json or None if not applicable.
        """
        item: NodeItem = element.item
        if isinstance(item, DocItem):
            provenance: ProvenanceItem = item.prov[element.provenance_index]
            pdf_rect: PdfRect = self._convert_bbox_to_pdfrect(provenance.bbox, page_view, page_height)
            return self._convert_pdfrect_to_list_str(pdf_rect)

        return None

    def _convert_bbox_to_pdfrect(self, bbox: BoundingBox, page_view: PdfPageView, page_height: float) -> PdfRect:
        """
        Convert bounding box to PDFix SDK PdfRect.
        CoordOrigin.BOTTOMLEFT is PDF system where [0, 0] is in bottom left part.
        CoordOrigin.TOPLEFT is Image system where [0, 0] is in top left part.
        PDFix SDK RectToPage expects image coordinates and creates PDF coordinates in respect to rotation, etc.

        Args:
            bbox (BoundingBox): Bounding box to convert.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.

        Returns:
            PDFix SDK PdfRect.
        """
        if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
            # Convert to top left origin for PDFix SDK
            bbox = bbox.to_top_left_origin(page_height)

        rectangle: PdfDevRect = PdfDevRect()
        rectangle.left = round(bbox.l)
        rectangle.top = round(bbox.t)
        rectangle.right = round(bbox.r)
        rectangle.bottom = round(bbox.b)

        return page_view.RectToPage(rectangle)

    def _convert_pdfrect_to_list_str(self, pdf_rect: PdfRect) -> list[str]:
        """
        Convert PDFix SDK PdfRect to list of strings as pdfix template expects.

        Args:
            pdf_rect (PdfRect): PDFix SDK rectangle to convert.

        Returns:
            List of strings representing bbox for json.
        """
        return [str(pdf_rect.left), str(pdf_rect.bottom), str(pdf_rect.right), str(pdf_rect.top)]

    def _get_label(self, element: InternalElement) -> str:
        """
        Get label value for json as pdfix template expects.

        Args:
            element (InternalElement): Element to get label for.

        Returns:
            Label as string for json purposes.
        """
        item: NodeItem = element.item
        if isinstance(item, DocItem):
            return str(item.label)
        if isinstance(item, GroupItem):
            return str(item.label)
        return ""

    def _create_cells(self, table: TableData, page_view: PdfPageView, page_height: float, table_ref: str) -> list:
        """
        Create cell elements for table in json as pdfix template expects.

        Args:
            table (TableData): Table data from docling.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.
            page_height (float): Height of the page to convert bbox.
            table_ref (str): ID of the table parent.

        Returns:
            List of cell elements as dicts for json.
        """
        cells: list = []
        table_cells: list[list[TableCell]] = table.grid

        for row in table_cells:
            for cell in row:
                cell_row: int = cell.start_row_offset_idx + 1
                cell_column: int = cell.start_col_offset_idx + 1
                # cell_id: str = f"{table_ref}-cell-{cell_row}-{cell_column}"
                cell_scope: str = self._get_cell_scope(cell)
                cell_dict: dict = {
                    "cell_column": str(cell_row),
                    "cell_column_span": str(cell.col_span),
                    "cell_row": str(cell_column),
                    "cell_row_span": str(cell.row_span),
                    "cell_header": self._convert_bool_to_str(cell.row_header or cell.column_header),
                    "cell_scope": cell_scope,
                    "comment": f"Cell Pos: [{cell_row}, {cell_column}]",
                    # "name": cell_id,
                    # "parent": table_ref,
                    "type": "pde_cell",
                }
                if cell.bbox:
                    pdf_rect: PdfRect = self._convert_bbox_to_pdfrect(cell.bbox, page_view, page_height)
                    cell_dict["bbox"] = self._convert_pdfrect_to_list_str(pdf_rect)
                if cell.text:
                    cell_dict["text"] = cell.text
                cells.append(cell_dict)

        return cells

    def _get_cell_scope(self, cell: TableCell) -> str:
        """
        Get cell scope value for json as pdfix template expects.

        Args:
            cell (TableCell): Cell to get scope for.

        Returns:
            "row", "column", "both" or "" depending on cell headers.
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
        Create value for json as pdfix template expects.

        Args:
            value (bool): Value to convert.

        Returns:
            Converted bool to string for json purposes.
        """
        return "true" if value else "false"

    def _get_list_type(self, item: ListItem) -> str:
        """
        Get list type value for json as pdfix template expects.

        Args:
            group (GroupItem): Group to get list type for.

        Returns:
            List type as string for json purposes.
        """
        marker: str = item.marker.strip()
        stripped_marker: str = marker.lstrip("([").rstrip(")].:")
        if item.enumerated:
            if re.fullmatch(r"\d+", stripped_marker):
                return "Decimal"
            # Docling for upper roman uses only "[IVXLCDM]+\." for original (not stripped) marker
            if re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", stripped_marker):
                return "UpperRoman"
            # Docling for lower roman uses only "[ivxlcdm]+\." for original (not stripped) marker
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
        Calculate bounding box that covers all children elements.

        Args:
            children (list[InternalElement]): List of child elements to calculate bbox for.
            page_view (PdfPageView): PDFix SDK page view to get page dimensions for bbox conversion.
            page_height (float): Height of the page to convert bbox.

        Returns:
            Bbox covering all children as list of strings for json purposes.
        """
        if len(children) == 0:
            return ["0", "0", "0", "0"]

        result: Optional[PdfRect] = None

        for child in children:
            if isinstance(child.item, DocItem) and len(child.item.prov) > 0:
                provenance: ProvenanceItem = child.item.prov[0]
                bbox: BoundingBox = provenance.bbox
                pdf_rect: PdfRect = self._convert_bbox_to_pdfrect(bbox, page_view, page_height)

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
