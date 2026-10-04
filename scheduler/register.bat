@echo off
echo Registering Deep Signal daily task at 08:00...
schtasks /create ^
  /tn "DeepSignalPipeline" ^
  /tr "\"%~dp0run.bat\"" ^
  /sc daily ^
  /st 08:00 ^
  /ru %USERNAME% ^
  /f
echo.
echo Done. Verify with:
echo   schtasks /query /tn "DeepSignalPipeline"
echo.
echo To run manually right now:
echo   schtasks /run /tn "DeepSignalPipeline"
