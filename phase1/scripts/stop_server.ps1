param([int]$Port = 8000)

# 停掉监听该端口的进程，以及命令行里带 uvicorn server.main 的 python 进程
$targets = @()

try {
    $targets += (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop).OwningProcess
} catch { }

try {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*uvicorn server.main*' } |
        ForEach-Object { $targets += $_.ProcessId }
} catch { }

$targets = $targets | Where-Object { $_ -and $_ -ne 0 } | Sort-Object -Unique

if (-not $targets) {
    Write-Host "Nothing is listening on port $Port."
    exit 0
}

foreach ($procId in $targets) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "Stopped PID $procId"
    } catch {
        Write-Host "Cannot stop PID ${procId}: $($_.Exception.Message)"
    }
}

Start-Sleep -Milliseconds 500
$still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($still) { Write-Host "Port $Port is still in use." } else { Write-Host "Port $Port is free." }
