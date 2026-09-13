"""Synthetic two-device publishing and Git synchronization regressions."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import daily_report as report
from shared_diary import merge_blocks, sync_repository


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cfg = dict(output_dir=str(self.root), timezone='Asia/Shanghai', device_id='personal-mac',
                        device_name='个人 Mac', legacy_device_id='personal-mac')
        self.packet = dict(status='ready', timezone='Asia/Shanghai', report_date='2026-09-12',
                           partial=False, sessions=[{'messages': [{'id': 'e', 'role': 'user'}]}])
        self.draft = dict(items=[dict(project='Example', text='完成单元检查。', state='completed', evidence=['e'])],
                          reflection=dict(text='保留验证结果。', evidence=['e']))
        self.path = self.root / '2026/9/12.md'

    def save(self, cfg=None):
        return report.publish(cfg or self.cfg, self.packet, self.draft)

    def test_two_devices_rerun_preserves_other_and_handwriting(self):
        self.path.parent.mkdir(parents=True)
        handwritten = '手写前言\r\n'.encode()
        self.path.write_bytes(handwritten)
        self.save()
        work = dict(self.cfg, device_id='work-mac', device_name='公司 Mac')
        self.save(work)
        before = self.path.read_bytes()
        self.draft['items'][0]['text'] = '补充检查结果。'
        self.save()
        after = self.path.read_bytes()
        marker = b'<!-- daily-work-report:work-mac:start -->'
        self.assertEqual(before[before.index(marker):], after[after.index(marker):])
        self.assertTrue(after.startswith(handwritten))
        self.assertEqual(after.count(b'personal-mac:start'), 1)
        self.assertIn('补充检查结果'.encode(), after)

    def test_legacy_owner_only_migrates_its_block(self):
        self.path.parent.mkdir(parents=True)
        old = b'hand\r\n<!-- daily-work-report:start -->\nold\n<!-- daily-work-report:end -->\r\nfoot'
        self.path.write_bytes(old)
        self.save(dict(self.cfg, device_id='work-mac'))
        self.assertTrue(self.path.read_bytes().startswith(old))
        self.save()
        text = self.path.read_bytes()
        self.assertNotIn(b'<!-- daily-work-report:start -->', text)
        self.assertIn(b'\r\nfoot', text)
        self.assertIn(b'work-mac:start', text)

    def test_invalid_markers_leave_original_unchanged(self):
        self.path.parent.mkdir(parents=True)
        samples = [b'<!-- daily-work-report:start -->',
                   b'<!-- daily-work-report:bad:id:start -->',
                   b'prefix<!-- daily-work-report:work-mac:start -->\n<!-- daily-work-report:work-mac:end -->',
                   b'<!-- daily-work-report:work-mac:start -->\n<!-- daily-work-report:personal-mac:end -->',
                   b'<!-- daily-work-report:work-mac:start -->\n<!-- daily-work-report:work-mac:end -->\n' * 2]
        for old in samples:
            with self.subTest(old=old):
                self.path.write_bytes(old)
                with self.assertRaises(ValueError): self.save()
                self.assertEqual(self.path.read_bytes(), old)

    def test_unknown_legacy_ownership_stops(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('<!-- daily-work-report:start -->\nx\n<!-- daily-work-report:end -->')
        cfg = {k:v for k,v in self.cfg.items() if k != 'legacy_device_id'}
        with self.assertRaises(ValueError): self.save(cfg)

    def test_skip_partial_and_validation_failure(self):
        self.packet['partial'] = True
        self.save()
        before = self.path.read_bytes()
        self.assertIn(report.NOTE.encode(), before)
        self.assertEqual(report.publish(self.cfg, self.packet, {'items': []})['status'], 'skipped')
        self.assertEqual(self.path.read_bytes(), before)
        self.draft['items'][0]['evidence'] = ['missing']
        with self.assertRaises(ValueError): self.save()
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_standard_save_never_touches_diary(self):
        with patch.object(report, 'atomic_write', side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.save()
        self.assertFalse(self.path.exists())

    def test_concurrent_edit_survives(self):
        self.save()
        original_fsync = os.fsync
        calls = []
        def edit(fd):
            original_fsync(fd)
            calls.append(fd)
            if len(calls) == 2:  # Final diary flush, after standard temp report.
                self.path.write_bytes(b'concurrent hand edit')
        with patch('shared_diary.os.fsync', side_effect=edit):
            with self.assertRaises(ValueError): self.save()
        self.assertEqual(self.path.read_bytes(), b'concurrent hand edit')

    def test_symlink_rejected(self):
        target = self.root / 'other'
        target.mkdir()
        try: (self.root / '2026').symlink_to(target, target_is_directory=True)
        except OSError: self.skipTest('symlink unavailable')
        with self.assertRaises(ValueError): self.save()
        self.assertEqual(list(target.iterdir()), [])

    def test_draft_cannot_inject_markers(self):
        self.draft['items'][0]['text'] = '内容 <!-- daily-work-report:work-mac:start -->'
        with self.assertRaises(ValueError): self.save()
        self.assertFalse(self.path.exists())

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT).decode().strip()

    def test_two_git_clones_and_dirty_diverged_guards(self):
        remote = self.root / 'remote.git'
        self.git(self.root, 'init', '--bare', str(remote))
        clones = [self.root / name for name in ('a','b')]
        for clone in clones:
            self.git(self.root, 'clone', str(remote), str(clone))
            self.git(clone, 'config', 'user.name', 'Test')
            self.git(clone, 'config', 'user.email', 'test@example.invalid')
            self.git(clone, 'checkout', '-b', 'main')
        a,b = clones
        (a/'initial').write_text('initial')
        self.git(a,'add','.');self.git(a,'commit','-m','initial');self.git(a,'push','origin','main')
        # Bootstrap second clone's unborn main, then exercise real sync flow.
        self.git(b,'pull','--ff-only','origin','main')
        for clone,device in [(a,'personal-mac'),(b,'work-mac'),(a,'personal-mac')]:
            sync_repository(clone,str(remote))
            self.save(dict(self.cfg,output_dir=str(clone/'diary'),device_id=device))
            self.git(clone,'add','.')
            if self.git(clone,'diff','--cached','--name-only'):
                self.git(clone,'commit','-m',device)
            self.git(clone,'push','origin','main')
        diary = a/'diary/2026/9/12.md'
        self.assertIn(b'work-mac:start',diary.read_bytes())
        (a/'dirty').write_text('dirty')
        with self.assertRaises(ValueError):sync_repository(a,str(remote))
        (a/'dirty').unlink()
        for clone in (a,b):
            (clone/'different').write_text(clone.name)
            self.git(clone,'add','.');self.git(clone,'commit','-m','diverge')
        self.git(b,'push','origin','main')
        head = self.git(a,'rev-parse','HEAD')
        with self.assertRaises(ValueError):sync_repository(a,str(remote))
        self.assertEqual(self.git(a,'rev-parse','HEAD'),head)
        with self.assertRaises(ValueError):sync_repository(a,'wrong-url')


if __name__ == '__main__':
    unittest.main()
