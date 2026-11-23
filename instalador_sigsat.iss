; Script de Inno Setup 6 para el instalador de SIGSAT
[Setup]
AppName=SIGSAT
AppVersion=1.0
AppPublisher=SIGSAT - Proyecto academico UPIICSA-IPN
DefaultDirName={autopf}\SIGSAT
DefaultGroupName=SIGSAT
DisableProgramGroupPage=yes
OutputDir=salida
OutputBaseFilename=SIGSAT_Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName=SIGSAT
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\SIGSAT\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SIGSAT"; Filename: "{app}\SIGSAT.exe"
Name: "{autodesktop}\SIGSAT"; Filename: "{app}\SIGSAT.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SIGSAT.exe"; Description: "Ejecutar SIGSAT"; Flags: nowait postinstall skipifsilent

; Los datos de la aplicacion se guardan en %LOCALAPPDATA%\SIGSAT y NO se borran al desinstalar.
