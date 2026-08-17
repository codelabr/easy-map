<#
.SYNOPSIS
  Installs the easy-map skill for ChatGPT Codex and/or Claude Code on Windows.

.DESCRIPTION
  Both assistants read skills from the same shape of folder:

      ~\.codex\skills\easy-map\SKILL.md
      ~\.claude\skills\easy-map\SKILL.md

  so one script serves both. It looks for each assistant, asks which ones to
  install for, copies the whole package (the instructions, the engine, the
  fonts and the references), and points the copy at its own engine so the skill
  works from any working folder rather than only inside a clone of the source
  repository.

  Boundary shapefiles are not installed: they are ~135 MB and their terms of
  use are the user's to accept. The script asks where they are, if anywhere,
  and records the answer for the engine to find.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install.ps1 -Targets codex,claude -Shapefiles D:\gis\boundaries -Quiet
#>
[CmdletBinding()]
param(
  # Accepts an array or one comma-separated string: `powershell -File` hands a
  # comma-separated argument over as a single string, which is how most people
  # will call this.
  [string[]] $Targets,

  [string] $Shapefiles,

  [switch] $Quiet,

  # Leave the interpreter alone even when there is none. For machines where
  # Python is managed centrally and an extra copy would be unwelcome.
  [switch] $SkipPython,

  # Do not unpack the boundaries the package carries. For a machine that
  # already has them somewhere else, or has no room for another 135 MB.
  [switch] $SkipShapefiles
)

$ErrorActionPreference = 'Stop'
$SkillName = 'easy-map'

#: Nothing in the engine uses syntax newer than this, so an existing 3.10 is
#: left in place rather than replaced.
$MinPython  = [Version]'3.10'
$WantPython = '3.13'

# Windows PowerShell 5.1 still negotiates TLS 1.0, which the download hosts
# refuse; the failure reads as a connection error rather than a protocol one.
if ([Net.ServicePointManager]::SecurityProtocol -notmatch 'Tls12') {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

if ($Targets) {
  $Targets = @($Targets -split ',' | ForEach-Object { $_.Trim().ToLower() } |
               Where-Object { $_ })
  $unknown = @($Targets | Where-Object { $_ -notin @('codex', 'claude') })
  if ($unknown) { throw "Unknown target(s): $($unknown -join ', '). Use codex, claude, or both." }
}

# The package is the folder this script's parent contains, so the script works
# from a clone and from an unpacked download alike.
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "skills\$SkillName"

if (-not (Test-Path (Join-Path $Source 'SKILL.md'))) {
  throw "Cannot find the skill at $Source. Run this from the project it ships in."
}

function Find-Assistant {
  param([string] $Name, [string] $Command, [string] $Folder)
  $home_ = [Environment]::GetFolderPath('UserProfile')
  $dir = Join-Path $home_ $Folder
  $onPath = $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
  [pscustomobject]@{
    Key       = $Name
    Label     = if ($Name -eq 'codex') { 'ChatGPT Codex' } else { 'Claude Code' }
    Directory = $dir
    # Either signal is enough: the CLI may not be on PATH when the assistant is
    # installed as an app or an IDE extension, and the folder may not exist yet
    # on a fresh install that has never been run.
    Present   = $onPath -or (Test-Path $dir)
    Evidence  = @(
      if ($onPath) { "'$Command' on PATH" }
      if (Test-Path $dir) { "$Folder exists" }
    ) -join ', '
  }
}

$found = @(
  (Find-Assistant -Name 'codex'  -Command 'codex'  -Folder '.codex'),
  (Find-Assistant -Name 'claude' -Command 'claude' -Folder '.claude')
)

Write-Host ''
Write-Host "easy-map installer" -ForegroundColor Cyan
Write-Host ("  package: {0}" -f $Source)
Write-Host ''
foreach ($a in $found) {
  if ($a.Present) {
    Write-Host ("  [found]     {0}  ({1})" -f $a.Label, $a.Evidence) -ForegroundColor Green
  } else {
    Write-Host ("  [not found] {0}" -f $a.Label) -ForegroundColor DarkGray
  }
}
Write-Host ''

if (-not $Targets) {
  $available = @($found | Where-Object { $_.Present })
  if ($available.Count -eq 0) {
    throw "Neither assistant was found. Install one, or pass -Targets to force."
  }
  if ($Quiet) {
    $Targets = $available.Key
  } else {
    Write-Host "Install the skill for which assistant?"
    for ($i = 0; $i -lt $available.Count; $i++) {
      Write-Host ("  {0}) {1}" -f ($i + 1), $available[$i].Label)
    }
    Write-Host ("  {0}) all of them" -f ($available.Count + 1))
    $answer = Read-Host "Enter numbers separated by commas, or press Enter for all"
    if ([string]::IsNullOrWhiteSpace($answer) -or
        $answer -eq [string]($available.Count + 1)) {
      $Targets = $available.Key
    } else {
      $picked = $answer -split ',' | ForEach-Object { $_.Trim() } |
                Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }
      $Targets = @($picked | Where-Object { $_ -ge 1 -and $_ -le $available.Count } |
                  ForEach-Object { $available[$_ - 1].Key })
    }
    if (-not $Targets) { throw "Nothing selected." }
  }
}

# --- python ----------------------------------------------------------------
# The skill is Python. Without an interpreter the folder installs cleanly and
# then does nothing, which is a worse outcome than saying so here.

function Find-Python {
  <#
    The newest usable interpreter, or $null. `py -3` is checked as well as the
    two names because the Windows launcher often knows about an installation
    that never made it onto PATH.
  #>
  $best = $null

  # Two PowerShell traps live in these four lines.
  #
  # The snippet carries NO quote characters: PowerShell strips quotes when it
  # hands an argument to a native program, so `print("%d.%d" % ...)` reaches
  # Python as `print(%d.%d % ...)` and every interpreter on the machine looks
  # like a syntax error, which reads as "no Python installed".
  #
  # And a native program's stderr becomes a terminating error while
  # $ErrorActionPreference is 'Stop', so the version check has to run relaxed
  # and be judged by its exit code.
  $snippet = 'import sys;print(sys.version.split()[0])'
  $prior = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    foreach ($candidate in @(
        @{ Exe = 'python3'; Pre = @() },
        @{ Exe = 'python';  Pre = @() },
        @{ Exe = 'py';      Pre = @('-3') })) {
      if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
      # A bare `python` on Windows is often the Store stub, which prints
      # nothing and exits non-zero. Asking for a version weeds that out.
      $printed = & $candidate.Exe @($candidate.Pre + @('-c', $snippet)) 2>$null
      if ($LASTEXITCODE -ne 0 -or -not $printed) { continue }
      $parsed = $null
      if (-not [Version]::TryParse(("$printed" -split '\r?\n')[0].Trim(), [ref]$parsed)) { continue }
      if (-not $best -or $parsed -gt $best.Version) {
        $best = [pscustomobject]@{ Command = $candidate.Exe; Version = $parsed }
      }
    }
  } finally {
    $ErrorActionPreference = $prior
  }
  return $best
}

function Resolve-Uv {
  <# The uv executable, installing it first if it is not there yet. #>
  $found = Get-Command uv -ErrorAction SilentlyContinue
  if ($found) { return $found.Source }

  Write-Host "  installing uv, which fetches the Python build"
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

  # A freshly installed uv is not on this process's PATH, so look where its
  # installer puts it rather than re-reading PATH.
  $guess = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local\bin\uv.exe'
  if (Test-Path $guess) { return $guess }
  $found = Get-Command uv -ErrorAction SilentlyContinue
  if ($found) { return $found.Source }
  throw "uv was installed but could not be located afterwards."
}

if (-not $SkipPython) {
  # Announce the step before doing it. On a machine that already has Python the
  # whole check is one line, which is indistinguishable from the assistant
  # detection above it and reads as though nothing happened.
  Write-Host "Checking for Python..."
  $python = Find-Python
  if ($python -and $python.Version -ge $MinPython) {
    Write-Host ("  [found]     Python {0} ({1}) - nothing to install" -f $python.Version, $python.Command) -ForegroundColor Green
  } else {
    if ($python) {
      $why = "Python $($python.Version) is older than $MinPython"
    } else {
      $why = "No Python was found on this machine"
    }
    Write-Host ("  [missing]   {0}. The skill cannot draw anything without one." -f $why) -ForegroundColor Yellow

    $install = $true
    if (-not $Quiet) {
      $answer = Read-Host "Install Python $WantPython now? [Y/n]"
      $install = [string]::IsNullOrWhiteSpace($answer) -or $answer -match '^\s*[Yy]'
    }

    if ($install) {
      # uv downloads a standalone build into the user's own folder: no
      # administrator rights, no package manager to install first, and the same
      # two commands on Windows and macOS. The skill's own commands already run
      # through uv, so this adds no dependency that was not there already.
      try {
        $uv = Resolve-Uv
        Write-Host ("  installing Python {0}" -f $WantPython)
        & $uv python install $WantPython
        if ($LASTEXITCODE -ne 0) { throw "uv python install exited with $LASTEXITCODE" }
        Write-Host ("  [ok]        Python {0} installed" -f $WantPython) -ForegroundColor Green
      } catch {
        Write-Host ("  could not install Python automatically: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
        Write-Host "  Install Python $WantPython yourself from https://www.python.org/downloads/ and run this again."
      }
    } else {
      Write-Host "  Skipped. The skill will install, but cannot run until a Python is present." -ForegroundColor Yellow
    }
  }
  Write-Host ''
}

# --- boundaries ------------------------------------------------------------
# The package carries the two boundary sets as zips, so an ordinary install
# needs no separate download and no manual unpacking. A path given on the
# command line still wins: somebody who already holds them should not be made
# to keep a second copy.
$Bundle = @{
  provinces = Join-Path $Root 'shapefiles\provinces.zip'
  communes  = Join-Path $Root 'shapefiles\communes.zip'
}
$HasBundle = -not $SkipShapefiles -and
             ($Bundle.Values | Where-Object { Test-Path $_ }).Count -eq $Bundle.Count

if (-not $Shapefiles -and $HasBundle) {
  $target = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.easy-map\shapefiles'
  $already = @('provinces', 'communes') |
             Where-Object { Get-ChildItem (Join-Path $target $_) -Filter *.shp -ErrorAction SilentlyContinue }

  if ($already.Count -eq 2) {
    Write-Host ''
    Write-Host ("  [found]     boundaries already unpacked at {0}" -f $target) -ForegroundColor Green
    $Shapefiles = $target
  } else {
    $unpack = $true
    if (-not $Quiet) {
      Write-Host ''
      Write-Host "This package includes Vietnam's administrative boundaries."
      Write-Host ("  Unpacking them takes about 135 MB at {0}" -f $target)
      $answer = Read-Host "Unpack them now? [Y/n]"
      $unpack = [string]::IsNullOrWhiteSpace($answer) -or $answer -match '^\s*[Yy]'
    }
    if ($unpack) {
      foreach ($level in 'provinces', 'communes') {
        $into = Join-Path $target $level
        Write-Host ("  unpacking {0}" -f $level)
        New-Item -ItemType Directory -Force $into | Out-Null
        Expand-Archive -LiteralPath $Bundle[$level] -DestinationPath $into -Force
      }
      $Shapefiles = $target
      Write-Host "  [ok]        boundaries unpacked" -ForegroundColor Green
    }
  }
}

if (-not $Shapefiles -and -not $Quiet) {
  Write-Host ''
  Write-Host "Where are the administrative boundary shapefiles?"
  Write-Host "  A folder holding provinces\ and communes\. Press Enter to skip;"
  Write-Host "  see shapefiles\README.md for what is needed and where to get it."
  $Shapefiles = (Read-Host "Path").Trim('"', ' ')
}
if ($Shapefiles) {
  $Shapefiles = [IO.Path]::GetFullPath($Shapefiles)
  $missing = @('provinces', 'communes') |
             Where-Object { -not (Test-Path (Join-Path $Shapefiles $_)) }
  if ($missing) {
    Write-Host ("  warning: {0} has no {1} subfolder. Recorded anyway; the engine will say so when it draws." -f
                $Shapefiles, ($missing -join ' or ')) -ForegroundColor Yellow
  }
  [Environment]::SetEnvironmentVariable('EASY_MAP_SHAPEFILES', $Shapefiles, 'User')
  $env:EASY_MAP_SHAPEFILES = $Shapefiles
  Write-Host ("  EASY_MAP_SHAPEFILES set for your account -> {0}" -f $Shapefiles)
}

# --- copy ------------------------------------------------------------------
$Parts = @('SKILL.md', 'scripts', 'assets', 'references', 'agents')

foreach ($key in $Targets) {
  $a = $found | Where-Object { $_.Key -eq $key } | Select-Object -First 1
  $dest = Join-Path $a.Directory "skills\$SkillName"

  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  New-Item -ItemType Directory -Force $dest | Out-Null

  foreach ($part in $Parts) {
    $from = Join-Path $Source $part
    if (-not (Test-Path $from)) { continue }
    if (Test-Path $from -PathType Container) {
      Copy-Item $from $dest -Recurse -Force
    } else {
      Copy-Item $from $dest -Force
    }
  }
  Get-ChildItem $dest -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  # The instructions ship with paths relative to the source repository. An
  # installed copy is not inside that repository, so point every command at the
  # engine that was just copied next to it.
  $skillFile = Join-Path $dest 'SKILL.md'
  $text = Get-Content $skillFile -Raw -Encoding UTF8
  $engine = (Join-Path $dest 'scripts\easy_map.py') -replace '\\', '/'
  $before = ([regex]::Matches($text, [regex]::Escape("skills/$SkillName/scripts/easy_map.py"))).Count
  $text = $text -replace [regex]::Escape("skills/$SkillName/scripts/easy_map.py"), "`"$engine`""

  # `Set-Content -Encoding UTF8` writes a byte-order mark on Windows PowerShell
  # 5.1, and a BOM in front of the opening `---` hides the YAML frontmatter:
  # Codex then does not register the skill at all, while Claude Code strips the
  # mark and gives no sign anything is wrong. Write the bytes directly instead.
  [IO.File]::WriteAllText($skillFile, $text, (New-Object Text.UTF8Encoding $false))

  # That frontmatter is the only reason either assistant opens this file, so
  # check it survived rather than trusting the encoding flag.
  $head = [IO.File]::ReadAllBytes($skillFile) | Select-Object -First 3
  if (($head -join ',') -ne '45,45,45') {
    throw ("$skillFile does not begin with ---, so the assistant will not see " +
           "its frontmatter (first bytes: $($head -join ' ')).")
  }

  $files = (Get-ChildItem $dest -Recurse -File).Count
  Write-Host ''
  Write-Host ("  installed for {0}" -f $a.Label) -ForegroundColor Green
  Write-Host ("    {0}" -f $dest)
  Write-Host ("    {0} files, {1} command paths rewritten" -f $files, $before)
}

Write-Host ''
Write-Host "Done. Start a new assistant session so it picks the skill up." -ForegroundColor Cyan
if (-not $Shapefiles) {
  Write-Host "No boundaries recorded: the skill will read and check data but cannot draw." -ForegroundColor Yellow
}
