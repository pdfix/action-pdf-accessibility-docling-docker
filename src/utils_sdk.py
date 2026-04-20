import ctypes
import json
import logging
from typing import Optional

from docling_core.types.doc import BoundingBox, CoordOrigin
from pdfixsdk import PdfDevRect, Pdfix, PdfPageView, PdfRect

from exceptions import PdfixActivationException, PdfixAuthorizationException
from logger import get_logger

logger: logging.Logger = get_logger()


def authorize_sdk(pdfix: Pdfix, license_name: Optional[str], license_key: Optional[str]) -> None:
    """
    Tries to authorize or activate Pdfix license.

    Args:
        pdfix (Pdfix): Pdfix sdk instance.
        license_name (string): Pdfix sdk license name (e-mail)
        license_key (string): Pdfix sdk license key
    """
    if license_name and license_key:
        authorization = pdfix.GetAccountAuthorization()
        if not authorization.Authorize(license_name, license_key):
            raise PdfixAuthorizationException(pdfix)
    elif license_key:
        if not pdfix.GetStandarsAuthorization().Activate(license_key):
            raise PdfixActivationException(pdfix)
    else:
        logger.info("No license name or key provided. Using PDFix SDK trial")


def convert_bbox_to_pdfrect(bbox: BoundingBox, page_view: PdfPageView, page_height: float) -> PdfRect:
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


def json_to_raw_data(json_dict: dict) -> tuple[ctypes.Array[ctypes.c_ubyte], int]:
    """
    Converts a JSON dictionary into a raw byte array (c_ubyte array) that can be used for low-level data operations.

    Parameters:
        json_dict (dict): A Python dictionary to be converted into JSON format and then into raw bytes.

    Returns:
        tuple: A tuple containing:
            - json_data_raw (ctypes.c_ubyte array): The raw byte array representation of the JSON data.
            - json_data_size (int): The size of the JSON data in bytes.
    """
    json_str: str = json.dumps(json_dict)
    json_data: bytearray = bytearray(json_str.encode("utf-8"))
    json_data_size: int = len(json_str)
    json_data_raw: ctypes.Array[ctypes.c_ubyte] = (ctypes.c_ubyte * json_data_size).from_buffer(json_data)
    return json_data_raw, json_data_size
