"""Testing Framework - Suite pengujian untuk komponen Manus Agent."""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from typing import Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    name: str
    category: str
    status: str = "pending"
    duration: float = 0.0
    error: Optional[str] = None
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "duration": round(self.duration, 3),
            "error": self.error,
            "details": self.details,
        }


class TestSuite:
    def __init__(self, name: str = "Manus Agent Tests"):
        self.name = name
        self.tests: list[dict] = []
        self.results: list[TestResult] = []
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None

    def add_test(self, name: str, func: Callable, category: str = "unit"):
        self.tests.append({"name": name, "func": func, "category": category})

    async def run_all(self) -> dict:
        self.started_at = time.time()
        self.results = []

        for test in self.tests:
            result = TestResult(name=test["name"], category=test["category"])
            start = time.time()

            try:
                ret = test["func"]()
                if asyncio.iscoroutine(ret):
                    ret = await ret
                result.status = "passed"
                result.details = str(ret)[:500] if ret else ""
            except AssertionError as e:
                result.status = "failed"
                result.error = str(e)
            except Exception as e:
                result.status = "error"
                result.error = f"{type(e).__name__}: {str(e)}"
            finally:
                result.duration = time.time() - start

            self.results.append(result)

        self.completed_at = time.time()
        return self.get_summary()

    def get_summary(self) -> dict:
        passed = sum(1 for r in self.results if r.status == "passed")
        failed = sum(1 for r in self.results if r.status == "failed")
        errors = sum(1 for r in self.results if r.status == "error")
        total = len(self.results)
        duration = (self.completed_at or time.time()) - (self.started_at or time.time())

        return {
            "suite": self.name,
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "duration": round(duration, 3),
            "results": [r.to_dict() for r in self.results],
        }


def create_test_suite() -> TestSuite:
    suite = TestSuite("Manus Agent Full Test Suite")

    suite.add_test("VM Manager - Create VM", test_vm_create, "sandbox")
    suite.add_test("VM Manager - Start/Stop VM", test_vm_lifecycle, "sandbox")
    suite.add_test("VM Manager - Isolation Levels", test_vm_isolation, "sandbox")
    suite.add_test("VM Manager - Resource Limits", test_vm_resource_limits, "sandbox")
    suite.add_test("VM Manager - Snapshots", test_vm_snapshots, "sandbox")
    suite.add_test("VM Manager - Network Policy", test_vm_network_policy, "sandbox")

    suite.add_test("Shell Session - Create Session", test_shell_create, "shell")
    suite.add_test("Shell Session - Execute Command", test_shell_execute, "shell")
    suite.add_test("Shell Session - History", test_shell_history, "shell")

    suite.add_test("Spreadsheet - Create CSV", test_spreadsheet_create, "tools")
    suite.add_test("Spreadsheet - Read/Write", test_spreadsheet_readwrite, "tools")
    suite.add_test("Spreadsheet - Filter/Sort", test_spreadsheet_filter_sort, "tools")
    suite.add_test("Spreadsheet - Statistics", test_spreadsheet_stats, "tools")
    suite.add_test("Spreadsheet - Formula", test_spreadsheet_formula, "tools")
    suite.add_test("Spreadsheet - Search", test_spreadsheet_search, "tools")
    suite.add_test("Spreadsheet - Pivot Table", test_spreadsheet_pivot, "tools")

    suite.add_test("Playbook - Create Playbook", test_playbook_create, "tools")
    suite.add_test("Playbook - Dry Run", test_playbook_dry_run, "tools")
    suite.add_test("Playbook - Pattern Detection", test_playbook_patterns, "tools")

    suite.add_test("WebDev - Init Project", test_webdev_init, "tools")
    suite.add_test("WebDev - Export Zip", test_webdev_zip, "tools")
    suite.add_test("WebDev - File Operations", test_webdev_files, "tools")

    suite.add_test("Slides - Create Presentation", test_slides_create, "tools")
    suite.add_test("Slides - Manage Slides", test_slides_manage, "tools")
    suite.add_test("Slides - Export HTML", test_slides_export_html, "tools")

    return suite


def test_vm_create():
    from sandbox_env.vm_manager import VMManager, IsolationLevel
    mgr = VMManager(base_dir="/tmp/test_vm_workspace")
    result = mgr.create_vm("test-vm", "python3", IsolationLevel.BASIC)
    assert result["success"], f"VM creation failed: {result}"
    assert "vm_id" in result
    mgr.destroy_vm(result["vm_id"])
    return "VM create OK"


def test_vm_lifecycle():
    from sandbox_env.vm_manager import VMManager, VMState
    mgr = VMManager(base_dir="/tmp/test_vm_workspace")
    r = mgr.create_vm("lifecycle-vm", "python3")
    vm_id = r["vm_id"]

    r = mgr.start_vm(vm_id)
    assert r["success"]
    assert r["state"] == "running"

    r = mgr.pause_vm(vm_id)
    assert r["success"]
    assert r["state"] == "paused"

    r = mgr.resume_vm(vm_id)
    assert r["success"]
    assert r["state"] == "running"

    r = mgr.stop_vm(vm_id)
    assert r["success"]
    assert r["state"] == "stopped"

    mgr.destroy_vm(vm_id)
    return "VM lifecycle OK"


def test_vm_isolation():
    from sandbox_env.vm_manager import VMManager, IsolationLevel, ResourceLimits
    for level in IsolationLevel:
        limits = ResourceLimits.from_isolation_level(level)
        assert limits.max_memory_mb > 0
    return "VM isolation levels OK"


def test_vm_resource_limits():
    from sandbox_env.vm_manager import VMManager
    mgr = VMManager(base_dir="/tmp/test_vm_workspace")
    r = mgr.create_vm("limits-vm", "python3")
    vm_id = r["vm_id"]

    r = mgr.set_resource_limits(vm_id, {"max_memory_mb": 256, "max_cpu_percent": 25})
    assert r["success"]
    assert r["resource_limits"]["max_memory_mb"] == 256

    mgr.destroy_vm(vm_id)
    return "VM resource limits OK"


def test_vm_snapshots():
    from sandbox_env.vm_manager import VMManager
    mgr = VMManager(base_dir="/tmp/test_vm_workspace")
    r = mgr.create_vm("snap-vm", "python3")
    vm_id = r["vm_id"]

    test_file = os.path.join(mgr.vms[vm_id].working_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("snapshot test data")

    r = mgr.create_snapshot(vm_id, "test-snapshot")
    assert r["success"]
    snap_id = r["snapshot"]["snapshot_id"]

    os.unlink(test_file)
    assert not os.path.exists(test_file)

    r = mgr.restore_snapshot(vm_id, snap_id)
    assert r["success"]
    assert os.path.exists(test_file)

    mgr.destroy_vm(vm_id)
    return "VM snapshots OK"


def test_vm_network_policy():
    from sandbox_env.vm_manager import VMManager
    mgr = VMManager(base_dir="/tmp/test_vm_workspace")
    r = mgr.create_vm("net-vm", "python3")
    vm_id = r["vm_id"]

    r = mgr.set_network_policy(vm_id, {
        "allowed_outbound": ["api.example.com"],
        "blocked_outbound": ["malware.com"],
        "rate_limit_mbps": 5.0,
    })
    assert r["success"]

    vm = mgr.vms[vm_id]
    assert vm.network_policy.is_outbound_allowed("api.example.com")
    assert not vm.network_policy.is_outbound_allowed("malware.com")

    mgr.destroy_vm(vm_id)
    return "VM network policy OK"


async def test_shell_create():
    from sandbox_env.shell_session import ShellSessionManager
    mgr = ShellSessionManager()
    r = await mgr.create_session(working_dir="/tmp/test_shell")
    assert r["success"]
    sid = r["session_id"]
    await mgr.close_session(sid)
    return "Shell create OK"


async def test_shell_execute():
    from sandbox_env.shell_session import ShellSessionManager
    mgr = ShellSessionManager()
    r = await mgr.create_session(working_dir="/tmp/test_shell")
    sid = r["session_id"]

    r = await mgr.execute_in_session(sid, "echo 'hello world'")
    assert r["success"]
    assert "hello world" in r["stdout"]

    r = await mgr.execute_in_session(sid, "pwd")
    assert r["success"]

    await mgr.close_session(sid)
    return "Shell execute OK"


async def test_shell_history():
    from sandbox_env.shell_session import ShellSessionManager
    mgr = ShellSessionManager()
    r = await mgr.create_session(working_dir="/tmp/test_shell")
    sid = r["session_id"]

    await mgr.execute_in_session(sid, "echo 'cmd1'")
    await mgr.execute_in_session(sid, "echo 'cmd2'")

    r = mgr.get_session_history(sid)
    assert r["success"]
    assert len(r["history"]) >= 2

    await mgr.close_session(sid)
    return "Shell history OK"


def test_spreadsheet_create():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    r = tool.create_spreadsheet("test", ["Name", "Age", "City"],
                                 data=[["Alice", "30", "Jakarta"], ["Bob", "25", "Bandung"]])
    assert r["success"]
    return "Spreadsheet create OK"


def test_spreadsheet_readwrite():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")

    fp = "/tmp/test_spreadsheets/rw_test.csv"
    r = tool.write_csv(fp, ["A", "B"], [["1", "2"], ["3", "4"]])
    assert r["success"]

    r = tool.read_spreadsheet(fp)
    assert r["success"]
    assert r["total_rows"] == 2
    return "Spreadsheet read/write OK"


def test_spreadsheet_filter_sort():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    fp = "/tmp/test_spreadsheets/filter_test.csv"
    tool.write_csv(fp, ["Name", "Score"], [["A", "90"], ["B", "75"], ["C", "85"]])

    r = tool.filter_data(fp, "Score", "gt", "80")
    assert r["success"]
    assert r["total_rows"] == 2

    r = tool.sort_data(fp, "Score", ascending=False)
    assert r["success"]
    return "Spreadsheet filter/sort OK"


def test_spreadsheet_stats():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    fp = "/tmp/test_spreadsheets/stats_test.csv"
    tool.write_csv(fp, ["Name", "Value"], [["A", "10"], ["B", "20"], ["C", "30"]])

    r = tool.get_statistics(fp, "Value")
    assert r["success"]
    stats = r["statistics"]["columns"]["Value"]
    assert stats["sum"] == 60
    assert stats["mean"] == 20.0
    return "Spreadsheet stats OK"


def test_spreadsheet_formula():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    fp = "/tmp/test_spreadsheets/formula_test.csv"
    tool.write_csv(fp, ["A", "B"], [["10", "20"], ["30", "40"]])

    r = tool.apply_formula(fp, "Total", "sum", ["A", "B"])
    assert r["success"]

    r2 = tool.read_spreadsheet(fp)
    assert "Total" in r2["headers"]
    return "Spreadsheet formula OK"


def test_spreadsheet_search():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    fp = "/tmp/test_spreadsheets/search_test.csv"
    tool.write_csv(fp, ["Name", "City"], [["Alice", "Jakarta"], ["Bob", "Bandung"]])

    r = tool.search_data(fp, "Jakarta")
    assert r["success"]
    assert r["total_matches"] >= 1
    return "Spreadsheet search OK"


def test_spreadsheet_pivot():
    from tools.spreadsheet_tool import SpreadsheetTool
    tool = SpreadsheetTool(output_dir="/tmp/test_spreadsheets")
    fp = "/tmp/test_spreadsheets/pivot_test.csv"
    tool.write_csv(fp, ["Region", "Product", "Sales"],
                   [["North", "A", "100"], ["North", "B", "200"],
                    ["South", "A", "150"], ["South", "B", "250"]])

    r = tool.pivot_table(fp, "Region", "Product", "Sales", "sum")
    assert r["success"]
    assert r["total_rows"] == 2
    return "Spreadsheet pivot OK"


def test_playbook_create():
    from tools.playbook_manager import PlaybookManager
    mgr = PlaybookManager(storage_dir="/tmp/test_playbooks")
    r = mgr.create_playbook(
        name="Test Playbook",
        description="Testing",
        steps=[
            {"tool": "shell_tool", "action": "run", "params": {"command": "echo hello"}},
            {"tool": "file_tool", "action": "write", "params": {"path": "test.txt", "content": "data"}},
        ],
    )
    assert r["success"]
    assert r["playbook"]["step_count"] == 2
    return "Playbook create OK"


async def test_playbook_dry_run():
    from tools.playbook_manager import PlaybookManager
    mgr = PlaybookManager(storage_dir="/tmp/test_playbooks")
    r = mgr.create_playbook(
        name="Dry Run Test",
        steps=[{"tool": "shell_tool", "action": "run", "params": {"command": "echo ${name}"}}],
        variables={"name": "world"},
    )
    pb_id = r["playbook"]["playbook_id"]

    r = await mgr.execute_playbook(pb_id, dry_run=True)
    assert r["success"]
    assert r["dry_run"]
    return "Playbook dry run OK"


def test_playbook_patterns():
    from tools.playbook_manager import PlaybookManager
    mgr = PlaybookManager(storage_dir="/tmp/test_playbooks")

    for i in range(5):
        mgr.record_tool_execution("shell_tool", {"command": "ls"}, "output", True, 0.1)
        mgr.record_tool_execution("file_tool", {"path": "test"}, "ok", True, 0.05)

    patterns = mgr.detect_patterns(min_occurrences=3)
    assert isinstance(patterns, list)
    return f"Pattern detection OK ({len(patterns)} patterns)"


def test_webdev_init():
    from tools.webdev_tool import WebDevTool
    tool = WebDevTool()
    r = tool.init_project("test-app", "flask", output_dir="/tmp/test_webdev")
    assert r["success"]
    assert os.path.exists(os.path.join("/tmp/test_webdev/test-app", "app.py"))
    return "WebDev init OK"


def test_webdev_zip():
    from tools.webdev_tool import WebDevTool
    tool = WebDevTool()
    tool._output_dir = "/tmp/test_webdev_exports"
    os.makedirs(tool._output_dir, exist_ok=True)

    proj_dir = "/tmp/test_webdev/test-app"
    if not os.path.exists(proj_dir):
        tool.init_project("test-app", "flask", output_dir="/tmp/test_webdev")

    r = tool.export_zip(proj_dir)
    assert r["success"]
    assert r["files_count"] > 0
    return "WebDev zip export OK"


def test_webdev_files():
    from tools.webdev_tool import WebDevTool
    tool = WebDevTool()
    proj_dir = "/tmp/test_webdev/test-app"
    if not os.path.exists(proj_dir):
        tool.init_project("test-app", "flask", output_dir="/tmp/test_webdev")

    r = tool.write_file(proj_dir, "newfile.txt", "hello world")
    assert r["success"]

    r = tool.read_file(proj_dir, "newfile.txt")
    assert r["success"]
    assert r["content"] == "hello world"

    r = tool.edit_file(proj_dir, "newfile.txt", "hello world", "hello manus")
    assert r["success"]

    r = tool.read_file(proj_dir, "newfile.txt")
    assert r["content"] == "hello manus"
    return "WebDev file operations OK"


def test_slides_create():
    from tools.slides_tool import SlidesTool
    tool = SlidesTool(output_dir="/tmp/test_slides")
    pres = tool.create_presentation("Test Pres", author="Test", theme="modern")
    assert pres.title == "Test Pres"
    pres.add_slide("Slide 1", "Content 1")
    pres.add_slide("Slide 2", "Content 2")
    assert len(pres.slides) == 2
    return "Slides create OK"


def test_slides_manage():
    from tools.slides_tool import SlidesTool
    tool = SlidesTool(output_dir="/tmp/test_slides")
    pres = tool.create_presentation("Manage Test")
    pres.add_slide("S1", "C1")
    pres.add_slide("S2", "C2")
    pres.add_slide("S3", "C3")

    r = tool.update_slide(pres, 1, title="S2 Updated")
    assert r["success"]
    assert pres.slides[1].title == "S2 Updated"

    r = tool.remove_slide(pres, 2)
    assert r["success"]
    assert len(pres.slides) == 2

    r = tool.duplicate_slide(pres, 0)
    assert r["success"]
    assert len(pres.slides) == 3
    return "Slides manage OK"


def test_slides_export_html():
    from tools.slides_tool import SlidesTool
    tool = SlidesTool(output_dir="/tmp/test_slides")
    pres = tool.create_presentation("Export Test", theme="dark")
    pres.add_slide("Title", "", "title")
    pres.add_slide("Content", "Some text here")

    result = tool.export_html(pres)
    assert "berhasil" in result
    return "Slides export HTML OK"


async def run_all_tests() -> dict:
    suite = create_test_suite()
    return await suite.run_all()


if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    print(json.dumps(result, indent=2))
    passed = result["passed"]
    total = result["total"]
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed ({result['pass_rate']}%)")
    if result["failed"] > 0 or result["errors"] > 0:
        print(f"Failed: {result['failed']}, Errors: {result['errors']}")
        for r in result["results"]:
            if r["status"] != "passed":
                print(f"  FAIL: {r['name']} - {r['error']}")
    sys.exit(0 if passed == total else 1)
