# Shorts Studio MVP

A local Python starter for generating vertical Shorts storyboard cards and rendering them into an MP4 with FFmpeg.

## Requirements
- Python 3.11+
- FFmpeg installed and available on PATH

## Setup (Windows)
1. Extract the project ZIP.
2. Open PowerShell in the extracted folder.
3. Run `python -m pip install -r requirements.txt`.
4. Run `python app.py`.
5. Open http://127.0.0.1:8765 in your browser.

This MVP uses template-based storyboards and still-image scene cards. AI generation, voice-over, YouTube upload, analytics, and a full timeline editor are not included yet.

## Tests
Run `python -m unittest discover -s tests -v`.
