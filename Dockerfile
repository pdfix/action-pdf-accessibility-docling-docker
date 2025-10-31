# Use the official Debian slim image with python 3.12 as a base (transformers from hugging face does not work with python 3.13 atm)
FROM python:3.12-slim

# Update system and Install python3 and necessary dependencies
RUN apt-get update && \
    apt-get install -y \
    python3-pip \
    python3-venv \
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


# no longer run inside container as layer gets too big
# Copy script to download models into container and run it
# COPY download_models.py /usr/docling/
# RUN venv/bin/python3 download_models.py

# Copy models data that we moved from original snapshot location
COPY model/ /usr/docling/src/model


# Set Hugging Face environment variable to avoid online fetch
ENV TRANSFORMERS_OFFLINE=1


# Add softlink for the model directory into root directory
RUN mkdir -p /data && \
    ln -s /usr/docling/src/model /model


# License
COPY THIRD_PARTY_LICENSES.md /THIRD_PARTY_LICENSES.md
LABEL license="https://pdfix.net/terms (PDFix SDK) and Apache License 2.0 (Docling layout by HuggingPanda)" 


ENTRYPOINT ["/usr/docling/venv/bin/python3", "/usr/docling/src/main.py"]
