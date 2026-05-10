@echo off
echo Starting local API documentation server...
echo.
echo Please open your browser and go to:
echo http://localhost:8080
echo.
echo Press Ctrl+C in this window to stop the server when you are done.
python -m http.server 8080
