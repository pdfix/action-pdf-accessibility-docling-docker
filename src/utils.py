import base64
import json
import logging
from pathlib import Path
from typing import Any

import latex2mathml.converter

# import torch
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
    # Disable warnings about NNPACK unsupported hardware when running in docker image
    # torch.backends.nnpack.set_flags(False)

    # Disable RapidOCR logging
    logging.getLogger("RapidOCR").disabled = True

    # Docling pulls in Hugging Face deps (transformers / huggingface_hub) which can emit their own tqdm bars
    # (notably: "Loading weights"). Disable those so only our own progress bar is shown.
    transformers_logging.disable_progress_bar()

    # Disable Hugging Face logging about:
    # Passing `generation_config` together with generation-related arguments...
    transformers_logging.set_verbosity_error()

    # Disable Hugging Face logging about:
    # Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable ...
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


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
