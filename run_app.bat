@echo off
rem Start the Flood Relief Stockpile Planner. Double-click this file.
cd /d "%~dp0"
rem create the virtual environment on first use
if not exist .venv ( py -m venv .venv )
rem install or update the pinned packages (quick when already installed)
.venv\Scripts\python -m pip install -q -r requirements.txt
rem launch the app; it opens in your browser at http://localhost:8501
.venv\Scripts\python -m streamlit run app.py
pause
