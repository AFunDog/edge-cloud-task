param(
    [string]$Task = "姿态识别",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "src\frontend\edge_frontend"
$env:PYTHONPATH = Join-Path $root "src"
$env:EDGE_TASK = $Task

if (-not (Test-Path $python)) {
    throw "未找到 $python，请先创建虚拟环境并安装项目依赖。"
}

if (-not $SkipInstall -and -not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "[edge-dev] 安装边端前端依赖..."
    & npm.cmd --prefix $frontend install
}

$processes = @()

function Start-EdgeProcess {
    param([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory)
    Write-Host "[edge-dev] 启动 $Name"
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru
    $script:processes += $process
}

function Wait-EdgeApi {
    $deadline = (Get-Date).AddSeconds(60)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 2
            if ($response.status -eq "ok") {
                Write-Host "[edge-dev] 边端 API 已就绪"
                return
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 400
    }
    throw "边端 API 在 60 秒内未就绪。最后错误：$lastError"
}

try {
    Start-EdgeProcess "边端后端" $python @("-m", "uvicorn", "backend.edge_api.main:app", "--reload", "--port", "8001") $root
    Start-EdgeProcess "边端前端" "npm.cmd" @("--prefix", $frontend, "run", "dev") $root
    Wait-EdgeApi

    Write-Host ""
    Write-Host "[edge-dev] 边端后端（含采集器）和前端已启动"
    Write-Host "[edge-dev] 前端: http://localhost:5174"
    Write-Host "[edge-dev] 后端: http://localhost:8001/docs"
    Write-Host "[edge-dev] 按 Ctrl+C 停止全部模块"

    while ($true) {
        $exited = $processes | Where-Object { $_.HasExited }
        if ($exited) { throw "子进程提前退出，退出码: $($exited[0].ExitCode)" }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`n[edge-dev] 正在停止全部模块..."
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
