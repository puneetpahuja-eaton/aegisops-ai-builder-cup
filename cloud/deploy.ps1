param(
    [string]$Project = 'project-fd312a16-8445-4b1f-862',
    [string]$Region = 'asia-south1',
    [string]$Model = 'gemini-2.5-flash',
    [string]$Service = 'kairos-ai'
)
$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\e0838503\AppData\Local\Programs\Python\Python311\python.exe'
$Cli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\lib\gcloud.py'
$env:REQUESTS_CA_BUNDLE = Join-Path $env:APPDATA 'gcloud\windows-trusted-roots.pem'
Set-Location (Split-Path $PSScriptRoot -Parent)
$Config = Get-Content (Join-Path $PSScriptRoot 'deployment.json') -Raw | ConvertFrom-Json
$Variables = "USE_VERTEX=1,USE_FIRESTORE=1,SEED_DEMO=1,GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=$Model,EMBED_MODEL=text-embedding-004,GCS_BUCKET=$($Config.bucket),BQ_DATASET=$($Config.dataset),FORCE_MOCK=0"
& $Python $Cli run deploy $Service --source . --project=$Project --region=$Region `
    --build-service-account="projects/$Project/serviceAccounts/$($Config.build_account)" `
    --service-account=$($Config.service_account) --allow-unauthenticated `
    --set-env-vars=$Variables --memory=1Gi --cpu=1 --min-instances=0 `
    --max-instances=4 --concurrency=8 --timeout=300 --port=8080 --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cloud Run deployment failed.' }
& $Python $Cli run services describe $Service --project=$Project --region=$Region --format='value(status.url)'
if ($LASTEXITCODE -ne 0) { throw 'Could not retrieve Cloud Run URL.' }
