@echo off
echo ========================================
echo   RUNNING QUALITY GATE
echo ========================================

echo [1/4] Ruff Check...
ruff check .
if %errorlevel% neq 0 exit /b %errorlevel%

echo [2/4] Ruff Format...
ruff format --check .
if %errorlevel% neq 0 exit /b %errorlevel%

echo [3/4] Pytest...
python -m pytest -q
if %errorlevel% neq 0 exit /b %errorlevel%

echo [4/4] Mypy...
python -m mypy app
if %errorlevel% neq 0 exit /b %errorlevel%

echo ========================================
echo   ALL QUALITY GATES PASSED!
echo ========================================