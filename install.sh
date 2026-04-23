#!/usr/bin/env sh
#
# SaturnZap one-line installer.
#
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/lqwdtech/SaturnZap/main/install.sh | sh
#
# Optional environment variables:
#   SZ_VERSION  Pin a specific SaturnZap release tag (default: latest GitHub release).
#               Example: SZ_VERSION=v1.3.0 sh install.sh
#   SZ_PREFIX   Install prefix passed to `uv tool install`. Default: uv's default.
#
# What this script does:
#   1. Ensures `uv` is installed (installs to ~/.local/bin if missing).
#   2. Resolves the latest SaturnZap GitHub Release tag (or honours $SZ_VERSION).
#   3. Downloads the saturnzap and ldk-node wheels from that release into a
#      temporary directory.
#   4. Runs `uv tool install saturnzap --find-links <tmpdir>` so uv resolves the
#      vendored ldk-node wheel locally instead of failing on PyPI.
#   5. Cleans up the temporary directory.
#
# Why this exists:
#   `ldk-node` is not yet published to PyPI, so a plain `uv tool install
#   saturnzap` fails to resolve dependencies. This installer hides the
#   `--find-links` plumbing behind a single command.

set -eu

REPO="lqwdtech/SaturnZap"
GITHUB_API="https://api.github.com/repos/${REPO}"
GITHUB_DL="https://github.com/${REPO}/releases/download"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

need() {
    command -v "$1" >/dev/null 2>&1 || err "required tool '$1' not found in PATH"
}

need curl
need tar  # only used if we ever need the sdist; keep guard for clear errors

# --- 1. ensure uv -----------------------------------------------------------

if ! command -v uv >/dev/null 2>&1; then
    log "uv not found, installing to ~/.local/bin"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The uv installer drops the binary in ~/.local/bin; make sure this shell
    # session can find it for the rest of the script.
    if [ -d "$HOME/.local/bin" ]; then
        PATH="$HOME/.local/bin:$PATH"
        export PATH
    fi
    command -v uv >/dev/null 2>&1 || err "uv install reported success but 'uv' is still not in PATH; add ~/.local/bin to PATH and re-run"
fi
log "uv: $(command -v uv) ($(uv --version 2>/dev/null || echo unknown))"

# --- 2. resolve version -----------------------------------------------------

if [ "${SZ_VERSION:-}" = "" ]; then
    log "resolving latest SaturnZap release tag"
    # Parse the JSON without jq to keep the install script dependency-free.
    SZ_VERSION=$(curl -sL "${GITHUB_API}/releases/latest" \
        | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' \
        | head -n 1)
    [ -n "$SZ_VERSION" ] || err "could not determine latest release tag from GitHub"
fi
log "installing SaturnZap ${SZ_VERSION}"

# Strip the leading "v" for use in the wheel filename.
SZ_NUM="${SZ_VERSION#v}"

# --- 3. download wheels into a temp dir -------------------------------------

TMPDIR=$(mktemp -d -t saturnzap-install.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

# Try to fetch the explicit asset list so we pick up whatever ldk_node wheel
# is shipped with this release (in case the version pin changes later).
log "fetching release asset list"
ASSETS=$(curl -sL "${GITHUB_API}/releases/tags/${SZ_VERSION}" \
    | sed -n 's/.*"name": *"\([^"]*\.whl\)".*/\1/p' \
    | sort -u)

if [ -z "$ASSETS" ]; then
    err "no wheels found on release ${SZ_VERSION}"
fi

for asset in $ASSETS; do
    log "downloading ${asset}"
    curl -sSL --fail \
        -o "${TMPDIR}/${asset}" \
        "${GITHUB_DL}/${SZ_VERSION}/${asset}" \
        || err "failed to download ${asset}"
done

# --- 4. install with uv -----------------------------------------------------

PREFIX_ARG=""
if [ -n "${SZ_PREFIX:-}" ]; then
    PREFIX_ARG="--prefix ${SZ_PREFIX}"
fi

log "running: uv tool install saturnzap==${SZ_NUM} --find-links ${TMPDIR}"
# shellcheck disable=SC2086 # PREFIX_ARG is intentionally unquoted to allow empty expansion
uv tool install ${PREFIX_ARG} "saturnzap==${SZ_NUM}" --find-links "${TMPDIR}"

# --- 5. done ---------------------------------------------------------------

log "SaturnZap ${SZ_VERSION} installed."
log "Try: sz --version"
log "Next:"
log "  export SZ_PASSPHRASE='your-secure-passphrase'"
log "  sz setup --auto"
