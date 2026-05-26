# Check if Codex auth.json has valid credentials
# Exit 0 if found, 1 otherwise
# Usage: powershell -File check-config.ps1 <auth_json_path>
param([Parameter(Mandatory=$true)][string]$AuthPath)

if (-not (Test-Path $AuthPath)) { exit 1 }

try {
    $size = (Get-Item $AuthPath).Length
    if ($size -lt 20) { exit 1 }

    $content = Get-Content -Raw -Path $AuthPath -Encoding UTF8
    $data = $content | ConvertFrom-Json -ErrorAction Stop

    # BYOK path: OPENAI_API_KEY must be a non-trivial string
    $key = $data.OPENAI_API_KEY
    if ($key -and $key.Length -gt 5) { exit 0 }

    # ChatGPT OAuth path: tokens.access_token must exist
    if ($data.tokens -and $data.tokens.access_token) { exit 0 }
} catch {}

exit 1
