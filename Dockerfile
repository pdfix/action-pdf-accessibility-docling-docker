# Use the official Debian slim image with python 3.12 as a base (transformers from hugging face does not work with python 3.13 atm)
FROM python:3.12-slim

# Update system and Install python3 and necessary dependencies
RUN apt-get update && \
    apt-get install -y \
    python3-pip \
    python3-venv \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/docling/


# Create a virtual environment and install dependencies
ENV VIRTUAL_ENV=venv
RUN python3 -m venv venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY requirements.txt /usr/docling/
RUN pip install --no-cache-dir -r requirements.txt && rm -rf /root/.cache/pip


# Copy config.json and the source code
COPY config.json /usr/docling/
COPY src/ /usr/docling/src/


# # no longer run inside container as layer gets too big
# # Copy script to download models into container and run it
COPY download_models.py /usr/docling/
COPY example example
RUN venv/bin/python3 download_models.py
RUN rm -rf example

# Copy models data that we moved from original snapshot location
# COPY rapidocr_models/ /usr/docling/venv/lib/python3.12/site-packages/rapidocr/models/
# COPY .cache/hub/models--docling-project--CodeFormulaV2 
# COPY .cache/hub/models--docling-project--docling-layout-heron
# COPY .cache/hub/models--docling-project--docling-models
# COPY .cache/hub/models--HuggingFaceTB--SmolVLM-256M-Instruct
# COPY .cache/hub/models--ibm-granite--granite-vision-3.1-2b-preview
# COPY .cache/hub/models--ibm-granite--granite-vision-3.2-2b
# COPY .cache/hub/models--ibm-granite--granite-vision-3.3-2b

# Add data folder into image
RUN mkdir -p /data


# # License
# COPY THIRD_PARTY_LICENSES.md /THIRD_PARTY_LICENSES.md
# LABEL license="https://pdfix.net/terms (PDFix SDK) and Apache License 2.0 (Docling layout by HuggingPanda)" 


ENTRYPOINT ["/usr/docling/venv/bin/python3", "/usr/docling/src/main.py"]
