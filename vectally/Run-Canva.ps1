# VECTALLY - bangun desain Canva dari resep: paket native + TypeCraft, lalu ekspor PNG untuk QA.
#   .\Run-Canva.ps1 -Code A09
# Syarat: gateway CUSBE (D:\Codex\cusbe-remote-mcp), sesi login Canva di browser gateway,
#         dan akses sementara dibuka dulu di laptop:
#         & 'D:\Codex\cusbe-remote-mcp\scripts\Authorize-Privileged.ps1' -Minutes 10
# Robot tidak memanggil AI. Setiap run membuat desain Canva BARU (desain lama tidak diubah).
param(
    [Parameter(Mandatory = $true)][string]$Code,
    [string]$PythonExe = 'D:\bedahasset\.venv\Scripts\python.exe',
    [string]$NodeExe = 'D:\Node js\node.exe',
    [string]$GatewayRoot = 'D:\Codex\cusbe-remote-mcp',
    [string]$BoxJson
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$here = $PSScriptRoot
& $PythonExe (Join-Path $here ("recipes\" + $Code.ToLower() + ".py"))
if ($LASTEXITCODE -ne 0) { throw "Resep $Code gagal" }
& $PythonExe (Join-Path $here 'recipes\typecraft_quads.py') $Code
if ($LASTEXITCODE -ne 0) { throw "Quad TypeCraft $Code gagal" }
$prep = @((Join-Path $here 'robot\prepare_job.py'), $Code)
if ($BoxJson) { $prep += @('--box-json', $BoxJson) }
& $PythonExe @prep
if ($LASTEXITCODE -ne 0) { throw "Persiapan job $Code gagal" }
$env:CUSBE_GATEWAY_ROOT = $GatewayRoot
& $NodeExe (Join-Path $here 'robot\canva_robot.mjs') (Join-Path $here "outputs\VECTALLY-canva\$Code\JOB.json") --full
if ($LASTEXITCODE -ne 0) { throw "Robot Canva belum lulus; lihat FAILED.json di outputs\VECTALLY-canva\$Code\runs" }
Write-Host "Selesai. Bukti di outputs\VECTALLY-canva\$Code\runs" -ForegroundColor Green
