param([switch]$AllModels, [switch]$Klein9B)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot 'ComfyUI_windows_portable'
$cache = Join-Path $PSScriptRoot '.downloads'
$null = New-Item -ItemType Directory -Force $cache

function Get-VerifiedFile([string]$Uri, [string]$Path, [string]$Digest) {
    if (Test-Path -LiteralPath $Path) {
        if ((Get-FileHash -LiteralPath $Path).Hash -ne $Digest) {
            throw "Unexpected checksum for $Path. Move the file aside and rerun setup."
        }
        return
    }
    $null = New-Item -ItemType Directory -Force (Split-Path $Path)
    $part = "$Path.part"
    Write-Host "Downloading $(Split-Path $Path -Leaf)"
    if (!(Test-Path -LiteralPath $part) -or (Get-FileHash -LiteralPath $part).Hash -ne $Digest) {
        & curl.exe --fail --location --retry 3 --continue-at - --output $part $Uri
        if ($LASTEXITCODE -ne 0) { throw 'Download interrupted. Rerun setup to resume.' }
        if ((Get-FileHash -LiteralPath $part).Hash -ne $Digest) {
            throw "Checksum mismatch. Remove $part and rerun setup."
        }
    }
    Move-Item -LiteralPath $part -Destination $Path
}

$lock = [IO.File]::Open((Join-Path $cache 'setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    if (!(Test-Path -LiteralPath $runtime)) {
        $archive = Join-Path $cache 'ComfyUI-v0.46.0-nvidia.7z'
        Get-VerifiedFile 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.46.0/ComfyUI_windows_portable_nvidia.7z' $archive '6a5255c7ec01fdc54bdbd8e4507073cf6acda2fbeea74ae1829a50681af5fac6'
        & tar.exe -xf $archive -C $cache
        if ($LASTEXITCODE -ne 0) { throw 'Could not extract the NVIDIA runtime.' }
        $extracted = (Resolve-Path -LiteralPath (Join-Path $cache 'ComfyUI_windows_portable')).Path
        if ((Split-Path $extracted) -ne $cache -or (Split-Path $runtime) -ne $PSScriptRoot) {
            throw 'Unexpected runtime installation directory.'
        }
        Move-Item -LiteralPath $extracted -Destination $runtime
    }
    if (!(Test-Path -LiteralPath "$runtime/python_embeded/python.exe") -or !(Test-Path -LiteralPath "$runtime/ComfyUI/main.py")) {
        throw "Incomplete portable installation at $runtime. Move it aside before retrying."
    }
    $models = Join-Path $runtime 'ComfyUI/models'
    $shared = 'https://huggingface.co/Comfy-Org/Flux-2-Klein-4B/resolve/5b3abca5c0dc1ecd4eaf3340868d09063fc1c965/split_files'
    $bfl = 'https://huggingface.co/black-forest-labs'
    Get-VerifiedFile "$shared/text_encoders/qwen_3_4b.safetensors" "$models/text_encoders/qwen_3_4b.safetensors" '6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a'
    Get-VerifiedFile "$shared/vae/flux2-vae.safetensors" "$models/vae/flux2-vae.safetensors" '868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3'
    Get-VerifiedFile "$bfl/FLUX.2-klein-4b-fp8/resolve/5b4408e59397a4a37ccb46afe426d8ed86379441/flux-2-klein-4b-fp8.safetensors" "$models/diffusion_models/flux-2-klein-4b-fp8.safetensors" '97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6'
    if ($AllModels) {
        Get-VerifiedFile "$bfl/FLUX.2-klein-4b-nvfp4/resolve/1db2b2f776c24b76f1122e5f69ab1949fc620068/flux-2-klein-4b-nvfp4.safetensors" "$models/diffusion_models/flux-2-klein-4b-nvfp4.safetensors" 'd8c5007b6a3bbbdfd38538bbcef5101a55dfde81894f58d2e3c8701cdef3542b'
        Get-VerifiedFile "$bfl/FLUX.2-klein-base-4b-fp8/resolve/103db268c10d4d3921101b46057671f9ac460da6/flux-2-klein-base-4b-fp8.safetensors" "$models/diffusion_models/flux-2-klein-base-4b-fp8.safetensors" '44bab3a86fe98b85d21dd2a4729ebdc3ae51fb8a39f76e457e18c724219e6840'
    }
    if ($Klein9B) {
        $checkpoint = 'flux-2-klein-9b-fp8.safetensors'
        $destination = Join-Path "$models/diffusion_models" $checkpoint
        $candidate = $destination
        if (!(Test-Path -LiteralPath $destination)) {
            $staging = Join-Path $cache 'klein-9b'
            $candidate = Join-Path $staging $checkpoint
            if (!(Test-Path -LiteralPath $candidate)) {
                $repo = 'black-forest-labs/FLUX.2-klein-9b-fp8'
                $revision = '4d7225e69b516f7dc74779d1f6602abbe6ab4647'
                Write-Host "Downloading $checkpoint from the approved Hugging Face account"
                $download = @'
import sys
from getpass import getpass
from huggingface_hub import get_token, hf_hub_download

repo, filename, revision, folder = sys.argv[1:]
token = get_token()
if not token and sys.stdin.isatty():
    token = getpass('Hugging Face read token for this download (hidden): ').strip()
if not token:
    sys.exit('A Hugging Face read token or a manually downloaded checkpoint is required.')
hf_hub_download(repo, filename, revision=revision, local_dir=folder, token=token)
'@
                & "$runtime/python_embeded/python.exe" -s -c $download $repo $checkpoint $revision $staging
                if ($LASTEXITCODE -ne 0) {
                    throw "Could not download Klein 9B. Check your Hugging Face model access and local login, or place the checkpoint at $destination and rerun setup."
                }
            }
        }
        if ((Get-FileHash -LiteralPath $candidate).Hash -ne '865ba09f5b4c3cbd3468a4bd3acb9fcb2f8740c54317482f0bcd4ed1d3655cee') {
            throw "Unexpected checksum for $candidate. Move the file aside and rerun setup."
        }
        if ($candidate -ne $destination) { Move-Item -LiteralPath $candidate -Destination $destination }
        $encoder = 'qwen_3_8b_fp8mixed.safetensors'
        Get-VerifiedFile "https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/1138ce884c8e977cdacacbe779784fec4426bb3f/split_files/text_encoders/$encoder" "$models/text_encoders/$encoder" 'abad16806e0cbabc54e0325d6565847443fe396d5f0be38bb3cd3fe75a1201d6'
    }
    Write-Host 'Ready. Double-click Start ImageMagic.cmd.'
} finally {
    $lock.Dispose()
}
