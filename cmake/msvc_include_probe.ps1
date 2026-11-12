param([string]$Compiler, [string]$Source, [string]$Object)
$ErrorActionPreference = 'Stop'
# Decode MSVC output using the console code page, or ANSI without a console.
# Keep this script ASCII so Windows PowerShell 5 can load it without a BOM.
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class CnnConsoleCodePage {
    [DllImport("kernel32.dll")] public static extern uint GetConsoleOutputCP();
    [DllImport("kernel32.dll")] public static extern uint GetACP();
}
'@
$codepage = [CnnConsoleCodePage]::GetConsoleOutputCP()
if ($codepage -eq 0) { $codepage = [CnnConsoleCodePage]::GetACP() }
$process = New-Object System.Diagnostics.Process
$process.StartInfo.FileName = $Compiler
$process.StartInfo.Arguments = '/nologo /showIncludes /c "' + $Source + '" /Fo"' + $Object + '"'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.RedirectStandardOutput = $true
$process.StartInfo.RedirectStandardError = $true
$encoding = [System.Text.Encoding]::GetEncoding([int]$codepage)
$process.StartInfo.StandardOutputEncoding = $encoding
$process.StartInfo.StandardErrorEncoding = $encoding
$null = $process.Start()
$stdout = $process.StandardOutput.ReadToEndAsync()
$stderr = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::Write($stdout.Result)
[Console]::Write($stderr.Result)
exit $process.ExitCode
