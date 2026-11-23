"""Find STELplot's README and user guide, and split them into sections for the help window."""

__author__ = "Daniel Shiwarski"

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def doc_path(name):
    """Path to README.md or USER_GUIDE.md, from the source folder or a built app."""
    roots = [os.path.join(HERE, "docs"), os.path.dirname(HERE)]
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        roots = [os.path.join(frozen, "stelplot", "docs"), frozen] + roots
    for root in roots:
        path = os.path.join(root, name)
        if os.path.exists(path):
            return path
    return None


def icon_path(relative):
    """Path to a file in stelplot/icons (for example 'macos/STEL_Plot_icon_256.png')."""
    roots = [os.path.join(HERE, "icons")]
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        roots.insert(0, os.path.join(frozen, "stelplot", "icons"))
    for root in roots:
        path = os.path.join(root, relative)
        if os.path.exists(path):
            return path
    return None


def split_sections(markdown):
    """[(title, markdown)] split at '## ' headings. Text before the first one is 'Overview'."""
    sections, title, lines = [], "Overview", []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if any(s.strip() for s in lines):
                sections.append((title, "\n".join(lines).strip()))
            title, lines = line[3:].strip(), []
        elif line.startswith("# ") and not sections and not lines:
            continue
        else:
            lines.append(line)
    if any(s.strip() for s in lines):
        sections.append((title, "\n".join(lines).strip()))
    return sections


def load_sections(name):
    path = doc_path(name)
    if path is None:
        return [("Not found", f"{name} was not found next to STELplot.")]
    with open(path, encoding="utf-8") as fh:
        return split_sections(fh.read())
