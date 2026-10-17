"""Lifecycle payload/real process tests; not a native Codex host activation test."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import agent_hooks
import demo
import fixtures
import wiki


class AgentHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name).resolve()
        self.root = self.sandbox/'repo with spaces'; self.root.mkdir()
        wiki.git(self.root, 'init', '-b', 'contrib/hooks')
        fixtures.seed(self.root)
        self.base = demo.commit(self.root, 'baseline')

    def event(self, name, **kw):
        return dict(hook_event_name=name, cwd=str(self.root), session_id='synthetic', **kw)

    def call(self, event, cwd=None):
        return agent_hooks.handle(event, cwd or self.root)

    def invoke(self, data, cwd=None):
        p = subprocess.run([sys.executable, str(SCRIPTS/'agent_hooks.py')], input=data,
                           capture_output=True, cwd=cwd or self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(b'Traceback', p.stderr)
        return json.loads(p.stdout)

    def test_session_start_read_only_policy_context(self):
        before = wiki.git(self.root, 'status', '--porcelain')
        result = self.call(self.event('SessionStart'))
        self.assertIn('docs/POLICY.md', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(result['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertEqual(wiki.git(self.root, 'status', '--porcelain'), before)

    def test_prompt_selects_only_paths_and_explicit_versions(self):
        result = self.call(self.event('UserPromptSubmit', prompt='queue FixtureQueue/1'))
        output = result['hookSpecificOutput']['additionalContext']
        self.assertIn('wiki/concepts/queue.md', output)
        self.assertIn('FixtureQueue/1', output)
        self.assertNotIn('capacity is 8', output)

    def test_no_version_guess(self):
        result = self.call(self.event('UserPromptSubmit', prompt='queue FixtureQueue/10'))
        output = result['hookSpecificOutput']['additionalContext']
        self.assertIn('"explicit_versions": []', output)
        self.assertNotIn('"FixtureQueue/1"', output)

    def test_prompt_transcript_not_saved_or_executed(self):
        forbidden=self.sandbox/'never-read'; forbidden.write_text('PRIVATE_TRANSCRIPT_TOKEN')
        result=self.call(self.event('UserPromptSubmit', prompt='queue $(touch sentinel) SECRET_PROMPT_TOKEN',transcript_path=str(forbidden)))
        self.assertNotIn('SECRET_PROMPT_TOKEN',json.dumps(result))
        self.assertNotIn('PRIVATE_TRANSCRIPT_TOKEN',json.dumps(result))
        self.assertFalse((self.root/'sentinel').exists())
        self.assertEqual(wiki.git(self.root,'status','--porcelain'),'')

    def test_missing_transcript_never_opened(self):
        result=self.call(self.event('SessionStart',transcript_path='/not/a/real/transcript'))
        self.assertIn('hookSpecificOutput',result)

    def test_no_match_still_supplies_workflow(self):
        result=self.call(self.event('UserPromptSubmit',prompt='unrelated xyz'))
        self.assertIn('[]',result['hookSpecificOutput']['additionalContext'])

    def test_bad_wiki_never_returns_candidate_data(self):
        p=self.root/'wiki/concepts/queue.md';m,b=wiki.read_page(p)
        m.update(scope='project',title='PRIVATE_TITLE');fixtures.write(p,m,b)
        result=self.call(self.event('UserPromptSubmit',prompt='PRIVATE_TITLE'))
        self.assertNotIn('PRIVATE_TITLE',json.dumps(result))
        self.assertIn('preflight failed',result['hookSpecificOutput']['additionalContext'])

    def test_symlink_raw_fails_without_content(self):
        outside=self.sandbox/'private.md';outside.write_text('PRIVATE_TOKEN')
        (self.root/'raw/escape.md').symlink_to(outside)
        result=self.call(self.event('SessionStart'))
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(result))
        self.assertIn('preflight failed',result['hookSpecificOutput']['additionalContext'])

    def test_stop_clean_no_followup(self):
        self.assertEqual(self.call(self.event('Stop')), {})

    def test_stop_code_change_requests_one_learning_review(self):
        (self.root/'script.py').write_text('x=1\n')
        result=self.call(self.event('Stop'))
        self.assertEqual(result['decision'],'block')
        self.assertIn('Do not manufacture',result['reason'])
        self.assertNotIn('decision',self.call(self.event('Stop',stop_hook_active=True)))

    def test_stop_errors_one_followup_no_private_output(self):
        (self.root/'raw/fixture-v1.md').write_text('PRIVATE_BAD_SOURCE')
        result=self.call(self.event('Stop',stop_hook_active=False))
        self.assertEqual(result['decision'],'block')
        self.assertNotIn('PRIVATE_BAD_SOURCE',json.dumps(result))
        repeated=self.call(self.event('Stop',stop_hook_active=True))
        self.assertNotIn('decision',repeated)
        self.assertIn('already ran',repeated['systemMessage'])

    def test_stop_valid_change_review_reminder_no_mutation(self):
        wiki.record(self.root,'maintain','synthetic hook test')
        before=(self.root/'wiki/log.md').read_bytes()
        result=self.call(self.event('Stop'))
        self.assertNotIn('decision',result)
        self.assertIn('passed structural',result['systemMessage'])
        self.assertEqual((self.root/'wiki/log.md').read_bytes(),before)

    def test_detached_read_allowed(self):
        wiki.git(self.root,'checkout','--detach',self.base)
        self.assertIn('hookSpecificOutput',self.call(self.event('SessionStart')))

    def test_unsupported_event_no_action(self):
        self.assertEqual(self.call(self.event('PermissionRequest')), {})

    def test_malformed_event_advisory(self):
        for raw in (b'invalid', b'[]', b'{"hook_event_name": 3}', b'x'*(1024*1024+1)):
            with self.subTest(raw=raw[:30]):
                output=self.invoke(raw)
                self.assertNotIn('decision',output)

    def test_outside_cwd_rejected(self):
        with self.assertRaises(ValueError):self.call(self.event('SessionStart', **{}) | {'cwd': str(self.sandbox)})

    def test_subdirectory_cwd_allowed(self):
        payload=self.event('SessionStart'); payload['cwd']=str(self.root/'wiki')
        self.assertIn('hookSpecificOutput',self.call(payload, cwd=self.root/'wiki'))

    def test_consumer_template_submodule(self):
        project=self.sandbox/'project';project.mkdir()
        wiki.git(project,'init','-b','main')
        wiki.git(project,'-c','protocol.file.allow=always','submodule','add',str(self.root),'knowledge/shared')
        demo.commit(project,'pin')
        (project/'wiki').mkdir()
        (project/'wiki/local.md').write_text('Unrelated local project wiki; do not misidentify as shared.\n')
        demo.commit(project,'add unrelated root wiki')
        payload=dict(hook_event_name='SessionStart',cwd=str(project))
        output=self.call(payload,cwd=project)
        self.assertIn('knowledge/shared/docs/POLICY.md',output['hookSpecificOutput']['additionalContext'])
        self.assertEqual(wiki.git(project,'status','--porcelain'),'')

    def test_actual_config_command_from_subdirectory(self):
        (self.root/'scripts').mkdir()
        for name in ('agent_hooks.py','wiki.py'):shutil.copy(SCRIPTS/name,self.root/'scripts'/name)
        config=json.loads((SCRIPTS.parent/'.codex/hooks.json').read_text())
        self.assertEqual(set(config['hooks']),agent_hooks.SUPPORTED)
        for event in config['hooks']:
            with self.subTest(event=event):
                command=config['hooks'][event][0]['hooks'][0]['command']
                payload=self.event(event,prompt='queue FixtureQueue/1')
                result=subprocess.run(command,shell=True,executable='/bin/sh',cwd=self.root/'wiki',input=json.dumps(payload),text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                json.loads(result.stdout)

    def test_help_exists(self):
        p=subprocess.run([sys.executable,str(SCRIPTS/'agent_hooks.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertIn('stdin',p.stdout)
