# 开发启动脚本
# ============
# 用法（在 backend 目录下）：
#   .\dev.ps1              启动
#   .\dev.ps1 -Stop        只停止，不启动
#   .\dev.ps1 -Port 8001   换端口
#
# 为什么需要这个脚本：
#   Windows 上 Ctrl+C 有时停不干净 uvicorn 的子进程（尤其带 --reload 时），
#   下次启动就会撞上「端口被占」。这个脚本每次启动前先自动清理。

param(
    [int]$Port = 8000,
    [switch]$Stop,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

function Stop-OnPort([int]$p) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return $false }
    $killed = $false
    foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "  停止占用端口 $p 的进程：$($proc.ProcessName) (PID $procId)" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction Stop
            $killed = $true
        } catch {
            Write-Host "  PID $procId 已不存在，跳过" -ForegroundColor DarkGray
        }
    }
    if ($killed) { Start-Sleep -Seconds 2 }
    return $killed
}

Write-Host ""
Write-Host "无界·叙事引擎 后端" -ForegroundColor Cyan

# 清理端口
Stop-OnPort $Port | Out-Null

if ($Stop) {
    Write-Host "  已停止。" -ForegroundColor Green
    Write-Host ""
    exit 0
}

# 检查虚拟环境
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "  找不到虚拟环境，请先运行：" -ForegroundColor Red
    Write-Host "    python -m venv .venv" -ForegroundColor Gray
    Write-Host "    .venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Gray
    exit 1
}

# 检查配置
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  提示：还没有 .env，服务能启动但没有可用的模型。" -ForegroundColor Yellow
    Write-Host "        复制 .env.example 为 .env 并填入 API Key。" -ForegroundColor DarkGray
}

# 局域网地址（方便手机访问）
$lan = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  本机：   http://127.0.0.1:$Port/" -ForegroundColor Green
if ($lan) { Write-Host "  手机：   http://${lan}:$Port/   (需同一 WiFi)" -ForegroundColor Green }
Write-Host "  接口文档：http://127.0.0.1:$Port/docs" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Ctrl+C 停止" -ForegroundColor DarkGray
Write-Host ""

$args = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
if (-not $NoReload) { $args += "--reload" }

Push-Location $PSScriptRoot
try { & $py @args } finally { Pop-Location }
