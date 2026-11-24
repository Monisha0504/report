@echo off
cd /d %~dp0
python -m pip install -q -r requirements.txt
python -m uvicorn app.main:app --port 8000
