@echo off
setlocal enabledelayedexpansion

set "AUDIO_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Finished Episodes"
set "OUTPUT_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Transcripts"
set "MODEL=medium"
set "PATH=C:\ffmpeg\bin;%PATH%"

:: Default host names suggested during speaker labeling
set "HOST1=Rocket"
set "HOST2=Trog"

:: Path to the speaker labeling script (same folder as this bat)
set "LABEL_SCRIPT=%~dp0label-speakers.py"

:: Load HuggingFace token from secrets file (not committed to git)
set "SECRETS_FILE=%~dp0secrets.bat"
if not exist "%SECRETS_FILE%" (
    echo ERROR: secrets.bat not found at %SECRETS_FILE%
    echo Please create it with the line:  set "HF_TOKEN=your_token_here"
    echo See secrets.bat.example for reference.
    echo.
    pause
    exit /b 1
)
call "%SECRETS_FILE%"

echo ============================================
echo   Salt All The Things - Episode Transcriber
echo      (with Speaker Diarization via WhisperX)
echo ============================================
echo.

:: Make sure output folder exists
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

:: Count mp3 files
set COUNT=0
for %%f in ("%AUDIO_DIR%\*.mp3") do set /a COUNT+=1

if %COUNT%==0 (
    echo No .mp3 files found in:
    echo %AUDIO_DIR%
    echo.
    pause
    exit /b
)

echo Found %COUNT% .mp3 file(s) in:
echo %AUDIO_DIR%
echo.
echo Output going to:
echo %OUTPUT_DIR%
echo.
echo Model: %MODEL%
echo Hosts: %HOST1%, %HOST2%
echo.
echo Press any key to start transcribing, or Ctrl+C to cancel...
pause >nul
echo.

set CURRENT=0
for %%f in ("%AUDIO_DIR%\*.mp3") do (
    set /a CURRENT+=1
    set "BASENAME=%%~nf"
    echo [!CURRENT!/%COUNT%] Transcribing: %%~nxf
    echo -------------------------------------------

    :: Skip if labeled transcript already exists
    if exist "%OUTPUT_DIR%\!BASENAME!.txt" (
        echo   Already transcribed, skipping.
        echo.
    ) else (
        :: Step 1: Run WhisperX with diarization, output JSON so we get speaker labels
        echo   Transcribing with speaker diarization...
        set "JSON_OUT=%OUTPUT_DIR%\!BASENAME!.json"
        whisperx "%%f" --model %MODEL% --language en --compute_type int8 --diarize --hf_token %HF_TOKEN% --output_format json --output_dir "%OUTPUT_DIR%"
        if errorlevel 1 (
            echo   ERROR: WhisperX failed on %%~nxf
        ) else (
            if exist "!JSON_OUT!" (
                echo   WhisperX complete. Now identifying speakers...
                echo.

                :: Step 2: Run the speaker labeling script interactively
                python "!LABEL_SCRIPT!" "!JSON_OUT!" "%OUTPUT_DIR%\!BASENAME!.txt" --hosts %HOST1% %HOST2%
                if errorlevel 1 (
                    echo   ERROR: Speaker labeling failed. Raw JSON kept at !JSON_OUT!
                ) else (
                    echo   Labeled transcript saved as !BASENAME!.txt
                )
            ) else (
                echo   WARNING: Expected JSON output not found. Check %OUTPUT_DIR% manually.
            )
        )
        echo.
    )
)

echo ============================================
echo   Done! %COUNT% file(s) processed.
echo ============================================
echo.
pause
