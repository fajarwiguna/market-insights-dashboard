param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$frontendDirectory = Join-Path $projectRoot "frontend"
$pythonExecutable = Join-Path $projectRoot ".venv\Scripts\python.exe"
$nextCli = Join-Path $frontendDirectory "node_modules\next\dist\bin\next"
$logDirectory = Join-Path $projectRoot "runtime\logs\app"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$script:managedServices = @()

function Test-PortAvailable {
    param([int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Start-LoggedService {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )

    $stdoutPath = Join-Path $logDirectory "$runId-$Name.stdout.log"
    $stderrPath = Join-Path $logDirectory "$runId-$Name.stderr.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $service = [pscustomobject]@{
        Name = $Name
        Process = $process
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
    }
    $script:managedServices += $service
    Write-Host "Menyalakan $Name (PID $($process.Id))"
}

function Show-ServiceLogs {
    foreach ($service in $script:managedServices) {
        foreach ($logPath in @($service.StdoutPath, $service.StderrPath)) {
            if (Test-Path -LiteralPath $logPath) {
                Write-Host "`n--- $logPath (baris terakhir) ---" -ForegroundColor DarkCyan
                Get-Content -LiteralPath $logPath -Tail 35
            }
        }
    }
}

function Stop-ManagedServices {
    $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
    for ($index = $script:managedServices.Count - 1; $index -ge 0; $index--) {
        $service = $script:managedServices[$index]
        try {
            if (-not $service.Process.HasExited) {
                & $taskkill /PID $service.Process.Id /T /F 2>$null | Out-Null
            }
        } catch {
            # Proses mungkin sudah berhenti saat cleanup dimulai.
        }
    }
}

function Read-RefreshTimes {
    if (Test-Path Env:REFRESH_TIMES) {
        return $env:REFRESH_TIMES.Trim().Trim('"').Trim("'")
    }

    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) { return "" }
    $setting = Get-Content -LiteralPath $envFile |
        Where-Object { $_ -match '^\s*REFRESH_TIMES\s*=' } |
        Select-Object -Last 1
    if (-not $setting) { return "" }

    $value = ($setting -split "=", 2)[1].Trim()
    $value = ($value -split '\s+#', 2)[0].Trim().Trim('"').Trim("'")
    return $value
}

$exitCode = 0
try {
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw "Python virtualenv tidak ditemukan: $pythonExecutable`nBuat .venv dan install backend/requirements.txt terlebih dahulu."
    }
    if (-not (Test-Path -LiteralPath $nextCli)) {
        throw "Dependensi frontend belum tersedia. Jalankan 'npm ci' sekali dari direktori frontend."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env"))) {
        throw "File .env belum ada di root project. Salin .env.example menjadi .env dan isi konfigurasi."
    }

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $nodeCommand) {
        throw "Node.js tidak ditemukan di PATH. Install Node.js lalu buka PowerShell baru."
    }
    if ($ApiPort -eq $FrontendPort) {
        throw "Port API dan frontend harus berbeda."
    }

    foreach ($port in @($ApiPort, $FrontendPort)) {
        if (-not (Test-PortAvailable -Port $port)) {
            throw "Port $port sedang digunakan. Hentikan app lama yang memakai port tersebut, lalu jalankan script lagi."
        }
    }

    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

    $backendArguments = @(
        "-u", "-m", "uvicorn", "market_report.api.main:app",
        "--app-dir", "backend/src",
        "--host", "127.0.0.1", "--port", "$ApiPort",
        "--reload", "--reload-dir", "backend/src"
    )
    Start-LoggedService -Name "api" -FilePath $pythonExecutable `
        -ArgumentList $backendArguments -WorkingDirectory $projectRoot

    Start-LoggedService -Name "worker" -FilePath $pythonExecutable `
        -ArgumentList @("-u", "backend/src/market_report/worker/main.py") `
        -WorkingDirectory $projectRoot

    $refreshTimes = Read-RefreshTimes
    if ($refreshTimes) {
        $timePattern = '^(?:(?:[01]\d|2[0-3]):[0-5]\d)(?:,(?:(?:[01]\d|2[0-3]):[0-5]\d))*$'
        if ($refreshTimes -match $timePattern) {
            Start-LoggedService -Name "scheduler" -FilePath $pythonExecutable `
                -ArgumentList @("-u", "backend/src/market_report/scheduler/main.py") `
                -WorkingDirectory $projectRoot
        } else {
            Write-Warning "Scheduler tidak dinyalakan karena REFRESH_TIMES tidak valid. Gunakan format HH:MM,HH:MM atau kosongkan untuk menonaktifkan jadwal."
        }
    } else {
        Write-Host "Scheduler tidak dinyalakan (REFRESH_TIMES kosong)."
    }

    $nextArgument = '"' + $nextCli + '"'
    $frontendArguments = @($nextArgument, "dev", "--hostname", "127.0.0.1", "--port", "$FrontendPort")
    Start-LoggedService -Name "frontend" -FilePath $nodeCommand.Source `
        -ArgumentList $frontendArguments -WorkingDirectory $frontendDirectory

    $apiReady = $false
    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        foreach ($service in $script:managedServices) {
            $service.Process.Refresh()
            if ($service.Process.HasExited) {
                throw "$($service.Name) berhenti saat startup (exit code $($service.Process.ExitCode))."
            }
        }

        if (-not $apiReady) {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
                $apiReady = $health.status -eq "ok"
            } catch { }
        }
        if (-not $frontendReady) {
            try {
                Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -TimeoutSec 2 -UseBasicParsing | Out-Null
                $frontendReady = $true
            } catch { }
        }
        if ($apiReady -and $frontendReady) { break }
        Start-Sleep -Seconds 1
    }

    if (-not $apiReady -or -not $frontendReady) {
        throw "API atau frontend belum siap dalam 60 detik. Periksa log di $logDirectory."
    }

    Write-Host "`nDaily Market Report berjalan:" -ForegroundColor Green
    Write-Host "  Website : http://127.0.0.1:$FrontendPort"
    Write-Host "  API     : http://127.0.0.1:$ApiPort"
    Write-Host "  Log     : $logDirectory"
    Write-Host "Tekan Ctrl+C untuk menghentikan seluruh proses."
    try { Start-Process "http://127.0.0.1:$FrontendPort" } catch {
        Write-Warning "Browser tidak dapat dibuka otomatis; buka alamat website di atas secara manual."
    }

    while ($true) {
        foreach ($service in $script:managedServices) {
            $service.Process.Refresh()
            if ($service.Process.HasExited) {
                throw "$($service.Name) berhenti (exit code $($service.Process.ExitCode))."
            }
        }
        Start-Sleep -Seconds 1
    }
} catch {
    $exitCode = 1
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    if ($script:managedServices.Count -gt 0) { Show-ServiceLogs }
} finally {
    if ($script:managedServices.Count -gt 0) {
        Write-Host "`nMenghentikan proses app..."
        Stop-ManagedServices
    }
}

if ($exitCode -ne 0) { exit $exitCode }
