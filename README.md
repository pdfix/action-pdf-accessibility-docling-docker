# PDF Accessibility Docling

Uses Docling-Layout for layout recognition, running fully offline. For PDF output without watermarks, a **PDFix SDK** license is required.

## Table of Contents

- [PDF Accessibility Docling](#pdf-accessibility-docling)
  - [Getting started](#getting-started)
  - [Usage](#usage)
  - [Commands](#commands)
  - [Arguments](#arguments)
  - [Examples](#examples)
  - [Model](#model)
  - [Help \& support](#help--support)
  - [Licenses](#licenses)

## Getting started

You need Docker installed. The first run downloads the image and may take longer than later runs.

## Usage

Mount a folder into the container and run a subcommand:

```bash
docker run --rm -v "$(pwd)":/data -w /data pdfix/pdf-accessibility-docling:latest <command> [options]
```

## Commands

- `tag`: Autotag a PDF (PDF → PDF)
- `template`: Create a PDFix layout template JSON (PDF → JSON)

## Arguments

### Common (`tag` and `template`)

| Option | Required | Type / expected value | Description |
|---|:---:|---|---|
| `--input`, `-i` | yes | Path to an existing `.pdf` file | Input PDF |
| `--output`, `-o` | yes | Path for `.pdf` (`tag`) or `.json` (`template`) | Output file |
| `--name` | no | String (PDFix account license name) | PDFix license name |
| `--key` | no | String (PDFix account license key) | PDFix license key |
| `--do_image_description` | no | Boolean string: `true`/`false`, `yes`/`no`, `1`/`0` (default: `false`) | Alt text for Figure tags |
| `--do_formula_recognition` | no | Boolean string (default: `false`) | Formula recognition |
| `--per_page` | no | Boolean string (default: `false`) | Process page by page |
| `--bbox_overlap` | no | Float (default **0.6**) | Docling bbox overlap threshold |

## Examples

Tag a PDF:

```bash
docker run --rm -v "$(pwd)":/data -w /data pdfix/pdf-accessibility-docling:latest \
  tag --name "${LICENSE_NAME}" --key "${LICENSE_KEY}" \
  -i /data/input.pdf -o /data/output.pdf \
  --do_image_description true --do_formula_recognition true --per_page true
```

Create a layout template JSON:

```bash
docker run --rm -v "$(pwd)":/data -w /data pdfix/pdf-accessibility-docling:latest \
  template --name "${LICENSE_NAME}" --key "${LICENSE_KEY}" \
  -i /data/input.pdf -o /data/output.json
```

## Model

The image includes the Docling-Layout model and runs fully offline (CPU).

## Help & support

For PDFix SDK licensing or issues, contact `support@pdfix.net`.

## Licenses

- [PDFix Terms](https://pdfix.net/terms)
- [Docling](https://docling-project.github.io/docling/) — [MIT License](https://github.com/docling-project/docling/blob/main/LICENSE)
