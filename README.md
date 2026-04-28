# Autotag PDF Document Using Docling and PDFix SDK

A Dockerized solution for automated PDF tagging using Docling and PDFix SDK. Supports pdf tagging, pdfix layout template generation.

## Table of Contents

- [Autotag PDF Document Using Docling and PDFix SDK](#autotag-pdf-document-using-docling-and-pdfix-sdk)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
  - [Run a Docker Container ](#run-docker-container)
    - [Run Docker Container for Autotagging](#run-docker-container-for-autotagging)
    - [Run Docker Container for Layout Template JSON Creation](#run-docker-container-for-template-json-creation)
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

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/pdf-accessibility-docling:latest tag --name $LICENSE_NAME --key $LICENSE_KEY -i input.pdf -o output.pdf --do_image_description true --do_formula_recognition true --per_page true
```

These arguments are optional:

- `--do_image_description` (default: false)  
  Enables a VLM (Vision-Language Model) to generate descriptions for raster images.

- `--do_formula_recognition` (default: false)  
  Enables an AI model that converts formulas into their LaTeX representation.

- `--per_page` (default: false)  
  Processes the PDF page by page instead of sending the entire document to Docling at once.  
  Each page is rendered and processed individually, providing visual feedback on progress.  
  Note: This mode increases processing time, as Docling initialization is repeated for each page.

These arguments are for an account-based PDFix license.

```bash
--name ${LICENSE_NAME} --key ${LICENSE_KEY}
```

Contact support for more information.

### Run Docker Container for Layout Template JSON Creation

Similar as previous but output is JSON file containing layout template for PDFix SDK.

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/pdf-accessibility-docling:latest template --name $LICENSE_NAME --key $LICENSE_KEY -i input.pdf -o output.json --do_image_description true --do_formula_recognition true --per_page true
```

## Exporting Configuration for Integration

To export the configuration JSON file, use the following command:

```bash
docker run -v $(pwd):/data -w /data --rm pdfix/pdf-accessibility-docling:latest config -o config.json
```

## Model

Used model is [Docling-Layout](https://huggingface.co/HuggingPanda/docling-layout) in offline mode (whole model is inside docker image). It is configured to work with CPU.

## License

This repository uses the [Docling](https://docling-project.github.io/docling/), which is licensed under the [MIT License](https://github.com/docling-project/docling/blob/main/LICENSE). See `THIRD_PARTY_LICENSES.md` for details.

The Docker image includes:

- PDFix SDK, subject to [PDFix Terms](https://pdfix.net/terms)
- Docling, MIT License

Trial version of the PDFix SDK may apply a watermark on the page and redact random parts of the PDF including the scanned image in background. Contact us to get an evaluation or production license.

## Help & Support

To obtain a PDFix SDK license or report an issue please contact us at support@pdfix.net.
For more information visit https://pdfix.net
