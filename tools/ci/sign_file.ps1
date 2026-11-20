<#
.SYNOPSIS
    Signs a binary file using the official SignPath PowerShell module.

.DESCRIPTION
    This script is invoked by Velopack CLI via --signTemplate during packaging.
    Supports two submission modes:
    1. Default mode (SIGNPATH_ARTIFACT_CONFIGURATION_SLUG is not set):
       Packages the single file into a temporary zip archive, submits it to SignPath
       using the project's default artifact configuration (matching the legacy build-release workflow),
       downloads the signed zip, extracts it, and verifies the extracted file matches the original file name.
    2. Explicit slug mode (SIGNPATH_ARTIFACT_CONFIGURATION_SLUG is set):
       Submits the raw executable directly with -ArtifactConfigurationSlug.

    Security & Integrity Checks:
    Before replacing the target file, the returned file is strictly verified:
    - File extension must match the original.
    - PE header magic bytes ('MZ', 0x4D 0x5A) must match.
    A zip archive or invalid binary will never overwrite the target executable.

.PARAMETER FilePath
    Path to the executable to sign.

.NOTES
    SignPath PowerShell Module & Cmdlet Specification:
    - Module: SignPath (PowerShell Gallery: https://www.powershellgallery.com/packages/SignPath)
    - Cmdlet: Submit-SigningRequest (Documentation: https://about.signpath.io/documentation/powershell/submit-signingrequest)
    Cmdlet Parameters Used:
    - -ApiToken: [string] Authentication token for SignPath REST API (Source: official docs)
    - -OrganizationId: [string] Organization identifier/slug (Source: official docs)
    - -ProjectSlug: [string] Project slug configured in SignPath (Source: official docs)
    - -SigningPolicySlug: [string] Signing policy slug (e.g. 'release-signing') (Source: official docs)
    - -ArtifactConfigurationSlug: [string, optional] Artifact configuration slug for raw binaries (Source: official docs)
    - -InputArtifactPath: [string] Path to artifact to upload (zip or raw binary) (Source: official docs)
    - -OutputArtifactPath: [string] Path where signed artifact will be downloaded (Source: official docs)
    - -WaitForCompletion: [switch] Wait synchronously until request completes and download artifact (Source: official docs)
    Note on -Force: The -Force parameter is not a documented parameter of Submit-SigningRequest in SignPath documentation and has been removed.
#>

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
$artifactConfigSlug = $env:SIGNPATH_ARTIFACT_CONFIGURATION_SLUG

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
$fileName = [System.IO.Path]::GetFileName($fullPath)
$origExt = [System.IO.Path]::GetExtension($fullPath)

# Create isolated temporary workspace for signing
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("signpath_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $candidateFile = $null

    if (-not [string]::IsNullOrWhiteSpace($artifactConfigSlug)) {
        # Explicit slug mode: submit raw executable directly
        Write-Host "Submitting raw binary $fileName with ArtifactConfigurationSlug '$artifactConfigSlug'..."
        $signedRawFile = Join-Path $tempDir ("signed_" + $fileName)
        Submit-SigningRequest `
            -ApiToken $apiToken `
            -OrganizationId $organizationId `
            -ProjectSlug $projectSlug `
            -SigningPolicySlug $signingPolicySlug `
            -ArtifactConfigurationSlug $artifactConfigSlug `
            -InputArtifactPath $fullPath `
            -WaitForCompletion `
            -OutputArtifactPath $signedRawFile

        if (-not (Test-Path $signedRawFile)) {
            throw "SignPath failed to produce signed file: $signedRawFile"
        }
        $candidateFile = $signedRawFile
    } else {
        # Default mode: package single file into zip, submit to default artifact configuration
        Write-Host "Packaging $fileName into zip archive for default artifact configuration..."
        $inputZip = Join-Path $tempDir "unsigned.zip"
        Compress-Archive -Path $fullPath -DestinationPath $inputZip -Force

        $outputZip = Join-Path $tempDir "signed.zip"
        Submit-SigningRequest `
            -ApiToken $apiToken `
            -OrganizationId $organizationId `
            -ProjectSlug $projectSlug `
            -SigningPolicySlug $signingPolicySlug `
            -InputArtifactPath $inputZip `
            -WaitForCompletion `
            -OutputArtifactPath $outputZip

        if (-not (Test-Path $outputZip)) {
            throw "SignPath failed to produce signed archive: $outputZip"
        }

        # Extract signed archive
        $extractDir = Join-Path $tempDir "extracted"
        Expand-Archive -Path $outputZip -DestinationPath $extractDir -Force

        # Verify extracted file contains the expected binary
        $extractedFile = Join-Path $extractDir $fileName
        if (-not (Test-Path $extractedFile)) {
            # Search recursively in case the zip created a subfolder
            $found = Get-ChildItem -Path $extractDir -Filter $fileName -Recurse | Select-Object -First 1 -ExpandProperty FullName
            if ($found -and (Test-Path $found)) {
                $extractedFile = $found
            } else {
                throw "Extracted archive does not contain expected file: $fileName"
            }
        }
        $candidateFile = $extractedFile
    }

    # Integrity & Safety Verification:
    # 1. Extension check
    $candExt = [System.IO.Path]::GetExtension($candidateFile)
    if ($origExt -ne $candExt) {
        throw "File extension mismatch: original file has '$origExt', signed candidate has '$candExt'"
    }

    # 2. PE header check: executable must start with 'MZ' (0x4D 0x5A)
    $stream = [System.IO.File]::OpenRead($candidateFile)
    $b0 = -1
    $b1 = -1
    try {
        $b0 = $stream.ReadByte()
        $b1 = $stream.ReadByte()
    } finally {
        $stream.Close()
    }

    if ($b0 -ne 0x4D -or $b1 -ne 0x5A) {
        throw ("Invalid PE header in signed file: expected 'MZ' (0x4D 0x5A), got (0x{0:X2} 0x{1:X2}). " +
               "The candidate may be a zip archive or invalid file. Refusing to overwrite original executable.") -f $b0, $b1
    }

    # Replace original binary
    Move-Item -Path $candidateFile -Destination $fullPath -Force
    Write-Host "Successfully verified and replaced: $fullPath"
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
