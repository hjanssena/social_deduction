"""
build.py — Village of Shadows packaging script (cross-platform).

Usage:
    python build.py 0.2.0
    python build.py 0.2.0 --renpy-sdk "/path/to/renpy-sdk"
    python build.py 0.2.0 --skip-renpy          # skip Ren'Py build
    python build.py 0.2.0 --skip-installer       # skip Inno Setup step (Windows only)

Prerequisites:
    pip install pyinstaller
    Ren'Py SDK (https://www.renpy.org/latest.html) — only needed for --renpy-sdk
    Inno Setup 6 (Windows only, https://jrsoftware.org/isinfo.php)

Outputs:
    dist/game_server/           PyInstaller bundle
    dist/VillageOfShadows-<v>-pc/   Ren'Py build (if built)
    dist/VillageOfShadows-<v>-Setup.exe   Installer (Windows only, if built)
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Locate the build Python.  On Windows we need a 3.11 venv for GPT4All compat;
# on Linux the system / active venv Python is fine.
if IS_WINDOWS:
    PYTHON_BUILD = os.path.join(ROOT, "venv311", "Scripts", "python.exe")
else:
    PYTHON_BUILD = os.path.join(ROOT, "virtenv", "bin", "python")

RENPY_PROJECT = os.path.join(ROOT, "renpy_client")
OPTIONS_RPY = os.path.join(RENPY_PROJECT, "game", "options.rpy")
VERSION_FILE = os.path.join(ROOT, "VERSION")
DIST = os.path.join(ROOT, "dist")
INNO_COMPILER = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

EXE_EXT = ".exe" if IS_WINDOWS else ""
SERVER_EXE_NAME = f"game_server{EXE_EXT}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def update_version_file(version: str):
    with open(VERSION_FILE, "w") as f:
        f.write(version + "\n")
    print(f"VERSION file updated to {version}")


def update_options_rpy(version: str):
    with open(OPTIONS_RPY, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'(define\s+config\.version\s*=\s*)"[^"]*"',
        f'\\1"{version}"',
        content,
    )
    with open(OPTIONS_RPY, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"options.rpy version updated to {version}")


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------

def build_server():
    """Run PyInstaller using game_server.spec (or auto-generate), via the build Python."""
    if not os.path.isfile(PYTHON_BUILD):
        if IS_WINDOWS:
            hint = "Create it with: py -3.11 -m venv venv311 && venv311\\Scripts\\pip install -r requirements.txt"
        else:
            hint = "Create it with: python -m venv virtenv && virtenv/bin/pip install -r requirements.txt"
        raise FileNotFoundError(f"Build Python not found at {PYTHON_BUILD}. {hint}")

    spec = os.path.join(ROOT, "game_server.spec")
    if os.path.isfile(spec):
        run([PYTHON_BUILD, "-m", "PyInstaller", "--noconfirm", spec], cwd=ROOT)
    else:
        # Auto-generate a basic PyInstaller invocation
        print("No game_server.spec found — running PyInstaller with default options.")
        run([
            PYTHON_BUILD, "-m", "PyInstaller",
            "--noconfirm", "--name", "game_server",
            "--collect-all", "llama_cpp",
            "server_entry.py",
        ], cwd=ROOT)

    server_dist = os.path.join(DIST, "game_server")

    # Copy config.json next to the exe (relative path open() in server code).
    shutil.copy(os.path.join(ROOT, "config.json"), server_dist)
    print(f"config.json copied to {server_dist}")

    # GPT4All DLL fix (Windows only): create libllmodel.dll alias
    if IS_WINDOWS:
        gpt4all_build = os.path.join(server_dist, "_internal", "gpt4all", "llmodel_DO_NOT_MODIFY", "build")
        llmodel = os.path.join(gpt4all_build, "llmodel.dll")
        libllmodel = os.path.join(gpt4all_build, "libllmodel.dll")
        if os.path.isfile(llmodel) and not os.path.isfile(libllmodel):
            shutil.copy(llmodel, libllmodel)
            print(f"Created libllmodel.dll alias in {gpt4all_build}")

    # Copy llms/ next to the exe so config.json's ./llms/ path resolves correctly.
    llms_src = os.path.join(ROOT, "llms")
    llms_dst = os.path.join(server_dist, "llms")
    if os.path.isdir(llms_src):
        if os.path.exists(llms_dst):
            shutil.rmtree(llms_dst)
        shutil.copytree(llms_src, llms_dst)
        print(f"llms/ copied to {llms_dst}")


def build_renpy(renpy_sdk: str, version: str):
    """Call the Ren'Py SDK distributor CLI, then inject the game_server bundle.

    After building, extracts the pc zip and copies game_server/ inside so
    Ren'Py's script.rpy can find and launch it via renpy.config.basedir.
    """
    # Find the Ren'Py executable (platform-aware)
    renpy_exe = None
    for candidate in ["renpy.exe", "renpy.sh", "renpy"]:
        path = os.path.join(renpy_sdk, candidate)
        if os.path.isfile(path):
            renpy_exe = path
            break

    if renpy_exe is None:
        print(f"WARNING: renpy executable not found in {renpy_sdk}, skipping Ren'Py build.")
        return

    # Syntax: renpy <sdk-launcher> distribute <project> --destination <dest>
    sdk_launcher = os.path.join(renpy_sdk, "launcher")
    os.makedirs(DIST, exist_ok=True)
    run([renpy_exe, sdk_launcher, "distribute", RENPY_PROJECT, "--destination", DIST])

    # Extract the pc zip into dist/ so we can inject the server.
    pc_zip = os.path.join(DIST, f"VillageOfShadows-{version}-pc.zip")
    if not os.path.isfile(pc_zip):
        # Try to find it if Ren'Py used a slightly different name.
        for f in os.listdir(DIST):
            if f.endswith("-pc.zip"):
                pc_zip = os.path.join(DIST, f)
                break

    if not os.path.isfile(pc_zip):
        print("WARNING: could not find pc.zip — skipping server injection.")
        return

    extract_dir = os.path.join(DIST, f"VillageOfShadows-{version}-pc")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    print(f"Extracting {pc_zip} → {extract_dir}")
    with zipfile.ZipFile(pc_zip, "r") as zf:
        zf.extractall(DIST)

    # The zip contains a top-level folder; find it.
    pc_root = None
    with zipfile.ZipFile(pc_zip, "r") as zf:
        top = {name.split("/")[0] for name in zf.namelist()}
        if len(top) == 1:
            pc_root = os.path.join(DIST, top.pop())
    if pc_root and pc_root != extract_dir:
        os.rename(pc_root, extract_dir)

    # Copy the PyInstaller server bundle into the Ren'Py folder.
    server_src = os.path.join(DIST, "game_server")
    server_dst = os.path.join(extract_dir, "game_server")
    if os.path.exists(server_dst):
        shutil.rmtree(server_dst)
    shutil.copytree(server_src, server_dst)
    print(f"Injected game_server/ → {server_dst}")


def build_installer(version: str, has_renpy: bool):
    """Generate an Inno Setup .iss file and compile it (Windows only)."""
    if not IS_WINDOWS:
        print("Skipping Inno Setup installer (not on Windows).")
        _build_linux_archive(version, has_renpy)
        return

    if not os.path.isfile(INNO_COMPILER):
        print(f"WARNING: Inno Setup not found at {INNO_COMPILER}, skipping installer.")
        return

    # After build_renpy the extracted+injected folder is the single source of truth.
    # If no Ren'Py build, fall back to server-only.
    renpy_dist = os.path.join(DIST, f"VillageOfShadows-{version}-pc")
    server_dist = os.path.join(DIST, "game_server")
    output_dir = DIST
    output_name = f"VillageOfShadows-{version}-Setup"

    if has_renpy and os.path.isdir(renpy_dist):
        # The extracted folder already contains game_server/ inside it.
        files_section = textwrap.dedent(f"""\
            ; --- Full game (Ren'Py frontend + embedded game_server) ---
            Source: "{renpy_dist}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
        """)
    else:
        # Server-only fallback (no Ren'Py build).
        files_section = textwrap.dedent(f"""\
            ; --- Game server (PyInstaller bundle) ---
            Source: "{server_dist}\\*"; DestDir: "{{app}}\\game_server"; Flags: ignoreversion recursesubdirs createallsubdirs
        """)

    iss = textwrap.dedent(f"""\
        #define AppName "Village of Shadows"
        #define AppVersion "{version}"
        #define AppPublisher "Hugo Janssen"
        #define AppExeName "VillageOfShadows.exe"

        [Setup]
        AppId={{{{8B3F1A2C-4D5E-4F6A-9B0C-1D2E3F4A5B6C}}}}
        AppName={{#AppName}}
        AppVersion={{#AppVersion}}
        AppPublisher={{#AppPublisher}}
        DefaultDirName={{autopf}}\\VillageOfShadows
        DefaultGroupName={{#AppName}}
        OutputDir={output_dir}
        OutputBaseFilename={output_name}
        Compression=lzma2/ultra64
        SolidCompression=yes
        WizardStyle=modern

        [Languages]
        Name: "english"; MessagesFile: "compiler:Default.isl"

        [Tasks]
        Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

        [Files]
        {files_section}

        [Icons]
        Name: "{{group}}\\{{#AppName}}"; Filename: "{{app}}\\game\\{{#AppExeName}}"
        Name: "{{userdesktop}}\\{{#AppName}}"; Filename: "{{app}}\\game\\{{#AppExeName}}"; Tasks: desktopicon

        [Run]
        Filename: "{{app}}\\game\\{{#AppExeName}}"; Description: "{{cm:LaunchProgram,{{#AppName}}}}"; Flags: nowait postinstall skipifsilent
    """)

    iss_path = os.path.join(ROOT, "installer.iss")
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(iss)
    print(f"installer.iss written")

    run([INNO_COMPILER, iss_path])
    print(f"\nInstaller: {os.path.join(output_dir, output_name)}.exe")


def _build_linux_archive(version: str, has_renpy: bool):
    """On Linux, create a .tar.gz archive instead of an installer."""
    renpy_dist = os.path.join(DIST, f"VillageOfShadows-{version}-pc")
    server_dist = os.path.join(DIST, "game_server")

    if has_renpy and os.path.isdir(renpy_dist):
        archive_src = renpy_dist
    elif os.path.isdir(server_dist):
        archive_src = server_dist
    else:
        print("WARNING: nothing to archive.")
        return

    archive_name = f"VillageOfShadows-{version}-linux"
    archive_path = os.path.join(DIST, archive_name)

    import tarfile
    tar_path = archive_path + ".tar.gz"
    print(f"Creating {tar_path}")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(archive_src, arcname=archive_name)
    print(f"Archive: {tar_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build and package Village of Shadows.")
    parser.add_argument("version", help="Version string, e.g. 0.2.0")
    parser.add_argument("--renpy-sdk", metavar="PATH", help="Path to Ren'Py SDK root")
    parser.add_argument("--skip-server", action="store_true", help="Skip PyInstaller step")
    parser.add_argument("--skip-renpy", action="store_true", help="Skip Ren'Py build step")
    parser.add_argument("--skip-installer", action="store_true", help="Skip installer/archive step")
    args = parser.parse_args()

    version = args.version
    has_renpy_sdk = bool(args.renpy_sdk) and not args.skip_renpy

    print(f"\n=== Building Village of Shadows v{version} ({platform.system()}) ===\n")

    # 1. Update version strings
    update_version_file(version)
    update_options_rpy(version)

    # 2. PyInstaller
    if not args.skip_server:
        build_server()
    else:
        print("Skipping server build.")

    # 3. Ren'Py
    if has_renpy_sdk:
        build_renpy(args.renpy_sdk, version)
    else:
        print("Skipping Ren'Py build (no --renpy-sdk provided or --skip-renpy set).")

    # 4. Installer (Windows) or archive (Linux)
    if not args.skip_installer:
        build_installer(version, has_renpy=has_renpy_sdk)
    else:
        print("Skipping installer/archive build.")

    print(f"\n=== Done: v{version} ===")


if __name__ == "__main__":
    main()
