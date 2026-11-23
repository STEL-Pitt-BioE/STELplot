#!/bin/bash
# Double-click launcher for STELplot on macOS. Author: Daniel Shiwarski
cd "$(dirname "$0")" || exit 1
for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" \
            "/opt/homebrew/Caskroom/miniforge/base" "/opt/miniconda3" "/opt/anaconda3"; do
    if [ -f "$base/etc/profile.d/conda.sh" ]; then
        source "$base/etc/profile.d/conda.sh"
        break
    fi
done
if ! command -v conda >/dev/null 2>&1; then
    echo "Could not find conda. See INSTALL.md, Step 2."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
fi
if ! conda activate stelplot; then
    echo "The stelplot environment was not found. See INSTALL.md, Step 3."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
fi
python stelplot_app.py
