import json
import logging
from pathlib import Path
from typing import Any, Optional

from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON
from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    CoordOrigin,
    DescriptionAnnotation,
    DocItemLabel,
    FormulaItem,
    GroupLabel,
    ListGroup,
    ListItem,
    NodeItem,
    PictureItem,
    ProvenanceItem,
    RefItem,
    TextItem,
)
from docling_ibm_models.layoutmodel.layout_predictor import LayoutPredictor
from huggingface_hub import snapshot_download
from PIL import Image
from transformers import AutoModelForVision2Seq, AutoProcessor

from internal_classes import InternalElement
from logger import get_logger

logger: logging.Logger = get_logger()


class CellProcessor:
    """
    This is for detecting what elements are inside table cell.
    Docling by default takes table as terminal element and does not detect what is inside table cells.
    This approach uses same VLM model as Docling.
    Using docling layout model is not suitable as it is trained for A4 pages and not smal cell images.
    """

    MODEL_ID = "HuggingFaceTB/SmolVLM-256M-Instruct"
    DEVICE = "cpu"

    def __init__(self) -> None:
        """
        Constructor.
        """
        self.processor: Any = AutoProcessor.from_pretrained(self.MODEL_ID)
        self.model: Any = AutoModelForVision2Seq.from_pretrained(
            self.MODEL_ID  # , torch_dtype=torch.float32, device_map="auto"
        ).to(self.DEVICE)

        # self.model.eval()

    def process_cell_docling(
        self,
        cell_image_path: Path,
        page_number: int,
        cell_bbox: BoundingBox,
        cell_id: str,
    ) -> list[InternalElement]:
        """
        Process cell from docling data by using its picture and calling it on docling layout model.

        Args:
            cell_image_path (Path): Path to image of cell content.
            page_number (int): Page number of the cell in the document.
            cell_bbox (BoundingBox): Bounding box of the cell in the document.
            parent_id (str): ID of the parent element.
            parent (InternalElement): None if cell is parent, ListGroup if parent is list.

        Returns:
            list[InternalElement]: List of internal elements inside the element (cell).
        """
        result: list[dict] = self._call_layout_model(cell_image_path)
        logger.info(f"Docling layout output:\n{result}")
        # cell_image: Image.Image = Image.open(cell_image_path).convert("RGB")
        # size: list[int] = [cell_image.width, cell_image.height]
        # return self._get_elements_from_docling(result, size, page_number, cell_bbox, cell_id, None)
        return []

    def _get_docling_layout_model_path(self) -> str:
        """
        Ask hugging face library where it would cache the docling layout model.
        """
        return snapshot_download(
            repo_id=DOCLING_LAYOUT_HERON.repo_id,
            revision=DOCLING_LAYOUT_HERON.revision,
            local_files_only=True,  # no downloads
        )

    def _call_layout_model(self, cell_image_path: Path) -> list[dict]:
        # Resolve the local artifact path used by Docling
        artifact_path: str = self._get_docling_layout_model_path()

        # Create predictor (same config Docling uses)
        predictor: LayoutPredictor = LayoutPredictor(
            artifact_path=artifact_path,
            device="cpu",
        )

        # Load image
        image: Image.Image = Image.open(cell_image_path).convert("RGB")

        # Run prediction (batch size = 1)
        predictions: list[list[dict]] = predictor.predict_batch([image])

        # Return first (and only) page result
        return predictions[0]

    def _get_elements_from_docling(
        self,
        data: dict,
        size: list[int],
        page_number: int,
        cell_bbox: BoundingBox,
        parent_id: str,
        parent: Optional[InternalElement],
    ) -> list[InternalElement]:
        """
        From AI dictionary and docling cell data create all internal elements that are inside the cells.

        Args:
            data (dict): AI model output as dictionary.
            size (list[int]): Size of the cell image [width, height].
            page_number (int): Page number of the cell in the document.
            cell_bbox (BoundingBox): Bounding box of the cell in the document.
            parent_id (str): ID of the parent element.
            parent (InternalElement): None if cell is parent, ListGroup if parent is list.

        Returns:
            list[InternalElement]: List of internal elements inside the element (cell or list).
        """
        result: list[InternalElement] = []
        for element in data.get("elements", []):
            # TODO better parsing of model output data
            element_type: str = element.get("type", "text")

            # Calculate element coordinates
            bbox: list[float] = element.get("bbox", [0.0, 0.0, 1.0, 1.0])
            coords_bbox: list[float] = [
                cell_bbox.l + bbox[0] * size[0],
                cell_bbox.b + bbox[1] * size[1],
                cell_bbox.l + bbox[2] * size[0],
                cell_bbox.b + bbox[3] * size[1],
            ]
            element_bbox: BoundingBox = BoundingBox(
                l=coords_bbox[0],
                t=coords_bbox[3],
                r=coords_bbox[2],
                b=coords_bbox[1],
                coord_origin=CoordOrigin.BOTTOMLEFT,
            )
            provenances: list[ProvenanceItem] = [
                ProvenanceItem(page_no=page_number, bbox=element_bbox, charspan=(0, 0))
            ]

            element_id: str = f"{parent_id}_{len(result) + 1}"

            item: Optional[NodeItem] = None
            list_items: list[InternalElement] = []

            match element_type:
                case "formula":
                    item = FormulaItem(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        label=DocItemLabel.FORMULA,
                        prov=provenances,
                        orig="",
                        text=element.get("text", ""),
                        formatting=None,
                        hyperlink=None,
                    )
                case "image":
                    annotation: DescriptionAnnotation = DescriptionAnnotation(
                        kind="description",
                        text=element.get("image_description", ""),
                        provenance=self.MODEL_ID,
                    )
                    item = PictureItem(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        label=DocItemLabel.PICTURE,
                        prov=provenances,
                        captions=[],
                        references=[],
                        footnotes=[],
                        image=None,
                        annotations=[annotation],
                    )
                case "list":
                    item = ListGroup(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        name="cell_group",  # TODO better name
                        label=GroupLabel.LIST,
                    )
                case "text":
                    if parent:  # isinstance(parent.item, ListGroup):
                        item = ListItem(
                            self_ref=element_id,
                            parent=RefItem(**{"$ref": parent_id}),
                            children=[],
                            content_layer=ContentLayer.BODY,
                            meta=None,
                            label=DocItemLabel.LIST_ITEM,
                            prov=provenances,
                            orig="",
                            text=element.get("text", ""),
                            formatting=None,
                            hyperlink=None,
                            enumerated=False,
                            marker="",
                        )
                    else:
                        item = TextItem(
                            self_ref=element_id,
                            parent=RefItem(**{"$ref": parent_id}),
                            children=[],
                            content_layer=ContentLayer.BODY,
                            meta=None,
                            label=DocItemLabel.TEXT,
                            prov=provenances,
                            orig="",
                            text=element.get("text", ""),
                            formatting=None,
                            hyperlink=None,
                        )

            if item is not None:
                internal_element: InternalElement = InternalElement(item=item, parent=parent)

                children: list[dict] = element.get("elements", [])
                if children:
                    list_items = self._get_elements_from_docling(
                        {"elements": children}, size, page_number, cell_bbox, element_id, internal_element
                    )
                result.append(internal_element)
            if list_items:
                result.extend(list_items)
        return result

    def process_cell_vlm(
        self,
        cell_image_path: Path,
        page_number: int,
        cell_bbox: BoundingBox,
        cell_id: str,
    ) -> list[InternalElement]:
        """
        Process a single cell image and return the extracted elements as a JSON string.

        Limitations:
        - Lists are sometimes returned as "text" unless clearly bulleted
        - Very small formulas may be classified as "text"
        - Does not do recursive element extraction

        Args:
            cell_image_path (Path): Path to the cell image.
            page_number (int): Page number of the cell in the document.

        Returns:
            str: JSON string representing the extracted elements.
        """
        output: tuple[str, list[int]] = self._call_ai(cell_image_path)
        data: dict = self._convert(output[0])
        return self._get_elements_from_vlm(data, output[1], page_number, cell_bbox, cell_id, None)

    def _call_ai(self, cell_image_path: Path) -> tuple[str, list[int]]:
        """
        Opens Image and uses it as input for AI model.

        Args:
            cell_image_path (Path): Path to the cell image.

        Returns:
            tuple[str, list[int]]: Output JSON string and image size [width, height].
        """
        cell_image: Image.Image = Image.open(cell_image_path).convert("RGB")
        size: list[int] = [cell_image.width, cell_image.height]

        prompt: str = """
You are analyzing the content of a single table cell.

Identify all distinct elements inside the cell.
For each found element, return:
- type: one of ["text", "formula", "image", "list"].
- bbox: [x_min, y_min, x_max, y_max] normalized between 0 and 1 and XY being bottom-left origin.
For list element return additionally:
- list-elements: List of "elements" ["text", "formula", "image"] inside the list with their respective bounding boxes.

Return ONLY valid JSON.
"""

        messages: list = [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]},
        ]

        advanced_prompt: Any = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs: Any = self.processor(images=[cell_image], text=advanced_prompt, return_tensors="pt")
        inputs = inputs.to(self.DEVICE)

        # inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        # with torch.no_grad():
        #     generated_ids: Any = self.model.generate(**inputs, max_new_tokens=512, do_sample=False)

        generated_ids: Any = self.model.generate(**inputs, max_new_tokens=500)
        generated_texts: list[str] = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
        )

        ai_output: str = generated_texts[0]  # self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        output_json: str = ai_output.split("Assistant: ")[-1].strip()
        logger.info(f"Cell AI output:\n{output_json}")

        return output_json, size

    def _convert(self, string_json: str) -> dict:
        """
        Converts AI model output that should be JSON string into dictionary

        Args:
            string_json (str): JSON string from AI model.

        Returns:
            Parsed JSON data.
        """
        try:
            data = json.loads(string_json)
            if isinstance(data, dict):
                return data
            else:
                raise ValueError("Invalid JSON format")
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format")

    def _get_elements_from_vlm(
        self,
        data: dict,
        size: list[int],
        page_number: int,
        cell_bbox: BoundingBox,
        parent_id: str,
        parent: Optional[InternalElement],
    ) -> list[InternalElement]:
        """
        From AI dictionary and docling cell data create all internal elements that are inside the cells.

        Args:
            data (dict): AI model output as dictionary.
            size (list[int]): Size of the cell image [width, height].
            page_number (int): Page number of the cell in the document.
            cell_bbox (BoundingBox): Bounding box of the cell in the document.
            parent_id (str): ID of the parent element.
            parent (InternalElement): None if cell is parent, ListGroup if parent is list.

        Returns:
            list[InternalElement]: List of internal elements inside the element (cell or list).
        """
        result: list[InternalElement] = []
        for element in data.get("elements", []):
            element_type: str = element.get("type", "text")

            # Calculate element coordinates
            bbox: list[float] = element.get("bbox", [0.0, 0.0, 1.0, 1.0])
            coords_bbox: list[float] = [
                cell_bbox.l + bbox[0] * size[0],
                cell_bbox.b + bbox[1] * size[1],
                cell_bbox.l + bbox[2] * size[0],
                cell_bbox.b + bbox[3] * size[1],
            ]
            element_bbox: BoundingBox = BoundingBox(
                l=coords_bbox[0],
                t=coords_bbox[3],
                r=coords_bbox[2],
                b=coords_bbox[1],
                coord_origin=CoordOrigin.BOTTOMLEFT,
            )
            provenances: list[ProvenanceItem] = [
                ProvenanceItem(page_no=page_number, bbox=element_bbox, charspan=(0, 0))
            ]

            element_id: str = f"{parent_id}_{len(result) + 1}"

            item: Optional[NodeItem] = None
            list_items: list[InternalElement] = []

            match element_type:
                case "formula":
                    item = FormulaItem(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        label=DocItemLabel.FORMULA,
                        prov=provenances,
                        orig="",
                        text=element.get("text", ""),
                        formatting=None,
                        hyperlink=None,
                    )
                case "image":
                    annotation: DescriptionAnnotation = DescriptionAnnotation(
                        kind="description",
                        text=element.get("image_description", ""),
                        provenance=self.MODEL_ID,
                    )
                    item = PictureItem(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        label=DocItemLabel.PICTURE,
                        prov=provenances,
                        captions=[],
                        references=[],
                        footnotes=[],
                        image=None,
                        annotations=[annotation],
                    )
                case "list":
                    item = ListGroup(
                        self_ref=element_id,
                        parent=RefItem(**{"$ref": parent_id}),
                        children=[],
                        content_layer=ContentLayer.BODY,
                        meta=None,
                        name="cell_group",  # TODO better name
                        label=GroupLabel.LIST,
                    )
                case "text":
                    if parent:  # isinstance(parent.item, ListGroup):
                        item = ListItem(
                            self_ref=element_id,
                            parent=RefItem(**{"$ref": parent_id}),
                            children=[],
                            content_layer=ContentLayer.BODY,
                            meta=None,
                            label=DocItemLabel.LIST_ITEM,
                            prov=provenances,
                            orig="",
                            text=element.get("text", ""),
                            formatting=None,
                            hyperlink=None,
                            enumerated=False,
                            marker="",
                        )
                    else:
                        item = TextItem(
                            self_ref=element_id,
                            parent=RefItem(**{"$ref": parent_id}),
                            children=[],
                            content_layer=ContentLayer.BODY,
                            meta=None,
                            label=DocItemLabel.TEXT,
                            prov=provenances,
                            orig="",
                            text=element.get("text", ""),
                            formatting=None,
                            hyperlink=None,
                        )

            if item is not None:
                internal_element: InternalElement = InternalElement(item=item, parent=parent)

                children: list[dict] = element.get("elements", [])
                if children:
                    list_items = self._get_elements_from_vlm(
                        {"elements": children}, size, page_number, cell_bbox, element_id, internal_element
                    )
                result.append(internal_element)
            if list_items:
                result.extend(list_items)
        return result
