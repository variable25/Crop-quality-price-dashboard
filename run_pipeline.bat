@echo off
setlocal
rem run_pipeline.bat - run the Crop Lab ETL pipeline once (used by Windows Task Scheduler).
rem Opens Docker Desktop only if it is closed, runs the pipeline, then closes
rem whatever this script opened. If Docker was already open, it is left alone.

cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=logs\scheduler.log"
set STARTED_DOCKER=0
set RESULT=1
echo %date% %time% ---- scheduled run >> "%LOG%"

rem 1. Is Docker already running?
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

rem 2. No: open Docker Desktop and remember that this script did it
echo %date% %time% opening Docker Desktop >> "%LOG%"
docker desktop start >> "%LOG%" 2>&1
set STARTED_DOCKER=1

rem 3. Wait up to 3 minutes (36 checks, 5 seconds apart) for the Docker engine
set /a TRIES=0
:wait_for_docker
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a TRIES+=1
if %TRIES% geq 36 goto docker_failed
ping -n 6 127.0.0.1 >nul
goto wait_for_docker

:docker_failed
echo %date% %time% Docker did not start within 3 minutes >> "%LOG%"
goto cleanup

:docker_ready
rem 4. Start the database container and wait until its healthcheck passes
docker compose up -d --wait postgres >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %date% %time% database container did not become healthy >> "%LOG%"
    goto cleanup
)

rem 5. Run the pipeline with the project's own Python and keep its exit code
".venv\Scripts\python.exe" -m pipeline.run >> "%LOG%" 2>&1
set RESULT=%ERRORLEVEL%
echo %date% %time% pipeline finished with exit code %RESULT% >> "%LOG%"

:cleanup
rem 6. Put things back: close Docker only if this script opened it
if "%STARTED_DOCKER%"=="1" (
    echo %date% %time% closing Docker Desktop >> "%LOG%"
    docker compose stop >> "%LOG%" 2>&1
    docker desktop stop >> "%LOG%" 2>&1
)
exit /b %RESULT%