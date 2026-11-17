# 24bit7's updater (17 Nov 2026). 24bit7 runs it, from a copy in the update folder, once it has downloaded a new
# release beside itself, checked it against its fingerprint and unpacked it. This script:
#   1. waits for 24bit7 to close (and any other 24bit7 from the same folder, such as the Multiroom follower);
#   2. renames the old folder to "<folder> <old version> backup";
#   3. moves the new copy into the old folder's place;
#   4. copies across everything of yours the new copy doesn't ship: .env, 24bit7.db, profiles, logs;
#   5. leaves update_result.txt for 24bit7 to say how it went, and starts 24bit7 again.
# If anything goes wrong after step 2, the new copy is taken away and the old one put back and started.
# It never downloads anything and never runs anything but 24bit7.exe.

param(
    [Parameter(Mandatory)][string]$AppDir,
    [Parameter(Mandatory)][string]$NewDir,
    [Parameter(Mandatory)][string]$WorkDir,
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$OldVersion,
    [int]$WaitPid = 0,
    [switch]$NoStart,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = "Updating 24bit7 to $Version" } catch {}
$AppDir = $AppDir.TrimEnd('\')
$parent = Split-Path -Parent $AppDir
$leaf = Split-Path -Leaf $AppDir

function Say([string]$text) { Write-Host $text }

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

Say "Updating 24bit7 from $OldVersion to $Version."
Say "Waiting for 24bit7 to close..."
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
    Say "The update didn't start: $why"
    Finish "failed`t$why" $AppDir
    if (-not $NoPause) { Start-Sleep -Seconds 8 }
    exit 1
}
Say "Your old copy is kept as $(Split-Path -Leaf $backup)."

try {
    Retry { Move-Item -LiteralPath $NewDir -Destination $AppDir }
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir '24bit7.exe'))) { throw "the new copy has no 24bit7.exe" }
    $shipped = @(Get-ChildItem -LiteralPath $AppDir -Force | ForEach-Object { $_.Name })
    foreach ($item in Get-ChildItem -LiteralPath $backup -Force) {
        if ($shipped -notcontains $item.Name -and $item.Name -ne 'update_result.txt') {
            Copy-Item -LiteralPath $item.FullName -Destination $AppDir -Recurse -Force
        }
    }
    Say "Your settings, history and profiles are copied across."
} catch {
    $why = $_.Exception.Message
    Say "The update didn't finish: $why"
    Say "Putting your old copy back."
    try {
        if (Test-Path -LiteralPath $AppDir) { Retry { Remove-Item -LiteralPath $AppDir -Recurse -Force } }
        Retry { Rename-Item -LiteralPath $backup -NewName $leaf }
    } catch {
        Say "It couldn't be put back ($($_.Exception.Message)). Your old copy is in $backup."
        if (-not $NoPause) { Start-Sleep -Seconds 30 }
        exit 2
    }
    Finish "failed`t$why" $AppDir
    if (-not $NoPause) { Start-Sleep -Seconds 8 }
    exit 1
}

Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
Say "Starting 24bit7 $Version."
Finish "ok`t$OldVersion`t$backup" $AppDir
if (-not $NoPause) { Start-Sleep -Seconds 2 }
exit 0
