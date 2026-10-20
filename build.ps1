param([switch]$BuildOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$stageRoot = Join-Path $PSScriptRoot 'stage\YuiCompanion'
$installedRoot = Join-Path $PSScriptRoot 'dist\YuiCompanion'
$installedExe = Join-Path $installedRoot 'YuiCompanion.exe'

& $python -m PyInstaller --noconfirm --windowed --onedir --name YuiCompanion --distpath stage --add-data 'assets;assets' --hidden-import winrt.windows.foundation --hidden-import winrt.windows.foundation.collections --hidden-import winrt.windows.media --hidden-import winrt.windows.storage.streams --exclude-module tkinter --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module pywinauto --exclude-module pycaw app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败；已安装版本未被替换' }

$check = Start-Process -FilePath (Join-Path $stageRoot 'YuiCompanion.exe') -ArgumentList '--self-check' -WindowStyle Hidden -PassThru
if (-not $check.WaitForExit(25000)) { throw '自检超时；已安装版本未被替换' }
if ($check.ExitCode -ne 0) { throw '自检退出异常' }
$report = Get-Content -LiteralPath (Join-Path $stageRoot 'output\build-check.json') -Raw | ConvertFrom-Json
if (-not $report.character_visible -or -not $report.audio_playing) { throw '自检失败；已安装版本未被替换' }
if ($BuildOnly) { Write-Output "自检完成：$stageRoot"; exit 0 }

# Only stop this installation. Other copies and the music client remain untouched.
Get-Process -Name YuiCompanion -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installedExe } | Stop-Process -Force
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'output'),$installedRoot -Force | Out-Null
$settingsPath = Join-Path $installedRoot 'data\settings.json'
if (Test-Path -LiteralPath $settingsPath) {
    Copy-Item -LiteralPath $settingsPath -Destination (Join-Path $PSScriptRoot 'output\preserved-settings.json') -Force
}
# Merge verified program files, keeping all existing user data in place.
$ownedActions = Join-Path $installedRoot '_internal\assets\actions'
if (Test-Path -LiteralPath $ownedActions) {
    $resolvedActions = (Resolve-Path -LiteralPath $ownedActions).Path
    $resolvedInstall = (Resolve-Path -LiteralPath $installedRoot).Path
    if (-not $resolvedActions.StartsWith($resolvedInstall + '\',[System.StringComparison]::OrdinalIgnoreCase)) {
        throw '内置动作路径超出安装目录'
    }
    # Replace only program-owned bundled packs; EXE-side user actions are kept.
    Remove-Item -LiteralPath $resolvedActions -Recurse -Force
}
Get-ChildItem -LiteralPath $stageRoot -Force | Where-Object { $_.Name -notin @('data','output','actions') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $installedRoot -Recurse -Force
}
# Remove only obsolete bundled artwork, never user data.
foreach ($oldAsset in @('yui-guitar.png','guitar-generation-prompt.txt')) {
    $oldAssetPath = Join-Path $installedRoot "_internal\assets\$oldAsset"
    if (Test-Path -LiteralPath $oldAssetPath) {
        Remove-Item -LiteralPath $oldAssetPath -Force
    }
}
Copy-Item -LiteralPath 'README.md' -Destination (Join-Path $installedRoot '使用说明.md') -Force
Copy-Item -LiteralPath 'VALIDATION.md' -Destination (Join-Path $installedRoot '验证结果.md') -Force
Copy-Item -LiteralPath 'REFERENCE_NOTES.md' -Destination (Join-Path $installedRoot '开发参考.md') -Force
Copy-Item -LiteralPath 'ACTION_WORKFLOW.md' -Destination (Join-Path $installedRoot '动作导入规范.md') -Force
if (Test-Path -LiteralPath 'output\motion-demo.mp4') {
    Copy-Item -LiteralPath 'output\motion-demo.mp4' -Destination (Join-Path $installedRoot '动作演示.mp4') -Force
}
if (Test-Path -LiteralPath 'output\corn-demo.gif') {
    Copy-Item -LiteralPath 'output\corn-demo.gif' -Destination (Join-Path $installedRoot '啃玉米演示.gif') -Force
}
if (Test-Path -LiteralPath 'output\new-actions-demo.mp4') {
    Copy-Item -LiteralPath 'output\new-actions-demo.mp4' -Destination (Join-Path $installedRoot '新动作演示.mp4') -Force
}
& $python tools\package.py
if ($LASTEXITCODE -ne 0) { throw '压缩包生成失败' }
