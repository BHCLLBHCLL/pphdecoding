<#
编译 NativeBridge（MSVC Build Tools）。

用法:
    powershell -ExecutionPolicy Bypass -File native\build.ps1
#>

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root "native\out"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $Vswhere)) {
    throw "vswhere.exe not found"
}
$VsInstall = & $Vswhere -latest -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    -property installationPath
if (-not $VsInstall) {
    throw "Visual Studio Build Tools with VC++ not found"
}

$VcVars = Join-Path $VsInstall "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $VcVars)) {
    throw "vcvars64.bat not found: $VcVars"
}

$Src = Join-Path $Root "native\scflow_bridge.cpp"
$Dll = Join-Path $OutDir "scflow_bridge.dll"

$ClArgs = @(
    "/nologo", "/LD", "/EHsc", "/O2",
    "/D", "SCF_BRIDGE_BUILD",
    "`"$Src`"",
    "/Fe:`"$Dll`""
)
$Cmd = "`"$VcVars`" && cl $($ClArgs -join ' ')"
Write-Host "Building: $Cmd"
cmd /c $Cmd | Out-Host
if (-not (Test-Path $Dll)) {
    throw "build failed: $Dll not produced"
}
Write-Host "OK -> $Dll"
