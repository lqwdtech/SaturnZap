#!/usr/bin/env bash
# PostToolUse hook: run `uv sync` after edits to src/saturnzap/
# Reads JSON from stdin, checks if the edited file is under src/saturnzap/
set -e

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('toolName',''))" 2>/dev/null || true)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('input',{}).get('filePath',''))" 2>/dev/null || true)

if [[ "$TOOL_NAME" =~ ^(replace_string_in_file|create_file|multi_replace_string_in_file)$ ]] && [[ "$FILE_PATH" == *"src/saturnzap/"* ]]; then
    cd /root/saturnzap && uv sync --quiet 2>&1
fi
