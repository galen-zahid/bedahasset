# bedahasset - jalankan pemecah layer
#   .\run.ps1                         # semua gambar di .\in  ->  .\out
#   .\run.ps1 -In D:\desain -Out D:\hasil
#   .\run.ps1 -Force                  # proses ulang yang sudah selesai
#   .\run.ps1 -Mode layers            # mode lama (pecah layer); default: rebuild
param(
    [string]$In = "in",
    [string]$Out = "out",
    [ValidateSet("rebuild", "layers")][string]$Mode = "rebuild",
    [switch]$Force
)
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$vpy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    Write-Host "Belum di-setup. Jalankan setup.bat dulu." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $In)) {
    New-Item -ItemType Directory -Path $In | Out-Null
    Write-Host "Folder '$In' dibuat. Taruh gambar PNG/JPG di sana lalu jalankan lagi." -ForegroundColor Yellow
    exit 0
}
$argsList = @("split.py", $In, $Out, "--mode", $Mode)
if ($Force) { $argsList += "--force" }
& $vpy @argsList
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "`nSelesai. Hasil di: $(Resolve-Path $Out)" -ForegroundColor Green
} elseif ($code -eq 3) {
    Write-Host "`nModel AI belum lengkap (koneksi putus?). Jalankan lagi; download dilanjutkan." -ForegroundColor Yellow
} else {
    Write-Host "`nAda file yang gagal. Detail di $Out\log.txt" -ForegroundColor Yellow
}
exit $code
