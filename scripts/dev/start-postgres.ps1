[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 55432
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Test-Path -LiteralPath "variable:PSNativeCommandUseErrorActionPreference") {
    Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $false -Scope Script
}

function Assert-NoProjectPathReparsePoint {
    param([string]$LocalAppData)

    $currentPath = $LocalAppData
    foreach ($component in @("stock-research-agent", "postgres", "data")) {
        $currentPath = Join-Path $currentPath $component
        if (-not (Test-Path -LiteralPath $currentPath -PathType Container)) {
            throw "Project-owned PostgreSQL path does not exist: $currentPath"
        }
        $item = Get-Item -LiteralPath $currentPath -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing PostgreSQL action through reparse point: $currentPath"
        }
    }

    return $currentPath
}

function Get-ProjectPostgresPaths {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is required to locate the project-owned PostgreSQL cluster."
    }

    $configuredData = Assert-NoProjectPathReparsePoint -LocalAppData $env:LOCALAPPDATA
    $configuredRoot = Split-Path -Parent $configuredData

    $resolvedRoot = (Resolve-Path -LiteralPath $configuredRoot).Path
    $resolvedData = (Resolve-Path -LiteralPath $configuredData).Path
    $rootPrefix = $resolvedRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedData.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing PostgreSQL action outside the project-owned root."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedData "PG_VERSION") -PathType Leaf)) {
        throw "The project-owned data directory is not an initialized PostgreSQL cluster."
    }

    [pscustomobject]@{
        Root = $resolvedRoot
        Data = $resolvedData
        Log = Join-Path $resolvedRoot "postgres.log"
    }
}

$paths = Get-ProjectPostgresPaths
$pgCtl = (Get-Command pg_ctl.exe -ErrorAction Stop).Source
$postgres = (Get-Command postgres.exe -ErrorAction Stop).Source
$version = & $postgres --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch "PostgreSQL\) 17\.") {
    throw "PostgreSQL 17 is required; detected: $version"
}

& $pgCtl status -D $paths.Data *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Project-owned PostgreSQL cluster is already running."
    exit 0
}

if ($PSCmdlet.ShouldProcess($paths.Data, "Start project-owned PostgreSQL 17 on 127.0.0.1:$Port")) {
    & $pgCtl start -D $paths.Data -l $paths.Log -o "-h 127.0.0.1 -p $Port"
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL failed to start. Review $($paths.Log)."
    }

    $pgIsReady = (Get-Command pg_isready.exe -ErrorAction Stop).Source
    & $pgIsReady -h 127.0.0.1 -p $Port
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL started but did not become ready on port $Port."
    }
}
