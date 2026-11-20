param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $FilePath)) {
    throw "File to sign not found: $FilePath"
}

$apiToken = $env:SIGNPATH_API_TOKEN
$organizationId = $env:SIGNPATH_ORGANIZATION_ID
$projectSlug = if ($env:SIGNPATH_PROJECT_SLUG) { $env:SIGNPATH_PROJECT_SLUG } else { 'ZenlessZoneZero-OneDragon' }
$signingPolicySlug = if ($env:SIGNPATH_SIGNING_POLICY_SLUG) { $env:SIGNPATH_SIGNING_POLICY_SLUG } else { 'release-signing' }

if ([string]::IsNullOrWhiteSpace($apiToken) -or [string]::IsNullOrWhiteSpace($organizationId)) {
    throw "Missing required SignPath environment variables: SIGNPATH_API_TOKEN and/or SIGNPATH_ORGANIZATION_ID"
}

# Ensure SignPath PowerShell module is available
if (-not (Get-Module -ListAvailable -Name SignPath)) {
    Write-Host "Installing SignPath PowerShell module..."
    Install-Module -Name SignPath -Scope CurrentUser -Force -Repository PSGallery
}
Import-Module SignPath

$fullPath = (Resolve-Path $FilePath).Path
Write-Host "Submitting signing request for $fullPath via SignPath..."
$tempSignedFile = "$fullPath.signed"

Submit-SigningRequest `
    -ApiToken $apiToken `
    -OrganizationId $organizationId `
    -ProjectSlug $projectSlug `
    -SigningPolicySlug $signingPolicySlug `
    -InputArtifactPath $fullPath `
    -WaitForCompletion `
    -OutputArtifactPath $tempSignedFile `
    -Force

if (-not (Test-Path $tempSignedFile)) {
    throw "SignPath failed to produce signed file: $tempSignedFile"
}

Move-Item -Path $tempSignedFile -Destination $fullPath -Force
Write-Host "Successfully signed and replaced: $fullPath"
