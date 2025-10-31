# Autotag PDF Document Using Docling and PDFix SDK

A Dockerized solution for automated PDF tagging using Docling and PDFix SDK. Supports pdf tagging, pdfix layout template generation.

## Table of Contents

- [Autotag PDF Document Using Docling and PDFix SDK](#autotag-pdf-document-using-docling-and-pdfix-sdk)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
  - [Run a Docker Container ](#run-docker-container)
    - [Run Docker Container for Autotagging](#run-docker-container-for-autotagging)
    - [Run Docker Container for Template JSON Creation](#run-docker-container-for-template-json-creation)
  - [Exporting PDFix Configuration for Integration](#exporting-pdfix-configuration-for-integration)
  - [Model](#model)
  - [License](#license)
  - [Help \& Support](#help--support)

## Getting Started

To use this application, Docker must be installed on the system. If Docker is not installed, please follow the instructions on the [official Docker website](https://docs.docker.com/get-docker/) to install it.
First run will pull the docker image, which may take some time. Make your own image for more advanced use.

## Run a Docker Container

### Run Docker Container for Autotagging

To run the Docker container, map directories containing PDF documents to the container (using the `-v` parameter) and pass the paths to the input/output PDF documents inside the running container.
In this example local folder is maped into container and file `input.pdf` is taken as input PDF document. Output is saved into current folder as `output.pdf`.  
Threshold is bringed down from default `30%` to `10%`.  
Zoom is increased from default `200%` to `400%`.

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/pdf-accessibility-docling:latest tag --name $LICENSE_NAME --key $LICENSE_KEY -i input.pdf -o output.pdf --threshold 0.1 --zoom 4.0"
```

These arguments are for an account-based PDFix license.

```bash
--name ${LICENSE_NAME} --key ${LICENSE_KEY}
```

Contact support for more information.

### Run Docker Container for Template JSON Creation

Similar as previous but output is JSON file containing layout template for PDFix SDK.

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/pdf-accessibility-docling:latest template -i input.pdf -o output.json --threshold 0.1 --zoom 4.0"
```

## Exporting Configuration for Integration

To export the configuration JSON file, use the following command:

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/alt-text-blip-large:latest config -o config.json
```

## Model

Used model is [Docling-Layout](https://huggingface.co/HuggingPanda/docling-layout) in offline mode (whole model is inside docker image). It is configured to work with CPU.

## License

This repository uses the [Docling-Layout](https://huggingface.co/HuggingPanda/docling-layout) from HuggingPanda, which is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). See `THIRD_PARTY_LICENSES.md` for details.

The Docker image includes:

- PDFix SDK, subject to [PDFix Terms](https://pdfix.net/terms)
- Docling layout model, Apache License 2.0 (HuggingPanda)

Trial version of the PDFix SDK may apply a watermark on the page and redact random parts of the PDF including the scanned image in background. Contact us to get an evaluation or production license.

## Help & Support

To obtain a PDFix SDK license or report an issue please contact us at support@pdfix.net.
For more information visit https://pdfix.net
