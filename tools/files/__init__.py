"""Shared multi-format file handling library.

This package is NOT a registered tool (the registry only loads
tools/<name>/<name>.py). It's the engine behind the unified read/write/edit/
delete file tools, which dispatch by file extension to the right handler.
"""

from tools.files.dispatch import read_any, write_any, edit_any

__all__ = ["read_any", "write_any", "edit_any"]
