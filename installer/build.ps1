# 配布パッケージ (dist\TelloBlocks, TelloBlocks-portable.zip, TelloBlocks-setup.exe) を作る。
# 使い方:  powershell -ExecutionPolicy Bypass -File installer\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv-build"
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
$py = "$venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip pyinstaller pyserial uflash
if ($LASTEXITCODE) { throw "pip install failed" }

& $py -m unittest discover -s tests
if ($LASTEXITCODE) { throw "tests failed" }

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --onedir --console --name TelloBlocks `
    --add-data "web;web" --add-data "programs\default.json;programs" `
    --collect-submodules serial launcher.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$app = Join-Path $root "dist\TelloBlocks"
Copy-Item installer\files\* $app -Recurse -Force

# micro:bit 用 hex
$hexDir = Join-Path $root "build\hex"
New-Item -ItemType Directory -Force $hexDir, "$app\microbit" | Out-Null
$p = Start-Process "$venv\Scripts\uflash.exe" -ArgumentList "microbit\main.py", $hexDir -NoNewWindow -PassThru
if (-not $p.WaitForExit(60000)) { $p.Kill() }
if (Test-Path "$hexDir\micropython.hex") {
    Copy-Item "$hexDir\micropython.hex" "$app\microbit\tello_handle.hex"
} else {
    Write-Warning "hex を作れませんでした (uflash)。microbit\main.py を手動で書き込んでください。"
}
Copy-Item microbit\main.py "$app\microbit\main.py"

# ZIP (UTF-8 のファイル名で作る)
$zip = Join-Path $root "dist\TelloBlocks-portable.zip"
& $py installer\make_zip.py $app $zip

# Inno Setup
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
              "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if ($iscc) {
    & $iscc installer\TelloBlocks.iss
    if ($LASTEXITCODE) { throw "ISCC failed" }
} else {
    Write-Warning "Inno Setup が無いので setup.exe は作りません (winget install JRSoftware.InnoSetup --scope user)"
}
Get-ChildItem dist -File | Select-Object Name, @{n="MB"; e={[math]::Round($_.Length/1MB, 1)}}
