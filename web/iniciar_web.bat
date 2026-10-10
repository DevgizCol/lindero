@echo off
rem Arranca la plataforma en este equipo: http://127.0.0.1:5080
rem Antes de abrirla al público: defina PLANOS_ADMIN_CLAVE y publique detrás de HTTPS (PLANOS_HTTPS=1).
setlocal
if "%PLANOS_ADMIN_CLAVE%"=="" echo AVISO: sin PLANOS_ADMIN_CLAVE el panel /admin queda deshabilitado.
pushd "%~dp0.."
python web\app.py
popd
