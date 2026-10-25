import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.security import security_manager
from core.task_dispatcher import BASE_DIR, TaskDispatcher


class DispatcherPathSecurityTests(unittest.TestCase):
    def setUp(self):
        self.dispatcher = TaskDispatcher()

    def _with_roots(self, roots):
        resolved_roots = [Path(root).resolve(strict=False) for root in roots]
        return patch.object(TaskDispatcher, "_get_authorized_roots", return_value=resolved_roots)

    def _report_patches(self, workspace, project_dir):
        project_manager = SimpleNamespace(
            get_project=lambda _name: SimpleNamespace(path=str(project_dir))
        )
        return (
            patch("core.task_dispatcher.BASE_DIR", Path(workspace)),
            patch.dict(sys.modules, {
                "core.project_manager": SimpleNamespace(project_manager=project_manager)
            }),
            patch.object(security_manager, "get_security_audit_log", return_value="synthetic audit log"),
        )

    def test_move_files_preserves_organization_inside_approved_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            allowed_root = Path(temporary_directory) / "approved"
            source = allowed_root / "Downloads"
            source.mkdir(parents=True)
            (source / "report.pdf").write_text("synthetic", encoding="utf-8")

            with self._with_roots([allowed_root]):
                result = self.dispatcher._move_files({"source": str(source)})

            self.assertTrue(result.success, result.error)
            self.assertTrue((source / "Organized" / "Documents" / "report.pdf").is_file())
            self.assertFalse((source / "report.pdf").exists())

    def test_move_files_rejects_parent_traversal_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            allowed_root = Path(temporary_directory) / "approved"
            source = allowed_root / "Downloads"
            source.mkdir(parents=True)
            source_file = source / "report.pdf"
            source_file.write_text("synthetic", encoding="utf-8")
            escaped_destination = source / ".." / "escaped"
            traversing_source = source / ".." / "Downloads"

            with self._with_roots([allowed_root]):
                result = self.dispatcher._move_files({
                    "source": str(source), "destination": str(escaped_destination)
                })
                source_result = self.dispatcher._move_files({"source": str(traversing_source)})

            self.assertFalse(result.success)
            self.assertEqual(result.error, "DESTINATION_PATH_TRAVERSAL")
            self.assertFalse(source_result.success)
            self.assertEqual(source_result.error, "SOURCE_PATH_TRAVERSAL")
            self.assertTrue(source_file.is_file())
            self.assertFalse((allowed_root / "escaped").exists())

    def test_move_files_rejects_source_and_destination_outside_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            allowed_root = root / "approved"
            outside_root = root / "outside"
            source = allowed_root / "Downloads"
            source.mkdir(parents=True)
            outside_root.mkdir()
            outside_file = outside_root / "secret.txt"
            outside_file.write_text("synthetic", encoding="utf-8")

            with self._with_roots([allowed_root]):
                denied_source = self.dispatcher._move_files({
                    "source": str(outside_root), "destination": str(source / "Organized")
                })
                denied_destination = self.dispatcher._move_files({
                    "source": str(source), "destination": str(outside_root / "Organized")
                })

            self.assertFalse(denied_source.success)
            self.assertEqual(denied_source.error, "SOURCE_PATH_OUTSIDE_APPROVED_ROOTS")
            self.assertFalse(denied_destination.success)
            self.assertEqual(denied_destination.error, "DESTINATION_PATH_OUTSIDE_APPROVED_ROOTS")
            self.assertTrue(outside_file.is_file())
            self.assertFalse((source / "Organized").exists())
            self.assertFalse((outside_root / "Organized").exists())

    def test_move_files_rejects_source_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            allowed_root = root / "approved"
            source = allowed_root / "Downloads"
            source.mkdir(parents=True)
            outside_file = root / "outside.txt"
            outside_file.write_text("synthetic", encoding="utf-8")
            source_link = source / "linked.txt"
            try:
                source_link.symlink_to(outside_file)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"file symlinks unavailable: {exc}")

            with self._with_roots([allowed_root]):
                result = self.dispatcher._move_files({"source": str(source)})

            self.assertFalse(result.success)
            self.assertEqual(result.error, "SOURCE_SYMLINK_ESCAPE")
            self.assertTrue(source_link.is_symlink())
            self.assertTrue(outside_file.is_file())
            self.assertFalse((source / "Organized").exists())

    def test_move_files_rejects_destination_symlink_escape_before_moves(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            allowed_root = root / "approved"
            source = allowed_root / "Downloads"
            destination = source / "Organized"
            source.mkdir(parents=True)
            destination.mkdir()
            source_file = source / "report.pdf"
            source_file.write_text("synthetic", encoding="utf-8")
            outside_root = root / "outside"
            outside_root.mkdir()
            try:
                (destination / "Documents").symlink_to(outside_root, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            with self._with_roots([allowed_root]):
                result = self.dispatcher._move_files({"source": str(source), "destination": str(destination)})

            self.assertFalse(result.success)
            self.assertEqual(result.error, "DESTINATION_PATH_ESCAPE")
            self.assertTrue(source_file.is_file())
            self.assertFalse((outside_root / "report.pdf").exists())

    def test_report_project_traversal_is_sanitized_and_confined(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            workspace.mkdir()
            project_dir = Path(temporary_directory) / "synthetic-project"
            project_dir.mkdir()
            patches = self._report_patches(workspace, project_dir)
            with patches[0], patches[1], patches[2]:
                result = self.dispatcher._generate_document_summary({
                    "goal": "save audit report", "project": "../../escape / project", "save_report": True
                })

            self.assertTrue(result.success, result.error)
            report = Path(result.generated_files[0]).resolve()
            reports_dir = (workspace / "memory" / "artifacts" / "audits").resolve()
            self.assertTrue(report.is_relative_to(reports_dir))
            self.assertTrue(report.is_file())
            self.assertRegex(report.name, r"^escape-project_audit_and_bug_report_[0-9a-f]{32}\.md$")
            self.assertIn("**Target Project:** ../../escape / project", report.read_text(encoding="utf-8"))

    def test_report_filename_collision_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            project_dir = Path(temporary_directory) / "synthetic-project"
            workspace.mkdir()
            project_dir.mkdir()
            reports_dir = workspace / "memory" / "artifacts" / "audits"
            reports_dir.mkdir(parents=True)
            existing = reports_dir / f"collision-name_audit_and_bug_report_{'1' * 32}.md"
            existing.write_text("preserve this", encoding="utf-8")
            patches = self._report_patches(workspace, project_dir)
            with patches[0], patches[1], patches[2], patch(
                "core.task_dispatcher.uuid.uuid4",
                side_effect=[SimpleNamespace(hex=str(index) * 32) for index in range(1, 6)],
            ):
                result = self.dispatcher._generate_document_summary({
                    "goal": "save report", "project": "Collision Name", "save_report": True
                })

            self.assertTrue(result.success, result.error)
            self.assertEqual(existing.read_text(encoding="utf-8"), "preserve this")
            self.assertTrue(Path(result.generated_files[0]).is_file())
            self.assertIn("2" * 32, result.generated_files[0])

    def test_report_directory_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            outside = Path(temporary_directory) / "outside"
            reports_dir = workspace / "memory" / "artifacts" / "audits"
            reports_dir.parent.mkdir(parents=True)
            outside.mkdir()
            try:
                reports_dir.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            with patch("core.task_dispatcher.BASE_DIR", workspace):
                result = self.dispatcher._generate_document_summary({
                    "goal": "save report", "project": "synthetic", "save_report": True
                })

            self.assertFalse(result.success)
            self.assertEqual(result.error, "REPORT_PATH_OUTSIDE_ARTIFACTS")
            self.assertEqual(list(outside.iterdir()), [])

    def test_configured_authorized_roots_are_explicit_and_unpatched(self):
        roots = TaskDispatcher._get_authorized_roots()
        expected_roots = {BASE_DIR.resolve(strict=False)}
        home = Path.home().resolve(strict=False)
        for directory_name in ("Downloads", "Documents", "Desktop"):
            configured_directory = (Path.home() / directory_name).resolve(strict=False)
            if (
                configured_directory != home
                and configured_directory.is_relative_to(home)
                and configured_directory.name.casefold() == directory_name.casefold()
            ):
                expected_roots.add(configured_directory)

        self.assertEqual(set(roots), expected_roots)
        self.assertNotIn(home, roots, "The whole user profile must not be an authorization root")
        for root in roots:
            self.assertNotEqual(root, Path(root.anchor), f"Root must not be a bare drive: {root}")
            self.assertGreater(len(root.parts), 1, f"Root must be a subdirectory, not root: {root}")
        self.assertIn(BASE_DIR.resolve(strict=False), roots)

    def test_user_folder_reparse_escape_is_not_authorized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            home = root / "profile"
            outside_downloads = root / "outside" / "Downloads"
            home.mkdir()
            outside_downloads.mkdir(parents=True)
            try:
                (home / "Downloads").symlink_to(outside_downloads, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            with patch("core.task_dispatcher.Path.home", return_value=home):
                roots = TaskDispatcher._get_authorized_roots()
                resolved, error = TaskDispatcher._resolve_authorized_path(outside_downloads)

            self.assertNotIn(outside_downloads.resolve(), roots)
            self.assertIsNone(resolved)
            self.assertEqual(error, "PATH_OUTSIDE_APPROVED_ROOTS")

    @unittest.skipUnless(sys.platform == "win32", "Windows system path policy is Windows-specific")
    def test_resolve_authorized_path_rejects_windows_system_directories_unpatched(self):
        resolved, error = TaskDispatcher._resolve_authorized_path("C:/Windows")
        self.assertIsNone(resolved)
        self.assertEqual(error, "PATH_OUTSIDE_APPROVED_ROOTS")

        resolved_sys, error_sys = TaskDispatcher._resolve_authorized_path("C:/Windows/System32")
        self.assertIsNone(resolved_sys)
        self.assertEqual(error_sys, "PATH_OUTSIDE_APPROVED_ROOTS")

        resolved_pf, error_pf = TaskDispatcher._resolve_authorized_path("C:/Program Files")
        self.assertIsNone(resolved_pf)
        self.assertEqual(error_pf, "PATH_OUTSIDE_APPROVED_ROOTS")

    @unittest.skipUnless(sys.platform == "win32", "Drive roots are Windows-specific")
    def test_resolve_authorized_path_rejects_drive_roots_unpatched(self):
        resolved_c, error_c = TaskDispatcher._resolve_authorized_path("C:/")
        self.assertIsNone(resolved_c)
        self.assertEqual(error_c, "PATH_IS_DRIVE_ROOT")

        resolved_d, error_d = TaskDispatcher._resolve_authorized_path("D:/")
        self.assertIsNone(resolved_d)
        self.assertEqual(error_d, "PATH_IS_DRIVE_ROOT")

    def test_resolve_authorized_path_accepts_approved_roots_unpatched(self):
        downloads = (Path.home() / "Downloads").resolve(strict=False)
        resolved_dl, error_dl = TaskDispatcher._resolve_authorized_path(downloads / "synthetic-fixture")
        self.assertEqual(error_dl, "")
        self.assertEqual(resolved_dl, downloads / "synthetic-fixture")

        workspace = BASE_DIR.resolve(strict=False)
        resolved_ws, error_ws = TaskDispatcher._resolve_authorized_path(workspace / "synthetic-fixture")
        self.assertEqual(error_ws, "")
        self.assertEqual(resolved_ws, workspace / "synthetic-fixture")

    def test_resolve_authorized_path_rejects_parent_traversal_unpatched(self):
        traversal = Path.home() / "Downloads" / ".." / "outside"
        resolved, error = TaskDispatcher._resolve_authorized_path(traversal)
        self.assertIsNone(resolved)
        self.assertEqual(error, "PATH_TRAVERSAL")

    @unittest.skipUnless(sys.platform == "win32", "Windows system path policy is Windows-specific")
    def test_move_files_rejects_system_directory_unpatched(self):
        result = self.dispatcher._move_files({"source": "C:/Windows"})
        self.assertFalse(result.success)
        self.assertEqual(result.error, "SOURCE_PATH_OUTSIDE_APPROVED_ROOTS")

        result_dst = self.dispatcher._move_files({
            "source": str(Path.home() / "Downloads"),
            "destination": "C:/Windows/Organized"
        })
        self.assertFalse(result_dst.success)
        self.assertEqual(result_dst.error, "DESTINATION_PATH_OUTSIDE_APPROVED_ROOTS")


if __name__ == "__main__":
    unittest.main()
