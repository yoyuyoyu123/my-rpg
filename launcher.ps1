param(
    [int]$Port = 8000
)

# ASCII-only source keeps this launcher compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$dataDir = Join-Path $backend 'data'
$pidFile = Join-Path $dataDir 'launcher-process.json'
$setupScript = Join-Path $backend 'setup.ps1'
$gameUrl = "http://127.0.0.1:$Port/"
$settingsUrl = "$gameUrl`?launcher=settings"
$script:serverProcess = $null
$script:setupProcess = $null
$script:lastLogOut = ''
$script:lastLogErr = ''
$script:stopPendingId = 0
$script:restartPending = $false
$script:backendReady = $false

function Test-WujiHealth {
    try {
        $reply = Invoke-RestMethod -Uri "$gameUrl`health" -TimeoutSec 2
        return ($reply.status -eq 'ok' -and $reply.product -eq 'wuji-rpg')
    } catch {
        return $false
    }
}

function Get-OwnedServerProcess {
    # Same launcher session: use the process handle we received from
    # Start-Process first. This avoids a blocking/fragile WMI lookup when the
    # user presses Stop immediately after startup.
    if ($script:serverProcess) {
        try {
            if (-not $script:serverProcess.HasExited) { return $script:serverProcess }
        } catch { $script:serverProcess = $null }
    }
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    try {
        $info = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json
        $processId = [int]$info.pid
        $process = Get-Process -Id $processId -ErrorAction Stop
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
        $command = [string]$details.CommandLine
        if ($command -notmatch 'uvicorn' -or $command -notmatch 'app\.main:app') { return $null }
        return $process
    } catch {
        return $null
    }
}

function Open-Url([string]$Url) {
    try { Start-Process $Url | Out-Null } catch {
        [System.Windows.Forms.MessageBox]::Show("Could not open the browser.`r`n$($_.Exception.Message)", 'Wuji RPG') | Out-Null
    }
}

function Set-LauncherStatus([string]$Text, [System.Drawing.Color]$Color) {
    if ($script:statusLabel) {
        $script:statusLabel.Text = $Text
        $script:statusLabel.ForeColor = $Color
    }
}

function Update-LauncherStatus {
    # 停止后也要显式恢复按钮；不能只在在线分支里设为可用。
    # 某些 Windows 进程退出时序会让启动器先经历一次 offline 刷新，
    # 如果这里不恢复，Start and Play 会看起来像失效了。
    if ($script:playButton) { $script:playButton.Enabled = $true }
    if ($script:settingsButton) { $script:settingsButton.Enabled = $true }
    if ($script:stopPendingId -gt 0) {
        $pending = Get-Process -Id $script:stopPendingId -ErrorAction SilentlyContinue
        if ($pending) {
            Set-LauncherStatus 'Stopping backend...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
            if ($script:playButton) { $script:playButton.Enabled = $false }
            if ($script:settingsButton) { $script:settingsButton.Enabled = $false }
            return
        }
        $script:stopPendingId = 0
        $script:serverProcess = $null
        $script:backendReady = $false
        if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue }
        if ($script:restartPending) {
            # 旧进程确认退出之后才启动新的，否则会撞上「端口已被占用」
            $script:restartPending = $false
            Set-LauncherStatus 'Restarting backend...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
            Start-WujiBackend '' | Out-Null
            return
        }
        Set-LauncherStatus 'Backend stopped - ready to start again' ([System.Drawing.Color]::FromArgb(205, 120, 105))
    }
    # Keep the timer local and non-blocking. An HTTP health probe here can
    # freeze WinForms for its timeout whenever the backend is offline.
    $running = $false
    if ($script:serverProcess) {
        try { $running = -not $script:serverProcess.HasExited } catch { $script:serverProcess = $null }
    }
    if ($script:backendReady -and (-not $script:serverProcess -or $running)) {
        Set-LauncherStatus 'Backend online - ready to play' ([System.Drawing.Color]::FromArgb(105, 210, 175))
        return
    }
    if ($running) {
        Set-LauncherStatus 'Backend is starting...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
    } elseif ($script:setupProcess -and -not $script:setupProcess.HasExited) {
        Set-LauncherStatus 'Installing local environment - this may take a few minutes...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
    } else {
        Set-LauncherStatus 'Backend offline' ([System.Drawing.Color]::FromArgb(205, 120, 105))
    }
}

function Start-WujiBackend([string]$OpenAfter) {
    if (Test-WujiHealth) {
        $script:backendReady = $true
        if ($OpenAfter) { Open-Url $OpenAfter }
        Update-LauncherStatus
        return $true
    }
    if (-not (Test-Path -LiteralPath $python)) {
        Set-LauncherStatus 'Environment missing - click Install / Repair first' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        [System.Windows.Forms.MessageBox]::Show(
            'The local Python environment is not installed yet. Click Install / Repair, wait until it finishes, then click Start and Play.',
            'Wuji RPG - setup required'
        ) | Out-Null
        return $false
    }
    try {
        $check = & $python -c "import fastapi, pydantic, sqlalchemy, aiosqlite, uvicorn" 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($check | Out-String) }
    } catch {
        Set-LauncherStatus 'Environment incomplete - click Install / Repair' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        return $false
    }

    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $script:lastLogOut = Join-Path $dataDir "server-$stamp.out.log"
    $script:lastLogErr = Join-Path $dataDir "server-$stamp.err.log"
    $hostAddress = if ($script:lanCheck.Checked) { '0.0.0.0' } else { '127.0.0.1' }
    $arguments = @('-m', 'uvicorn', 'app.main:app', '--host', $hostAddress, '--port', "$Port")

    try {
        Set-LauncherStatus 'Starting backend...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
        $script:serverProcess = Start-Process -FilePath $python -ArgumentList $arguments `
            -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $script:lastLogOut -RedirectStandardError $script:lastLogErr
        @{
            pid = $script:serverProcess.Id
            port = $Port
            started_at = (Get-Date).ToString('o')
            stdout = $script:lastLogOut
            stderr = $script:lastLogErr
        } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $pidFile

        for ($i = 0; $i -lt 48; $i++) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 250
            if (Test-WujiHealth) {
                $script:backendReady = $true
                Update-LauncherStatus
                if ($OpenAfter) { Open-Url $OpenAfter }
                return $true
            }
            if ($script:serverProcess.HasExited) { break }
        }
        throw 'The backend did not become ready. Open Logs to see the error.'
    } catch {
        $script:backendReady = $false
        Set-LauncherStatus 'Start failed - open Logs for details' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Wuji RPG - start failed') | Out-Null
        return $false
    }
}

function Get-ServerProcessOnPort {
    # 接管不是本启动器起的后端。开发时经常从终端手动跑 uvicorn，
    # 改完代码却没有顺手的方式重启——这正是「后端跑着旧代码」的来源。
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    } catch { return $null }
    foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
        try {
            $details = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
            $command = [string]$details.CommandLine
            # 只认自家后端，别误杀端口上碰巧的别的进程
            if ($command -match 'uvicorn' -and $command -match 'app\.main:app') {
                return Get-Process -Id $procId -ErrorAction Stop
            }
        } catch { continue }
    }
    return $null
}

function Restart-WujiBackend {
    if ($script:stopPendingId -gt 0) { Update-LauncherStatus; return }

    $target = Get-OwnedServerProcess
    if (-not $target) { $target = Get-ServerProcessOnPort }

    if (-not $target) {
        # 本来就没在跑，直接起一个
        Start-WujiBackend '' | Out-Null
        return
    }

    try {
        $targetId = $target.Id
        Stop-Process -Id $targetId -Force -ErrorAction Stop
        # 不在 UI 线程上同步等待：置标记，交给定时器确认退出后再启动。
        $script:stopPendingId = $targetId
        $script:restartPending = $true
        $script:backendReady = $false
        Set-LauncherStatus 'Restarting backend...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
        $script:playButton.Enabled = $false
        $script:settingsButton.Enabled = $false
    } catch {
        $script:restartPending = $false
        [System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Wuji RPG - restart failed') | Out-Null
    }
}

function Stop-WujiBackend {
    if ($script:stopPendingId -gt 0) {
        Update-LauncherStatus
        return
    }
    $owned = Get-OwnedServerProcess
    if (-not $owned) {
        # An externally started backend is intentionally left untouched. Do
        # not run a synchronous health request from the stop click either.
        Set-LauncherStatus 'No backend owned by this launcher' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        Update-LauncherStatus
        return
    }
    try {
        $ownedId = $owned.Id
        Stop-Process -Id $ownedId -Force -ErrorAction Stop
        # Do not wait synchronously on the WinForms UI thread. The timer will
        # confirm exit and re-enable Start and Play on the next tick.
        $script:stopPendingId = $ownedId
        $script:backendReady = $false
        Set-LauncherStatus 'Stopping backend...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
        $script:playButton.Enabled = $false
        $script:settingsButton.Enabled = $false
    } catch {
        [System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Wuji RPG - stop failed') | Out-Null
    }
}

function Start-WujiSetup {
    if ($script:setupProcess -and -not $script:setupProcess.HasExited) { return }
    if (-not (Test-Path -LiteralPath $setupScript)) {
        [System.Windows.Forms.MessageBox]::Show('backend/setup.ps1 is missing.', 'Wuji RPG') | Out-Null
        return
    }
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $script:lastLogOut = Join-Path $dataDir "setup-$stamp.out.log"
    $script:lastLogErr = Join-Path $dataDir "setup-$stamp.err.log"
    try {
        $script:setupProcess = Start-Process -FilePath 'powershell.exe' `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $setupScript) `
            -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $script:lastLogOut -RedirectStandardError $script:lastLogErr
        Set-LauncherStatus 'Installing local environment - this may take a few minutes...' ([System.Drawing.Color]::FromArgb(235, 188, 92))
        $script:setupButton.Enabled = $false
    } catch {
        Set-LauncherStatus 'Setup could not start' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Wuji RPG - setup failed') | Out-Null
    }
}

function Create-DesktopShortcut {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'Wuji RPG.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = "$env:WINDIR\System32\wscript.exe"
        $entry = Join-Path $root ([string]([char]0x542F) + [char]0x52A8 + [char]0x65E0 + [char]0x754C + '.vbs')
        if (-not (Test-Path -LiteralPath $entry)) { $entry = Join-Path $root 'Start Wuji RPG.vbs' }
        $shortcut.Arguments = '"' + $entry + '"'
        $shortcut.WorkingDirectory = $root
        $shortcut.Description = 'Start Wuji RPG without a terminal window'
        $shortcut.Save()
        [System.Windows.Forms.MessageBox]::Show("Desktop shortcut created:`r`n$shortcutPath", 'Wuji RPG') | Out-Null
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Wuji RPG - shortcut failed') | Out-Null
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Wuji RPG Launcher'
$form.Size = New-Object System.Drawing.Size(650, 474)
$form.StartPosition = 'CenterScreen'
$form.BackColor = [System.Drawing.Color]::FromArgb(10, 31, 36)
$form.ForeColor = [System.Drawing.Color]::FromArgb(220, 235, 226)
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = 'WUJI RPG'
$title.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 24)
$title.ForeColor = [System.Drawing.Color]::FromArgb(236, 196, 120)
$title.Location = New-Object System.Drawing.Point(28, 22)
$title.AutoSize = $true
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = 'Local AI interactive fiction launcher'
$subtitle.Location = New-Object System.Drawing.Point(31, 67)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(135, 172, 168)
$subtitle.AutoSize = $true
$form.Controls.Add($subtitle)

$script:statusLabel = New-Object System.Windows.Forms.Label
$script:statusLabel.Text = 'Checking backend...'
$script:statusLabel.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 12)
$script:statusLabel.Location = New-Object System.Drawing.Point(31, 108)
$script:statusLabel.Size = New-Object System.Drawing.Size(570, 28)
$form.Controls.Add($script:statusLabel)

$script:playButton = New-Object System.Windows.Forms.Button
$script:playButton.Text = 'Start and Play'
$script:playButton.Location = New-Object System.Drawing.Point(31, 151)
$script:playButton.Size = New-Object System.Drawing.Size(280, 48)
$script:playButton.BackColor = [System.Drawing.Color]::FromArgb(202, 158, 79)
$script:playButton.ForeColor = [System.Drawing.Color]::FromArgb(18, 31, 33)
$script:playButton.FlatStyle = 'Flat'
$script:playButton.Add_Click({ Start-WujiBackend $gameUrl | Out-Null })
$form.Controls.Add($script:playButton)

$script:settingsButton = New-Object System.Windows.Forms.Button
$script:settingsButton.Text = 'API Settings'
$script:settingsButton.Location = New-Object System.Drawing.Point(325, 151)
$script:settingsButton.Size = New-Object System.Drawing.Size(280, 48)
$script:settingsButton.FlatStyle = 'Flat'
$script:settingsButton.BackColor = [System.Drawing.Color]::FromArgb(31, 70, 73)
$script:settingsButton.ForeColor = [System.Drawing.Color]::FromArgb(220, 235, 226)
$script:settingsButton.Add_Click({ Start-WujiBackend $settingsUrl | Out-Null })
$form.Controls.Add($script:settingsButton)

# 重启单独占一行并做成主色：改完后端代码之后最常按的就是它。
# 之前只有 Stop + Start 两步，中间还得自己判断旧进程退干净没有——
# 漏掉就会出现「后端还跑着旧代码」，而且从界面上完全看不出来。
$restartButton = New-Object System.Windows.Forms.Button
$restartButton.Text = 'Restart Backend (apply code changes)'
$restartButton.Location = New-Object System.Drawing.Point(31, 217)
$restartButton.Size = New-Object System.Drawing.Size(574, 38)
$restartButton.FlatStyle = 'Flat'
$restartButton.BackColor = [System.Drawing.Color]::FromArgb(31, 70, 73)
$restartButton.ForeColor = [System.Drawing.Color]::FromArgb(220, 235, 226)
$restartButton.Add_Click({ Restart-WujiBackend })
$form.Controls.Add($restartButton)

$script:setupButton = New-Object System.Windows.Forms.Button
$script:setupButton.Text = 'Install / Repair'
$script:setupButton.Location = New-Object System.Drawing.Point(31, 261)
$script:setupButton.Size = New-Object System.Drawing.Size(180, 38)
$script:setupButton.FlatStyle = 'Flat'
$script:setupButton.Add_Click({ Start-WujiSetup })
$form.Controls.Add($script:setupButton)

$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = 'Stop Backend'
$stopButton.Location = New-Object System.Drawing.Point(226, 261)
$stopButton.Size = New-Object System.Drawing.Size(180, 38)
$stopButton.FlatStyle = 'Flat'
$stopButton.Add_Click({ Stop-WujiBackend })
$form.Controls.Add($stopButton)

$logButton = New-Object System.Windows.Forms.Button
$logButton.Text = 'Open Logs'
$logButton.Location = New-Object System.Drawing.Point(421, 261)
$logButton.Size = New-Object System.Drawing.Size(184, 38)
$logButton.FlatStyle = 'Flat'
$logButton.Add_Click({ New-Item -ItemType Directory -Force -Path $dataDir | Out-Null; Start-Process explorer.exe -ArgumentList $dataDir })
$form.Controls.Add($logButton)

$shortcutButton = New-Object System.Windows.Forms.Button
$shortcutButton.Text = 'Create Desktop Shortcut'
$shortcutButton.Location = New-Object System.Drawing.Point(31, 319)
$shortcutButton.Size = New-Object System.Drawing.Size(280, 36)
$shortcutButton.FlatStyle = 'Flat'
$shortcutButton.Add_Click({ Create-DesktopShortcut })
$form.Controls.Add($shortcutButton)

$script:lanCheck = New-Object System.Windows.Forms.CheckBox
$script:lanCheck.Text = 'Allow phones on the same network (next start)'
$script:lanCheck.Location = New-Object System.Drawing.Point(325, 326)
$script:lanCheck.Size = New-Object System.Drawing.Size(290, 28)
$script:lanCheck.ForeColor = [System.Drawing.Color]::FromArgb(165, 190, 184)
$form.Controls.Add($script:lanCheck)

$note = New-Object System.Windows.Forms.Label
$note.Text = "Closing this launcher leaves the backend running. Reopen it to stop the server.`r`nAPI keys are configured in the web page and stored only in backend/.env."
$note.Location = New-Object System.Drawing.Point(31, 377)
$note.Size = New-Object System.Drawing.Size(575, 46)
$note.ForeColor = [System.Drawing.Color]::FromArgb(115, 148, 145)
$form.Controls.Add($note)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1000
$timer.Add_Tick({
    if ($script:setupProcess -and $script:setupProcess.HasExited) {
        $exitCode = $script:setupProcess.ExitCode
        $script:setupProcess = $null
        $script:setupButton.Enabled = $true
        if ($exitCode -eq 0) {
            Set-LauncherStatus 'Environment ready - click Start and Play' ([System.Drawing.Color]::FromArgb(105, 210, 175))
        } else {
            Set-LauncherStatus 'Setup failed - open Logs for details' ([System.Drawing.Color]::FromArgb(205, 120, 105))
        }
    } else {
        Update-LauncherStatus
    }
})
$timer.Start()

$form.Add_Shown({
    Update-LauncherStatus
})
$form.Add_FormClosed({ $timer.Stop() })
[void]$form.ShowDialog()
