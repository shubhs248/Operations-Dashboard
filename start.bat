@echo off
REM Quick start for local development on Windows
echo Starting Platform Operations Dashboard...
echo.

if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo IMPORTANT: Edit .env with your credentials before proceeding.
    pause
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate
pip install -r requirements.txt -q

echo.
echo Starting server on http://localhost:9100
echo API docs at http://localhost:9100/docs
echo.
python -m app.main
