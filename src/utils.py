import base64
import json
import sys
from pathlib import Path
from typing import Any

import latex2mathml.converter

from constants import CONFIG_FILE


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
        print(f"Error reading {CONFIG_FILE}: {e}", file=sys.stderr)
        return "unknown"
