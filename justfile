# Development recipes for the kit itself. An operator never needs these: `init` and
# `arhugula` are the whole operator surface. Each recipe needs only uv.

python := "uv run --quiet --no-project --python 3.12 -- python"

# List the recipes.
default:
    @just --list

# Run the kit's own unit tests (Python standard library only; no deployment needed).
test:
    PYTHONPATH=lib {{python}} -m unittest discover -s tests -v

# Rewrite the generated parts of the documentation from the program's own tables.
docs-reference:
    PYTHONPATH=lib {{python}} -m arhugula_kit.docgen

# Rewrite the Grafana dashboards, alert rules and panel index from tools/dashboards.py.
dashboards:
    {{python}} tools/dashboards.py write

# Check the documentation: generated parts current, no machine path, plain-language audit.
docs-check:
    PYTHONPATH=lib {{python}} -m arhugula_kit.docgen --check
    {{python}} tools/dashboards.py check
    bin/docs-check.sh

# Run every marked command block of the documentation against a deployment home.
witness home:
    bin/witness.sh {{home}}
