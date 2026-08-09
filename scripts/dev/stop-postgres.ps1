[CmdletBinding(SupportsShouldProcess)]
param()

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

function Get-ProjectPostgresDataDirectory {
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

    return $resolvedData
}

$dataDirectory = Get-ProjectPostgresDataDirectory
$pgCtl = (Get-Command pg_ctl.exe -ErrorAction Stop).Source

& $pgCtl status -D $dataDirectory *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Output "Project-owned PostgreSQL cluster is already stopped."
    exit 0
}

if ($PSCmdlet.ShouldProcess($dataDirectory, "Stop only the project-owned PostgreSQL cluster")) {
    & $pgCtl stop -D $dataDirectory -m fast
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL failed to stop cleanly."
    }
}
