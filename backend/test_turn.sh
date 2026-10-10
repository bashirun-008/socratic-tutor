#!/usr/bin/env bash
# Usage: ./test_turn.sh path/to/circuit.jpg "I don't get why the current splits here"
curl -s -X POST http://localhost:8000/tutor/turn \
  -F "image=@$1" -F "message=$2" | python -m json.tool
