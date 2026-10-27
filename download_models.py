from pathlib import Path

from docling.datamodel.pipeline_options import LayoutObjectDetectionOptions, smolvlm_picture_description
from docling.datamodel.settings import settings
from docling.models.utils.hf_model_download import download_hf_model
from docling.utils.model_downloader import download_models
from huggingface_hub import snapshot_download

# Pre-download only the models used at runtime. src/ai.py sets artifacts_path, so docling never downloads anything
# and a missing model fails the conversion.
models_path: Path = settings.cache_dir.joinpath("models")

# Table structure (do_table_structure), CodeFormulaV2 (--do_formula_recognition) and RapidOCR (OCR on Linux)
download_models(
    output_dir=models_path,
    with_layout=False,
    with_tableformer=True,
    with_code_formula=True,
    with_picture_classifier=False,
    with_rapidocr=True,
)

# Layout model, without its ONNX variant (docling-layout-heron-onnx) that docling does not use by default
layout_spec = LayoutObjectDetectionOptions().model_spec
download_hf_model(
    repo_id=layout_spec.repo_id,
    revision=layout_spec.revision,
    local_dir=models_path.joinpath(layout_spec.repo_id.replace("/", "--")),
)

# SmolVLM for --do_image_description, without the onnx/ folder (2.8 GB) that transformers does not load
assert smolvlm_picture_description.repo_id is not None
snapshot_download(
    repo_id=smolvlm_picture_description.repo_id,
    local_dir=models_path.joinpath(smolvlm_picture_description.repo_cache_folder),
    ignore_patterns=["onnx/*"],
)
