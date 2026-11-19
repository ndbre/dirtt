# Starts the D.I.R.T.T. nav sim (WSL: SITL + nav_sim.py + Cloudflare tunnel) when Windows boots,
# before anyone logs in, and keeps it running.
#
# Run in PowerShell AS ADMINISTRATOR, from this folder:
#     powershell -ExecutionPolicy Bypass -File .\register_task.ps1
#
# It asks for your Windows password (for a Microsoft account, that account's password, not the PIN),
# so the task can run while nobody is logged in.
# Remove it later with:  Unregister-ScheduledTask -TaskName "DIRTT nav sim"

param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$LinuxUser = "dirtt"
)

$script = "/home/$LinuxUser/dirtt/code/Navigation/server/start_sim.sh"
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\wsl.exe" `
    -Argument "-d $Distro -u $LinuxUser -- bash -lc $script"

$atBoot = New-ScheduledTaskTrigger -AtStartup
$atBoot.Delay = "PT1M"                       # give networking a minute after boot
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$cred = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" `
    -Message "Windows password for $env:USERNAME (lets the sim start before anyone logs in)"

Register-ScheduledTask -TaskName "DIRTT nav sim" -Description "D.I.R.T.T. navigation sim (WSL)" `
    -Action $action -Trigger @($atBoot, $atLogon) -Settings $settings `
    -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force

Write-Host ""
Write-Host "Registered. Start it now with:  Start-ScheduledTask -TaskName 'DIRTT nav sim'"
