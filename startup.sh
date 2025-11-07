#!/bin/bash

# Download spaCy model if not present
python -m spacy download pt_core_news_sm --quiet || true

# Start application
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
