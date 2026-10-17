import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import fixtures
import wiki
import demo


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'repo'; self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/test')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'Baseline')

    def mutate(self, change):
        p = self.root/'wiki/concepts/queue.md'
        m, b = wiki.read_page(p); change(m); fixtures.write(p,m,b)

    def errors(self): return '\n'.join(wiki.lint(self.root, self.base)['errors'])

    def test_evidence_wrong_version(self):
        self.mutate(lambda m:(m.update(applies_to=['FixtureQueue/2']),m['claims'][0].update(applies_to=['FixtureQueue/2'])))
        self.assertIn('Evidence version',self.errors())
    def test_recorded_query_and_lint(self):
        wiki.record(self.root,'query',{'pages':['wiki/concepts/queue.md']})
        wiki.record(self.root,'lint',wiki.lint(self.root,self.base))
        self.assertEqual(self.errors(),'')
    def test_unreferenced_private_source(self):
        fixtures.write(self.root/'raw/private.md',dict(origin='private',collected_at='2026-10-15',scope='project',version='1',permission='denied'),'Private')
        self.assertIn('not cleared',self.errors())
    def test_bad_contradiction_shape(self):
        self.mutate(lambda m:m.update(contradictions=['bad']))
        self.assertIn('Contradiction must',self.errors())
    def test_log_trailing_bytes_preserved(self):
        p=self.root/'wiki/log.md';p.write_text(p.read_text().rstrip())
        self.assertIn('append-only',self.errors())
    def test_valid_baseline(self): self.assertEqual(self.errors(), '')
    def test_missing_metadata(self):
        self.mutate(lambda m: m.pop('title')); self.assertIn('title', self.errors())
    def test_malformed_metadata(self):
        self.mutate(lambda m: m.update(tags=42)); self.assertIn('tags', self.errors())
    def test_project_scope_rejected(self):
        self.mutate(lambda m: m.update(scope='project')); self.assertIn('Project/session', self.errors())
    def test_private_source_rejected(self):
        p=self.root/'raw/fixture-v1.md'; m,b=wiki.read_page(p);m['scope']='project';fixtures.write(p,m,b)
        self.assertIn('not cleared', self.errors())
    def test_broken_links(self):
        with (self.root/'wiki/concepts/queue.md').open('a') as f:f.write('\n[bad](missing.md)\n')
        self.assertIn('broken link', self.errors())
    def test_index_drift(self):
        (self.root/'wiki/index.md').write_text('# Wrong\n'); self.assertIn('Index drift', self.errors())
    def test_orphan_page(self):
        p=self.root/'wiki/concepts/new.md';m,b=wiki.read_page(self.root/'wiki/concepts/queue.md');m['id']='other';fixtures.write(p,m,b)
        self.assertIn('orphan', self.errors())
    def test_immutable_raw(self):
        with (self.root/'raw/fixture-v1.md').open('a') as f:f.write('change')
        self.assertIn('Immutable',self.errors())
    def test_deleted_source(self):
        (self.root/'raw/fixture-v1.md').unlink(); self.assertTrue(self.errors())
    def test_log_rewrite(self):
        (self.root/'wiki/log.md').write_text('# Wiki log\n');self.assertIn('append-only', self.errors())
    def test_claim_source_mismatch(self):
        self.mutate(lambda m:m['claims'][0].update(sources=['raw/missing.md']))
        self.assertIn('outside page',self.errors())
    def test_verified_requires_evidence(self):
        self.mutate(lambda m:m.update(status='verified'));self.assertIn('Review record',self.errors())
    def test_stale_warning(self):
        self.mutate(lambda m:m.update(updated_at='2020-01-01'))
        self.assertTrue(any('stale' in w for w in wiki.lint(self.root)['warnings']))
    def test_contradiction_and_version_query(self):
        fixtures.seed(self.root,2)
        self.assertTrue(any('CONTRADICTION' in w for w in wiki.lint(self.root)['warnings']))
        r=wiki.query(self.root,'queue','FixtureQueue/2')[0]
        self.assertEqual(r['claims'][0]['sources'],['raw/fixture-v2.md'])
        self.assertEqual(r['claims'][1]['kind'],'inference')
        self.assertEqual(wiki.query(self.root,'queue','unknown'),[])
    def test_dirty_guard_keeps_changes(self):
        p=self.root/'draft.txt';p.write_text('keep me')
        with self.assertRaises(ValueError):wiki.branch_guard(self.root,clean=True)
        self.assertEqual(p.read_text(),'keep me')
    def test_detached_guard(self):
        wiki.git(self.root,'checkout','--detach',self.base)
        with self.assertRaises(ValueError):wiki.record(self.root,'query','x')
        self.assertEqual(wiki.git(self.root,'status','--porcelain'),'')
    def test_main_guard(self):
        wiki.git(self.root,'checkout','-b','main')
        with self.assertRaises(ValueError):wiki.record(self.root,'query','x')
    def test_symlink_rejected(self):
        (self.root/'wiki/concepts/escape.md').symlink_to(self.root/'wiki/concepts/queue.md')
        self.assertIn('symlink', self.errors())
    def test_missing_baseline_rejected(self):
        self.assertTrue(wiki.lint(self.root,'bad-revision')['errors'])
    def test_query_read_only(self):
        wiki.query(self.root,'queue','FixtureQueue/1')
        self.assertEqual(wiki.git(self.root,'status','--porcelain'),'')
    def test_adapter_single_policy(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/'AGENTS.md').read_text(),(root/'CLAUDE.md').read_text())
        self.assertIn('docs/POLICY.md',(root/'AGENTS.md').read_text())
    def test_real_git_demo_and_pin_failures(self):
        out=Path(self.temp.name)/'demo';result=demo.run(out)
        self.assertNotEqual(result['A'], result['B'])
        a=out/'A';sub=a/'knowledge/shared';before=wiki.git(sub,'rev-parse','HEAD')
        with self.assertRaises(ValueError):wiki.pin(a,'f'*40)
        self.assertEqual(wiki.git(sub,'rev-parse','HEAD'),before)
        (sub/'dirty.txt').write_text('preserve')
        with self.assertRaises(ValueError):wiki.pin(a,result['B'])
        self.assertEqual((sub/'dirty.txt').read_text(),'preserve')
        b=out/'B';wiki.git(b,'submodule','deinit','knowledge/shared')
        with self.assertRaises(ValueError):wiki.pin(b,result['A'])
    def test_concurrent_worktree_logs(self):
        branches=[]
        for name in ('one','two'):
            p=Path(self.temp.name)/name
            wiki.git(self.root,'worktree','add','-b','contrib/'+name,str(p),'HEAD')
            wiki.record(p,'ingest',name);demo.commit(p,name);branches.append(p)
        wiki.git(self.root,'merge','--ff-only','contrib/one')
        parent_one=wiki.git(self.root,'rev-parse','HEAD');parent_two=wiki.git(branches[1],'rev-parse','HEAD')
        old_one=(self.root/'wiki/log.md').read_text();old_two=(branches[1]/'wiki/log.md').read_text()
        with self.assertRaises(ValueError):
            wiki.git(self.root,'-c','user.name=Local Fixture','-c','user.email=fixture@example.invalid','merge','--no-commit','contrib/two')
        self.assertIn('UU wiki/log.md',wiki.git(self.root,'status','--porcelain'))
        self.assertIn('two',wiki.git(self.root,'log','-1','--format=%s',parent_two))
        # Preserve first-parent prefix and append incoming events missing from it.
        merged=old_one + ''.join(line+'\n' for line in old_two.splitlines() if line not in old_one.splitlines())
        (self.root/'wiki/log.md').write_text(merged)
        (self.root/'wiki/index.md').write_text(wiki.index_text(self.root))
        wiki.git(self.root,'add','wiki/log.md','wiki/index.md')
        self.assertEqual(wiki.lint(self.root,parent_one,parent_two)['errors'],[])
        demo.commit(self.root,'Merge contributions preserving both event streams')
        self.assertEqual(len(wiki.git(self.root,'rev-list','--parents','-n','1','HEAD').split()),3)
        self.assertIn('one',merged);self.assertIn('two',merged)
        (self.root/'wiki/log.md').write_text(old_one)
        self.assertIn('Incoming log event lost',str(wiki.lint(self.root,parent_one,parent_two)['errors']))



if __name__ == '__main__':unittest.main()
