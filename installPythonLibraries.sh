#!/bin/bash

### This script installs Python libraries required by a specified Python file. ###
### Usage: 
  # 1.
# sudo chmod +x installPythonLibraries.sh
  # 2.
# sudo apt install python3-pip -y
  # 3.
# ./installPythonLibraries.sh testttt.py  

PYTHON_FILE="$1"
VENV_DIR="venv"

if [[ -z "$PYTHON_FILE" ]]; then
  echo "Usage: $0 testttt.py"
  exit 1
fi

if [[ ! -f "$PYTHON_FILE" ]]; then
  echo "File not found: $PYTHON_FILE"
  exit 1
fi

# Create or recreate virtual environment when missing or invalid
needs_venv=0
if [[ ! -d "$VENV_DIR" ]]; then
  needs_venv=1
else
  if [[ ! -x "$VENV_DIR/bin/python3" ]] || ! "$VENV_DIR/bin/python3" -c 'import sys' >/dev/null 2>&1; then
    needs_venv=1
  fi
fi

if [[ $needs_venv -eq 1 ]]; then
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# Activate the virtual environment
# To manually activate the venv, run: source "$VENV_DIR/bin/activate"
source "$VENV_DIR/bin/activate"

# Verify venv activation and rebuild if needed
if ! command -v python3 &> /dev/null || ! "$VENV_DIR/bin/python3" -c 'import sys' >/dev/null 2>&1; then
  echo "Virtual environment is corrupted. Rebuilding..."
  deactivate 2>/dev/null || true
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
fi

PIP_CMD="$VENV_DIR/bin/python3 -m pip"
"$PIP_CMD" install --upgrade pip setuptools wheel

# Extract import statements and get unique module names
IMPORTS=$(grep -E '^\s*(import|from) ' "$PYTHON_FILE" | \
  sed -E 's/^\s*import\s+([a-zA-Z0-9_]+).*/\1/' | \
  sed -E 's/^\s*from\s+([a-zA-Z0-9_]+).*/\1/' | \
  grep -v '^$' | sort | uniq)

# Try to install each module via pip
for module in $IMPORTS; do
  pip3 install "$module"
done

echo "All detected modules installed in virtual environment '$VENV_DIR'."
echo ""
echo "To activate the virtual environment in future sessions, run:"
echo "  source $VENV_DIR/bin/activate"
