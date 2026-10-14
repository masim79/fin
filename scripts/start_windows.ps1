$ErrorActionPreference = "Stop"

$ContainerName = "finally"
$ImageName = "finally"
$Port = 8000

Set-Location "$PSScriptRoot\.."

# .env is gitignored, so a clean checkout has none and `docker run --env-file`
# would abort before the container ever starts. Seed it from the example and
# let the app run on the simulator until a real key is filled in.
if (-not (Test-Path ".env")) {
    Write-Host "No .env found - creating one from .env.example."
    Copy-Item ".env.example" ".env"
    Write-Host "Add your OPENROUTER_API_KEY to .env to enable AI chat."
}

# Build if image doesn't exist or -Build flag passed
$needsBuild = $args -contains "--build"
if (-not $needsBuild) {
    docker image inspect $ImageName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $needsBuild = $true }
}

if ($needsBuild) {
    Write-Host "Building image..."
    docker build -t $ImageName .
}

# Stop existing container if running (idempotent)
docker rm -f $ContainerName 2>$null | Out-Null

# Run container
docker run -d `
    --name $ContainerName `
    -p "${Port}:8000" `
    -v finally-data:/app/db `
    --env-file .env `
    $ImageName

Write-Host "FinAlly running at http://localhost:$Port"
Start-Process "http://localhost:$Port"
