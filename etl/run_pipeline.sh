#!/usr/bin/env bash
# Rebuild data/seed.json from data/Dock_Schedule_-_Synthetic_Sample.xlsx
set -euo pipefail
cd "$(dirname "$0")"
python3 extract.py      # grid -> raw_bookings.json
python3 normalize.py    # classify + canonicalise -> normalized.json
python3 registry.py     # register tabs -> registry.json
python3 seed.py         # -> seed.json (compact, embedded in the app)
cp seed.json ../data/seed.json
python3 gen_example.py  # adds the worked example season (and self-checks it)
echo "Analysis (optional): python3 regprobe.py && python3 conflicts.py && python3 infer.py && python3 overflow.py && python3 stats.py"
