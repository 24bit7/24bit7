# 24bit7 - the end of build.bat: publishing to GitHub.
#
# build.bat only gets here once the tests have passed, the build worked and the
# release zip was made, so there's no question to answer: it publishes.
#   6. Checks before publishing: gh installed and signed in, release_notes\vX.Y.Z.md
#      committed, no release with this tag yet, everything committed and pushed.
#      Any problem stops it here: nothing goes online.
#   7. Publishes with gh: the zip, the title and the notes file, then opens the page.
#
# build.bat runs it: powershell -NoProfile -ExecutionPolicy Bypass -File release.ps1 -Version 1.8.0 -Zip releases\...

param([Parameter(Mandatory)][string]$Version, [Parameter(Mandatory)][string]$Zip)

Set-Location $PSScriptRoot
# a window opened before gh was installed doesn't know where it is
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$tag = "v$Version"
$notes = "release_notes\$tag.md"

# --- 6. Checks ---
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

# --- 7. Publish ---
gh release create $tag $Zip --title "24bit7 $Version" --notes-file $notes --target (git rev-parse HEAD)
if ($LASTEXITCODE) {
    Write-Host "Publishing didn't go through (see above). Nothing else was changed."
    exit 1
}
Write-Host "Published $tag."
gh release view $tag --web
