#!/bin/zsh
# Run every marked command block of the documentation against a deployment home.
#
#   bin/witness.sh <home> [--project NAME] [--project-path PATH] [--list] [page ...]
#
# The home must already be initialized (`<home>/kit/init`). Each block's output is kept
# under <home>/logs/witness. Exits 1 when any block does not run as its page documents.
set -u
KIT=${0:A:h:h}
[[ $# -ge 1 ]] || { print -u2 "usage: bin/witness.sh <home> [--list] [page ...]"; exit 2 }
PYTHON=${1:A}/env/bin/python
[[ -x $PYTHON ]] || { print -u2 "witness: no harness environment at ${1:A}/env. Run its init first."; exit 3 }
PYTHONPATH=$KIT/lib exec $PYTHON -m arhugula_kit.witness "$@"
