$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "tools\CurseForge Discord Bot Manager.vbs"
$shortcutPath = Join-Path $root "CurseForge Discord Bot Manager.lnk"
$iconPath = Join-Path $root "tools\bot-manager.ico"

if (-not (Test-Path -LiteralPath $target)) {
    throw "Launcher not found: $target"
}

if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Icon not found: $iconPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "CurseForge Discord Bot Manager"
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"
