import tqdm
from docling_core.types.doc import CoordOrigin, DocItem

from internal_classes import InternalElement, InternalPage
from template.page_template_json_creator import PageTemplateJsonCreator


class XYTemplateJsonCreator(PageTemplateJsonCreator):
    """X/Y bbox reading order: rd_sort 2, elements sorted top-left to bottom-right, no rd_index."""

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        super().__init__(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        self.page_map_settings[0]["rd_sort"] = "2"

    def _get_page_elements(self, page: InternalPage) -> list[InternalElement]:
        return sorted(page.ordered_elements, key=lambda element: self._element_bbox_sort_key(element, page.height))

    def _element_bbox_sort_key(self, element: InternalElement, page_height: float) -> tuple[float, float]:
        item = element.item
        if isinstance(item, DocItem) and item.prov:
            provenance_index: int = element.provenance_index if element.provenance_index >= 0 else 0
            bbox = item.prov[provenance_index].bbox
            if bbox.coord_origin != CoordOrigin.TOPLEFT:
                bbox = bbox.to_top_left_origin(page_height)
            return (bbox.t, bbox.l)
        return (float("inf"), float("inf"))
