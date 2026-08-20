[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ForwardedArguments
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $projectRoot 'run.py'

$candidates = [System.Collections.Generic.List[object]]::new()

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $candidates.Add([pscustomobject]@{ File = $pythonCommand.Source; Prefix = @() })
}

if ($env:LOCALAPPDATA) {
    Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            $candidate = Join-Path $_.FullName 'python.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $candidates.Add([pscustomobject]@{ File = $candidate; Prefix = @() })
            }
        }
}

$pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyCommand) {
    $candidates.Add([pscustomobject]@{ File = $pyCommand.Source; Prefix = @('-3') })
}

if ($env:USERPROFILE) {
    $codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $codexPython -PathType Leaf) {
        $candidates.Add([pscustomobject]@{ File = $codexPython; Prefix = @() })
    }
}

$selected = $null
foreach ($candidate in $candidates) {
    $versionArgs = @($candidate.Prefix) + @('-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)')
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & $candidate.File @versionArgs 2>$null
    $candidateExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($candidateExitCode -eq 0) {
        $selected = $candidate
        break
    }
}

if (-not $selected) {
    throw 'Python 3.10 or newer was not found. Do not use the Python 2.7 bundled with ArcGIS.'
}

$arguments = @($selected.Prefix) + @($runScript) + @($ForwardedArguments)
& $selected.File @arguments
exit $LASTEXITCODE
