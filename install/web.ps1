<#
.SYNOPSIS
  One-command installer for the easy-map skill on Windows.

.DESCRIPTION
  Downloads the package from GitHub into a temporary folder and hands it to
  install\install.ps1, which finds your assistants, asks which to install for,
  and copies the skill into place. Nothing is left behind: the download is
  deleted, and only the installed copy survives.

  Run it straight from the web:

      irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1 | iex

  To pass options, invoke it as a script block instead:

      & ([scriptblock]::Create((irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1))) -Targets codex -Quiet

.EXAMPLE
  irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1 | iex
#>
[CmdletBinding()]
param(
  [string[]] $Targets,
  [string]   $Shapefiles,
  [switch]   $Quiet,
  # A branch or tag. Pin this if you want a fixed version rather than whatever
  # main holds today.
  [string]   $Ref = 'main'
)

$ErrorActionPreference = 'Stop'
$Repo = 'codelabr/easy-map'

# Windows PowerShell 5.1 still negotiates TLS 1.0 by default; github.com has
# refused that since 2018, and the failure reads as a connection error rather
# than a protocol one.
if ([Net.ServicePointManager]::SecurityProtocol -notmatch 'Tls12') {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

$temp = Join-Path ([IO.Path]::GetTempPath()) ('easy-map-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $temp | Out-Null

try {
  $zip = Join-Path $temp 'package.zip'
  $url = "https://codeload.github.com/$Repo/zip/refs/heads/$Ref"

  Write-Host ''
  Write-Host ("downloading {0} ({1})" -f $Repo, $Ref) -ForegroundColor Cyan

  # Drawing the progress bar costs more than the transfer on 5.1: it repaints
  # the console on every buffer and turns a 6 MB download into a minute.
  $prior = $ProgressPreference
  $ProgressPreference = 'SilentlyContinue'
  try {
    # GitHub rate-limits anonymous downloads per IP address and answers 429.
    # That clears by itself, so wait and try again rather than making somebody
    # rerun the whole command and guess at how long to leave it.
    $attempt = 0
    while ($true) {
      $attempt++
      try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        break
      } catch {
        $status = 0
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        if ($status -ne 429) {
          throw "Could not download $url. $($_.Exception.Message)"
        }
        if ($attempt -ge 4) {
          throw ("GitHub is rate-limiting this address (429) and four tries did not " +
                 "get through. It clears on its own; try again in a few minutes.")
        }
        $wait = 15 * $attempt
        Write-Host ("  rate-limited by GitHub (429). Waiting {0}s, then attempt {1} of 4." -f
                    $wait, ($attempt + 1)) -ForegroundColor Yellow
        Start-Sleep -Seconds $wait
      }
    }
  } finally {
    $ProgressPreference = $prior
  }

  Expand-Archive -LiteralPath $zip -DestinationPath $temp -Force

  # GitHub wraps the archive in one folder named <repo>-<ref>, so take the only
  # directory rather than guessing at the name a slash in the ref would mangle.
  $src = Get-ChildItem $temp -Directory | Select-Object -First 1
  if (-not $src) { throw "The archive from $url held no folder." }

  $installer = Join-Path $src.FullName 'install\install.ps1'
  if (-not (Test-Path $installer)) {
    throw "The download has no install\install.ps1. Is '$Ref' a branch of $Repo?"
  }

  $forward = @{}
  if ($Targets)    { $forward.Targets    = $Targets }
  if ($Shapefiles) { $forward.Shapefiles = $Shapefiles }
  if ($Quiet)      { $forward.Quiet      = $true }

  & $installer @forward
}
finally {
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}
