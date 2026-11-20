# Starts the D.I.R.T.T. nav sim (WSL: SITL + nav_sim.py + Cloudflare tunnel) when Windows boots,
# before anyone logs in, and keeps it running.
#
# Run in PowerShell AS ADMINISTRATOR, from this folder:
#     powershell -ExecutionPolicy Bypass -File .\register_task.ps1
#
# It asks for your Windows password (for a Microsoft account, that account's password, not the PIN),
# so the task can run while nobody is logged in. If the account has no password, leave it blank:
# the sim then starts at log-on (and a password-less account signs in by itself at boot).
# Linux user isn't "dirtt"?  add  -LinuxUser <name>   Distro isn't Ubuntu-24.04?  add  -Distro <name>
# Remove it later with:  Unregister-ScheduledTask -TaskName "DIRTT nav sim"

param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$LinuxUser = "dirtt"
)

$script = "/home/$LinuxUser/dirtt/code/Navigation/server/start_sim.sh"
# conhost --headless: no console window for someone to close by accident
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\conhost.exe" `
    -Argument "--headless $env:WINDIR\System32\wsl.exe -d $Distro -u $LinuxUser -- bash -lc $script"

$atBoot = New-ScheduledTaskTrigger -AtStartup
$atBoot.Delay = "PT1M"                       # give networking a minute after boot
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# Watchdog: also try every 10 minutes. If the sim is already running the task is skipped
# (MultipleInstances IgnoreNew, and start_sim.sh refuses a second copy), so this only restarts it
# after a crash, an update restart of WSL, or a "pkill -f start_sim.sh".
$atLogon.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$cred = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" `
    -Message "Windows password for $env:USERNAME (leave blank if the account has none)"
$pw = $cred.GetNetworkCredential().Password

if ([string]::IsNullOrEmpty($pw)) {
    # No password: a task can't run before log-on, so start it at log-on. An account with no
    # password signs in by itself at boot, so the sim still comes up after a restart.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName "DIRTT nav sim" -Description "D.I.R.T.T. navigation sim (WSL)" `
        -Action $action -Trigger $atLogon -Settings $settings -Principal $principal -Force
    Write-Host "No password given: the sim starts when $env:USERNAME signs in."
} else {
    Register-ScheduledTask -TaskName "DIRTT nav sim" -Description "D.I.R.T.T. navigation sim (WSL)" `
        -Action $action -Trigger @($atBoot, $atLogon) -Settings $settings `
        -User $cred.UserName -Password $pw -RunLevel Limited -Force
}

Write-Host ""
Write-Host "Registered. Start it now with:  Start-ScheduledTask -TaskName 'DIRTT nav sim'"
