# ImageMagic

ImageMagic is a native Windows desktop app for local image generation and editing. Type a prompt to generate a 1024 × 1024 image with FLUX.2 Klein 4B. The three-column gallery keeps the original and its edits together. ComfyUI runs inference on your machine.

The home page lists your sessions. Enter a name and choose **Create session**, or open an existing session to return to its gallery. Use **All sessions** to go back. Use **Full screen** or **F11** to toggle fullscreen. **Esc** closes the current image or dialog first, then exits fullscreen.

Choose **Choose folder…** before creating a session. Select a parent folder in the Windows dialog. The form shows the new session folder it will create there (for example, `D:\Artwork\Coast`). If that name is taken, it suggests `Coast (2)`. Choose **Use default** to save in the usual gallery. Originals, edits, and that session’s trash use the selected location. If a drive is disconnected, reconnect it at the same path to reopen the session.

Choose **Delete** beside a session to review its image count. Each original and each saved edit counts as one image. The confirmation also shows how many more images are in that session’s trash. Choose **Delete permanently** to remove the session and both sets of images.

The first time you open the updated studio, it registers existing named sessions in its local SQLite catalog. Their images and save locations stay the same. Images created before named sessions still appear under **Previous images**.

## Install and run

**Windows installer:** Download **ImageMagic-Setup-1.1.0.exe** from the [GitHub releases](https://github.com/sukritganesh/ImageMagic/releases), run it, and open **ImageMagic** from Start. Choose **Download and start** on first launch to install the default models. To upgrade v1.0.0, close the studio and run the installer in the same folder. Allow 25 GB of free space. See the [Windows setup guide](docs/WINDOWS-SETUP.md) for first-run instructions, optional models, and uninstall behavior.

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

Double-click **Start ImageMagic.cmd** to start or reopen this installation. The launcher uses port 8188 by default, then tries 8189, 8190, and so on if needed. If this installation is already running, the launcher reopens its current port even if a lower port has since become available. The desktop window connects to that service over loopback. Opening the launcher again brings the same window forward. Closing the window lets queued jobs finish in the background. Startup diagnostics are in `studio.log`.

### Add Klein 9B FP8

Sign in to Hugging Face and request access on the [official Klein 9B FP8 model page](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-fp8). The 9B weights use the FLUX Non-Commercial License. The checkpoint and its Qwen 3 8B text encoder need about 18.1 GB of additional disk space.

After the default setup, run the optional installer from the repository root. It uses your local Hugging Face login if available. Otherwise, paste a [read token](https://huggingface.co/settings/tokens) that can download the gated model at the hidden prompt. Setup uses the pasted token only for the download.

```powershell
.\setup.ps1 -Klein9B
```

If you prefer to download in your browser, save `flux-2-klein-9b-fp8.safetensors` from the model page to `ComfyUI_windows_portable/ComfyUI/models/diffusion_models/` and run `.\setup.ps1 -Klein9B`. Setup verifies that file and downloads the encoder. Reopen the session to select **Klein 9B · FP8**.

### Add Z-Image-Turbo

From the source or install folder, run `.\setup.ps1 -ZImageTurbo` and reopen the session. Choose **Z-Image-Turbo · BF16** to generate 1024 × 1024 images in eight steps. The setup reuses Klein’s Qwen encoder and downloads about 12.6 GB for the checkpoint and decoder. Instruction edits of these images use Klein 4B FP8. [ComfyUI workflow](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo)

## Use the gallery

- Choose a model and enter a prompt. Klein 4B FP8 is the four-step default. Optional Klein 9B FP8 also uses four steps. Compact uses a smaller 4B checkpoint and encodes text on the CPU. Base uses 50 steps.
- Click a picture to expand it. Scroll or use **+ / −** to zoom, drag to pan, and use **← / →** to compare versions. Escape or a click outside the picture returns you to the previous view.
- Click the caption to read the full prompt or edit the selected version. Describe the change and choose **Generate edit**. The selected image serves as a visual reference. The new version appears on the same card.
- The card and details show which model made the selected version. Klein images use their original model for edits.
- Open the caption to delete the selected version or the entire card. Each version is a complete PNG, so later edits still work if you delete their source. Deleting the last version removes the card. Click outside a dialog or press Escape to return to the previous view.
- Deleted PNGs stay in a batch folder inside `.trash` in that session’s output folder. To restore them, move them back to the folder containing `.trash` with their original filenames. To reclaim disk space, choose **Empty trash** next to the gallery count. Review the number of images and choose **Delete permanently** to empty that session’s trash.
- To back up, stop the studio and copy `ComfyUI_windows_portable/ComfyUI/output/ImageMagic/` (including `imagemagic.sqlite3`) and each custom session folder. Restore custom folders at their original paths, including their `.imagemagic-session` files. The PNG metadata stores the prompt, model, seed, submission time, and version relationships. Preserve filenames and metadata.

## Project layout

- [desktop/](desktop/) — native Windows app, session list, gallery, fullscreen viewer, and build script.
- [launch_studio.py](launch_studio.py) — starts or reuses the local inference service for each installation.
- [storage.py](custom_nodes/imagemagic_studio/storage.py) — SQLite session catalog and save locations.

The source launcher compiles the desktop executable with the .NET Framework compiler included in Windows 11. Close the window before rebuilding. It updates the portable service when its Python files change. For contributor conventions, see [CONTRIBUTING.md](CONTRIBUTING.md).

Setup downloads third-party software and model weights directly from their publishers. Their respective licenses apply. [ComfyUI release](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.46.0) · [FLUX.2 Klein 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) · [ComfyUI encoder and VAE](https://huggingface.co/Comfy-Org/Flux-2-Klein-4B)
