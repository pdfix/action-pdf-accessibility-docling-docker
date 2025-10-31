import ctypes
import json
from typing import Optional

from pdfixsdk import Pdfix

from exceptions import PdfixActivationException, PdfixAuthorizationException


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
        print("No license name or key provided. Using PDFix SDK trial")


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
