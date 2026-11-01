@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    echo [WARNING] .venv not found - falling back to system Python.
    echo Run the setup steps in README.md section 2 first if you see "No module named streamlit".
    set "PY=python"
)

start "ResolveIQ automation worker" cmd /k ""%PY%" -m services.automation_worker --interval 30"
echo Open http://localhost:8501 in your browser once Streamlit starts.
"%PY%" -m streamlit run app.py
pause
