$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\e0838503\AppData\Local\Programs\Python\Python311\python.exe'
$Cli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\lib\gcloud.py'
$env:REQUESTS_CA_BUNDLE = Join-Path $env:APPDATA 'gcloud\windows-trusted-roots.pem'
$env:GOOGLE_OAUTH_ACCESS_TOKEN = & $Python $Cli auth print-access-token
if ($LASTEXITCODE -ne 0) { throw 'Authenticate with gcloud auth login first.' }
$env:USE_VERTEX = '1'
$env:FORCE_MOCK = '0'
$env:GOOGLE_CLOUD_PROJECT = 'project-fd312a16-8445-4b1f-862'
$env:GOOGLE_CLOUD_LOCATION = 'global'
$env:GEMINI_MODEL = 'gemini-2.5-flash'
$env:GCS_BUCKET = 'aegisops-498775210896-demo'
$env:BQ_DATASET = 'aegisops_audit'
Set-Location $PSScriptRoot
Write-Output 'Starting local cloud-backed demo. The short-lived token expires in about one hour; restart this script to renew it.'
& $Python -m streamlit run app.py --server.port=8502 --browser.gatherUsageStats=false
