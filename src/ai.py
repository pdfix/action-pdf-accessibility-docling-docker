import logging
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import (
    # AutoModelForCausalLM,
    # AutoProcessor,
    BatchFeature,
    RTDetrForObjectDetection,
    RTDetrImageProcessor,
)

from logger import get_logger

logger: logging.Logger = get_logger()

LAYOUT_MODEL_PATH: str = Path(__file__).parent.parent.joinpath("model").resolve().as_posix()
# FORMULA_MODEL: str = "ds4sd/CodeFormulaV2"
# FORMULA_MODEL_PATH: str = "formula-model"
# TABLE_MODEL: str = "ds4sd/docling-models"
# TABLE_MODEL_PATH: str = "model_artifacts/tableformer/accurate"


class Region:
    def __init__(
        self, score: torch.Tensor, label: torch.Tensor, box: torch.Tensor, model: RTDetrForObjectDetection
    ) -> None:
        logger.debug(f"Raw data: label: {label}, score: {score}, box: {box}")
        # Box is 4 floats:
        # (x_min, y_min, x_max, y_max)
        # (left, top, right, bottom)
        # TOP-LEFT is (0,0)
        self.box: list[float] = [round(float(i), 2) for i in box.tolist()]
        # this model labels from 1
        label_pointer: int = int(label.item()) + 1
        self.label: str = model.config.id2label[label_pointer]
        self.score: float = float(score.item())
        logger.debug(f"Created data: label: {self.label}, score: {self.score * 100}%, box: {self.box}")


def process_page(image_path: str, threshold: float) -> list[Region]:
    """
    Use Docling for layout recognition of document page image.

    Args:
        image_path (str): Path to file containing image.
        threshold (float): Threshold under which results from AI are ignored.

    Returns:
        List of regions (BBoxes and types)
    """
    # Load the processor and model
    processor: RTDetrImageProcessor = RTDetrImageProcessor.from_pretrained(LAYOUT_MODEL_PATH, local_files_only=True)
    model: RTDetrForObjectDetection = RTDetrForObjectDetection.from_pretrained(LAYOUT_MODEL_PATH, local_files_only=True)

    # Load image data
    image: Image.Image = Image.open(image_path)
    if image.mode != "RGB":
        image = image.convert(mode="RGB")

    # Prepare inputs
    inputs: BatchFeature = processor(images=image, return_tensors="pt")

    # Generate layout
    with torch.no_grad():
        outputs: Any = model(**inputs)

    # Decode layout
    target_sizes: torch.Tensor = torch.tensor([image.size[::-1]])
    results: list[dict] = processor.post_process_object_detection(
        outputs,
        target_sizes=target_sizes,  # type: ignore[arg-type]
        threshold=threshold,
    )
    # Convert layout
    res: list[Region] = []

    for result in results:
        for score, label_id, box in zip(result["scores"], result["labels"], result["boxes"]):
            res.append(Region(score, label_id, box, model))

    # Return layout
    return res


####### WIP #######
# def process_table(image_path: str) -> dict:
#     """
#     Use Docling tableformer model to identify the structure of the table.

#     Args:
#         image_path (str): Path to file containing image.

#     Returns:
#         Latex representation of formula
#     """


# def process_formula(image_path: str) -> str:
#     """
#     Use Docling formula model to craft latex representation of formula from image.
#     Image of formula should be at 120 DPI.

#     Args:
#         image_path (str): Path to file containing image.

#     Returns:
#         Latex representation of formula
#     """
#     # Load model
#     processor: AutoProcessor = AutoProcessor.from_pretrained(FORMULA_MODEL, use_fast=False)
#     model: AutoModelForCausalLM = AutoModelForCausalLM.from_pretrained(FORMULA_MODEL)

#     # Load image data
#     image: Image.Image = Image.open(image_path)
#     if image.mode != "RGB":
#         image = image.convert(mode="RGB")

#     # Preprocess
#     inputs: Any = processor(images=image, return_tensors="pt")

#     # Inference
#     with torch.no_grad():
#         generated_ids: Any = model.generate(
#             inputs["pixel_values"],
#             max_new_tokens=1024,
#             do_sample=False,  # could use sampling if needed
#         )

#     output: str = processor.decode(generated_ids[0], skip_special_tokens=True)
#     return output
