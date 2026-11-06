#!/usr/bin/env python3
"""Command-line tool for managing a small store's product inventory.

Products are stored in a local JSON file (default: products.json in the
current working directory). Each invocation performs one operation and exits.

Exit codes:
    0  success (including an empty list or a help request)
    1  product ID not found, invalid stored data, or a file read/write failure
    2  invalid command syntax, missing arguments, or invalid input values
"""

import argparse
import json
import os
import re
import sys
import tempfile

DEFAULT_FILE = "products.json"

EXIT_OK = 0
EXIT_DATA_ERROR = 1
# Exit code 2 (invalid usage or input) is produced by argparse itself.

# [0-9] instead of \d so non-ASCII digits (e.g. Arabic-Indic) are rejected.
PRICE_INPUT_RE = re.compile(r"[0-9]+(\.[0-9]{1,2})?")
STORED_PRICE_RE = re.compile(r"(0|[1-9][0-9]*)\.[0-9]{2}")
NONNEG_INT_RE = re.compile(r"[0-9]+")

PRODUCT_KEYS = {"id", "name", "price", "quantity"}
STORE_KEYS = {"next_id", "products"}


# One exception type for expected failures (missing ID, bad data file, file I/O errors).
# It carries exit code 1. main() catches it and prints one clean line to stderr,
# so no Python traceback appears. Exit code 2 comes from argparse instead.
class CLIError(Exception):
    """An expected failure: reported on stderr with an exit code, no traceback."""

    def __init__(self, message, exit_code):
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Input validation (used as argparse "type" functions, so invalid values are
# rejected with exit code 2 before any file is read or written)
# ---------------------------------------------------------------------------

def parse_name(text):
    name = text.strip()
    if not name:
        raise argparse.ArgumentTypeError(
            "name must contain at least one non-whitespace character")
    return name


def parse_price(text):
    if not PRICE_INPUT_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"invalid price {text!r}: use digits with an optional decimal point "
            "and one or two decimal places (e.g. 4, 4.5, 4.50)")
    whole, _, fraction = text.partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = (fraction + "00")[:2]
    return f"{whole}.{fraction}"


def parse_nonneg_int(text, label):
    if not NONNEG_INT_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"invalid {label} {text!r}: must be a nonnegative whole number")
    return int(text)


def parse_quantity(text):
    return parse_nonneg_int(text, "quantity")


def parse_threshold(text):
    return parse_nonneg_int(text, "threshold")


def parse_id(text):
    if not NONNEG_INT_RE.fullmatch(text) or int(text) == 0:
        raise argparse.ArgumentTypeError(
            f"invalid ID {text!r}: must be a positive whole number")
    return int(text)


def parse_path(text):
    if not text:
        raise argparse.ArgumentTypeError("file path must not be empty")
    return text


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def empty_store():
    return {"next_id": 1, "products": []}


def is_int(value):
    # bool is a subclass of int in Python; JSON true/false must not count.
    return isinstance(value, int) and not isinstance(value, bool)


def validate_store(data):
    """Return an error message if data is not a valid store, else None."""
    if not isinstance(data, dict):
        return "top-level value must be an object"
    if set(data) != STORE_KEYS:
        return "top-level object must have exactly the keys 'next_id' and 'products'"
    next_id = data["next_id"]
    if not is_int(next_id) or next_id < 1:
        return "'next_id' must be a positive integer"
    products = data["products"]
    if not isinstance(products, list):
        return "'products' must be an array"

    seen_ids = set()
    for index, product in enumerate(products):
        where = f"product at position {index}"
        if not isinstance(product, dict):
            return f"{where} must be an object"
        if set(product) != PRODUCT_KEYS:
            return f"{where} must have exactly the keys id, name, price, quantity"
        pid = product["id"]
        if not is_int(pid) or pid < 1:
            return f"{where} has an invalid id"
        if pid in seen_ids:
            return f"duplicate product id {pid}"
        seen_ids.add(pid)
        if pid >= next_id:
            return f"'next_id' ({next_id}) must be greater than product id {pid}"
        name = product["name"]
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            return f"product {pid} has an invalid name"
        price = product["price"]
        if not isinstance(price, str) or not STORED_PRICE_RE.fullmatch(price):
            return f"product {pid} has an invalid price"
        quantity = product["quantity"]
        if not is_int(quantity) or quantity < 0:
            return f"product {pid} has an invalid quantity"
    return None


def load_store(path):
    """Read the store. A missing file is an empty store; anything else bad is an error."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return empty_store()
    except OSError as exc:
        raise CLIError(f"cannot read data file {path!r}: {exc.strerror or exc}",
                       EXIT_DATA_ERROR)

    invalid = f"data file {path!r} is not a valid product store"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CLIError(f"{invalid}: not valid UTF-8", EXIT_DATA_ERROR)
    if not text.strip():
        raise CLIError(f"{invalid}: file is empty", EXIT_DATA_ERROR)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CLIError(f"{invalid}: malformed JSON ({exc})", EXIT_DATA_ERROR)

    problem = validate_store(data)
    if problem:
        raise CLIError(f"{invalid}: {problem}", EXIT_DATA_ERROR)
    return data


def save_store(path, store):
    """Write the store atomically: write a temp file, then replace the original.

    If anything fails, the original file is left untouched. Missing parent
    directories are not created.
    """
    directory = os.path.dirname(os.path.abspath(path))
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".products-", suffix=".tmp",
                                         dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise CLIError(f"cannot write data file {path!r}: {exc.strerror or exc}",
                       EXIT_DATA_ERROR)
    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def find_product(store, product_id):
    for index, product in enumerate(store["products"]):
        if product["id"] == product_id:
            return index, product
    raise CLIError(f"product with ID {product_id} not found", EXIT_DATA_ERROR)


def sorted_by_id(products):
    return sorted(products, key=lambda product: product["id"])


# ---------------------------------------------------------------------------
# Commands: each returns the JSON-serialisable result to print on success
# ---------------------------------------------------------------------------

def cmd_add(args):
    store = load_store(args.file)
    product = {
        "id": store["next_id"],
        "name": args.name,
        "price": args.price,
        "quantity": args.quantity,
    }
    store["products"].append(product)
    store["next_id"] += 1
    save_store(args.file, store)
    return product


def cmd_list(args):
    store = load_store(args.file)
    return sorted_by_id(store["products"])


def cmd_get(args):
    store = load_store(args.file)
    _, product = find_product(store, args.id)
    return product


def cmd_update(args):
    store = load_store(args.file)
    index, product = find_product(store, args.id)
    updated = dict(product)
    if args.name is not None:
        updated["name"] = args.name
    if args.price is not None:
        updated["price"] = args.price
    if args.quantity is not None:
        updated["quantity"] = args.quantity
    store["products"][index] = updated
    save_store(args.file, store)
    return updated


def cmd_delete(args):
    store = load_store(args.file)
    index, _ = find_product(store, args.id)
    del store["products"][index]
    save_store(args.file, store)
    return {"deleted_id": args.id}


def cmd_low_stock(args):
    """Custom feature: products whose quantity is at or below a threshold.

    Sorted by quantity (most urgent first), then by ID, so the items that
    most need reordering appear at the top.
    """
    store = load_store(args.file)
    low = [p for p in store["products"] if p["quantity"] <= args.threshold]
    return sorted(low, key=lambda product: (product["quantity"], product["id"]))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="products.py",
        description="Manage a small store's product inventory stored in a JSON file.",
        epilog="Exit codes: 0 success, 1 not found / data or file error, "
               "2 invalid usage or input.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--file", metavar="PATH", type=parse_path, default=DEFAULT_FILE,
        help=f"JSON data file to use (default: {DEFAULT_FILE} in the current "
             "directory). Must appear before the command.")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND",
                                     title="commands")
    commands.required = True

    def add_command(name, help_text, func):
        sub = commands.add_parser(name, help=help_text, description=help_text,
                                  allow_abbrev=False)
        sub.set_defaults(func=func)
        return sub

    add = add_command("add", "Create a product and print it as JSON.", cmd_add)
    add.add_argument("--name", required=True, type=parse_name,
                     help="product name (leading/trailing whitespace is trimmed)")
    add.add_argument("--price", required=True, type=parse_price,
                     help="nonnegative price with up to two decimal places, e.g. 4.50")
    add.add_argument("--quantity", required=True, type=parse_quantity, metavar="QTY",
                     help="nonnegative whole-number quantity")

    add_command("list", "Print all products as a JSON array sorted by ID.", cmd_list)

    get = add_command("get", "Print the product with the given ID.", cmd_get)
    get.add_argument("id", metavar="ID", type=parse_id, help="product ID")

    update = add_command(
        "update",
        "Change one or more fields of a product and print the updated product.",
        cmd_update)
    update.add_argument("id", metavar="ID", type=parse_id, help="product ID")
    update.add_argument("--name", type=parse_name, help="new product name")
    update.add_argument("--price", type=parse_price, help="new price, e.g. 4.50")
    update.add_argument("--quantity", type=parse_quantity, metavar="QTY",
                        help="new quantity")

    delete = add_command("delete", "Delete the product with the given ID.", cmd_delete)
    delete.add_argument("id", metavar="ID", type=parse_id, help="product ID")
    delete.add_argument("--yes", action="store_true", required=True,
                        help="confirm the deletion (required)")

    low = add_command(
        "low-stock",
        "Report products whose quantity is at or below a threshold, "
        "lowest quantity first.",
        cmd_low_stock)
    low.add_argument("--threshold", required=True, type=parse_threshold,
                     metavar="QTY",
                     help="nonnegative whole number; products with quantity <= QTY "
                          "are reported")

    return parser, update


def main(argv=None):
    parser, update_parser = build_parser()
    args = parser.parse_args(argv)  # exits with code 2 on syntax errors

    if args.command == "update" and all(
            value is None for value in (args.name, args.price, args.quantity)):
        update_parser.error(
            "at least one of --name, --price, or --quantity is required")

    try:
        result = args.func(args)
    except CLIError as exc:
        print(f"products.py: error: {exc}", file=sys.stderr)
        return exc.exit_code

    print(json.dumps(result, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
