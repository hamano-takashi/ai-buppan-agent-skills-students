#!/usr/bin/env python3
"""Regression tests use synthetic data only; no live services."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import validate_distribution as vd

class DistributionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in vd.REQUIRED:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# Example\n', encoding='utf-8')
        self.skill = self.root / '.agents/skills/example/SKILL.md'
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text('---\nname: example\ndescription: "Synthetic test skill"\n---\n\n# Example\n', encoding='utf-8')
        (self.root/'SKILLS_INDEX.md').write_text('[example](.agents/skills/example/SKILL.md)\n', encoding='utf-8')
        self.record()
    def record(self):
        _, hashes = vd.validate(self.root, check_manifest=False)
        (self.root/vd.MANIFEST).write_text(json.dumps({'schema_version':1,'skill_count':1,'files':hashes}), encoding='utf-8')
    def errors(self):
        return vd.validate(self.root)[0]
    def test_clean_bundle(self):
        self.assertEqual([], self.errors())
    def test_mutated_file(self):
        self.skill.write_text(self.skill.read_text()+'Changed\n')
        self.assertTrue(any('does not match' in e for e in self.errors()))
    def test_sensitive_name_refused_before_read(self):
        hidden=self.root/('.'+'env');hidden.write_text('do not read')
        original=Path.read_bytes
        def guarded(p):
            if p==hidden:raise AssertionError('Sensitive file was read')
            return original(p)
        with patch.object(Path,'read_bytes',guarded):
            self.assertTrue(any('not read' in e for e in self.errors()))
    def test_sensitive_directory_refused_before_traversal(self):
        directory=self.skill.parent/('creden'+'tials')
        directory.mkdir()
        (directory/'notes.md').write_text('synthetic')
        original=Path.iterdir
        def guarded(p):
            if p==directory:raise AssertionError('Sensitive directory traversed')
            return original(p)
        with patch.object(Path,'iterdir',guarded):
            self.assertTrue(any('not traversed' in e for e in self.errors()))
    def test_unexpected_file(self):
        p=self.root/'local/notes.md';p.parent.mkdir();p.write_text('synthetic')
        self.assertTrue(any('not in permitted' in e for e in self.errors()))
    def test_secret_shape_redacted(self):
        fake='sk'+'-'+'A'*36
        (self.root/'README.md').write_text(fake)
        output='\n'.join(self.errors())
        self.assertIn('api-key-shape',output)
        self.assertNotIn(fake,output)
    def test_personal_path(self):
        value='/'+'Users'+'/example-person/example.txt'
        (self.root/'README.md').write_text(value)
        self.assertTrue(any('personal-path' in e for e in self.errors()))
    def test_public_url_not_a_home_path(self):
        (self.root/"README.md").write_text("https://ads.google.com/intl/ja_jp/home/tools/keyword-planner/")
        self.assertFalse(any("personal-path" in e for e in self.errors()))
    def test_broken_relative_link(self):
        (self.root/'README.md').write_text('[missing](absent.md)')
        self.assertTrue(any('missing link' in e for e in self.errors()))
    def test_outside_link(self):
        (self.root/'README.md').write_text('[outside](../../outside.md)')
        self.assertTrue(any('outside distribution' in e for e in self.errors()))
    def test_bad_frontmatter(self):
        self.skill.write_text('---\nname: other\ndescription: "example"\n---\n')
        self.assertTrue(any('name mismatch' in e for e in self.errors()))
    def test_symlink_refused(self):
        p=self.root/'docs/shortcut.md'
        try:p.symlink_to(self.root/'README.md')
        except OSError:self.skipTest('symlinks unavailable')
        self.assertTrue(any('symlink' in e for e in self.errors()))
    def test_markdown_code_example_not_a_link(self):
        (self.root/'README.md').write_text('```md\n[example](absent.md)\n```\n')
        self.assertFalse(any('missing link' in e for e in self.errors()))
    def test_binary_encodings_rejected(self):
        for payload in [b'bad'+bytes([0]), bytes([255]), b'GIF89a'+bytes([1])]:
            with self.subTest(payload=repr(payload)):
                (self.root/'README.md').write_bytes(payload)
                self.assertTrue(any(('binary' in e or 'UTF-8' in e or 'control characters' in e) for e in self.errors()))
    def test_oversized_file_rejected(self):
        (self.root/'README.md').write_bytes(b'a'*1_000_001)
        self.assertTrue(any('oversized' in e for e in self.errors()))
    def test_manifest_skill_count(self):
        p=self.root/vd.MANIFEST
        data=json.loads(p.read_text());data['skill_count']=2;p.write_text(json.dumps(data))
        self.assertTrue(any('skill count mismatch' in e for e in self.errors()))
    def test_directory_and_dangling_symlinks(self):
        for dest in [self.root/'docs',self.root/'absent']:
            p=self.root/'.agents/skills/example/shortcut'
            try:p.symlink_to(dest,target_is_directory=True)
            except OSError:self.skipTest('symlinks unavailable')
            self.assertTrue(any('symlink' in e for e in self.errors()))
            p.unlink()
    def test_manifest_write_refuses_unsafe_bundle(self):
        (self.root/'README.md').write_text('gh'+'p_'+'A'*36)
        before=(self.root/vd.MANIFEST).read_bytes()
        with patch('sys.argv',['validate','--root',str(self.root),'--write-manifest']),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1,vd.main())
        self.assertEqual(before,(self.root/vd.MANIFEST).read_bytes())

if __name__=='__main__':unittest.main(verbosity=2)
