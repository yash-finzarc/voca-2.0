@echo off
REM Batch script to pull audio files from server using pscp (PuTTY)
REM Make sure PuTTY is installed and pscp.exe is in your PATH

set SERVER_HOST=172.105.50.83
set SERVER_USER=root
set SERVER_AUDIO_DIR=/root/voca-2.0/audio_logs
set LOCAL_AUDIO_DIR=audio_logs

echo Pulling audio files from server...
echo.

REM Check if call SID is provided
if "%1"=="" (
    echo Pulling ALL audio files...
    pscp -r %SERVER_USER%@%SERVER_HOST%:%SERVER_AUDIO_DIR%/ %LOCAL_AUDIO_DIR%/
) else (
    echo Pulling audio files for call: %1
    pscp -r %SERVER_USER%@%SERVER_HOST%:%SERVER_AUDIO_DIR%/%1/ %LOCAL_AUDIO_DIR%/%1/
)

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully pulled audio files!
    echo Files are in: %CD%\%LOCAL_AUDIO_DIR%\
) else (
    echo.
    echo Error: pscp command failed or not found.
    echo.
    echo Please install PuTTY from https://www.putty.org/
    echo Or use WinSCP (GUI tool) from https://winscp.net/
)

pause


