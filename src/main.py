import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from autotag import AutotagUsingDoclingLayoutRecognition
from constants import CONFIG_FILE
from create_template import CreateTemplateJsonUsingDocling
from exceptions import (
    EC_ARG_GENERAL,
    MESSAGE_ARG_GENERAL,
    ArgumentInputPdfOutputJsonException,
    ArgumentInputPdfOutputPdfException,
    ArgumentZoomException,
    ExpectedException,
)
from image_update import DockerImageContainerUpdateChecker
from logger import get_logger

logger = get_logger()


def set_arguments(
    parser: argparse.ArgumentParser,
    names: list,
    required_output: bool = True,
    output_help: str = "",
) -> None:
    """
    Set arguments for the parser based on the provided names and options.

    Args:
        parser (argparse.ArgumentParser): The argument parser to set arguments for.
        names (list): List of argument names to set.
        required_output (bool): Whether the output argument is required. Defaults to True.
        output_help (str): Help shown for --output argument. Defaults to "".
    """
    for name in names:
        match name:
            case "input":
                parser.add_argument("--input", "-i", type=str, required=True, help="The input PDF file.")
            case "key":
                parser.add_argument("--key", type=str, default="", nargs="?", help="PDFix license key.")
            case "threshold":
                parser.add_argument(
                    "--threshold", type=float, default=0.3, help="Sets value under which results from AI are ignored."
                )
            case "name":
                parser.add_argument("--name", type=str, default="", nargs="?", help="PDFix license name.")
            case "output":
                parser.add_argument("--output", "-o", type=str, required=required_output, help=output_help)
            case "zoom":
                parser.add_argument(
                    "--zoom", type=float, default=2.0, help="Zoom level for the PDF page rendering (default: 2.0)."
                )


def run_config_subcommand(args) -> None:
    get_pdfix_config(args.output)


def get_pdfix_config(path: str) -> None:
    """
    If Path is not provided, output content of config.
    If Path is provided, copy config to destination path.

    Args:
        path (string): Destination path for config.json file
    """
    config_path = os.path.join(Path(__file__).parent.absolute(), f"../{CONFIG_FILE}")

    with open(config_path, "r", encoding="utf-8") as file:
        if path is None:
            print(file.read())
        else:
            with open(path, "w") as out:
                out.write(file.read())


def run_autotag_subcommand(args) -> None:
    autotagging_pdf(args.name, args.key, args.input, args.output, args.zoom, args.threshold)


def autotagging_pdf(
    license_name: Optional[str],
    license_key: Optional[str],
    input_path: str,
    output_path: str,
    zoom: float,
    threshold: float,
) -> None:
    """
    Autotagging PDF document with provided arguments

    Args:
        license_name (Optional[str]): Name used in authorization in PDFix-SDK.
        license_key (Optional[str]): Key used in authorization in PDFix-SDK.
        input_path (str): Path to PDF document.
        output_path (str): Path to PDF document.
        zoom (float): Zoom level for rendering the page.
        threshold (float): Threshold under which results from AI are ignored.
    """
    if zoom < 1.0 or zoom > 10.0:
        raise ArgumentZoomException()

    if input_path.lower().endswith(".pdf") and output_path.lower().endswith(".pdf"):
        autotag = AutotagUsingDoclingLayoutRecognition(
            license_name, license_key, input_path, output_path, zoom, threshold
        )
        autotag.process_file()
    else:
        raise ArgumentInputPdfOutputPdfException()


def run_template_subcommand(args) -> None:
    create_template_json(args.name, args.key, args.input, args.output, args.zoom, args.threshold)


def create_template_json(
    license_name: Optional[str],
    license_key: Optional[str],
    input_path: str,
    output_path: str,
    zoom: float,
    threshold: float,
) -> None:
    """
    Creating template json for PDF document using provided arguments

    Args:
        license_name (Optional[str]): Name used in authorization in PDFix-SDK.
        license_key (Optional[str]): Key used in authorization in PDFix-SDK.
        input_path (str): Path to PDF document.
        output_path (str): Path to JSON file.
        zoom (float): Zoom level for rendering the page.
        threshold (float): Threshold under which results from AI are ignored.
    """
    if zoom < 1.0 or zoom > 10.0:
        raise ArgumentZoomException()

    if input_path.lower().endswith(".pdf") and output_path.lower().endswith(".json"):
        template_creator = CreateTemplateJsonUsingDocling(
            license_name, license_key, input_path, output_path, zoom, threshold
        )
        template_creator.process_file()
    else:
        raise ArgumentInputPdfOutputJsonException()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autotag PDF file using layout recognition",
    )

    subparsers = parser.add_subparsers(title="Commands", dest="command", required=True)

    # Config subparser
    config_subparser = subparsers.add_parser(
        "config",
        help="Extract config file for integration",
    )
    set_arguments(
        config_subparser,
        ["output"],
        False,
        "Output to save the config JSON file. Application output is used if not provided.",
    )
    config_subparser.set_defaults(func=run_config_subcommand)

    # Autotag subparser
    autotag_subparser = subparsers.add_parser(
        "tag",
        help="Run autotag PDF document",
    )
    set_arguments(
        autotag_subparser,
        ["name", "key", "input", "output", "zoom", "threshold"],
        True,
        "The output PDF file.",
    )
    autotag_subparser.set_defaults(func=run_autotag_subcommand)

    # Template subparser
    template_subparser = subparsers.add_parser(
        "template",
        help="Create layout template JSON.",
    )
    set_arguments(
        template_subparser,
        ["name", "key", "input", "output", "zoom", "threshold"],
        True,
        "The output JSON file.",
    )
    template_subparser.set_defaults(func=run_template_subcommand)

    # Parse arguments
    try:
        args = parser.parse_args()
    except ExpectedException as e:
        logger.exception(e.message)
        sys.exit(e.error_code)
    except SystemExit as e:
        if e.code != 0:
            logger.exception(MESSAGE_ARG_GENERAL)
            sys.exit(EC_ARG_GENERAL)
        # This happens when --help is used, exit gracefully
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Failed to run the program: {e}")
        sys.exit(1)

    if hasattr(args, "func"):
        # Check for updates only when help is not checked
        update_checker = DockerImageContainerUpdateChecker()
        # Check it in separate thread not to be delayed when there is slow or no internet connection
        update_thread = threading.Thread(target=update_checker.check_for_image_updates)
        update_thread.start()

        # Run subcommand
        try:
            args.func(args)
        except ExpectedException as e:
            logger.exception(e.message)
            sys.exit(e.error_code)
        except Exception as e:
            logger.exception(f"Failed to run the program: {e}")
            sys.exit(1)
        finally:
            # Make sure to let update thread finish before exiting
            update_thread.join()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
