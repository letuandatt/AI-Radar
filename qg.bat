@echo off
echo ========================================
echo   RUNNING SMART QUALITY GATE
echo ========================================

:: ---------------------------------------------------------
:: [1/4] RUFF CHECK (With Auto-Fix)
:: ---------------------------------------------------------
echo [1/4] Ruff Check (Linting)...
ruff check .
if %errorlevel% neq 0 (
    echo [!] Linting errors found. Attempting auto-fix ^(ruff check . --fix^)...
    ruff check . --fix

    :: Check again to ensure all fixable errors are gone
    ruff check .
    if %errorlevel% neq 0 (
        echo [X] Auto-fix incomplete. Unfixable linting errors remain. Please fix manually.
        exit /b %errorlevel%
    )
    echo [+] Auto-fix successful!
)
echo [+] Ruff Check passed.

:: ---------------------------------------------------------
:: [2/4] RUFF FORMAT (With Auto-Fix)
:: ---------------------------------------------------------
echo [2/4] Ruff Format Check...
ruff format --check .
if %errorlevel% neq 0 (
    echo [!] Formatting issues found. Attempting auto-format ^(ruff format .^)...
    ruff format .

    :: Check again to ensure formatting is now correct
    ruff format --check .
    if %errorlevel% neq 0 (
        echo [X] Auto-format failed. Please fix manually.
        exit /b %errorlevel%
    )
    echo [+] Auto-format successful!
)
echo [+] Ruff Format passed.

:: ---------------------------------------------------------
:: [3/4] PYTEST (Manual Fix Only)
:: ---------------------------------------------------------
echo [3/4] Pytest...
python -m pytest -q
if %errorlevel% neq 0 (
    echo [X] Pytest failed. Please fix the logic/tests manually.
    exit /b %errorlevel%
)
echo [+] Pytest passed.

:: ---------------------------------------------------------
:: [4/4] MYPY (Manual Fix Only)
:: ---------------------------------------------------------
echo [4/4] Mypy (Type Checking)...
python -m mypy app
if %errorlevel% neq 0 (
    echo [X] Mypy failed. Please fix the type hints manually.
    exit /b %errorlevel%
)
echo [+] Mypy passed.

:: ---------------------------------------------------------
:: SUCCESS
:: ---------------------------------------------------------
echo ========================================
echo   ALL QUALITY GATES PASSED!
echo ========================================