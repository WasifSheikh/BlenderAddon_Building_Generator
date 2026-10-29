"""Run the extension's self-test in background Blender. CI runs this; locally it works the same way:

    blender --background --factory-startup --python-exit-code 1 --python tools/ci_selftest.py

Exits with code 1 when a case raises, breaks a rule (stretched rigid modules, walls on window sides ...),
differs from aa_building_generator/tests/selftest_baseline.json, or has no baseline yet. The baseline file
is left exactly as it was: update it from inside Blender (Self-Test with "Update baseline") and commit it.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import aa_building_generator as ext  # noqa: E402

ext.register()
from aa_building_generator import selftest  # noqa: E402

with open(selftest.BASELINE, encoding="utf-8") as fh:
    baseline = fh.read()
try:
    report = selftest.run_self_test(False)
finally:
    with open(selftest.BASELINE, "w", encoding="utf-8") as fh:    # never add cases from CI
        fh.write(baseline)

print(f"\nAA Building Generator self-test: {len(report['results'])} cases")
problems = [("ERROR", e) for e in report["errors"]] + \
           [("CHANGED", f"{n}: differs from the baseline") for n in report["changed"]] + \
           [("NO BASELINE", f"{n}: run the Self-Test in Blender and commit the updated baseline") for n in report["new"]]
for kind, msg in problems:
    print(f"  {kind}: {msg}")
print("FAILED" if problems else "OK")
sys.stdout.flush()
sys.exit(1 if problems else 0)
