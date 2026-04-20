import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from autotag import AutotagUsingDoclingLayoutRecognition
from constants import CONFIG_FILE
from create_template import CreateTemplateJsonUsingDocling
from exceptions import (
    EC_ARG_GENERAL,
    MESSAGE_ARG_GENERAL,
    ArgumentInputPdfOutputJsonException,
    ArgumentInputPdfOutputPdfException,
    ExpectedException,
)
from image_update import DockerImageContainerUpdateChecker
from logger import get_logger

logger = get_logger()


def str2bool(value: Any) -> bool:
    """
    Helper function to convert argument to boolean.

    Args:
        value (Any): The value to convert to boolean.

    Returns:
        Parsed argument as boolean.
    """
    if isinstance(value, bool):
        return value
    if value.lower() in ("yes", "true", "t", "1"):
        return True
    elif value.lower() in ("no", "false", "f", "0"):
        return False
    else:
        raise ValueError("Boolean value expected.")


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
            case "do_formula_recognition":
                parser.add_argument(
                    "--do_formula_recognition",
                    type=str2bool,
                    default=False,
                    help="Provides MathML reprezentation of Formula tag.",
                )
            case "do_image_description":
                parser.add_argument(
                    "--do_image_description", type=str2bool, default=False, help="Provides alt text for Figure tag."
                )
            case "input":
                parser.add_argument("--input", "-i", type=str, required=True, help="The input PDF file.")
            case "key":
                parser.add_argument("--key", type=str, default="", nargs="?", help="PDFix license key.")
            case "name":
                parser.add_argument("--name", type=str, default="", nargs="?", help="PDFix license name.")
            case "output":
                parser.add_argument("--output", "-o", type=str, required=required_output, help=output_help)
            case "per_page":
                parser.add_argument("--per_page", type=str2bool, default=False, help="Process PDF page by page.")


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
    autotagging_pdf(
        args.name,
        args.key,
        args.input,
        args.output,
        args.do_formula_recognition,
        args.do_image_description,
        args.per_page,
    )


def autotagging_pdf(
    license_name: Optional[str],
    license_key: Optional[str],
    input_path: str,
    output_path: str,
    do_formula_recognition: bool,
    do_image_description: bool,
    per_page: bool,
) -> None:
    """
    Autotagging PDF document with provided arguments

    Args:
        license_name (Optional[str]): Name used in authorization in PDFix-SDK.
        license_key (Optional[str]): Key used in authorization in PDFix-SDK.
        input_path (str): Path to PDF document.
        output_path (str): Path to PDF document.
        do_formula_recognition (bool): Do also formula recognition.
        do_image_description (bool): Do also image desrciption.
    """
    if input_path.lower().endswith(".pdf") and output_path.lower().endswith(".pdf"):
        autotag = AutotagUsingDoclingLayoutRecognition(
            license_name, license_key, input_path, output_path, do_formula_recognition, do_image_description, per_page
        )
        autotag.process_file()
    else:
        raise ArgumentInputPdfOutputPdfException()


def run_template_subcommand(args) -> None:
    create_template_json(
        args.name,
        args.key,
        args.input,
        args.output,
        args.do_formula_recognition,
        args.do_image_description,
        args.per_page,
    )


def create_template_json(
    license_name: Optional[str],
    license_key: Optional[str],
    input_path: str,
    output_path: str,
    do_formula_recognition: bool,
    do_image_description: bool,
    per_page: bool,
) -> None:
    """
    Creating template json for PDF document using provided arguments

    Args:
        license_name (Optional[str]): Name used in authorization in PDFix-SDK.
        license_key (Optional[str]): Key used in authorization in PDFix-SDK.
        input_path (str): Path to PDF document.
        output_path (str): Path to JSON file.
        do_formula_recognition (bool): Do also formula recognition.
        do_image_description (bool): Do also image desrciption.
    """
    if input_path.lower().endswith(".pdf") and output_path.lower().endswith(".json"):
        template_creator = CreateTemplateJsonUsingDocling(
            license_name, license_key, input_path, output_path, do_formula_recognition, do_image_description, per_page
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
        ["name", "key", "input", "output", "do_formula_recognition", "do_image_description", "per_page"],
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
        ["name", "key", "input", "output", "do_formula_recognition", "do_image_description", "per_page"],
        True,
        "The output JSON file.",
    )
    template_subparser.set_defaults(func=run_template_subcommand)

    # Parse arguments
    try:
        args = parser.parse_args()
    except ExpectedException as e:
        logger.error(e.message)
        sys.exit(e.error_code)
    except SystemExit as e:
        if e.code != 0:
            logger.error(MESSAGE_ARG_GENERAL)
            sys.exit(EC_ARG_GENERAL)
        # This happens when --help is used, exit gracefully
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to run the program:")
        logger.exception(e)
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
            logger.error(e.message)
            sys.exit(e.error_code)
        except Exception as e:
            logger.error("Failed to run the program:")
            logger.exception(e)
            sys.exit(1)
        finally:
            # Make sure to let update thread finish before exiting
            update_thread.join()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
