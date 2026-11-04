# bedahasset - instalasi sekali jalan (Windows PowerShell)
#   powershell -ExecutionPolicy Bypass -File setup.ps1          # CPU
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Gpu     # GPU NVIDIA (CUDA 12.4)
# Aman dijalankan berulang: langkah yang sudah beres dilewati / dilanjutkan.
param([switch]$Gpu)

$ErrorActionPreference = "Continue"   # native tools write warnings to stderr; we check $LASTEXITCODE
Set-Location -Path $PSScriptRoot

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nGAGAL: $msg" -ForegroundColor Red; exit 1 }

Step "Cek Python 3.11"
$pyExe = $null; $pyArgs = @()
try { $v = & py -3.11 --version 2>&1; if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-3.11") } } catch {}
if (-not $pyExe) {
    try { $v = & python --version 2>&1; if ("$v" -match "3\.11") { $pyExe = "python" } } catch {}
}
if (-not $pyExe) { Fail "Python 3.11 tidak ditemukan. Install dari https://www.python.org/downloads/release/python-3119/ (centang 'Add to PATH'), lalu jalankan lagi." }
Write-Host $v

Step "Cek ruang disk"
$drive = (Get-Item $PSScriptRoot).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB, 1)
Write-Host "Drive $($drive.Name): kosong $freeGB GB (library butuh ~2.5 GB)"
if ($freeGB -lt 3) { Write-Host "PERINGATAN: ruang disk tipis, instalasi bisa gagal." -ForegroundColor Yellow }
$home_drive = (Get-Item $env:USERPROFILE).PSDrive
$homeFree = [math]::Round($home_drive.Free / 1GB, 1)
Write-Host "Drive $($home_drive.Name): (tempat model AI) kosong $homeFree GB (model butuh ~2 GB)"
if ($homeFree -lt 2.5) {
    Write-Host "PERINGATAN: ruang untuk model kurang. Isi 'cache_dir' di config.yaml dengan folder di drive lain, mis. D:\ai-cache" -ForegroundColor Yellow
}

Step "Buat virtual environment (.venv)"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $venvArgs = $pyArgs + @("-m", "venv", ".venv")
    & $pyExe @venvArgs
    if ($LASTEXITCODE -ne 0) { Fail "gagal membuat .venv" }
} else { Write-Host ".venv sudah ada" }
$vpy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

Step "Update pip"
& $vpy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade gagal (cek koneksi internet)" }

Step "Install PyTorch"
$index = if ($Gpu) { "https://download.pytorch.org/whl/cu124" } else { "https://download.pytorch.org/whl/cpu" }
& $vpy -m pip install torch torchvision --index-url $index --retries 10 --timeout 60
if ($LASTEXITCODE -ne 0) { Fail "install torch gagal. Jalankan setup lagi (akan dilanjutkan)." }

Step "Install library lain"
& $vpy -m pip install -r requirements.txt --retries 10 --timeout 60
if ($LASTEXITCODE -ne 0) { Fail "install requirements gagal. Jalankan setup lagi." }
& $vpy -m pip install --no-deps simple-lama-inpainting==0.1.2 --retries 10
if ($LASTEXITCODE -ne 0) { Fail "install simple-lama-inpainting gagal." }
if ($Gpu) {
    & $vpy -m pip uninstall -y onnxruntime
    & $vpy -m pip install onnxruntime-gpu --retries 10
}

Step "Cek instalasi"
& $vpy split.py --check
if ($LASTEXITCODE -ne 0) { Fail "ada library yang belum terpasang (lihat di atas)" }

Step "Download model AI (~2 GB, bisa dilanjutkan kalau putus)"
& $vpy split.py --download-models
if ($LASTEXITCODE -ne 0) { Fail "download model belum selesai. Jalankan setup lagi, download akan DILANJUTKAN." }

if (-not (Test-Path "in")) { New-Item -ItemType Directory -Path "in" | Out-Null }
Write-Host "`nSELESAI. Taruh gambar di folder 'in', lalu jalankan run.bat (atau .\run.ps1)." -ForegroundColor Green
