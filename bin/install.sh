#!/bin/zsh
# Install the harness at the pinned commit into a deployment home.
#
#   bin/install.sh <home> [--reinstall]
#
# Clones or fetches upstream at PIN into <home>/upstream, builds the seven wheels and two
# hashed locks into <home>/dist, runs upstream's packaging gate, and installs a non-editable
# environment at <home>/env. It writes nothing outside <home>. Configuration is `init`'s job.
#
# Each step exits with its own code and prints what failed; nothing is retried or skipped.
set -u
setopt pipefail

KIT=${0:A:h:h}
UPSTREAM_URL=https://github.com/thestoryportal/arhugula-harness.git
PYTHON_VERSION=3.12
PACKAGES=(harness-core harness-is harness-as harness-cp harness-od harness-cxa harness-runtime)

fail() { print -u2 "install: $2"; exit $1 }
step() { print "install: $1" }

[[ $# -ge 1 ]] || fail 64 "usage: bin/install.sh <home> [--reinstall]"
HOME_DIR=${1:A}
REINSTALL=${2:-}
[[ -z $REINSTALL || $REINSTALL == --reinstall ]] || fail 64 "unknown option: $REINSTALL"
PIN=$(<$KIT/PIN) || fail 65 "cannot read $KIT/PIN"
PIN=${PIN//[[:space:]]/}
[[ $PIN =~ '^[0-9a-f]{40}$' ]] || fail 65 "PIN must be a 40-character commit id (got '$PIN')"

UPSTREAM=$HOME_DIR/upstream; DIST=$HOME_DIR/dist; ENV=$HOME_DIR/env; LOGS=$HOME_DIR/logs
command -v git >/dev/null || fail 66 "git is not on PATH (brew install git)"
command -v uv >/dev/null || fail 66 "uv is not on PATH (brew install uv)"
mkdir -p $HOME_DIR $LOGS || fail 67 "cannot create $HOME_DIR"

if [[ -x $ENV/bin/harness && -f $ENV/.arhugula-pin && $(<$ENV/.arhugula-pin) == $PIN && -z $REINSTALL ]]; then
  step "environment already at $PIN; nothing to do (pass --reinstall to rebuild)"
  exit 0
fi

step "upstream at ${PIN:0:8}"
if [[ -d $UPSTREAM/.git ]]; then
  git -C $UPSTREAM fetch --quiet origin || fail 70 "git fetch failed in $UPSTREAM"
else
  git clone --quiet $UPSTREAM_URL $UPSTREAM || fail 70 "git clone of $UPSTREAM_URL failed"
fi
git -C $UPSTREAM checkout --quiet --detach $PIN || fail 71 "commit $PIN is not in $UPSTREAM_URL"
[[ $(git -C $UPSTREAM rev-parse HEAD) == $PIN ]] || fail 71 "upstream HEAD is not $PIN"
[[ -z $(git -C $UPSTREAM status --short --untracked-files=no) ]] \
  || fail 72 "$UPSTREAM has local changes to tracked files; the install builds a clean pin only"

step "build wheels"
(cd $UPSTREAM && uv build --all-packages --wheel --clear --no-create-gitignore --out-dir $DIST) \
  > $LOGS/install-build.log 2>&1 || { tail -5 $LOGS/install-build.log >&2; fail 73 "uv build failed (log: $LOGS/install-build.log)" }

step "export hashed locks"
(cd $UPSTREAM && uv export --all-packages --no-dev --locked --format requirements.txt \
    --no-emit-project --no-emit-workspace --output-file $DIST/requirements.lock.txt) \
  > $LOGS/install-export.log 2>&1 || fail 74 "uv export failed (log: $LOGS/install-export.log)"
(cd $UPSTREAM && uv export --all-packages --no-dev --locked --format requirements.txt \
    --no-emit-project --no-emit-workspace --extra embedding \
    --output-file $DIST/requirements.lock.embedding.txt) \
  >> $LOGS/install-export.log 2>&1 || fail 74 "uv export (embedding) failed (log: $LOGS/install-export.log)"

step "packaging gate"
(cd $UPSTREAM && uv run --no-project --python $PYTHON_VERSION python tools/q4_packaging_gate.py --dist $DIST --check) \
  > $LOGS/install-gate.log 2>&1 || { head -20 $LOGS/install-gate.log >&2; fail 75 "upstream's packaging gate refused the build (log: $LOGS/install-gate.log)" }
grep -q '^ready: yes' $LOGS/install-gate.log || fail 75 "packaging gate did not print 'ready: yes' (log: $LOGS/install-gate.log)"

step "environment"
# The environment is replaced whole: its scripts hard-code its own path, so it is never patched.
[[ ! -e $ENV ]] || rm -rf $ENV || fail 76 "cannot remove the previous environment at $ENV"
uv venv --quiet --python $PYTHON_VERSION --no-project $ENV > $LOGS/install-env.log 2>&1 \
  || fail 76 "uv venv failed (log: $LOGS/install-env.log)"
VIRTUAL_ENV=$ENV uv pip install --python $ENV/bin/python --require-hashes --no-deps \
    -r $DIST/requirements.lock.embedding.txt >> $LOGS/install-env.log 2>&1 \
  || { tail -5 $LOGS/install-env.log >&2; fail 77 "dependency install failed (log: $LOGS/install-env.log)" }
VIRTUAL_ENV=$ENV uv pip install --python $ENV/bin/python --no-deps --no-index --find-links $DIST \
    $PACKAGES >> $LOGS/install-env.log 2>&1 \
  || { tail -5 $LOGS/install-env.log >&2; fail 77 "harness wheel install failed (log: $LOGS/install-env.log)" }

step "verify"
$ENV/bin/python - $ENV <<'PY' || fail 78 "the installed environment does not import the harness from its own site-packages"
import pathlib, sys
import harness_runtime
env = pathlib.Path(sys.argv[1]).resolve()
here = pathlib.Path(harness_runtime.__file__).resolve()
assert env in here.parents, f"harness_runtime is imported from {here}, outside {env}"
assert pathlib.Path(sys.prefix).resolve() == env, sys.prefix
PY
for script in harness harness-inspect harness-shutdown; do
  [[ -x $ENV/bin/$script ]] || fail 78 "$ENV/bin/$script is missing"
done
print -n $PIN > $ENV/.arhugula-pin
(cd $DIST && shasum -a 256 *.whl *.txt) > $DIST/SHA256SUMS
step "installed ${PIN:0:8} at $ENV"
