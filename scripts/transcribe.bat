@echo off
setlocal enabledelayedexpansion

set "AUDIO_DIR=J:\Shared drives\Salt All The Things\Show Recordings"
set "OUTPUT_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Transcripts"
set "MODEL=medium"
set "PATH=C:\ffmpeg\bin;%PATH%"

echo ============================================
echo   Salt All The Things - Episode Transcriber
echo ============================================
echo.

:: Make sure output folder exists
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

:: Count wav files
set COUNT=0
for %%f in ("%AUDIO_DIR%\*.wav") do set /a COUNT+=1

if %COUNT%==0 (
    echo No .wav files found in:
    echo %AUDIO_DIR%
    echo.
    pause
    exit /b
)

echo Found %COUNT% .wav file(s) in:
echo %AUDIO_DIR%
echo.
echo Output going to:
echo %OUTPUT_DIR%
echo.
echo Model: %MODEL%
echo.
echo Press any key to start transcribing, or Ctrl+C to cancel...
pause >nul
echo.

set CURRENT=0
for %%f in ("%AUDIO_DIR%\*.wav") do (
    set /a CURRENT+=1
    echo [!CURRENT!/%COUNT%] Transcribing: %%~nxf
    echo -------------------------------------------

    :: Skip if transcript already exists
    if exist "%OUTPUT_DIR%\%%~nf.txt" (
        echo   Already transcribed, skipping.
        echo.
    ) else (
        whisper "%%f" --model %MODEL% --language en --output_format txt --output_dir "%OUTPUT_DIR%"
        echo.
    )
)

echo ============================================
echo   Done! %COUNT% file(s) processed.
echo ============================================
echo.
pause
