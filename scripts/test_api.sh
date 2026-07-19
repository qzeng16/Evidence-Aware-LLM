#!/bin/bash

echo "Testing health endpoint..."
curl http://127.0.0.1:8000/health
echo ""
echo "--------------------------------"

echo "Testing Refuted claim..."
curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{"claim": "Are AI models always reliable on small biased datasets?"}'
echo ""
echo "--------------------------------"

echo "Testing Uncertain claim..."
curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{"claim": "Do bananas improve AI model reliability?"}'
echo ""
echo "--------------------------------"

echo "Testing Supported claim..."
curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{"claim": "Retrieval augmented generation can improve factual reliability."}'
echo ""
echo "--------------------------------"
