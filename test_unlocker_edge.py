"""Edge case tests for DLC Unlocker."""
import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

from pathlib import Path
from sims4_updater.core.unlocker import (
    is_admin, get_status, install, uninstall,
    _get_appdata_dir, _detect_client, _task_exists,
)

OUTPATH = Path("test_edge_output.txt")
outfile = open(OUTPATH, "w", encoding="utf-8")

def log(msg):
    outfile.write(msg + "\n")
    outfile.flush()

def report(msg):
    outfile.write(msg + "\n")
    outfile.flush()

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        report(f"  PASS: {name}")
        passed += 1
    else:
        report(f"  FAIL: {name} {detail}")
        failed += 1

report("=== DLC Unlocker Edge Case Tests ===")
report(f"Admin: {is_admin()}")
report("")

if not is_admin():
    report("ERROR: Must run as admin for edge case tests.")
    outfile.close()
    sys.exit(1)

client_name, client_path = _detect_client()
report(f"Client: {client_path}")
report("")

# ── Test 1: Double install (idempotent) ──────────────────────────
report("--- Test 1: Double install ---")
install(log)
report("First install done.")
s1 = get_status(log)
check("DLL installed after 1st", s1.dll_installed)
check("Config installed after 1st", s1.config_installed)
check("Task exists after 1st", s1.task_exists)

install(log)
report("Second install done.")
s2 = get_status(log)
check("DLL still installed after 2nd", s2.dll_installed)
check("Config still installed after 2nd", s2.config_installed)
check("Task still exists after 2nd", s2.task_exists)
report("")

# ── Test 2: machine.ini dedup ────────────────────────────────────
report("--- Test 2: machine.ini dedup ---")
machine_ini = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "EA Desktop" / "machine.ini"
)
if machine_ini.is_file():
    content = machine_ini.read_text(encoding="utf-8", errors="ignore")
    count = content.count("machine.bgsstandaloneenabled=0")
    check(f"machine.ini has exactly 1 bgsstandalone line (found {count})", count == 1)
else:
    report("  SKIP: machine.ini not found")
report("")

# ── Test 3: Partial state - remove DLL only ──────────────────────
report("--- Test 3: Partial state (DLL removed) ---")
dll_path = client_path / "version.dll"
if dll_path.is_file():
    dll_path.unlink()
s3 = get_status(log)
check("DLL missing", not s3.dll_installed)
check("Config still present", s3.config_installed)
check("Status shows partial", not s3.dll_installed and s3.config_installed)
report("")

# ── Test 4: Partial state - remove config only ───────────────────
report("--- Test 4: Partial state (config removed, DLL reinstalled) ---")
# Reinstall first to get everything back
install(log)
# Now remove config only
appdata_dir = _get_appdata_dir()
import shutil
if appdata_dir.is_dir():
    shutil.rmtree(appdata_dir, ignore_errors=True)
s4 = get_status(log)
check("DLL installed", s4.dll_installed)
check("Config missing", not s4.config_installed)
report("")

# ── Test 5: Uninstall from partial state ─────────────────────────
report("--- Test 5: Uninstall from partial state ---")
uninstall(log)
s5 = get_status(log)
check("DLL removed after uninstall", not s5.dll_installed)
check("Config removed after uninstall", not s5.config_installed)
check("Task removed after uninstall", not s5.task_exists)
report("")

# ── Test 6: Uninstall when already uninstalled ───────────────────
report("--- Test 6: Double uninstall ---")
try:
    uninstall(log)
    report("Second uninstall completed without error.")
    check("Double uninstall is safe", True)
except Exception as e:
    check(f"Double uninstall should not error", False, str(e))
s6 = get_status(log)
check("Still clean after double uninstall", not s6.dll_installed and not s6.config_installed)
report("")

# ── Test 7: Entitlements.ini content check ───────────────────────
report("--- Test 7: Entitlements content validation ---")
install(log)
ent_path = _get_appdata_dir() / "entitlements.ini"
if ent_path.is_file():
    content = ent_path.read_text(encoding="utf-8")
    sections = [l for l in content.splitlines() if l.startswith("[") and l.endswith("]")]
    iid_lines = [l for l in content.splitlines() if l.startswith("IID=")]
    etg_lines = [l for l in content.splitlines() if l.startswith("ETG=")]
    grp_lines = [l for l in content.splitlines() if l.startswith("GRP=")]
    typ_lines = [l for l in content.splitlines() if l.startswith("TYP=")]

    check(f"Sections found: {len(sections)}", len(sections) > 100)
    check(f"IID lines: {len(iid_lines)}", len(iid_lines) == len(sections))
    check(f"ETG lines: {len(etg_lines)}", len(etg_lines) == len(sections))
    check(f"GRP lines: {len(grp_lines)}", len(grp_lines) == len(sections))
    check(f"TYP lines: {len(typ_lines)}", len(typ_lines) == len(sections))
    check("All IIDs start with SIMS4", all("SIMS4" in l for l in iid_lines))
    check("All GRPs are THESIMS4PC", all(l == "GRP=THESIMS4PC" for l in grp_lines))
else:
    check("entitlements.ini exists after install", False)
report("")

# Final cleanup
uninstall(log)

report(f"=== Results: {passed} passed, {failed} failed ===")
outfile.close()
sys.exit(1 if failed > 0 else 0)
