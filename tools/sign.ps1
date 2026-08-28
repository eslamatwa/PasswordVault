<#
.SYNOPSIS
    Authenticode-sign the built PasswordVault.exe.

.DESCRIPTION
    The build produces an unsigned executable, which Windows Smart App
    Control blocks outright and SmartScreen warns about. This signs it.

    What signing does and does not buy you:

      * A certificate from a public CA (OV) makes the publisher name real
        and stops the "unknown publisher" warning. SmartScreen reputation
        still has to accumulate across downloads, so early users may still
        see a warning.
      * An EV certificate, or Azure Trusted Signing, carries reputation
        from the start and is what actually gets past Smart App Control
        without a waiting period.
      * A self-signed certificate buys nothing here. Smart App Control
        requires a signature that chains to a trusted root AND has
        reputation; a certificate you made yourself has neither. Making
        Windows trust it means installing it as a trusted root, which
        tells the machine to trust anything signed with that key -- a far
        worse trade than an unsigned binary, and it still would not
        satisfy Smart App Control.

    Use -SelfSigned only to prove this script works end to end. It is
    explicitly not a fix for the blocking.

.PARAMETER Thumbprint
    Thumbprint of a code-signing certificate already in your certificate
    store. Find it with:
        Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert

.PARAMETER PfxPath
    Path to a .pfx file. You will be prompted for its password; it is not
    taken as a parameter so it stays out of your shell history.

.PARAMETER Path
    The file to sign. Defaults to dist\PasswordVault.exe.

.PARAMETER TimestampUrl
    RFC 3161 timestamp server. Timestamping is not optional: without it
    every copy you shipped stops verifying the day the certificate
    expires. With it, signatures stay valid for the life of the
    timestamp.

.PARAMETER SelfSigned
    Create a throwaway certificate and sign with it, to check the
    plumbing. The result will still be blocked. Nothing is installed into
    any trusted root store.

.EXAMPLE
    .\tools\sign.ps1 -Thumbprint A1B2C3...

.EXAMPLE
    .\tools\sign.ps1 -PfxPath .\codesign.pfx
#>
[CmdletBinding(DefaultParameterSetName = "Thumbprint")]
param(
    [Parameter(ParameterSetName = "Thumbprint")]
    [string]$Thumbprint,

    [Parameter(ParameterSetName = "Pfx")]
    [string]$PfxPath,

    [Parameter(ParameterSetName = "SelfSigned")]
    [switch]$SelfSigned,

    [string]$Path = "dist\PasswordVault.exe",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    <#  signtool ships with the Windows SDK, which is not installed by
        default. The newest one is preferred: older ones predate SHA-256
        defaults and RFC 3161 timestamping.  #>
    $candidates = @()
    foreach ($root in @("${env:ProgramFiles(x86)}\Windows Kits\10\bin",
                        "${env:ProgramFiles}\Windows Kits\10\bin")) {
        if (Test-Path $root) {
            $candidates += Get-ChildItem $root -Recurse -Filter signtool.exe `
                -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match "\\x64\\" }
        }
    }
    $found = $candidates | Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($found) { return $found.FullName }

    $onPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

if (-not (Test-Path $Path)) {
    throw "Nothing to sign at '$Path'. Build first: python -m PyInstaller PasswordVault.spec"
}

$signtool = Find-SignTool
if (-not $signtool) {
    Write-Host ""
    Write-Host "signtool.exe was not found." -ForegroundColor Yellow
    Write-Host "It comes with the Windows SDK. Install just the signing"
    Write-Host "component with:"
    Write-Host ""
    Write-Host "    winget install Microsoft.WindowsSDK.10.0.26100" -ForegroundColor Cyan
    Write-Host ""
    throw "signtool.exe is required."
}
Write-Host "signtool: $signtool" -ForegroundColor DarkGray

$temporaryCert = $null
try {
    switch ($PSCmdlet.ParameterSetName) {
        "SelfSigned" {
            Write-Host ""
            Write-Host "Signing with a throwaway certificate." -ForegroundColor Yellow
            Write-Host "This proves the pipeline works. It does NOT stop Smart App"
            Write-Host "Control from blocking the file, and it is not meant to."
            Write-Host ""
            $temporaryCert = New-SelfSignedCertificate `
                -Type CodeSigningCert `
                -Subject "CN=PasswordVault Signing Test (not for release)" `
                -CertStoreLocation Cert:\CurrentUser\My `
                -NotAfter (Get-Date).AddDays(30)
            $args = @("sign", "/fd", "SHA256", "/sha1",
                      $temporaryCert.Thumbprint, $Path)
        }
        "Pfx" {
            if (-not (Test-Path $PfxPath)) {
                throw "No .pfx at '$PfxPath'."
            }
            $password = Read-Host "Password for $PfxPath" -AsSecureString
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
            $args = @("sign", "/fd", "SHA256", "/f", $PfxPath,
                      "/p", $plain, "/tr", $TimestampUrl, "/td", "SHA256",
                      $Path)
        }
        default {
            if (-not $Thumbprint) {
                Write-Host ""
                Write-Host "Give it a certificate. Either:" -ForegroundColor Yellow
                Write-Host "  -Thumbprint <hash>   a cert already in your store"
                Write-Host "  -PfxPath <file.pfx>  a cert file"
                Write-Host "  -SelfSigned          plumbing check only, still blocked"
                Write-Host ""
                Write-Host "Certificates currently available to you:"
                $available = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert `
                    -ErrorAction SilentlyContinue
                if ($available) {
                    $available | Format-Table Subject, NotAfter, Thumbprint -AutoSize
                } else {
                    Write-Host "  (none)" -ForegroundColor DarkGray
                }
                throw "No certificate specified."
            }
            $args = @("sign", "/fd", "SHA256", "/sha1", $Thumbprint,
                      "/tr", $TimestampUrl, "/td", "SHA256", $Path)
        }
    }

    Write-Host "Signing $Path ..." -ForegroundColor Cyan
    & $signtool @args
    if ($LASTEXITCODE -ne 0) { throw "signtool failed ($LASTEXITCODE)." }

    Write-Host ""
    Write-Host "Verifying ..." -ForegroundColor Cyan
    # /pa uses the Authenticode policy, which is what Windows itself
    # applies -- the default policy passes things Windows would reject.
    & $signtool "verify" "/pa" "/v" $Path
    $verified = $LASTEXITCODE -eq 0

    Write-Host ""
    if ($verified) {
        Write-Host "Signed and verified." -ForegroundColor Green
    } else {
        Write-Host "Signed, but Windows does not trust the signature." -ForegroundColor Yellow
        Write-Host "Expected with -SelfSigned. With a real certificate it means"
        Write-Host "the chain is incomplete -- install the CA's intermediate."
    }
    Get-AuthenticodeSignature $Path |
        Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
}
finally {
    if ($temporaryCert) {
        # A code-signing key with no owner is not something to leave lying
        # around, even a 30-day one.
        Remove-Item "Cert:\CurrentUser\My\$($temporaryCert.Thumbprint)" `
            -Force -ErrorAction SilentlyContinue
        Write-Host "Throwaway certificate removed." -ForegroundColor DarkGray
    }
}
