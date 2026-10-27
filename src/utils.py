import base64
import json
import logging
from pathlib import Path
from typing import Any

import latex2mathml.converter
from transformers.utils import logging as transformers_logging

from constants import CONFIG_FILE
from logger import get_logger

logger: logging.Logger = get_logger()


def convert_latex_to_mathml(latex_formula: str) -> str:
    """
    From LaTeX representation of formula create MathML representation of formula.

    Args:
        latex_formula (str): LaTeX representation of formula.

    Returns:
        MathML representation of formula.
    """
    try:
        # For most latex inputs creates mathml-3 representation
        # If it cannot convert it throws exception
        return latex2mathml.converter.convert(latex_formula)
    except Exception:
        pass
    return ""


def convert_to_base64(data: str) -> str:
    """
    Transforms data into base64.

    Args:
        data (str): Data to transform.

    Returns:
        Base64 representation of data.
    """
    data_bytes: bytes = data.encode("utf-8")
    return base64.b64encode(data_bytes).decode("utf-8")


def disable_additional_logging() -> None:
    """
    Disable additional logging.
    """
    # Disable RapidOCR logging about:
    # [RapidOCR] main.py:164: The text detection result is empty
    logging.getLogger("RapidOCR").disabled = True

    # Disable Docling logging about:
    # RapidOCR returned empty result!
    logging.getLogger("docling.models.stages.ocr.rapid_ocr_model").setLevel(logging.ERROR)

    # Docling pulls in Hugging Face deps (transformers / huggingface_hub) which can emit their own tqdm bars
    # (notably: "Loading weights"). Disable those so only our own progress bar is shown.
    transformers_logging.disable_progress_bar()

    # Disable Hugging Face logging when loading CodeFormulaV2 (formula recognition) about:
    # Model config: pad_token_id must be `None` or an integer within the vocabulary ...
    # The tied weights mapping and config for this model specifies to tie ... so we will NOT tie them ...
    transformers_logging.set_verbosity_error()


def get_current_version() -> str:
    """
    Read the current version from config.json.

    Returns:
        The current version of the Docker image.
    """
    config_path: Path = Path(__file__).parent.joinpath(f"../{CONFIG_FILE}").resolve()
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config: Any = json.load(file)
            return config.get("version", "unknown")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error reading {CONFIG_FILE}: {e}")
        return "unknown"


def clean_image_alternate_text_end(text: str) -> str:
    """
    Clean the end of the image alternate text. SmolVLM has ending token "<end_of_utterance>"
    and sometimes part of that text is included at the end of the alternate text.

    Args:
        text (str): SmolVLM image alternate text.

    Returns:
        The cleaned text.
    """
    end_token: str = "<end_of_utterance>"
    for length in range(len(end_token), 0, -1):
        short_end_token: str = end_token[:length]
        if text.endswith(short_end_token):
            return text[: -len(short_end_token)]
    return text
