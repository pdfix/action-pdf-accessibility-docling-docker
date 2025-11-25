from docling.document_converter import DocumentConverter

converter: DocumentConverter = DocumentConverter()
# This downloads necessary AI models
converter.convert("example/AutoTag_Sample.pdf")
