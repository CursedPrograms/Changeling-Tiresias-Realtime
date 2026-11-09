@echo off
setlocal
cd /d "%~dp0"
rem Changeling Tiresias Realtime runs in Changeling Tiresias's environment: it needs Changeling Tiresias and Changeling
rem Imago Realtime next to this folder (as in Changeling Studio). Missing ones are fetched here.
set "STUDIO=%~dp0.."
for %%A in (Tiresias Imago-Realtime) do (
    if not exist "%STUDIO%\Changeling-%%A" (
        echo Getting Changeling %%A ...
        git clone https://github.com/CursedPrograms/Changeling-%%A "%STUDIO%\Changeling-%%A" || goto :error
    )
)

rem The environment: Changeling Tiresias's, or a sibling's (Tiresias, Chronos and Natio need the same things).
set "PY="
for %%A in (Tiresias Tiresias Chronos Natio) do (
    if not defined PY if exist "%STUDIO%\Changeling-%%A\psdenv\Lib\site-packages	orch" set "PY=%STUDIO%\Changeling-%%A\psdenv\Scripts\python.exe"
)
if not defined PY (
    echo Setting up Changeling Tiresias first, once: its environment and its models.
    call "%STUDIO%\Changeling-Tiresias\run.bat" --download-models
    set "PY=%STUDIO%\Changeling-Tiresias\psdenv\Scripts\python.exe"
)
if not exist "%STUDIO%\Changeling-Imago-Realtime\venv\Scripts\python.exe" (
    echo Changeling Imago Realtime isn't set up yet: start its run.bat once, then come back.
)

"%PY%" live.py %*
exit /b %ERRORLEVEL%

:error
echo.
echo Setup failed, see the messages above.
pause
exit /b 1
