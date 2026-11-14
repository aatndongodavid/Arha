"""Fails when a business module is under the coverage threshold (master prompt section 15)."""
import json
import sys

report, threshold, modules = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
files = json.load(open(report))["files"]
failed = False
for module in modules:
    covered = total = 0
    for path, data in files.items():
        if f"/modules/{module}/" in path and "/adapters/" not in path:
            covered += data["summary"]["covered_lines"]
            total += data["summary"]["num_statements"]
    pct = 100 * covered / total if total else 0
    print(f"{module:14s} {pct:5.1f} %")
    failed |= pct < threshold
sys.exit(1 if failed else 0)
