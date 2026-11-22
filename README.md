# ImageMagic

ImageMagic is a local image generation and editing studio for Windows. Type a prompt to generate a 1024 × 1024 image with FLUX.2 Klein 4B. The three-column gallery keeps the original and its edits together. ComfyUI runs inference on your machine.

The home page lists your sessions. Enter a name and choose **Create session**, or open an existing session to return to its gallery. Use **All sessions** to go back. You can bookmark a session or open several in separate tabs.

Choose **Delete** beside a session to review its image count. Each original and each saved edit counts as one image. The confirmation also shows how many more images are in that session’s trash. Choose **Delete permanently** to remove the session and both sets of images.

Images created before sessions appear together in **Previous images**, including their edits. New sessions keep their images and a small name file in separate folders under the gallery backup directory.

## Install and run

**Windows installer:** Download **ImageMagic-Setup-1.0.0.exe** from the [GitHub releases](https://github.com/sukritganesh/ImageMagic/releases), run it, and open **ImageMagic** from Start. Press **Enter** to download the default models and open the studio. Allow 25 GB of free space. See the [Windows setup guide](docs/WINDOWS-SETUP.md) for first-run instructions, optional models, and uninstall behavior.

### Install from source

Use Windows 11 x64 with an NVIDIA GPU and a driver compatible with the ComfyUI NVIDIA portable build. The studio has been tested on an RTX 4090 Laptop GPU with 16 GB of VRAM and 64 GB of system RAM. Setup uses Windows PowerShell, `curl.exe`, and `tar.exe`. The portable build includes Python.

From PowerShell in a writable folder:

```powershell
git clone https://github.com/sukritganesh/ImageMagic.git
cd ImageMagic
.\setup.ps1
& '.\Start ImageMagic.cmd'
```

The default setup downloads about 14.5 GB, including the archive, encoder, decoder, and fast FP8 checkpoint. Allow additional disk space for the extracted runtime and your gallery. Setup verifies SHA-256 checksums and reuses existing files. Run `.\setup.ps1 -AllModels` to add Compact and Base (about 6.6 GB more). If PowerShell blocks the downloaded setup script, review it and use `Unblock-File .\setup.ps1` where your execution policy permits local scripts.

Double-click **Start ImageMagic.cmd** to start or reopen this installation. The launcher uses port 8188 by default, then tries 8189, 8190, and so on if needed. If this installation is already running, the launcher reopens its current port even if a lower port has since become available. It opens the selected URL in your browser and writes startup diagnostics to `studio.log`.

### Add Klein 9B FP8

Sign in to Hugging Face and request access on the [official Klein 9B FP8 model page](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-fp8). The 9B weights use the FLUX Non-Commercial License. The checkpoint and its Qwen 3 8B text encoder need about 18.1 GB of additional disk space.

After the default setup, run the optional installer from the repository root. It uses your local Hugging Face login if available. Otherwise, paste a [read token](https://huggingface.co/settings/tokens) that can download the gated model at the hidden prompt. Setup uses the pasted token only for the download.

```powershell
.\setup.ps1 -Klein9B
```

If you prefer to download in your browser, save `flux-2-klein-9b-fp8.safetensors` from the model page to `ComfyUI_windows_portable/ComfyUI/models/diffusion_models/` and run `.\setup.ps1 -Klein9B`. Setup verifies that file and downloads the encoder. Refresh the studio to select **Klein 9B · FP8**.

## Use the gallery

- Choose a model and enter a prompt. Klein 4B FP8 is the four-step default. Optional Klein 9B FP8 also uses four steps. Compact uses a smaller 4B checkpoint and encodes text on the CPU. Base uses 50 steps.
- Click a picture to expand it. Scroll or use **+ / −** to zoom, drag to pan, and use **← / →** to compare versions. Escape or a click outside the picture returns you to the previous view.
- Click the caption to read the full prompt or edit the selected version. Describe the change and choose **Generate edit**. The selected image serves as a visual reference. The new version appears on the same card.
- The card and details show which model made the selected version. Edits use the source version's model.
- Open the caption to delete the selected version or the entire card. Each version is a complete PNG, so later edits still work if you delete their source. Deleting the last version removes the card. Click outside a dialog or press Escape to return to the previous view.
- Deleted PNGs stay in a batch folder inside `.trash` in that session’s output folder. To restore them, move them back to the folder containing `.trash` with their original filenames. To reclaim disk space, choose **Empty trash** next to the gallery count. Review the number of images and choose **Delete permanently** to empty that session’s trash.
- Back up `ComfyUI_windows_portable/ComfyUI/output/ImageMagic/` to keep your gallery. The PNG metadata stores the prompt, model, seed, submission time, and version relationships. Preserve the filenames and metadata when moving images.

## Project layout

Edit the studio backend and browser UI in [custom_nodes/imagemagic_studio](custom_nodes/imagemagic_studio/). The launcher copies these files into the portable installation when starting the server. Restart the local ComfyUI process after changing the source. For contributor conventions, see [CONTRIBUTING.md](CONTRIBUTING.md).

Setup downloads third-party software and model weights directly from their publishers. Their respective licenses apply. [ComfyUI release](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.46.0) · [FLUX.2 Klein 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) · [ComfyUI encoder and VAE](https://huggingface.co/Comfy-Org/Flux-2-Klein-4B)
