#!/bin/bash
set -e
echo "=== silkroute setup ==="

# Python core (requires 3.12+)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
echo "Python CLI ready: silkroute --version"

# Dashboard
echo "Setting up dashboard..."
cd dashboard
npm install
cd ..

echo "Setup complete!"
echo "  Python: silkroute models"
echo "  Dashboard: cd dashboard && npm run dev"
echo "  Full stack: docker compose up -d"
