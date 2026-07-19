#!/bin/bash

curl -X POST "http://127.0.0.1:8000/verify" \
  -H "Content-Type: application/json" \
  -d '{"claim": "Are AI models always reliable on small biased datasets?"}' \
  | python3 -m json.tool
