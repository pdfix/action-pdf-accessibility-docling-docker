import tqdm

from template.page_template_json_creator import PageTemplateJsonCreator


class PdfTemplateJsonCreator(PageTemplateJsonCreator):
    """PDF reading order: rd_sort 3, elements marked with rd_index."""

    def __init__(
        self,
        input_path_str: str,
        bbox_overlap: float,
        progress_bar: tqdm,
        total_progress_units: int,
    ) -> None:
        super().__init__(input_path_str, bbox_overlap, progress_bar, total_progress_units)
        self.page_map_settings[0]["rd_sort"] = "3"
        self.add_rd_indexes = True
