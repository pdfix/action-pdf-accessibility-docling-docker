from typing import Any, Optional

from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument, NodeItem
from hierarchical.postprocessor import ResultPostprocessor

from internal_classes import InternalElement


class ApplyDoclingReadingOrder:
    def __init__(self, result: ConversionResult) -> None:
        self.result: ConversionResult = result
        self.reading_order: list[str] = []

    def apply(self, page_result: dict) -> None:

        docling_reading_order: DoclingReadingOrder = DoclingReadingOrder(self.result)
        self.reading_order = docling_reading_order.get_reading_order()

        # Add global reading order index to each element:
        self._apply_global_reading_order(page_result)

        # Sort elements by it
        self._sort_elements(page_result)

        # Transform to local reading order
        self._transform_to_local_reading_order(page_result)

    def _get_global_index(self, id: str) -> int:
        return self.reading_order.index(id)

    def _apply_global_reading_order(self, node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                self.walk(value)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict) and "name" in item:
                    # Add global reading order index
                    item["rd_index"] = self._get_global_index(item["name"])
                self.walk(item)

    def _sort_elements(self, node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                self._sort_elements(value)
        elif isinstance(node, list):
            should_sort: bool = False
            for item in node:
                if isinstance(item, dict) and "name" in item:
                    should_sort = True
                self._sort_elements(item)
            # Sort elements by global reading order index
            if should_sort:
                node.sort(key=lambda x: x["rd_index"])

    def _transform_to_local_reading_order(self, node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                self._transform_to_local_reading_order(value)
        elif isinstance(node, list):
            for item, index in enumerate(node):
                if isinstance(item, dict) and "name" in item:
                    # Now rewrite global to local index
                    item["rd_index"] = index
                self._transform_to_local_reading_order(item)


class DoclingReadingOrder:
    def __init__(self, result: ConversionResult) -> None:
        self.result: ConversionResult = result

    def get_reading_order(self) -> list[str]:
        result: list[str] = []

        # Docling post-process
        ResultPostprocessor(self.result).process()

        # Get document
        document: DoclingDocument = self.result.document

        # Flat the result
        for reference in document.body.children:
            # Get the item for the reference
            item: Optional[NodeItem] = self._get_item(document, reference.cref)
            if item is None:
                continue

            result.append(self._get_id(item))
            children_order: list[str] = self._get_children_order(item)
            if len(children_order) > 0:
                result.extend(children_order)

        # Return flatten reading order
        return result

    def _get_id(self, item: NodeItem) -> str:
        internal: InternalElement = InternalElement(item=item, parent=None)
        return internal.id()

    def _get_children_order(self, item: NodeItem) -> list[str]:
        result: list[str] = []

        # Get children
        children: list[NodeItem] = item.children

        # Get children order
        for child in children:
            result.append(self._get_id(child))
            children_order: list[str] = self._get_children_order(item)
            if len(children_order) > 0:
                result.extend(children_order)

        return result
