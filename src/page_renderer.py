from typing import BinaryIO, Optional

from pdfixsdk import (
    PdfImageParams,
    Pdfix,
    PdfPage,
    PdfPageRenderParams,
    PdfPageView,
    PsFileStream,
    PsImage,
    kImageDIBFormatArgb,
    kImageFormatJpg,
    kPsTruncate,
)
from PIL import Image

from exceptions import PdfixFailedToRenderException


def render_page(pdfix: Pdfix, pdf_page: PdfPage, page_view: PdfPageView, temp_file: BinaryIO) -> None:
    """
    Renders the PDF page into image

    Args:
        pdfix (Pdfix): Pdfix SDK.
        pdf_page (PdfPage): The page to render.
        page_view (PdfPageView): The view of the PDF page used for coordinate conversion.
        temp_file (BinaryIO): File to save image to.

    Returns:
        The path to the rendered image temporary file.
    """
    # Get the dimensions of the page view (device width and height)
    page_width: int = page_view.GetDeviceWidth()
    page_height: int = page_view.GetDeviceHeight()

    # Create an image with the specified dimensions and ARGB format
    page_image: Optional[PsImage] = pdfix.CreateImage(page_width, page_height, kImageDIBFormatArgb)
    if page_image is None:
        raise PdfixFailedToRenderException(pdfix, "Failed to create image of page")

    try:
        # Set up rendering parameters
        render_params: PdfPageRenderParams = PdfPageRenderParams()
        render_params.image = page_image
        render_params.matrix = page_view.GetDeviceMatrix()

        # Render the page content onto the image
        if not pdf_page.DrawContent(render_params):
            raise PdfixFailedToRenderException(pdfix, "Failed to draw content of page into image")

        # Save the rendered image to a temporary file in JPG format
        file_stream: Optional[PsFileStream] = pdfix.CreateFileStream(temp_file.name, kPsTruncate)
        if file_stream is None:
            raise PdfixFailedToRenderException(pdfix, "Unable to create file stream")

        try:
            # Set image parameters (format and quality)
            image_params: PdfImageParams = PdfImageParams()
            image_params.format = kImageFormatJpg
            image_params.quality = 100

            # Save the image to the file stream
            if not page_image.SaveToStream(file_stream, image_params):
                raise PdfixFailedToRenderException(pdfix, "Failed to save rendered image to temporary file")

        except Exception:
            raise
        finally:
            file_stream.Destroy()
    except Exception:
        raise
    finally:
        page_image.Destroy()


def crop_image(image_path: str, box: list[float], temp_file: BinaryIO) -> None:
    """
    Cut out part of image into new image. WIP (not tested).

    Args:
        image_path (str): Path to existing image.
        box (list[float]): List of left, top, right, bottom pixel values where top left is (0,0).
        temp_file (BinaryIO): File to save cutted image to.
    """
    with Image.open(image_path) as image:
        # Convert float coordinates to integers (Pillow needs integers)
        left, top, right, bottom = [int(round(coordinate)) for coordinate in box]

        # Crop the image
        cropped: Image.Image = image.crop((left, top, right, bottom))

        # Save cropped image into temporary file
        cropped.save(temp_file.name, format="JPEG")
