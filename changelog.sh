#!/usr/bin/env bash
set -euo pipefail

# Generate a Keep a Changelog-style CHANGELOG.md from git history.
# Usage: bash changelog.sh [output_file]

OUTPUT_FILE="${1:-CHANGELOG.md}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: changelog.sh must be run inside a git repository." >&2
  exit 1
fi

# Ensure tags are available when running from a shallow clone or CI checkout.
if git rev-parse --is-shallow-repository >/dev/null 2>&1 && \
   [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
  git fetch --tags --unshallow >/dev/null 2>&1 || git fetch --tags >/dev/null 2>&1 || true
else
  git fetch --tags >/dev/null 2>&1 || true
fi

LAST_TAG=""
if LAST_TAG="$(git describe --tags --abbrev=0 2>/dev/null)"; then
  RANGE="${LAST_TAG}..HEAD"
  SUBTITLE="Changes since ${LAST_TAG}"
else
  RANGE="HEAD"
  SUBTITLE="Changes from full git history (no tags found)"
fi

TODAY="$(date +%Y-%m-%d)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

ADDED="${TMP_DIR}/added"
FIXED="${TMP_DIR}/fixed"
CHANGED="${TMP_DIR}/changed"
REMOVED="${TMP_DIR}/removed"
: >"${ADDED}"
: >"${FIXED}"
: >"${CHANGED}"
: >"${REMOVED}"

# Read commits oldest -> newest for a stable, readable changelog.
# Format: subject only; merge commits are skipped to reduce noise.
while IFS= read -r subject; do
  [ -n "${subject}" ] || continue

  clean_subject="${subject}"
  clean_subject="${clean_subject#feat: }"
  clean_subject="${clean_subject#feat!: }"
  clean_subject="${clean_subject#fix: }"
  clean_subject="${clean_subject#fix!: }"
  clean_subject="${clean_subject#chore: }"
  clean_subject="${clean_subject#docs: }"
  clean_subject="${clean_subject#refactor: }"
  clean_subject="${clean_subject#perf: }"
  clean_subject="${clean_subject#test: }"
  clean_subject="${clean_subject#style: }"
  clean_subject="${clean_subject#build: }"
  clean_subject="${clean_subject#ci: }"
  clean_subject="${clean_subject#revert: }"

  lower="$(printf '%s' "${subject}" | tr '[:upper:]' '[:lower:]')"
  item="- ${clean_subject}"

  case "${lower}" in
    feat:*|feat\(*|*" add "*|add\ *|*" added "*|*" implement "*|implement\ *|*" introduce "*|introduce\ *)
      printf '%s\n' "${item}" >>"${ADDED}"
      ;;
    fix:*|fix\(*|*" fix "*|fix\ *|*" fixed "*|*" bug "*|*" resolve "*|resolve\ *)
      printf '%s\n' "${item}" >>"${FIXED}"
      ;;
    remove:*|removed:*|delete:*|deleted:*|*" remove "*|remove\ *|*" removed "*|*" delete "*|delete\ *|*" deprecate "*|deprecate\ *)
      printf '%s\n' "${item}" >>"${REMOVED}"
      ;;
    *)
      printf '%s\n' "${item}" >>"${CHANGED}"
      ;;
  esac
done < <(git log --reverse --no-merges --pretty=format:%s "${RANGE}")

write_section() {
  local title="$1"
  local file="$2"
  printf '### %s\n' "${title}"
  if [ -s "${file}" ]; then
    sort -u "${file}"
  else
    printf -- '- No changes detected.\n'
  fi
  printf '\n'
}

{
  printf '# Changelog\n\n'
  printf 'All notable changes generated from git history.\n\n'
  printf '## Unreleased - %s\n\n' "${TODAY}"
  printf '_%s._\n\n' "${SUBTITLE}"
  write_section "Added" "${ADDED}"
  write_section "Fixed" "${FIXED}"
  write_section "Changed" "${CHANGED}"
  write_section "Removed" "${REMOVED}"
} >"${OUTPUT_FILE}"

echo "Generated ${OUTPUT_FILE} (${SUBTITLE})."
