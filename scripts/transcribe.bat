@echo off
setlocal enabledelayedexpansion

:: ============================================
::   Salt All The Things - Episode Transcriber
::   v2.0 - Multi-machine / Smart Queue
:: ============================================

set "RAW_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Raw Dog Recordings"
set "FINISHED_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Finished Episodes"
set "OUTPUT_DIR=J:\Shared drives\Salt All The Things\Show Recordings\Transcripts"
set "MODEL=medium"
set "PATH=C:\ffmpeg\bin;%PATH%"

set "HOST1=Rocket"
set "HOST2=Trog"
set "LABEL_SCRIPT=%~dp0label-speakers.py"
set "SECRETS_FILE=%~dp0secrets.py"

if not exist "%SECRETS_FILE%" (
    echo ERROR: secrets.py not found at %SECRETS_FILE%
    echo Please copy scripts\secrets.py.example to scripts\secrets.py and fill it in.
    echo.
    pause
    exit /b 1
)
for /f "usebackq delims=" %%t in (`python -c "import sys; sys.path.insert(0, r'%~dp0'); import secrets as s; print(s.HF_TOKEN)"`) do set "HF_TOKEN=%%t"

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo ============================================
echo   Salt All The Things - Episode Transcriber
echo ============================================
echo.
echo Which folder do you want to scan?
echo   [1] Raw Dog Recordings (glued, pre-Skate)
echo   [2] Finished Episodes  (Skate's final output)
echo   [3] Both
echo.
set /p FOLDER_CHOICE="Enter 1, 2, or 3: "

set "SCAN_RAW=0"
set "SCAN_FINISHED=0"
if "%FOLDER_CHOICE%"=="1" set "SCAN_RAW=1"
if "%FOLDER_CHOICE%"=="2" set "SCAN_FINISHED=1"
if "%FOLDER_CHOICE%"=="3" (
    set "SCAN_RAW=1"
    set "SCAN_FINISHED=1"
)

if "%SCAN_RAW%"=="0" if "%SCAN_FINISHED%"=="0" (
    echo Invalid choice. Exiting.
    pause
    exit /b 1
)

echo.
echo Scanning for unprocessed or stale episodes...
echo.

set IDX=0

:: ---- Helper: get file's last-modified date as YYYYMMDDHHMMSS ----
:: We use PowerShell for reliable date comparison
:: Stored as: FILE_DATE_n=<timestamp>

if "%SCAN_RAW%"=="1" (
    echo [Raw Dog Recordings]
    for %%f in ("%RAW_DIR%\*.mp3" "%RAW_DIR%\*.wav") do (
        set "BASENAME=%%~nf"
        set "AUDIOFILE=%%f"
        set "TXTFILE=%OUTPUT_DIR%\!BASENAME!.txt"
        set "NEEDS_PROCESSING=0"
        set "REASON="

        if not exist "!TXTFILE!" (
            set "NEEDS_PROCESSING=1"
            set "REASON=no transcript"
        ) else (
            :: Compare dates via PowerShell - is audio newer than transcript?
            for /f %%d in ('powershell -NoProfile -Command ^
                "$a = (Get-Item '%%f').LastWriteTime; $b = (Get-Item '!TXTFILE!').LastWriteTime; if ($a -gt $b) { 'STALE' } else { 'OK' }"') do (
                if "%%d"=="STALE" (
                    set "NEEDS_PROCESSING=1"
                    set "REASON=transcript older than audio"
                )
            )
        )

        if "!NEEDS_PROCESSING!"=="1" (
            set /a IDX+=1
            set "FILE_!IDX!=%%f"
            set "NAME_!IDX!=%%~nxf"
            set "REASON_!IDX!=!REASON!"
            echo   [!IDX!] %%~nxf  ^(!REASON!^)
        )
    )
    echo.
)

if "%SCAN_FINISHED%"=="1" (
    echo [Finished Episodes]
    for %%f in ("%FINISHED_DIR%\*.mp3" "%FINISHED_DIR%\*.wav") do (
        set "BASENAME=%%~nf"
        set "AUDIOFILE=%%f"
        set "TXTFILE=%OUTPUT_DIR%\!BASENAME!.txt"
        set "NEEDS_PROCESSING=0"
        set "REASON="

        if not exist "!TXTFILE!" (
            set "NEEDS_PROCESSING=1"
            set "REASON=no transcript"
        ) else (
            for /f %%d in ('powershell -NoProfile -Command ^
                "$a = (Get-Item '%%f').LastWriteTime; $b = (Get-Item '!TXTFILE!').LastWriteTime; if ($a -gt $b) { 'STALE' } else { 'OK' }"') do (
                if "%%d"=="STALE" (
                    set "NEEDS_PROCESSING=1"
                    set "REASON=transcript older than audio"
                )
            )
        )

        if "!NEEDS_PROCESSING!"=="1" (
            set /a IDX+=1
            set "FILE_!IDX!=%%f"
            set "NAME_!IDX!=%%~nxf"
            set "REASON_!IDX!=!REASON!"
            echo   [!IDX!] %%~nxf  ^(!REASON!^)
        )
    )
    echo.
)

if %IDX%==0 (
    echo No unprocessed or stale episodes found. You're all caught up!
    echo.
    pause
    exit /b
)

echo Found %IDX% episode(s) needing transcription.
echo.
echo Enter the numbers you want THIS machine to process.
echo   Examples:  ALL   ^|   1   ^|   1 3 5   ^|   2-4   ^|   1 3-5 7
echo.
set /p SELECTION="Your selection: "

:: ---- Parse selection into a "selected" flag array ----
:: selected_n=1 means process file n

:: Initialize all to 0
for /l %%i in (1,1,%IDX%) do set "SELECTED_%%i=0"

:: Handle ALL
if /i "%SELECTION%"=="ALL" (
    for /l %%i in (1,1,%IDX%) do set "SELECTED_%%i=1"
    goto :run
)

:: Parse tokens (handles individual numbers and ranges like 2-4)
for %%t in (%SELECTION%) do (
    set "TOKEN=%%t"
    :: Check if token contains a dash (range)
    echo !TOKEN! | findstr /r "^[0-9][0-9]*-[0-9][0-9]*$" >nul 2>&1
    if not errorlevel 1 (
        :: It's a range - split on dash
        for /f "tokens=1,2 delims=-" %%a in ("!TOKEN!") do (
            set "RANGE_START=%%a"
            set "RANGE_END=%%b"
            for /l %%i in (!RANGE_START!,1,!RANGE_END!) do (
                if %%i geq 1 if %%i leq %IDX% set "SELECTED_%%i=1"
            )
        )
    ) else (
        :: It's a single number
        set "NUM=!TOKEN!"
        if !NUM! geq 1 if !NUM! leq %IDX% set "SELECTED_!NUM!=1"
    )
)

:run
echo.
echo ============================================
echo   Starting transcription...
echo ============================================
echo.

set DONE_COUNT=0
set SKIP_COUNT=0

for /l %%i in (1,1,%IDX%) do (
    if "!SELECTED_%%i!"=="1" (
        set /a DONE_COUNT+=1
        set "CURRENT_FILE=!FILE_%%i!"
        set "CURRENT_NAME=!NAME_%%i!"

        :: Extract basename without extension
        for %%x in ("!CURRENT_FILE!") do set "BASENAME=%%~nx"
        for %%x in ("!CURRENT_FILE!") do set "BASENAME=%%~n"
        :: Simpler approach: strip extension manually
        set "BASENAME=!CURRENT_NAME!"
        set "BASENAME=!BASENAME:.mp3=!"
        set "BASENAME=!BASENAME:.wav=!"
        set "BASENAME=!BASENAME:.MP3=!"
        set "BASENAME=!BASENAME:.WAV=!"

        echo [!DONE_COUNT!] Processing: !CURRENT_NAME!
        echo     Reason: !REASON_%%i!
        echo -------------------------------------------

        set "JSON_OUT=%OUTPUT_DIR%\!BASENAME!.json"
        set "TXT_OUT=%OUTPUT_DIR%\!BASENAME!.txt"

        echo   Step 1/2: Running WhisperX with diarization...
        whisperx "!CURRENT_FILE!" --model %MODEL% --language en --compute_type int8 --diarize --hf_token %HF_TOKEN% --output_format json --output_dir "%OUTPUT_DIR%"

        if errorlevel 1 (
            echo   ERROR: WhisperX failed on !CURRENT_NAME!
        ) else (
            if exist "!JSON_OUT!" (
                echo   Step 2/2: Identifying speakers...
                echo.
                python "!LABEL_SCRIPT!" "!JSON_OUT!" "!TXT_OUT!" --hosts %HOST1% %HOST2%
                if errorlevel 1 (
                    echo   ERROR: Speaker labeling failed. Raw JSON kept at !JSON_OUT!
                ) else (
                    echo   Done: !BASENAME!.txt
                )
            ) else (
                echo   WARNING: Expected JSON not found at !JSON_OUT!
                echo   Check %OUTPUT_DIR% manually.
            )
        )
        echo.
    ) else (
        set /a SKIP_COUNT+=1
    )
)

echo ============================================
echo   All done!
echo   Processed: %DONE_COUNT% episode(s)
echo ============================================
echo.

:: Play completion sound
powershell -NoProfile -c "(New-Object Media.SoundPlayer 'C:\Windows\Media\chimes.wav').PlaySync()"

pause