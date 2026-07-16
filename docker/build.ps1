# Build the sieng2-analyzer image. Run from the repo root or anywhere - this
# script cd's to the repo root itself so the build context is always correct.
$repoRoot = Split-Path -Parent $PSScriptRoot
docker build -t sieng2-analyzer -f "$repoRoot\docker\Dockerfile" $repoRoot
