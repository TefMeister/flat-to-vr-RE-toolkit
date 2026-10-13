@echo off
rem Builds Hand Freeze into dist\: the OpenXR layer (C++, needs Visual Studio 2022 Build Tools) and the app (C#, uses the
rem compiler that ships with Windows' .NET Framework 4). Run install.ps1 afterwards for the desktop icon.
setlocal
set HERE=%~dp0
set VCVARS=
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`call "%VSWHERE%" -latest -products * -property installationPath`) do set "VCVARS=%%i\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS%" (echo Visual Studio Build Tools not found & exit /b 1)
call "%VCVARS%" >nul
if not exist "%HERE%dist" mkdir "%HERE%dist"
if not exist "%HERE%build" mkdir "%HERE%build"

cl /nologo /O2 /EHsc /std:c++17 /LD /MT /W4 /I"%HERE%third_party" "%HERE%layer\hand_freeze_layer.cpp" ^
   /Fo"%HERE%build\\" /Fe"%HERE%dist\hand_freeze_layer.dll" /link /NOLOGO /IMPLIB:"%HERE%build\hand_freeze_layer.lib"
if errorlevel 1 (echo LAYER BUILD FAILED & exit /b 1)

"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /optimize+ /win32icon:"%HERE%app\hand_freeze.ico" ^
   /resource:"%HERE%app\summer.gif",summer.gif /resource:"%HERE%app\winter.gif",winter.gif ^
   /resource:"%HERE%app\Silkscreen-Regular.ttf",Silkscreen-Regular.ttf ^
   /out:"%HERE%dist\HandFreeze.exe" "%HERE%app\HandFreeze.cs" "%HERE%app\FreezeUi.cs"
if errorlevel 1 (echo APP BUILD FAILED & exit /b 1)
copy /y "%HERE%app\hand_freeze.ico" "%HERE%dist\" >nul
echo BUILD OK: %HERE%dist
