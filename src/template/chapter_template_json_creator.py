from template.page_template_json_creator import PageTemplateJsonCreator


class ChapterTemplateJsonCreator(PageTemplateJsonCreator):
    """
    Docling reading order with chapters and sections split into pages. Builds per-page element_create blocks holding
    the chapter/section hierarchy of that page (prepared by the converter). Keeps Docling reading order like
    PageTemplateJsonCreator, without it PDFix SDK would reorder content inside chapters and sections.
    """
