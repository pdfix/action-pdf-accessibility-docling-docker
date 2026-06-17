from docling.utils.model_downloader import download_models

# Pre-download all models used at runtime, including VLM models for formula/image enrichment.
download_models(with_smolvlm=True)
