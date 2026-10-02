# 24bit7 - the end of build.bat: the keyless test, then publishing to GitHub.
#
#   6. Unzips the release zip to Desktop\24bit7-test and opens it: a clean copy,
#      with no keys and no history.
#   7. Asks whether the test passed and whether to publish. The test copy is
#      closed and deleted either way. N stops here: nothing goes online.
#   8. Checks before publishing: gh installed and signed in, release_notes\vX.Y.Z.md
#      committed, no release with this tag yet, everything committed and pushed.
#   9. Publishes with gh: the zip, the title and the notes file, then opens the page.
#
# build.bat runs it: powershell -NoProfile -ExecutionPolicy Bypass -File release.ps1 -Version 1.8.0 -Zip releases\...

param([Parameter(Mandatory)][string]$Version, [Parameter(Mandatory)][string]$Zip)

Set-Location $PSScriptRoot
# a window opened before gh was installed doesn't know where it is
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$tag = "v$Version"
$notes = "release_notes\$tag.md"
$test = Join-Path ([Environment]::GetFolderPath("Desktop")) "24bit7-test"

function Remove-TestCopy {
    Get-Process 24bit7 -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$test*" } | Stop-Process -Force
    Start-Sleep -Seconds 1
    Remove-Item $test -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 6. Keyless test ---
Remove-TestCopy
try {
    Expand-Archive $Zip -DestinationPath $test -ErrorAction Stop
    $exe = Get-ChildItem $test -Recurse -Filter 24bit7.exe | Select-Object -First 1
    Start-Process $exe.FullName
} catch {
    Write-Host "Couldn't open a test copy ($($_.Exception.Message)). Nothing was published."
    Remove-TestCopy
    exit 1
}
Write-Host ""
Write-Host "Keyless test: a clean copy of $tag is open from $test (no keys, no history)."
Write-Host "Check it opens on Settings with the welcome message, the title bar says v$Version, and a build works."
Write-Host ""

# --- 7. Ask ---
$answer = Read-Host "Did the keyless test pass? Publish $tag to GitHub? (Y/N)"
Remove-TestCopy
if ($answer -notmatch '^\s*[Yy]') {
    Write-Host "Not published. Nothing went online."
    exit 0
}

# --- 8. Checks ---
$problems = @()
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    $problems += "The GitHub CLI isn't installed: winget install GitHub.cli, then gh auth login."
} else {
    gh auth status *> $null
    if ($LASTEXITCODE) {
        $problems += "gh isn't signed in: run gh auth login."
    } else {
        gh release view $tag *> $null
        if ($LASTEXITCODE -eq 0) { $problems += "A $tag release is already on GitHub." }
    }
}
if (-not (Test-Path $notes)) {
    $problems += "There are no release notes: write $notes, then commit and push it."
} else {
    git ls-files --error-unmatch $notes *> $null
    if ($LASTEXITCODE) { $problems += "$notes isn't committed yet." }
}
if (git status --porcelain --untracked-files=no) {
    $problems += "There are uncommitted changes: commit and push them first."
}
git fetch --quiet *> $null
$unpushed = git rev-list --count "@{u}..HEAD" 2> $null
if ($LASTEXITCODE -or [int]$unpushed -gt 0) {
    $problems += "Some commits haven't been pushed: run git push."
}
if ($problems.Count) {
    Write-Host ""
    Write-Host "Not published:"
    $problems | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Fix those, then publish with: gh release create $tag `"$Zip`" --title `"24bit7 $Version`" --notes-file $notes"
    exit 1
}

# --- 9. Publish ---
gh release create $tag $Zip --title "24bit7 $Version" --notes-file $notes --target (git rev-parse HEAD)
if ($LASTEXITCODE) {
    Write-Host "Publishing didn't go through (see above). Nothing else was changed."
    exit 1
}
Write-Host "Published $tag."
gh release view $tag --web
