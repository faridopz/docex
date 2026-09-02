#!/bin/bash
# NEEM Demo Setup — run this tonight before the demo tomorrow
# Usage: bash DEMO_SETUP.sh

set -e

echo "=========================================="
echo "DOCex NEEM Demo Setup"
echo "=========================================="
echo ""

cd ~/Desktop/docex || { echo "Error: ~/Desktop/docex not found"; exit 1; }

echo "1. Installing dependencies..."
pip3 install -r requirements.txt

echo ""
echo "2. Installing tesseract (OCR)..."
brew install tesseract

echo ""
echo "3. Checking OCR availability..."
OCR_STATUS=$(python3 -c "import fast_extract; print('OCR ready:', fast_extract.ocr_available())")
echo "   $OCR_STATUS"

if [[ ! "$OCR_STATUS" == *"True"* ]]; then
    echo "   ⚠️  WARNING: OCR not available. Photographed receipts won't read."
    echo "   Run: brew install tesseract && restart the API"
fi

echo ""
echo "4. Seeding demo data..."
python3 demo_seed.py

echo ""
echo "5. Generating demo documents..."
python3 make_demo_docs.py

echo ""
echo "6. Building frontend..."
cd web && npm run build
cd ..

echo ""
echo "=========================================="
echo "✓ Setup complete!"
echo "=========================================="
echo ""
echo "Next: open TWO terminals"
echo ""
echo "Terminal 1:"
echo "  cd ~/Desktop/docex && uvicorn api.main:app --reload --port 8000"
echo ""
echo "Terminal 2:"
echo "  cd ~/Desktop/docex/web && npm run dev"
echo ""
echo "Then sign in at http://localhost:3000/login"
echo ""
