"""
PyInstaller runtime hook — runs before any user code.
Adds gpt4all's native DLL directory to the Windows DLL search path so
ctypes can find libllmodel.dll's dependencies when loading by full path.
"""
import os
import sys

if sys.platform == "win32" and hasattr(sys, "_MEIPASS"):
    dirs = [
        os.path.join(sys._MEIPASS, "gpt4all", "llmodel_DO_NOT_MODIFY", "build"),
        sys._MEIPASS,
    ]
    for d in dirs:
        if os.path.isdir(d):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
