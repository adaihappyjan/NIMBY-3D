@echo off
setlocal
rem Nimby3D: the manager of the nimby3d add-on (manager\app.py), started with pythonw (no console window).
rem   Nimby3D.cmd            open the manager (a window; the browser when WebView2 or pywebview is missing)
rem   Nimby3D.cmd --browser  open it in the browser
rem   Nimby3D.cmd --check    only report which Python would be used
cd /d "%~dp0"

set "PYW=%N3D_PYTHONW%"
set "PYW_ARGS="
if not defined PYW if exist "%~dp0runtime\pythonw.exe" set "PYW=%~dp0runtime\pythonw.exe"
for %%V in (314 313 312 311 310) do (
  if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe"
)
if not defined PYW (
  where pythonw.exe >nul 2>nul && set "PYW=pythonw.exe"
)
if not defined PYW (
  where pyw.exe >nul 2>nul && set "PYW=pyw.exe" && set "PYW_ARGS=-3"
)
if not defined PYW goto not_found

"%PYW%" %PYW_ARGS% -c "import struct,sys; raise SystemExit(0 if sys.version_info >= (3, 10) and struct.calcsize('P') == 8 else 1)" >nul 2>nul
if errorlevel 1 goto not_found

if /i "%~1"=="--check" (
  echo launcher-ok using "%PYW%" %PYW_ARGS%
  exit /b 0
)
start "" "%PYW%" %PYW_ARGS% "%~dp0manager\app.py" %*
exit /b 0

:not_found
chcp 65001 >nul
echo.
echo [Nimby3D] 64-bit Python 3.10 or newer was not found.
echo [Nimby3D] 没有找到 64 位 Python 3.10 或更高版本。
echo Install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH"), then run Nimby3D.cmd again.
echo 请从上面的网址安装 Python（勾选 "Add python.exe to PATH"），然后重新运行 Nimby3D.cmd。
echo.
pause
exit /b 1
