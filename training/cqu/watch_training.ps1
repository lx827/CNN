# 只读训练监视窗口；本脚本不会启动、继续或终止模型训练。
param(
    [Parameter(Mandatory=$true)][string]$Runs,
    [Parameter(Mandatory=$true)][string]$Output,
    [switch]$History
)
$ErrorActionPreference = 'Stop'
$trainingRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$Host.UI.RawUI.WindowTitle = 'O9 训练日志与曲线监视（只读）'
Push-Location $trainingRepoRoot
try {
    . ./cloud/venv/Scripts/Activate.ps1
    $monitorArguments = @('-X', 'utf8', '-m', 'training.cqu.monitor', '--runs', $Runs, '--output', $Output, '--watch')
    if ($History) { $monitorArguments += '--history' }
    & python @monitorArguments
} finally {
    Pop-Location
}
