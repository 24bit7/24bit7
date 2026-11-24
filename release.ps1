# 24bit7 - the end of build.bat: publishing to GitHub.
#
# build.bat only gets here once the tests have passed, the build worked and the
# release zip was made, so there's no question to answer: it publishes.
#   6. Checks before publishing: gh installed and signed in, release_notes\vX.Y.Z.md
#      committed, no release with this tag yet, everything committed and pushed.
#      Any problem stops it here: nothing goes online.
#      The phone app's APK, built by GitHub for this commit, is fetched too.
#   7. Publishes with gh: the zip and its fingerprint (.sha256, for Update Now), the phone app's APK, the title
#      and the notes file, then opens the page.
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
# The phone app (24 Nov 2026): GitHub builds and signs it at every push to main (.github\workflows\android.yml),
# so the run for this very commit is fetched and its APK goes up beside the zip. No APK, no release.
$apk = $null
if (-not $problems.Count) {
    $head = git rev-parse HEAD
    $run = gh run list --workflow android.yml --commit $head --limit 1 --json databaseId --jq '.[0].databaseId' 2> $null
    if (-not $run) {
        gh workflow run android.yml --ref (git rev-parse --abbrev-ref HEAD) *> $null
        for ($i = 0; $i -lt 12 -and -not $run; $i++) {
            Start-Sleep -Seconds 5
            $run = gh run list --workflow android.yml --commit $head --limit 1 --json databaseId --jq '.[0].databaseId' 2> $null
        }
    }
    if ($run) {
        Write-Host "Waiting for the phone app's build on GitHub..."
        gh run watch $run --exit-status *> $null
        if ($LASTEXITCODE -eq 0) {
            $got = "releases\phone-$Version"
            if (Test-Path $got) { Remove-Item -Recurse -Force $got }
            gh run download $run -n 24bit7-phone -D $got *> $null
            if (Test-Path "$got\24bit7-phone.apk") {
                $apk = "releases\24bit7-phone-v$Version.apk"
                Move-Item -Force "$got\24bit7-phone.apk" $apk
                Remove-Item -Recurse -Force $got
            }
        }
    }
    if (-not $apk) { $problems += "The phone app's APK couldn't be fetched from GitHub (Actions, phone app)." }
}
if ($problems.Count) {
    Write-Host ""
    Write-Host "Not published:"
    $problems | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Fix those, then publish with: gh release create $tag `"$Zip`" --title `"24bit7 $Version`" --notes-file $notes"
    exit 1
}

# --- 7. Publish ---
# The zip's fingerprint goes up beside it: Update Now checks the download against it (17 Nov 2026)
$sha = "$Zip.sha256"
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash.ToLower()
Set-Content -LiteralPath $sha -Value "$hash  $(Split-Path -Leaf $Zip)" -Encoding Ascii
gh release create $tag $Zip $sha $apk --title "24bit7 $Version" --notes-file $notes --target (git rev-parse HEAD)
if ($LASTEXITCODE) {
    Write-Host "Publishing didn't go through (see above). Nothing else was changed."
    exit 1
}
Write-Host "Published $tag."
gh release view $tag --web
