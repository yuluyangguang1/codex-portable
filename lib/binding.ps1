# USB drive binding for Claude Portable
# Computes SHA256 hash of the volume's UniqueId (NTFS GUID).
# Storing only the hash prevents attackers from learning the original fingerprint.
#
# Modes:
#   check <portable_dir> <lock_file>  → exit 0 if match, 1 if mismatch, 2 if no lock
#   create <portable_dir> <lock_file> → write current fingerprint hash to lock file

param(
    [Parameter(Mandatory=$true)][ValidateSet('check','create')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$PortableDir,
    [Parameter(Mandatory=$true)][string]$LockFile
)

function Get-Fingerprint {
    param([string]$Path)
    try {
        $absolute = (Resolve-Path $Path -ErrorAction Stop).Path
        $drive = (Split-Path $absolute -Qualifier).TrimEnd(':')
        if (-not $drive) { return $null }

        # Method 1: Volume UniqueId (preferred — kernel-level GUID, requires NTFS internals to fake)
        try {
            $vol = Get-Volume -DriveLetter $drive -ErrorAction Stop
            if ($vol.UniqueId) { return "vol:$($vol.UniqueId)" }
        } catch {}

        # Method 2: WMI Win32_Volume.DeviceID (alternative GUID source)
        try {
            $wmi = Get-CimInstance -ClassName Win32_Volume -Filter "DriveLetter='${drive}:'" -ErrorAction Stop
            if ($wmi.DeviceID) { return "wmi:$($wmi.DeviceID)" }
        } catch {}

        # Method 3: Volume serial number (weakest, but always available)
        # Format: 1234-5678 from `vol`
        $volOutput = & cmd /c "vol ${drive}:" 2>$null
        $serialMatch = [regex]::Match([string]::Join("`n", $volOutput), '([0-9A-Fa-f]{4}-[0-9A-Fa-f]{4})')
        if ($serialMatch.Success) { return "ser:$($serialMatch.Groups[1].Value)" }
    } catch {}
    return $null
}

function Get-Hash {
    param([string]$InputString)
    if (-not $InputString) { return $null }
    # Add a static salt so attackers can't easily compute the hash from a guessed fingerprint
    $salted = "ClaudePortable-v1::" + $InputString
    $bytes = [Text.Encoding]::UTF8.GetBytes($salted)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hashBytes) -replace '-','').ToLower()
    } finally {
        $sha.Dispose()
    }
}

$fingerprint = Get-Fingerprint -Path $PortableDir
if (-not $fingerprint) {
    # Could not determine fingerprint — fail closed
    exit 3
}
$currentHash = Get-Hash -InputString $fingerprint

if ($Mode -eq 'check') {
    if (-not (Test-Path $LockFile)) { exit 2 }
    try {
        $storedHash = (Get-Content $LockFile -Raw -ErrorAction Stop).Trim()
        if ($currentHash -eq $storedHash) { exit 0 } else { exit 1 }
    } catch {
        exit 1
    }
} elseif ($Mode -eq 'create') {
    try {
        # Use [IO.File]::WriteAllText to avoid BOM
        [IO.File]::WriteAllText($LockFile, $currentHash)
        exit 0
    } catch {
        exit 4
    }
}
exit 5
