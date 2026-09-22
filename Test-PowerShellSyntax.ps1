[CmdletBinding()]
param([string]$Root = $PSScriptRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$errorsFound = New-Object System.Collections.Generic.List[string]
$files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.ps1')
foreach ($file in $files) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors)
    foreach ($parseError in @($parseErrors)) {
        $errorsFound.Add(('{0}:{1}:{2} {3}' -f $file.FullName, $parseError.Extent.StartLineNumber, $parseError.Extent.StartColumnNumber, $parseError.Message))
    }
}
if ($errorsFound.Count -gt 0) {
    Write-Host '[FAIL] PowerShell syntax errors:' -ForegroundColor Red
    foreach ($item in $errorsFound) { Write-Host $item -ForegroundColor Red }
    exit 1
}
Write-Host ('[OK] PowerShell syntax valid: ' + $files.Count + ' script(s)') -ForegroundColor Green
exit 0
