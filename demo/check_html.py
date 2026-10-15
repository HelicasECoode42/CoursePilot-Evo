#!/usr/bin/env python3
"""Validate the standalone CoursePilot demo's basic HTML structure."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "coursepilot-guided-demo.html"
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class StructureChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.ids: set[str] = set()
        self.errors: list[str] = []
        self.inline_scripts = 0
        self.in_script = False
        self.script_source: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate id: {element_id}")
            self.ids.add(element_id)
        if tag == "script":
            self.inline_scripts += 1
            self.in_script = True
            if attributes.get("src"):
                self.errors.append("demo must not load an external script")
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate id: {element_id}")
            self.ids.add(element_id)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False
        if tag in VOID_ELEMENTS:
            self.errors.append(f"void element has a closing tag: {tag}")
            return
        if not self.stack:
            self.errors.append(f"unexpected closing tag: {tag}")
            return
        opening = self.stack.pop()
        if opening != tag:
            self.errors.append(f"expected </{opening}> but found </{tag}>")

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.script_source.append(data)


def main() -> int:
    parser = StructureChecker()
    parser.feed(DEMO.read_text(encoding="utf-8"))
    parser.close()
    if parser.stack:
        parser.errors.append("unclosed elements: " + ", ".join(parser.stack))
    if parser.inline_scripts != 1:
        parser.errors.append(f"expected one inline script, found {parser.inline_scripts}")
    if "main" not in parser.ids or "screen" not in parser.ids:
        parser.errors.append("main content and question screen IDs are required")
    node = shutil.which("node")
    if not node:
        parser.errors.append("Node.js is required to check the inline script syntax")
    else:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js") as source:
            source.write("".join(parser.script_source))
            source.flush()
            result = subprocess.run(
                [node, "--check", source.name], capture_output=True, text=True
            )
        if result.returncode != 0:
            parser.errors.append("inline script syntax check failed: " + result.stderr.strip())
    if parser.errors:
        for error in parser.errors:
            print(f"FAIL: {error}")
        return 1
    print(
        f"PASS: {DEMO.relative_to(ROOT)} has balanced HTML, unique IDs, and valid inline script syntax"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
