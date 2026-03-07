Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = "E:\My code\AI-Intel-System"
Set-Location $repo

# 1) Run pipeline
python main.py
if ($LASTEXITCODE -ne 0) { throw "python main.py failed with exit code $LASTEXITCODE" }

# 2) Stage only data json files
git add data/*.json
if ($LASTEXITCODE -ne 0) { throw "git add failed with exit code $LASTEXITCODE" }

# 3) If nothing staged, exit quietly
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Host "No staged changes in data/*.json. Skip commit/push."
  exit 0
}

# 4) Commit with current date
$date = Get-Date -Format "yyyy-MM-dd"
$msg = "daily update $date"
git commit -m $msg
if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }

# 5) Push
git push
if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }

Write-Host "Done: $msg"

