from typing import Optional

from docling_core.types.doc import TableCell, TableData
from pdfixsdk import PdfPageView, PdfRect

from utils_sdk import convert_bbox_to_pdfrect


class DoclingPostProcessingTable:
    """
    This is for post processing bounding boxes of table cells to not have spaces between cells.
    """

    def __init__(
        self,
        table_bbox: PdfRect,
        table_data: TableData,
        table_cells: list[list[TableCell]],
        page_view: PdfPageView,
        page_height: float,
    ) -> None:
        """
        Constructor.

        Args:
            table_bbox (PdfRect): Bounding box of the table.
            table_data (TableData): Data of the table.
            table_cells (list[list[TableCell]]): Cells of the table.
            page_view (PdfPageView): View of the page.
            page_height (float): Height of the page.
        """
        self.table_bbox: PdfRect = table_bbox
        self.table_data: TableData = table_data
        self.table_cells: list[list[TableCell]] = table_cells
        self.page_view: PdfPageView = page_view
        self.page_height: float = page_height
        self.rows: int = table_data.num_rows
        self.cols: int = table_data.num_cols
        # print(f"Post processing table [{self.rows}x{self.cols}]")

    def get_bboxes(self) -> list[list[PdfRect]]:
        """
        Process table data cells to calculate each line average and return it as cell walls.
        This way each neighbouring cells do not have space in between them.

        Returns:
            Calculated bounding boxes of table cells as cell walls.
        """
        # Do not post process empty table
        if self.rows == 0 or self.cols == 0:
            return []

        # Convert docling data into PDFix data
        text_bboxes: list[list[Optional[PdfRect]]] = self._get_cell_text_bboxes()

        # print(f"T: ({self.table_bbox.left}, {self.table_bbox.top}, {self.table_bbox.right}, {self.table_bbox.bottom})")
        # self._pretty_print(text_bboxes)

        # Calculate average for each column/row line (sides are table bbox values)
        vertical_lines: list[int] = self._calculate_vertical_lines(text_bboxes)
        # self._pretty_print_list("Vertical lines", vertical_lines)
        horizontal_lines: list[int] = self._calculate_horizontal_lines(text_bboxes)
        # self._pretty_print_list("Horizontal lines", horizontal_lines)

        # Fill average lines into each cell bounding boxes
        bboxes: list[list[PdfRect]] = []

        for row in self.table_cells:
            row_bboxes: list[PdfRect] = []
            for cell in row:
                rectangle: PdfRect = PdfRect()
                rectangle.left = vertical_lines[cell.start_col_offset_idx]
                rectangle.right = vertical_lines[cell.end_col_offset_idx]
                rectangle.top = horizontal_lines[cell.start_row_offset_idx]
                rectangle.bottom = horizontal_lines[cell.end_row_offset_idx]
                row_bboxes.append(rectangle)
            bboxes.append(row_bboxes)

        # print("Result:")
        # self._pretty_print(bboxes)

        # Return it
        return bboxes

    def _get_cell_text_bboxes(self) -> list[list[Optional[PdfRect]]]:
        """
        Get bounding boxes of the text in table cells.

        Returns:
            For each cell bounding box of the text in the cell.
        """
        bboxes: list[list[PdfRect]] = []

        for row in self.table_cells:
            row_bboxes: list[PdfRect] = []
            for cell in row:
                if cell.bbox:
                    cell_bbox: PdfRect = convert_bbox_to_pdfrect(cell.bbox, self.page_view, self.page_height)
                    row_bboxes.append(cell_bbox)
                else:
                    row_bboxes.append(None)
            bboxes.append(row_bboxes)

        return bboxes

    def _calculate_vertical_lines(self, text_bboxes: list[list[Optional[PdfRect]]]) -> list[int]:
        """
        Returns for each column line:
        - left side of right cell
        - right side of left cell
        For first and last it returns table bbox.

        Args:
            text_bboxes (list[list[Optional[PdfRect]]]): Bounding boxes of the text in table cells.

        Returns:
            Each column line value.
        """
        # Initialize empty list with zeros for each column line
        vertical_lines: list[list[int]] = [[] for i in range(self.cols + 1)]

        # Table borders
        vertical_lines[0].append(self.table_bbox.left)
        vertical_lines[self.cols].append(self.table_bbox.right)

        # For each cell fill left and right line into each column line list
        for row in self.table_cells:
            for cell in row:
                # print(f"Accessing cell: [{cell.start_row_offset_idx}, {cell.start_col_offset_idx}]")
                cell_bbox: Optional[PdfRect] = text_bboxes[cell.start_row_offset_idx][cell.start_col_offset_idx]
                if cell_bbox:
                    left_index: int = cell.start_col_offset_idx
                    if left_index > 0:
                        vertical_lines[left_index].append(cell_bbox.left)
                    right_index: int = cell.end_col_offset_idx
                    if right_index < self.cols:
                        vertical_lines[right_index].append(cell_bbox.right)

        # for index, line in enumerate(vertical_lines):
        #     print(f"Line {index}: {line}")

        # Calculate average if data is available
        average_lines: list[Optional[int]] = []
        for index, line_values in enumerate(vertical_lines):
            if len(line_values) > 0:
                average_lines.append(int(sum(line_values) / len(line_values)))
            else:
                average_lines.append(None)

        # Fill missing data
        result_lines: list[int] = []

        for index in range(len(average_lines)):
            line_value: Optional[int] = average_lines[index]
            if line_value:
                result_lines.append(line_value)
            else:
                calculated: int = self._get_value_from_lines_for_line(average_lines, index)
                result_lines.append(calculated)

        return result_lines

    def _calculate_horizontal_lines(self, text_bboxes: list[list[Optional[PdfRect]]]) -> list[int]:
        """
        Returns for each row line:
        - bottom side of top cell
        - top side of bottom cell
        For first and last it returns table bbox.

        Args:
            text_bboxes (list[list[Optional[PdfRect]]]): Bounding boxes of the text in table cells.

        Returns:
            Each row line value.
        """
        # Initialize empty list with zeros for each row line
        horizontal_lines: list[list[int]] = [[] for i in range(self.rows + 1)]

        # Table borders
        horizontal_lines[0].append(self.table_bbox.top)
        horizontal_lines[self.rows].append(self.table_bbox.bottom)

        # For each cell fill top and bottom line into each row line list
        for row in self.table_cells:
            for cell in row:
                # print(f"Accessing cell: [{cell.start_row_offset_idx}, {cell.start_col_offset_idx}]")
                cell_bbox: Optional[PdfRect] = text_bboxes[cell.start_row_offset_idx][cell.start_col_offset_idx]
                if cell_bbox:
                    first_index: int = cell.start_row_offset_idx
                    if first_index > 0:
                        horizontal_lines[first_index].append(cell_bbox.bottom)
                    second_index: int = cell.end_row_offset_idx
                    if second_index < self.rows:
                        horizontal_lines[second_index].append(cell_bbox.top)

        # for index, line in enumerate(horizontal_lines):
        #     print(f"Line {index}: {line}")

        # Calculate average if data is available
        average_lines: list[Optional[int]] = []
        for index, line_values in enumerate(horizontal_lines):
            if len(line_values) > 0:
                average_lines.append(int(sum(line_values) / len(line_values)))
            else:
                average_lines.append(None)

        # Fill missing data
        result_lines: list[int] = []

        for index in range(len(average_lines)):
            line_value: Optional[int] = average_lines[index]
            if line_value:
                result_lines.append(line_value)
            else:
                calculated: int = self._get_value_from_lines_for_line(average_lines, index)
                result_lines.append(calculated)

        return result_lines

    def _get_value_from_lines_for_line(self, average_lines: list[Optional[int]], line_index: int) -> int:
        """
        Try to guess value from data around it.
        Which values we have already:
        - first and last (from table bbox)
        - previous index (as we already guessed it before)
        This algorithm is fallback only and assumes each column width is equal.

        Args:
            average_lines (list[Optional[int]]): List of average values for each column line.
            line_index (int): Index of the line to get value from.

        Returns:
            Guess value for the line.
        """
        # Search for first value after line:
        next_index: int = -1
        next_value: int = -1
        for index in range(line_index + 1, len(average_lines)):
            line: Optional[int] = average_lines[index]
            if line is not None:
                next_index = index
                next_value = line
                break

        previous_index: int = line_index - 1
        previous_line: Optional[int] = average_lines[previous_index]
        # It has already value from previous guessing so this is just for code checking
        previous_value: int = previous_line if previous_line else 0

        # Calculate line value from next and previous accoridng to index distance
        diff_value: int = next_value - previous_value
        diff_index: int = next_index - previous_index
        step_value: int = int(diff_value / diff_index)

        return previous_value + step_value

    # def _pretty_print(self, bboxes: list[list[Optional[PdfRect]]]) -> None:
    #     for row_index, row in enumerate(bboxes):
    #         for column_index, cell in enumerate(row):
    #             if cell:
    #                 print(f"[{row_index}, {column_index}] ({cell.left}, {cell.top}, {cell.right}, {cell.bottom})")
    #             else:
    #                 print(f"[{row_index}, {column_index}] (None)")

    # def _pretty_print_list(self, list_name: str, list: list[int]) -> None:
    #     print(f"{list_name}: {list}")
