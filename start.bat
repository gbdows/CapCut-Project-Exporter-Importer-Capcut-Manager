@echo off
echo ========================================
echo    CapCut Project Exporter
echo ========================================
echo.
echo Installation des dependances...
pip install -r requirements.txt
echo.
echo Demarrage du serveur web...
echo.
echo Ouvrez http://localhost:5000 dans votre navigateur
echo.
echo Pressez Ctrl+C pour arreter le serveur
echo.
python web_server.py
pause
