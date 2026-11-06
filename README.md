# Product Inventory CLI

A Python 3 command-line tool for a small store's product inventory. It creates, reads, updates, and deletes product records saved in a local JSON file. It uses only the Python standard library, so there is nothing to install.

## Requirements

- Python 3.8 or newer (tested with Python 3.13)

## Usage

```
python3 products.py [--file PATH] COMMAND [OPTIONS]
```

On Windows, use `py -3` in place of `python3`. `--file PATH` must come before the command. It picks the JSON data file. The default is `products.json` in the current directory.

| Command | What it does |
|---|---|
| `add --name NAME --price PRICE --quantity QTY` | Create a product and print it as JSON |
| `list` | Print all products as a JSON array, sorted by ID |
| `get ID` | Print one product |
| `update ID [--name NAME] [--price PRICE] [--quantity QTY]` | Change the given fields (at least one) and print the result |
| `delete ID --yes` | Delete a product and print `{"deleted_id": ID}` |
| `low-stock --threshold QTY` | **Custom feature.** List products with quantity at or below `QTY` |

Run `python3 products.py --help` or `python3 products.py COMMAND --help` for details.

### Field rules

- **name**: must contain at least one non-whitespace character. Leading and trailing spaces are trimmed. Duplicate names are allowed.
- **price**: digits, optionally followed by a decimal point and one or two digits (`0`, `4.5`, `4.50`). Signs, currency symbols, exponents, and extra decimal places are rejected. The price is stored as a string with two decimal places, such as `"4.50"`.
- **quantity**: a whole number, zero or more.
- **id**: assigned automatically, starting at 1. A deleted ID is never reused.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, including an empty list or a help request |
| 1 | Product not found, invalid stored data, or a file read/write failure |
| 2 | Invalid command syntax, missing arguments, or invalid input values |

Errors go to standard error. A failed command never changes the data file.

## Custom feature: low-stock report

### Who it helps and why

A small store owner or employee who places reorders. With many products, scrolling through `list` to find what is running out is slow, and an item can be missed. `low-stock` answers one question directly: *which products need restocking?* It returns only the products at or below a quantity you choose, with the most urgent items first, so the result works as a reorder checklist.

### Syntax

```
python3 products.py [--file PATH] low-stock --threshold QTY
```

### Inputs

- `--threshold QTY` (required): a nonnegative whole number. A product is reported if its `quantity <= QTY`. Use `--threshold 0` to find items that are completely out of stock.
- `--file PATH` (optional): the data file to check, the same as for the other commands.

### Logic

1. Load the products from the data file. A missing file counts as an empty store.
2. Keep each product whose `quantity` is less than or equal to the threshold.
3. Sort by quantity, lowest first. Products with equal quantity are sorted by ID.

The command only reads the data file. It never creates or changes it.

### Output

A JSON array of matching product objects. It prints `[]` when no products match. An invalid threshold, such as `-1`, `2.5`, or `abc`, prints an error to standard error and exits with code 2.

### Example

```
python3 products.py --file shop.json add --name "Notebook" --price 4.50 --quantity 10
python3 products.py --file shop.json add --name "Pencil" --price 1.25 --quantity 5
python3 products.py --file shop.json add --name "Eraser" --price 0.75 --quantity 0
python3 products.py --file shop.json low-stock --threshold 5
```

Output:

```json
[
  {
    "id": 3,
    "name": "Eraser",
    "price": "0.75",
    "quantity": 0
  },
  {
    "id": 2,
    "name": "Pencil",
    "price": "1.25",
    "quantity": 5
  }
]
```

Edge cases:

```
python3 products.py --file shop.json low-stock --threshold 0    # only Eraser
python3 products.py --file empty.json low-stock --threshold 5   # [] (no products)
python3 products.py --file shop.json low-stock --threshold -1   # error, exit code 2
```

## Data file format

```json
{
  "next_id": 2,
  "products": [
    {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10}
  ]
}
```

The file is UTF-8 JSON. If it is empty, malformed, or does not match this shape, the tool reports an error (exit code 1) and leaves the file unchanged. To save, the tool writes a temporary file in the same folder and then replaces the original with it, so an interrupted write cannot corrupt existing data.

## License

Released under the MIT License. See [LICENSE](LICENSE).
