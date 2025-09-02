#!/usr/bin/env python3
"""
Send macOS notifications as a reusable class or CLI.

CLI examples
- python notification.py                             # shows "Hello world."
- python notification.py -m "Custom"                 # shows custom message
- python notification.py -m msg -t Title -s Subtitle # adds title + subtitle
- python notification.py -m msg -i /path/to.png      # include content image (terminal-notifier)
- python notification.py -m msg -I /path/to.png      # set small app icon (terminal-notifier)
- python notification.py -m msg -f ./script.py       # run script when clicked (terminal-notifier)

Notes
- Uses AppleScript (osascript) for basic notifications and subtitles.
- Uses terminal-notifier (if available) for images/icons and click actions.
- When no click action is set, sender defaults to com.apple.Terminal for nicer icon.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _escape_applescript_string(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


@dataclass
class Notification:
    """Reusable macOS notification helper.

    Instance attributes act as defaults for every push(), and can be overridden per call.
    """

    title: str = "Scribbles"
    subtitle: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    sender: Optional[str] = None  # e.g., com.apple.Terminal (terminal-notifier only)
    auto_terminal_sender: bool = True  # default Terminal sender when not using click

    def _ensure_macos(self) -> bool:
        if platform.system() != "Darwin":
            sys.stderr.write("Error: macOS (Darwin) is required for notifications.\n")
            return False
        return True

    def _build_execute_wrapper(self, script_path: str) -> str:
        py = sys.executable or "/usr/bin/env python3"
        abs_script = str(Path(script_path).expanduser().resolve())
        fd, wrapper_path = tempfile.mkstemp(prefix="notify-run-", suffix=".sh")
        os.close(fd)
        contents = f"#!/bin/bash\n\n\"{py}\" \"{abs_script}\" >/dev/null 2>&1 &\n"
        with open(wrapper_path, "w", encoding="utf-8") as f:
            f.write(contents)
        os.chmod(wrapper_path, os.stat(wrapper_path).st_mode | stat.S_IEXEC)
        return wrapper_path

    def push(
        self,
        message: str = "Hello world.",
        *,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        image: Optional[str] = None,
        icon: Optional[str] = None,
        function: Optional[str] = None,
        sender: Optional[str] = None,
    ) -> int:
        """Send a notification. Instance defaults are used unless overridden.

        Args
        - message: Notification body text.
        - title/subtitle/image/icon/sender/function: Optional per-call overrides.
        Returns 0 on success; non-zero on error.
        """
        if not self._ensure_macos():
            return 1

        # Merge defaults with overrides
        title = title if title is not None else self.title
        subtitle = subtitle if subtitle is not None else self.subtitle
        image = image if image is not None else self.image
        icon = icon if icon is not None else self.icon

        # Choose sender: explicit arg > instance default > auto (if no click)
        if sender is not None:
            effective_sender = sender
        elif self.sender is not None:
            effective_sender = self.sender
        elif self.auto_terminal_sender and not function:
            effective_sender = "com.apple.Terminal"
        else:
            effective_sender = None

        use_terminal_notifier = (
            (bool(image) or bool(icon) or bool(function))
            and shutil.which("terminal-notifier") is not None
        )

        try:
            if use_terminal_notifier:
                if image and not os.path.exists(os.path.expanduser(image)):
                    sys.stderr.write(f"Warning: image not found at path: {image}. Proceeding without image.\n")
                    image = None
                if icon and not os.path.exists(os.path.expanduser(icon)):
                    sys.stderr.write(f"Warning: icon not found at path: {icon}. Proceeding without icon.\n")
                    icon = None
                if function and not os.path.exists(os.path.expanduser(function)):
                    sys.stderr.write(f"Warning: function script not found at path: {function}. Proceeding without click action.\n")
                    function = None

                cmd = [
                    "terminal-notifier",
                    "-message",
                    message,
                    "-title",
                    title,
                    "-ignoreDnD",
                ]
                if effective_sender:
                    cmd += ["-sender", effective_sender]
                if subtitle:
                    cmd += ["-subtitle", subtitle]
                if image:
                    img_url = Path(image).expanduser().resolve().as_uri()
                    cmd += ["-contentImage", img_url]
                if icon:
                    icon_url = Path(icon).expanduser().resolve().as_uri()
                    cmd += ["-appIcon", icon_url]
                if function:
                    wrapper = self._build_execute_wrapper(function)
                    cmd += ["-execute", wrapper]
            else:
                # AppleScript path
                esc_msg = _escape_applescript_string(message)
                esc_title = _escape_applescript_string(title)
                script = f'display notification "{esc_msg}" with title "{esc_title}"'
                if subtitle:
                    esc_sub = _escape_applescript_string(subtitle)
                    script += f' subtitle "{esc_sub}"'
                cmd = ["osascript", "-e", script]

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                sys.stderr.write(result.stderr.strip() + "\n")
                if (image or icon or function) and not use_terminal_notifier:
                    sys.stderr.write(
                        "Tip: For image/icon/click support, install terminal-notifier (brew install terminal-notifier).\n"
                    )
            return result.returncode
        except FileNotFoundError:
            sys.stderr.write("Error: required command not found (osascript or terminal-notifier).\n")
            return 1


def _cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send a macOS push notification with a custom message.")
    parser.add_argument("-m", "--message", default="test.")
    parser.add_argument("-t", "--title", default="WebTerm")
    parser.add_argument("-s", "--subtitle", default=None)
    parser.add_argument("-i", "--image", default="./tests/schuberto.png")
    parser.add_argument("-I", "--icon", default=None)
    parser.add_argument("--sender", default=None)
    parser.add_argument("-f", "--function", default=None, help="Path to a Python file to run on click (terminal-notifier)")

    args = parser.parse_args(argv)
    n = Notification(title=args.title)
    return n.push(
        args.message,
        title=args.title,
        subtitle=args.subtitle,
        image=args.image,
        icon=args.icon,
        function=args.function,
        sender=args.sender,
    )


if __name__ == "__main__":
    sys.exit(_cli())

