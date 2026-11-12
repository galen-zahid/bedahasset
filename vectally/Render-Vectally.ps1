# Render-Vectally.ps1 - render penuh VECTALLY dari PowerShell (Feed, Story, Highlight)
#
#   cd D:\bedahasset\vectally
#   .\Render-Vectally.ps1                      # semua keluarga
#   .\Render-Vectally.ps1 -Family Story        # satu keluarga
#   .\Render-Vectally.ps1 -Stamp 20261111      # lanjutkan folder hasil tertentu
#
# Alur per desain:
#   1. split.py --mode rebuild   : OCR teks + pisah bidang warna (program bedahasset)
#   2. batch_finalize.py         : geometri ulang dengan mesin smooth_native_paths (Codex+Claude),
#                                  font brand, Story S01-S05 pakai paket kurasi, QA + contact sheet
# Hasil siap impor: outputs\VECTALLY-final-<Stamp>\<Family>\NN_<kode>.json
# Aman diulang: desain yang sudah selesai dilewati, tidak ada file yang ditimpa.
param(
    [ValidateSet("All", "Feed", "Story", "Highlight")][string]$Family = "All",
    [string]$Stamp = (Get-Date -Format "yyyyMMdd"),
    [string]$SourceRoot = "",   # default: sources\VECTALLY
    [string]$OutRoot = ""       # default: outputs
)
$ErrorActionPreference = "Stop"
$Vectally = $PSScriptRoot
$Repo = Split-Path $Vectally -Parent
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$Sources = if ($SourceRoot) { $SourceRoot } else { Join-Path $Vectally "sources\VECTALLY" }
$Outs = if ($OutRoot) { $OutRoot } else { Join-Path $Vectally "outputs" }
$Rebuild = Join-Path $Outs "VECTALLY-rebuild-$Stamp"
$Final = Join-Path $Outs "VECTALLY-final-$Stamp"
# Config VECTALLY: tanpa fallback PNG, tanpa layer efek (semua bidang jadi shape native)
$Config = Join-Path $Vectally "config_vectally.yaml"
if (-not (Test-Path $Config)) { throw "Config VECTALLY hilang: $Config" }
if (-not (Test-Path $Py)) { throw "Python venv belum ada: $Py (jalankan D:\bedahasset\setup.ps1)" }
$Families = if ($Family -eq "All") { @("Feed", "Story", "Highlight") } else { @($Family) }

$start = Get-Date
foreach ($f in $Families) {
    Write-Host "`n=== [1/2] Render $f ===" -ForegroundColor Cyan
    Push-Location $Repo
    try {
        & $Py split.py (Join-Path $Sources $f) (Join-Path $Rebuild $f) --mode rebuild --config $Config
        if ($LASTEXITCODE -eq 3) { throw "Model AI belum lengkap. Jalankan ulang perintah yang sama." }
        if ($LASTEXITCODE -ne 0) { Write-Host "Ada desain $f yang gagal; detail di $Rebuild\$f\log.txt. Lanjut." -ForegroundColor Yellow }
    } finally { Pop-Location }
}

Write-Host "`n=== [2/2] Finalisasi (geometri Codex+Claude, font brand, QA) ===" -ForegroundColor Cyan
$tmpSources = $Sources
if ($Family -ne "All") {
    $tmpSources = Join-Path $env:TEMP "vectally-src-$Stamp"
    New-Item -ItemType Directory -Force -Path (Join-Path $tmpSources $Family) | Out-Null
    Copy-Item (Join-Path $Sources "$Family\*.png") (Join-Path $tmpSources $Family) -Force
}
& $Py (Join-Path $Vectally "work\batch_finalize.py") $Rebuild $Final $tmpSources
if ($LASTEXITCODE -ne 0) { throw "Finalisasi gagal (exit $LASTEXITCODE)." }

$mins = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
Write-Host "`nSelesai dalam $mins menit." -ForegroundColor Green
foreach ($f in $Families) {
    $dir = Join-Path $Final $f
    if (Test-Path $dir) {
        $n = (Get-ChildItem $dir -Filter "*.json").Count
        Write-Host ("  {0,-9} {1,3} paket siap impor -> {2}" -f $f, $n, $dir)
    }
}
Write-Host "Cek QA_SHEET.png dan QA_RINGKASAN.csv di tiap folder, lalu kabari Claude untuk impor ke Canva."
