@echo off
echo Installing dependencies...
pip install -r requirements.txt --quiet
echo.
echo Starting Photo Enhancer 4K server...
echo Open your browser at: http://localhost:5000
echo Press Ctrl+C to stop.
echo.
python server.py
pause
