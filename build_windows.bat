@echo off
REM ============================================================
REM  Genera SIGSAT.exe y el instalador SIGSAT_Instalador.exe
REM  Ejecutar en Windows, dentro de la carpeta del prototipo.
REM  Requisitos: Python 3.10+ (comando "py") e Inno Setup 6
REM  (https://jrsoftware.org/isinfo.php) para el instalador.
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] Creando entorno de compilacion...
py -3 -m venv .venv_build || goto :error
call .venv_build\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt pyinstaller || goto :error

echo [2/4] Generando la aplicacion con PyInstaller...
pyinstaller --noconfirm --clean --windowed --name SIGSAT main.py || goto :error

echo [3/4] Probando que el ejecutable abre (3 segundos)...
start "" /wait cmd /c "dist\SIGSAT\SIGSAT.exe --sin-guardar & exit" 2>nul
REM (si la ventana se abrio, cierrela; la prueba real es abrirlo a mano)

echo [4/4] Generando el instalador con Inno Setup...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo No se encontro Inno Setup 6. Instalelo y vuelva a ejecutar este archivo.
  echo La aplicacion ya quedo en dist\SIGSAT\SIGSAT.exe
  goto :fin
)
%ISCC% instalador_sigsat.iss || goto :error
echo.
echo Listo: salida\SIGSAT_Instalador.exe
goto :fin

:error
echo.
echo Hubo un error. Revise los mensajes de arriba.
exit /b 1
:fin
endlocal
