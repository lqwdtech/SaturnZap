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
#
#   On macOS the release wheel is Linux-only, so we additionally build the
#   ldk-node wheel from upstream source (one-time, ~5–10 min). This branch
#   is removed once ldk-node ships on PyPI.

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

OS=$(uname -s)

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

WORKDIR=$(mktemp -d -t saturnzap-install.XXXXXX)
trap 'rm -rf "$WORKDIR"' EXIT INT TERM

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
        -o "${WORKDIR}/${asset}" \
        "${GITHUB_DL}/${SZ_VERSION}/${asset}" \
        || err "failed to download ${asset}"
done

# --- 3a. macOS: replace the Linux ldk-node wheel with one built from source ---
#
# The ldk_node-*-py3-none-any.whl shipped on the SaturnZap release bundles a
# Linux .so. On macOS we ignore it and build a matching .dylib-bearing wheel
# from upstream. When ldk-node lands on PyPI this whole branch goes away.

if [ "$OS" = "Darwin" ]; then
    log "macOS detected — building the ldk-node wheel from source"
    log "(this happens once per install and takes ~5–10 minutes)"

    need git
    need python3

    # Determine the LDK version from the wheel name we already downloaded so
    # we build the matching upstream tag. The release ships a single
    # py3-none-any wheel for ldk_node.
    LDK_LINUX_WHEEL=$(ls "${WORKDIR}"/ldk_node-*-py3-none-any.whl 2>/dev/null | head -n1)
    [ -n "$LDK_LINUX_WHEEL" ] || err "no ldk_node wheel found in release assets"
    LDK_VERSION=$(basename "$LDK_LINUX_WHEEL" | sed -n 's/^ldk_node-\([0-9][0-9.]*\).*/\1/p')
    [ -n "$LDK_VERSION" ] || err "could not parse LDK version from $LDK_LINUX_WHEEL"
    log "matching ldk-node release: v${LDK_VERSION}"

    # Rust toolchain (required by upstream's build script).
    if ! command -v cargo >/dev/null 2>&1; then
        log "Rust toolchain not found — installing via rustup"
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
            | sh -s -- -y --default-toolchain stable --profile minimal
        # shellcheck disable=SC1091
        . "$HOME/.cargo/env"
    fi
    command -v cargo >/dev/null 2>&1 \
        || err "cargo still not in PATH; add ~/.cargo/bin to PATH and re-run"

    BUILD_DIR="${WORKDIR}/ldk-node-build"
    OUTDIR="${WORKDIR}/wheels-out"
    mkdir -p "$OUTDIR"
    log "cloning lightningdevkit/ldk-node@v${LDK_VERSION}"
    git clone --depth 1 --branch "v${LDK_VERSION}" \
        https://github.com/lightningdevkit/ldk-node.git "$BUILD_DIR" \
        >/dev/null 2>&1 \
        || err "failed to clone ldk-node@v${LDK_VERSION}"

    log "running uniffi_bindgen_generate_python.sh (Rust compile happens here)"
    (
        cd "$BUILD_DIR"
        ./scripts/uniffi_bindgen_generate_python.sh
    ) || err "ldk-node build script failed"

    # Build the wheel in an isolated venv so we don't depend on whatever
    # setuptools the user has globally.
    BUILD_VENV="${WORKDIR}/buildenv"
    log "creating build venv at ${BUILD_VENV}"
    python3 -m venv "$BUILD_VENV"
    "$BUILD_VENV/bin/pip" install --quiet --upgrade pip setuptools wheel build \
        || err "failed to install build dependencies in the build venv"

    log "building ldk_node wheel"
    "$BUILD_VENV/bin/python" -m build --wheel --no-isolation \
        --outdir "$OUTDIR" "$BUILD_DIR/bindings/python" \
        || err "ldk_node wheel build failed"

    # Drop the Linux wheel and copy in the freshly-built one.
    rm -f "$LDK_LINUX_WHEEL"

    NEW_LDK_WHEEL=$(find "$OUTDIR" "$BUILD_DIR/bindings/python/dist" \
        -maxdepth 2 -name 'ldk_node-*.whl' -print 2>/dev/null | head -n1)
    [ -n "$NEW_LDK_WHEEL" ] || err "build produced no ldk_node wheel"
    cp "$NEW_LDK_WHEEL" "$WORKDIR/" \
        || err "failed to copy built wheel into $WORKDIR"
    log "macOS wheel built: $(basename "$NEW_LDK_WHEEL")"
fi

# --- 4. install with uv -----------------------------------------------------

PREFIX_ARG=""
if [ -n "${SZ_PREFIX:-}" ]; then
    PREFIX_ARG="--prefix ${SZ_PREFIX}"
fi

log "running: uv tool install saturnzap==${SZ_NUM} --find-links ${WORKDIR}"
# shellcheck disable=SC2086 # PREFIX_ARG is intentionally unquoted to allow empty expansion
uv tool install ${PREFIX_ARG} "saturnzap==${SZ_NUM}" --find-links "${WORKDIR}"

# --- 5. done ---------------------------------------------------------------

log "SaturnZap ${SZ_VERSION} installed."
log "Try: sz --version"
log "Next:"
log "  export SZ_PASSPHRASE='your-secure-passphrase'"
log "  sz setup --auto"
