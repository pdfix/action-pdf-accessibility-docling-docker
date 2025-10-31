from transformers import RTDetrForObjectDetection, RTDetrImageProcessor

layout_model_name: str = "HuggingPanda/docling-layout"
layout_cache_dir: str = "./models"

processor: RTDetrImageProcessor = RTDetrImageProcessor.from_pretrained(layout_model_name, cache_dir=layout_cache_dir)
model: RTDetrForObjectDetection = RTDetrForObjectDetection.from_pretrained(
    layout_model_name, cache_dir=layout_cache_dir
)

# now layout model data is downloaded into "./models/models--HuggingPanda--docling-layout/snapshots/<hash>/"

##### WIP ######
# # Load model directly
# from transformers import AutoModel
# table_model: str = "docling-project/docling-models"
# model = AutoModel.from_pretrained(table_model, cache_dir=layout_cache_dir)
