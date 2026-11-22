# 24bit7's updater (17 Nov 2026). 24bit7 runs it, from a copy in the update folder, once it has downloaded a new
# release beside itself, checked it against its fingerprint and unpacked it. This script:
#   1. waits for 24bit7 to close (and any other 24bit7 from the same folder, such as the Multiroom follower);
#   2. renames the old folder to "<folder> <old version> backup";
#   3. moves the new copy into the old folder's place;
#   4. copies across everything of yours the new copy doesn't ship: .env, 24bit7.db, profiles, logs;
#   5. leaves update_result.txt for 24bit7 to say how it went, and starts 24bit7 again.
# Its lines are English here. 24bit7 hands it the same lines in the language it's set to (-Texts, a JSON file of
# English line: translated line), since it runs with 24bit7 closed and can't ask it; a line that isn't there is
# said in English (22 Nov 2026).
# If anything goes wrong after step 2, the new copy is taken away and the old one put back and started.
# It never downloads anything and never runs anything but 24bit7.exe.

param(
    [Parameter(Mandatory)][string]$AppDir,
    [Parameter(Mandatory)][string]$NewDir,
    [Parameter(Mandatory)][string]$WorkDir,
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$OldVersion,
    [int]$WaitPid = 0,
    [string]$Texts = '',
    [switch]$NoStart,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$AppDir = $AppDir.TrimEnd('\')
$parent = Split-Path -Parent $AppDir
$leaf = Split-Path -Leaf $AppDir

$translated = @{}
if ($Texts) {
    try {
        $read = Get-Content -LiteralPath $Texts -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($p in $read.PSObject.Properties) { $translated[$p.Name] = [string]$p.Value }
    } catch {}
}

function Line([string]$text, [hashtable]$fill = @{}) {
    # The line in the user's language where 24bit7 handed one over, with its {blanks} filled
    $line = if ($translated.ContainsKey($text) -and $translated[$text]) { $translated[$text] } else { $text }
    foreach ($k in $fill.Keys) { $line = $line.Replace('{' + $k + '}', [string]$fill[$k]) }
    return $line
}

function Say([string]$text, [hashtable]$fill = @{}) { Write-Host (Line $text $fill) }

try { $Host.UI.RawUI.WindowTitle = (Line 'Updating 24bit7 to {new}' @{ new = $Version }) } catch {}

function Retry([scriptblock]$step) {
    # Windows Defender or an Explorer window can hold a file for a moment: try for twenty seconds
    for ($i = 1; $i -le 10; $i++) {
        try { & $step; return } catch { if ($i -eq 10) { throw } ; Start-Sleep -Seconds 2 }
    }
}

function Finish([string]$result, [string]$dir) {
    try { Set-Content -LiteralPath (Join-Path $dir 'update_result.txt') -Value $result -Encoding UTF8 } catch {}
    if (-not $NoStart) {
        Start-Process -FilePath (Join-Path $dir '24bit7.exe') -WorkingDirectory $dir
    }
}

function Ours {
    Get-Process 24bit7 -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($AppDir + '\', [StringComparison]::OrdinalIgnoreCase)
    }
}

Say 'Updating 24bit7 from {old} to {new}.' @{ old = $OldVersion; new = $Version }
Say 'Waiting for 24bit7 to close...'
if ($WaitPid) { try { Wait-Process -Id $WaitPid -Timeout 60 -ErrorAction Stop } catch {} }
$deadline = (Get-Date).AddSeconds(20)
while ((Ours) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
Ours | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

$backup = Join-Path $parent "$leaf $OldVersion backup"
$n = 2
while (Test-Path -LiteralPath $backup) { $backup = Join-Path $parent "$leaf $OldVersion backup ($n)"; $n++ }

try {
    Retry { Rename-Item -LiteralPath $AppDir -NewName (Split-Path -Leaf $backup) }
} catch {
    $why = "the old copy couldn't be moved aside: $($_.Exception.Message)"
    Say "The update didn't start: {why}" @{ why = $why }
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue   # Update Now downloads afresh
    Finish "failed`t$why" $AppDir
    if (-not $NoPause) { Start-Sleep -Seconds 8 }
    exit 1
}
Say 'Your old copy is kept as {folder}.' @{ folder = (Split-Path -Leaf $backup) }

try {
    Retry { Move-Item -LiteralPath $NewDir -Destination $AppDir }
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir '24bit7.exe'))) { throw "the new copy has no 24bit7.exe" }
    $shipped = @(Get-ChildItem -LiteralPath $AppDir -Force | ForEach-Object { $_.Name })
    foreach ($item in Get-ChildItem -LiteralPath $backup -Force) {
        if ($shipped -notcontains $item.Name -and $item.Name -ne 'update_result.txt') {
            Copy-Item -LiteralPath $item.FullName -Destination $AppDir -Recurse -Force
        }
    }
    Say 'Your settings, history and profiles are copied across.'
} catch {
    $why = $_.Exception.Message
    Say "The update didn't finish: {why}" @{ why = $why }
    Say 'Putting your old copy back.'
    try {
        if (Test-Path -LiteralPath $AppDir) { Retry { Remove-Item -LiteralPath $AppDir -Recurse -Force } }
        Retry { Rename-Item -LiteralPath $backup -NewName $leaf }
    } catch {
        Say "It couldn't be put back ({why}). Your old copy is in {folder}." @{ why = $_.Exception.Message; folder = $backup }
        if (-not $NoPause) { Start-Sleep -Seconds 30 }
        exit 2
    }
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue   # Update Now downloads afresh
    Finish "failed`t$why" $AppDir
    if (-not $NoPause) { Start-Sleep -Seconds 8 }
    exit 1
}

Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
Say 'Starting 24bit7 {new}.' @{ new = $Version }
Finish "ok`t$OldVersion`t$backup" $AppDir
if (-not $NoPause) { Start-Sleep -Seconds 2 }
exit 0
