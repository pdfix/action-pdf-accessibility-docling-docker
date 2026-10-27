from io import BytesIO
from pathlib import Path
from typing import Iterator, Optional, Union

import pypdfium2 as pdfium
from docling.backend.docling_parse_backend import (
    ThreadedDoclingParseDocumentBackend,
    ThreadedDoclingParsePageBackend,
)
from docling.datamodel.backend_options import PdfBackendOptions, ThreadedDoclingParseBackendOptions
from docling.datamodel.document import InputDocument
from docling.utils.locks import pypdfium2_lock
from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_parse.pdf_parser import PageParseResult
from PIL import Image


class PdfiumImagePageBackend(ThreadedDoclingParsePageBackend):
    """
    Page parsed by docling-parse whose page image is rendered by pypdfium2.
    """

    def __init__(self, result: PageParseResult, pdfium_document: pdfium.PdfDocument) -> None:
        """
        Constructor.

        Args:
            result (PageParseResult): Page parsed by docling-parse (without rendered image).
            pdfium_document (pdfium.PdfDocument): Same document opened in pypdfium2 for rendering.
        """
        super().__init__(result, rendered=False)
        self.pdfium_document: pdfium.PdfDocument = pdfium_document

    def get_page_image(self, scale: float = 1, cropbox: Optional[BoundingBox] = None) -> Image.Image:
        """
        Render page image the same way as docling PyPdfiumPageBackend (render at 1.5x and downscale).
        The layout model detects lists, forms and tables much better on this image than on docling-parse one.

        Args:
            scale (float): Scale of the image (1 = 72 DPI).
            cropbox (Optional[BoundingBox]): Part of the page to render, whole page if None.

        Returns:
            RGB image of the page.
        """
        page_size = self.get_size()
        if not cropbox:
            cropbox = BoundingBox(l=0, r=page_size.width, t=0, b=page_size.height, coord_origin=CoordOrigin.TOPLEFT)
            padbox: BoundingBox = BoundingBox(l=0, r=0, t=0, b=0, coord_origin=CoordOrigin.BOTTOMLEFT)
        else:
            padbox = cropbox.to_bottom_left_origin(page_size.height).model_copy()
            padbox.r = page_size.width - padbox.r
            padbox.t = page_size.height - padbox.t

        with pypdfium2_lock:
            page: pdfium.PdfPage = self.pdfium_document[self.page_no - 1]
            bitmap: pdfium.PdfBitmap = page.render(scale=scale * 1.5, rotation=0, crop=padbox.as_tuple())
            image: Image.Image = bitmap.to_pil().copy()
            bitmap.close()
            page.close()

        size: tuple[int, int] = (round(cropbox.width * scale), round(cropbox.height * scale))
        return image.resize(size=size).convert("RGB")


class HybridDocumentBackend(ThreadedDoclingParseDocumentBackend):
    """
    Docling PDF backend: text and content parsed by docling-parse, page images rendered by pypdfium2.
    """

    def __init__(
        self,
        in_doc: InputDocument,
        path_or_stream: Union[BytesIO, Path],
        options: Optional[PdfBackendOptions] = None,
    ) -> None:
        """
        Constructor.

        Args:
            in_doc (InputDocument): Document being converted.
            path_or_stream (Union[BytesIO, Path]): PDF document.
            options (Optional[PdfBackendOptions]): Backend options.
        """
        # docling-parse does not render pages, pypdfium2 renders them on request
        values: dict = options.model_dump() if options else {}
        values["render_pages"] = False
        super().__init__(in_doc, path_or_stream, ThreadedDoclingParseBackendOptions(**values))

        source: Union[bytes, Path] = (
            path_or_stream.getvalue() if isinstance(path_or_stream, BytesIO) else path_or_stream
        )
        with pypdfium2_lock:
            self.pdfium_document: pdfium.PdfDocument = pdfium.PdfDocument(source)

    def iter_pages(self) -> Iterator[ThreadedDoclingParsePageBackend]:
        """
        Iterate parsed pages.

        Returns:
            Pages parsed by docling-parse with pypdfium2 page images.
        """
        self._iterating = True
        for result in self.parser.iterate_results():
            yield PdfiumImagePageBackend(result, self.pdfium_document)
        self._iterating = False

    def unload(self) -> None:
        """
        Close both documents.
        """
        if not self._closed:
            with pypdfium2_lock:
                self.pdfium_document.close()
        super().unload()
