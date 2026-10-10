@echo off
rem Ejecuta el motor con el Python del sistema. Ya no necesita QGIS:
rem   planos.bat planos --excel X.xlsx --dxf P.dxf --salida trabajos\x
setlocal
pushd "%~dp0"
python -m motor.cli %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
