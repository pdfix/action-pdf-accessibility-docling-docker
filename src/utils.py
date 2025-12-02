import base64

import latex2mathml.converter


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
