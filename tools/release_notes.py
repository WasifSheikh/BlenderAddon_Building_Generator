"""Release helper for CI: checks the tag against the manifest version and prints that version's changelog.

    python tools/release_notes.py v1.4.0 > notes.md

Fails when the tag doesn't match `version` in blender_manifest.toml, or CHANGELOG.md has no entry for it.
"""

import os
import re
import sys
import tomllib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(tag):
    with open(os.path.join(REPO, "aa_building_generator", "blender_manifest.toml"), "rb") as fh:
        version = tomllib.load(fh)["version"]
    if tag.lstrip("v") != version:
        sys.exit(f"Tag {tag} does not match the manifest version {version}: bump blender_manifest.toml or retag")
    with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(rf"^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        sys.exit(f"CHANGELOG.md has no '## {version}' section")
    print(m.group(1).strip())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
