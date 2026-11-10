[CmdletBinding()]
param(
    [ValidateSet('Status','Doctor','Audit','BuildGraphics','Compose','Compare')]
    [string]$Action = 'Status',
    [string[]]$Codes = @(),
    [switch]$AllSupported,
    [string]$PythonExe = 'D:/bedahasset/.venv/Scripts/python.exe',
    # Folder sumber PNG (Feed/Story/Highlight). Default: <repo>/sources/VECTALLY.
    [string]$SourceRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ManifestPath = Join-Path $PSScriptRoot 'jobs.json'
$CataloguePath = Join-Path $PSScriptRoot 'FONT_CATALOGUE.json'
$JobManifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
# Resep Python membaca path dari environment (work/vpaths.py); tidak ada lagi D:/ atau C:/ di resep.
$env:VECTALLY_ROOT = $WorkspaceRoot
if ($SourceRoot) { $env:VECTALLY_SOURCES = [IO.Path]::GetFullPath($SourceRoot) }
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$RunDirectory = Join-Path $PSScriptRoot "runs/$RunStamp-$Action"

function Get-PropertyValue($Object, [string]$Name) {
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -ne $Property) { return $Property.Value }
    return $null
}

function Resolve-WorkspacePath([string]$Relative) {
    $Full = [IO.Path]::GetFullPath((Join-Path $WorkspaceRoot $Relative))
    $Prefix = $WorkspaceRoot.TrimEnd([char[]]"\/") + [IO.Path]::DirectorySeparatorChar
    if (-not $Full.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path di luar workspace ditolak: $Relative"
    }
    return $Full
}

function Invoke-RecipeStep($Step, [string]$LogPath) {
    $Script = Resolve-WorkspacePath $Step.script
    if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw "Script hilang: $Script" }
    $Engine = if ($Step.engine -eq 'python') { $PythonExe } else { (Get-Command node -ErrorAction Stop).Source }
    $Arguments = @($Script)
    $Extra = Get-PropertyValue $Step 'args'
    if ($null -ne $Extra) { $Arguments += @($Extra) }
    Push-Location -LiteralPath $WorkspaceRoot
    try {
        & $Engine @Arguments 2>&1 | Tee-Object -FilePath $LogPath -Append | Out-Host
        $Code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($Code -ne 0) { throw "Proses gagal (exit $Code): $Script. Lihat $LogPath" }
}

function Invoke-PackageAudit([string]$Output, [string[]]$Packages = @()) {
    $Arguments = @(
        (Join-Path $PSScriptRoot 'audit_package.py'),
        '--root', $WorkspaceRoot,
        '--manifest', $ManifestPath,
        '--catalogue', $CataloguePath,
        '--output', $Output
    )
    if ($Packages.Count -gt 0) { $Arguments += '--packages'; $Arguments += $Packages }
    & $PythonExe @Arguments | Out-Host
    $Code = $LASTEXITCODE
    if ($Code -notin @(0,2)) { throw "Audit tidak berjalan: exit $Code" }
    return $Code
}

if ($Action -eq 'Status') {
    $Rows = Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'VECTALLY_STATUS.csv')
    $Rows | Group-Object phase | Select-Object Name,Count | Format-Table -AutoSize
    Write-Host '84 sumber; tidak ada pernyataan 100% final. Baca REPORT_VECTALLY.md dan STATE.json.'
    return
}

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw "Python belum ditemukan: $PythonExe" }
New-Item -ItemType Directory -Path $RunDirectory -Force | Out-Null
if ($Action -eq 'Doctor') {
    & $PythonExe -c "import sys,cv2,numpy,PIL,resvg_py,scipy; print(sys.executable); print('Dependensi render tersedia')"
    if ($LASTEXITCODE -ne 0) { throw 'Dependensi Python belum lengkap. Skrip ini tidak memasang paket otomatis.' }
    Get-Command node | Select-Object Name,Source | Format-Table -AutoSize
    Write-Host "Workspace: $WorkspaceRoot"
    Write-Host 'Canva tidak dibuka atau diubah.'
    return
}

if ($Action -eq 'Audit') {
    $Rows = Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'VECTALLY_STATUS.csv')
    $SourceChecks = foreach ($Row in $Rows) {
        $SourcePath = $Row.source
        if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
            $Leaf = Split-Path $Row.source -Leaf
            $Family = Split-Path (Split-Path $Row.source -Parent) -Leaf
            $Base = if ($env:VECTALLY_SOURCES) { $env:VECTALLY_SOURCES } else { Join-Path $WorkspaceRoot 'sources/VECTALLY' }
            $SourcePath = Join-Path (Join-Path $Base $Family) $Leaf
        }
        $Exists = Test-Path -LiteralPath $SourcePath -PathType Leaf
        $Actual = if ($Exists) { (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
        [pscustomobject]@{ code=$Row.code; source=$Row.source; exists=$Exists; hashMatches=($Actual -eq $Row.sha256); actualSha256=$Actual }
    }
    $SourceChecks | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RunDirectory 'SOURCE_AUDIT.json') -Encoding UTF8
    $AuditExit = Invoke-PackageAudit (Join-Path $RunDirectory 'PACKAGE_AUDIT.json')
    $SourceFailures = @($SourceChecks | Where-Object { -not $_.exists -or -not $_.hashMatches })
    Write-Host "Sumber: $($Rows.Count); sumber bermasalah: $($SourceFailures.Count)"
    Write-Host "Laporan: $RunDirectory"
    Write-Host 'Font Asap heavy pada kandidat S06 memang harus menghasilkan blocker.'
    if ($SourceFailures.Count -gt 0 -or $AuditExit -ne 0) { exit 2 }
    exit 0
}

$PropertyName = @{ BuildGraphics='build'; Compose='compose'; Compare='compare' }[$Action]
$Recipes = @($JobManifest.recipes | Where-Object { $null -ne (Get-PropertyValue $_ $PropertyName) })
if ($AllSupported) {
    if ($Codes.Count -gt 0) { throw 'Pilih -Codes atau -AllSupported, jangan keduanya.' }
    $Codes = @($Recipes | ForEach-Object { $_.code })
}
if ($Codes.Count -eq 0) { throw "Sebutkan -Codes. Yang didukung untuk $Action : $($Recipes.code -join ', ')" }
foreach ($Code in $Codes) {
    if ($Code -notin @($Recipes | ForEach-Object { $_.code })) {
        throw "Belum ada resep $Action untuk $Code. Tidak akan menebak atau mengganti metode."
    }
}
$SeenSteps = @{}
foreach ($Code in $Codes) {
    $Recipe = $Recipes | Where-Object { $_.code -eq $Code } | Select-Object -First 1
    $OutputDirectory = Resolve-WorkspacePath $Recipe.outputDir
    if ($Action -in @('BuildGraphics','Compose') -and (Test-Path -LiteralPath $OutputDirectory)) {
        $Backup = Join-Path $RunDirectory "backup/$Code"
        New-Item -ItemType Directory -Path $Backup -Force | Out-Null
        Copy-Item -LiteralPath $OutputDirectory -Destination $Backup -Recurse
    }
    foreach ($Step in @(Get-PropertyValue $Recipe $PropertyName)) {
        $StepKey = $Step | ConvertTo-Json -Compress -Depth 6
        if ($SeenSteps.ContainsKey($StepKey)) { continue }
        $SeenSteps[$StepKey] = $true
        Invoke-RecipeStep $Step (Join-Path $RunDirectory "$Code.log")
    }
    if ($Action -in @('BuildGraphics','Compose')) {
        $PackageName = if ($Action -eq 'BuildGraphics') { $Recipe.graphicsPackage } else { $Recipe.candidatePackage }
        $PackageFile = Join-Path $OutputDirectory $PackageName
        $AuditExit = Invoke-PackageAudit (Join-Path $RunDirectory "$Code-package-audit.json") @($PackageFile)
        if ($AuditExit -ne 0) { throw "Paket $Code diblokir audit. Tidak ada unggahan Canva. Lihat $RunDirectory" }
    }
}
Write-Host "Selesai menjalankan resep lokal: $($Codes -join ', '). Laporan: $RunDirectory"
Write-Host 'Ini bukan sertifikasi final. Impor Canva, ekspor aktual, pemeriksaan visual, dan buyer test tetap diperlukan.'
