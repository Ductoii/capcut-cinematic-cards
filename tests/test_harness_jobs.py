import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from capcut_harness.service import Service
from capcut_harness.actions import parse_command
from capcut_harness.legacy import cards
from test_harness_mix import draft,segment,save_project
from test_harness_audio import spoken_fixture


def wait_job(service,ident,states=('ready','failed','cancelled','interrupted'),timeout=40):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        job=service.job(ident)
        if job['state'] in states:return job
        time.sleep(.05)
    raise AssertionError('Job did not finish: '+str(service.job(ident)))


class JobsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def project(self):
        source,samples=spoken_fixture(self.root)
        p=self.root/'projects'/'My film';p.mkdir(parents=True)
        d=draft({'audios':[dict(id='voice',path=str(source))]},[dict(id='sound',type='audio',segments=[segment('speech','voice',duration=round(samples/48000*1e6))])],duration=round(samples/48000*1e6))
        return save_project(p,d)

    def test_command_parser_and_unknown_commands_never_become_shell(self):
        projects=[dict(id='p1',name='1027')]
        self.assertEqual(parse_command('cân âm thoại 1027',projects),dict(action='dialogue.analyze',project_id='p1',params={}))
        self.assertEqual(parse_command('phân tích 1027',projects),dict(action='project.inspect',project_id='p1'))
        self.assertEqual(parse_command('hoàn tác abc123',projects),dict(action='dialogue.undo',job_id='abc123'))
        with self.assertRaisesRegex(ValueError,'[Ll]ệnh|command'):parse_command('rm -rf /',projects)
        with self.assertRaisesRegex(ValueError,'project|Project'):parse_command('cân âm thoại unknown',projects)

    def test_actual_job_review_apply_undo_and_revision_idempotency(self):
        p=self.project();service=Service(self.root/'state',[p.parent]);self.addCleanup(service.close)
        project=service.projects()[0];self.assertEqual(project['name'],'My film')
        action=dict(action='dialogue.analyze',project_id=project['id'],params={},request_id='same-request')
        first=service.dispatch(action);again=service.dispatch(action);self.assertEqual(first['job_id'],again['job_id'])
        job=wait_job(service,first['job_id']);self.assertEqual(job['state'],'ready',str(job))
        self.assertGreater(len(job['report']['intervals']),0)
        revision=service.dispatch(dict(action='dialogue.render',job_id=job['id'],params={},excluded=[job['report']['intervals'][0]['id']]))
        newer=wait_job(service,revision['job_id']);self.assertEqual(newer['state'],'ready',str(newer))
        self.assertTrue(newer['report']['intervals'][0]['excluded']);self.assertEqual(newer['report']['intervals'][0]['gain_db'],0)
        with self.assertRaisesRegex(ValueError,'Newer'):
            service.dispatch(dict(action='dialogue.apply',job_id=job['id']))
        job=newer
        with mock.patch.object(cards,'editor_running',return_value=True):
            service.dispatch(dict(action='dialogue.apply',job_id=job['id']))
            busy=wait_job(service,job['id']);self.assertEqual(busy['state'],'ready');self.assertEqual(busy['error_type'],'editor_busy')
        with mock.patch.object(cards,'editor_running',return_value=False):
            service.dispatch(dict(action='dialogue.apply',job_id=job['id']));applied=wait_job(service,job['id'],('applied','failed','ready'))
            self.assertEqual(applied['state'],'applied',str(applied))
            service.dispatch(dict(action='dialogue.undo',job_id=job['id']));restored=wait_job(service,job['id'],('restored','failed','applied'))
            self.assertEqual(restored['state'],'restored',str(restored))
        service.close();restart=Service(self.root/'state',[p.parent]);self.addCleanup(restart.close)
        self.assertEqual(restart.job(job['id'])['state'],'restored')

    def test_restart_marks_unfinished_jobs_interrupted_and_retry_is_new_job(self):
        state=self.root/'state';(state/'jobs'/'a1').mkdir(parents=True)
        (state/'projects.json').write_text('{}')
        (state/'jobs'/'a1'/'job.json').write_text(json.dumps(dict(id='a1',state='running',action='dialogue.analyze',project_id='missing',params={},created_at='2026-10-28T00:00:00Z')))
        service=Service(state,[]);self.addCleanup(service.close)
        self.assertEqual(service.job('a1')['state'],'interrupted')
        with self.assertRaisesRegex(ValueError,'project|Project'):
            service.dispatch(dict(action='dialogue.retry',job_id='a1'))

    def test_retry_recovers_interrupted_mutation_using_same_stage(self):
        p=self.project();service=Service(self.root/'state',[p.parent]);project=service.projects()[0]
        service.store.save(dict(id='ab12',state='applying',operation='apply',project_id=project['id'],params={},created_at='2026-10-28',stage_path='saved-stage'))
        service.registry[project['id']]['latest_job']='ab12';service.store.write(service.root/'projects.json',service.registry);service.close()
        restarted=Service(self.root/'state',[p.parent]);self.addCleanup(restarted.close)
        operations=[]
        def execute(job,operation,*args):
            operations.append((job['id'],operation,job.get('stage_path')));return dict(state='applied')
        with mock.patch.object(restarted,'_execute',side_effect=execute):
            ticket=restarted.dispatch(dict(action='dialogue.retry',job_id='ab12'))
            result=wait_job(restarted,ticket['job_id'],('applied','failed'))
        self.assertEqual(result['state'],'applied',result)
        self.assertEqual(operations,[('ab12','apply','saved-stage')])

    def test_queued_apply_refuses_a_revision_replaced_while_waiting(self):
        p=self.project();service=Service(self.root/'state',[p.parent]);self.addCleanup(service.close)
        project=service.projects()[0];entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        original=service._execute;calls=[]
        def execute(job,operation,*args):
            if operation=='analyze':
                if not entered.is_set():entered.set();release.wait(10)
                return dict(state='ready')
            return original(job,operation,*args)
        with mock.patch.object(service,'_execute',side_effect=execute),mock.patch('capcut_harness.service.transaction.apply',side_effect=lambda *a:calls.append(a) or dict(verified=True)):
            service.dispatch(dict(action='dialogue.analyze',project_id=project['id'],params={}))
            self.assertTrue(entered.wait(5))
            service.store.save(dict(id='ab12',state='ready',operation='analyze',project_id=project['id'],params={},created_at='2026-10-28',stage_path='saved-stage'))
            service.registry[project['id']]['latest_job']='ab12'
            service.dispatch(dict(action='dialogue.apply',job_id='ab12'))
            service.dispatch(dict(action='dialogue.analyze',project_id=project['id'],params={}))
            release.set();job=wait_job(service,'ab12',('ready','applied','failed'))
        self.assertEqual(calls,[],'An obsolete queued review must not reach the writer')
        self.assertEqual(job['state'],'ready');self.assertIn('Newer',job['error'])

    def test_real_process_crash_is_recovered_after_restart_and_retry(self):
        import test_harness_transaction as fixtures
        fixture=fixtures.TransactionTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        timeline=fixture.project/'Timelines/main';timeline.mkdir(parents=True)
        for name in ('draft_info.json','draft_info.json.bak'):(timeline/name).write_bytes((fixture.project/name).read_bytes())
        (fixture.project/'Timelines/project.json').write_text(json.dumps(dict(main_timeline_id='main')))
        fixture.info=fixtures.inspect_audio(fixture.project)
        fixture.before={str(p.relative_to(fixture.project)):p.read_bytes() for p in fixture.project.rglob('*.json*')}
        stage=fixture.stage();service=Service(self.root/'state',[fixture.project]);project=service.projects()[0]
        service.store.save(dict(id='ab12',state='applying',operation='apply',project_id=project['id'],params={},created_at='2026-10-28',stage_path=str(stage)))
        service.registry[project['id']]['latest_job']='ab12';service.store.write(service.root/'projects.json',service.registry);service.close()
        code="""import os,sys
from capcut_harness import transaction as tx
from capcut_harness.legacy import cards
cards.editor_running=lambda:False
real=tx.atomic_copy
calls=[]
def crash(target,source):
    real(target,source);calls.append(str(target))
    if len(calls)==2:os._exit(23)
tx.atomic_copy=crash
tx.apply(sys.argv[1])
"""
        child=subprocess.run([sys.executable,'-c',code,str(stage)],capture_output=True,text=True,timeout=15)
        self.assertEqual(child.returncode,23,child.stderr)
        self.assertTrue((fixture.project/'.capcut-cards.lock').is_file())
        restarted=Service(self.root/'state',[fixture.project]);self.addCleanup(restarted.close)
        with mock.patch.object(cards,'editor_running',return_value=False):
            ticket=restarted.dispatch(dict(action='dialogue.retry',job_id='ab12'))
            job=wait_job(restarted,ticket['job_id'],('applied','failed','ready'))
            self.assertEqual(job['state'],'applied',job)
            restarted.dispatch(dict(action='dialogue.undo',job_id='ab12'))
            restored=wait_job(restarted,'ab12',('restored','applied','failed'))
            self.assertEqual(restored['state'],'restored',restored)
        for name,raw in fixture.before.items():self.assertEqual((fixture.project/name).read_bytes(),raw)
        self.assertFalse((fixture.project/'.capcut-cards.lock').exists())

    def test_worker_serializes_jobs_and_cancellation_reaches_running_job(self):
        p=self.project();service=Service(self.root/'state',[p.parent]);self.addCleanup(service.close)
        project=service.projects()[0];entered=threading.Event();release=threading.Event();order=[]
        def execute(job,operation,progress,cancelled):
            order.append(job['id']);entered.set()
            while not release.wait(.01):
                if cancelled():raise InterruptedError('Job cancelled')
            return dict(state='ready')
        with mock.patch.object(service,'_execute',side_effect=execute):
            one=service.dispatch(dict(action='dialogue.analyze',project_id=project['id']))
            self.assertTrue(entered.wait(2))
            two=service.dispatch(dict(action='dialogue.analyze',project_id=project['id']))
            self.assertEqual(service.job(two['job_id'])['state'],'queued')
            service.dispatch(dict(action='dialogue.cancel',job_id=one['job_id']))
            self.assertEqual(wait_job(service,one['job_id'])['state'],'cancelled')
            release.set();self.assertEqual(wait_job(service,two['job_id'])['state'],'ready')
            self.assertEqual(order,[one['job_id'],two['job_id']])


if __name__=='__main__':unittest.main()
