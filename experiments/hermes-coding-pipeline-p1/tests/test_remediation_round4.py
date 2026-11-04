"""Round-004 remediation regressions, offline only; no live Agent calls."""
from __future__ import annotations
import os
from pathlib import Path
import pytest

from p1 import gitops
from p1.workflow import Pipeline, PipelineError
from p1.trust import TrustBoundaryError, validate_private_task_home
from test_pipeline import start, approve


def _git_commit(repo: Path, message: str):
    gitops.git(repo, 'add', '-A')
    gitops.git(repo, 'commit', '-m', message)


def test_r4_002_nonascii_tester_addition_is_allowed(scenario):
    s=scenario;s['init']()
    p=Pipeline(s['home'])
    try:
        assert p.run(max_steps=1)['stage']=='gate0.2'
        p.approve_spec('user','approved',s['spec_sha'])
        assert p.run(max_steps=1)['stage']=='2'
        repo=s['worktree']; old=gitops.head(repo)
        (repo/'tests'/'test_注册.py').write_text('def test_中文(): assert True\n',encoding='utf-8')
        _git_commit(repo,'合法新增中文考卷')
        good,delta=gitops.test_commit_transition(repo,old,gitops.head(repo))
        assert good,delta
        assert delta==['A\ttests/test_注册.py']
    finally:p.close()


def test_r4_002_test_filename_with_spaces_and_tabs(scenario):
    s=scenario;s['init']()
    p=Pipeline(s['home'])
    try:
        assert p.run(max_steps=1)['stage']=='gate0.2'
        p.approve_spec('user','approved',s['spec_sha'])
        p.run(max_steps=1)
        repo=s['worktree'];old=gitops.head(repo)
        fname='test_空\t格.py'
        (repo/'tests'/fname).write_text('def test_ok(): assert True\n',encoding='utf-8')
        _git_commit(repo,'unicode with spaces')
        good,delta=gitops.test_commit_transition(repo,old,gitops.head(repo))
        assert good and delta==['A\ttests/'+fname],delta
    finally:p.close()


def test_r4_003_inflight_after_gate59_reports_reconciliation(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)['status']=='WAITING_GATE_5_9'
        count=p.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        rid=p.store.start_run(p.task_id,'5.3','arbitrator','SHA',{})
        after=p.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        assert after==count+1
        current=p.status()
        assert current['status']=='NEEDS_RECONCILIATION' and current['persisted_status']=='WAITING_GATE_5_9'
        assert current['unfinished_run_ids']==[rid]
        assert p.run()['status']=='NEEDS_RECONCILIATION'
        assert p.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==after
        with pytest.raises(PipelineError,match='unfinished invocation'):
            p.resume()
        with pytest.raises(PipelineError,match='evidence invalid'):
            p.export_report()
    finally:p.close()


@pytest.mark.skipif(os.name!='posix',reason='POSIX mode check runs only on POSIX')
def test_r4_001_private_boundary_checks_owner_and_mode(tmp_path):
    home=tmp_path/'private-ledger'
    home.mkdir(mode=0o700)
    db=home/'state.sqlite';db.write_bytes(b'local fake db for permission inspection')
    os.chmod(db,0o600)
    validate_private_task_home(home,require_database=True)
    os.chmod(db,0o644)
    with pytest.raises(TrustBoundaryError,match='group/other'):
        validate_private_task_home(home,require_database=True)
    os.chmod(db,0o600)
    os.chmod(home,0o755)
    with pytest.raises(TrustBoundaryError,match='group/other'):
        validate_private_task_home(home,require_database=True)


@pytest.mark.skipif(os.name!='posix',reason='POSIX mode check runs only on POSIX')
def test_r4_001_untrusted_integration_state_is_blocked_without_dispatch(scenario):
    from p1.workflow import initialize
    s=scenario
    adapters=s['root']/'sample-adapters.json'; adapters.write_text('{"harnesses":{}}')
    initialize(s['home'],'TEST-001',s['intent'],s['matrix'],s['gate01'],
               Path(__file__).resolve().parents[1]/'souls',s['project'],s['worktree'],
               'integration',adapter_config=adapters)
    # P1 never accepts a group/world-readable task root for real work.
    os.chmod(s['home'],0o755)
    p=Pipeline(s['home'])
    try:
        result=p.run()
        assert result['status']=='BLOCKED' and 'trust boundary invalid' in result['last_error']
        assert p.store.results(p.task_id)==[]
        assert p.verify_evidence()['verdict']=='NON_COMPLIANT'
    finally:p.close()

@pytest.mark.skipif(os.name!='posix',reason='POSIX mode check runs only on POSIX')
def test_r4_001_private_integrated_state_allows_preflight_but_not_unverified_harness(scenario):
    from p1.workflow import initialize
    s=scenario
    adapter=s['root']/'sample-adapters.json';adapter.write_text('{"harnesses":{}}')
    initialize(s['home'],'TEST-001',s['intent'],s['matrix'],s['gate01'],
               Path(__file__).resolve().parents[1]/'souls',s['project'],s['worktree'],
               'integration',adapter_config=adapter)
    os.chmod(s['home'],0o700)
    os.chmod(s['home']/'state.sqlite',0o600)
    p=Pipeline(s['home'])
    try:
        assert p.status()['status']=='READY' # OS trust boundary is actually satisfied
        outcome=p.run()
        assert outcome['status']=='BLOCKED' and 'NOT_VERIFIED' in outcome['last_error']
        assert p.store.results(p.task_id)==[]
    finally:p.close()


def test_r2_008_bounded_streaming_stops_large_output(scenario):
    import sys
    from p1.executor import _capture_bounded
    s=scenario
    script="import sys; sys.stdout.buffer.write(b'X'*16000); sys.stdout.flush()"
    outcome,meta=_capture_bounded([sys.executable,'-c',script],s['project'],{},15,limit=4096)
    assert len(outcome.stdout)==4096
    assert meta['stdout_truncated'] is True
    assert meta['output_limit_exceeded'] is True
    assert meta['stdout_bytes_observed']>=4096
    assert meta['limit_per_stream_bytes']==4096


def test_r2_008_normal_small_output_remains_complete(scenario):
    import sys
    from p1.executor import _capture_bounded
    s=scenario
    script="import sys; sys.stdout.write('{\\\"verdict\\\":\\\"PASS\\\"}')"
    outcome,meta=_capture_bounded([sys.executable,'-c',script],s['project'],{},15,limit=4096)
    assert outcome.returncode==0
    assert outcome.stdout==b'{"verdict":"PASS"}'
    assert not meta['stdout_truncated']
    assert not meta['output_limit_exceeded']
    assert not meta['timed_out']
