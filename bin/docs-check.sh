#!/bin/zsh
# Check the documentation pages. Exits non-zero on any finding.
#
#   bin/docs-check.sh [page ...]      default: README.md, CHANGELOG.md, docs/
#
# Two checks:
#   1. No page names an absolute path of anyone's machine.
#   2. The plain-language audit (the `iso-24495-text-audit` skill) reports no finding.
#
# The audit is an optional tool. When it is not installed this script says so and exits 4:
# an audit that did not run is never reported as a pass.
set -u
KIT=${0:A:h:h}
cd $KIT || exit 2

pages=("$@")
# AGENTS.md and CLAUDE.md are instructions for agent CLIs, written to a different craft
# (long paragraphs that restate a boundary are deliberate there), so they get the path
# check and not the plain-language audit.
(( $# )) || pages=(README.md CHANGELOG.md docs)
failed=0

for page in $pages; do
  [[ -e $page ]] || { print -u2 "docs-check: $page does not exist; nothing was checked"; exit 2 }
done

print "docs-check: machine paths"
if grep -rnE '/Users/[A-Za-z]|/Volumes/[A-Za-z]|/home/[a-z]' $pages AGENTS.md CLAUDE.md; then
  print -u2 "docs-check: a page names an absolute machine path; use <home> and <project>"
  failed=1
fi

print "docs-check: plain-language audit"
audit=${ISO_24495_AUDIT:-}
if [[ -z $audit ]]; then
  candidates=(~/.claude/plugins/cache/iso-24495/iso-24495-plain-language/*/skills/iso-24495-text-audit/scripts/audit-text-cli.ts(N))
  (( $#candidates )) && audit=$candidates[-1]
fi
if [[ -z $audit || ! -f $audit ]] || ! command -v bun >/dev/null; then
  print -u2 "docs-check: audit skill not installed. The plain-language audit did NOT run."
  print -u2 "  It needs the iso-24495-plain-language plugin's text-audit script and \`bun\`."
  print -u2 "  Point ISO_24495_AUDIT at audit-text-cli.ts to use a copy elsewhere."
  exit $(( failed ? 1 : 4 ))
fi
for page in $pages; do
  # The audit prints its findings and a count; its exit status does not carry the count.
  report=$(bun $audit $page --project-dir $KIT) || { print -u2 "docs-check: the audit failed on $page"; exit 2 }
  if ! print -r -- $report | grep -q '^Finding count: 0\.'; then
    print -r -- $report
    failed=1
  fi
done

(( failed )) && { print -u2 "docs-check: findings above"; exit 1 }
print "docs-check: no finding"
