from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from video_publisher.production_config import load_state_session
from video_publisher.durable_state import StateError

ROOT=Path(__file__).parents[1]


class ProductionWiringTests(unittest.TestCase):
    def test_wrong_ref_event_or_repo_before_network(self):
        base=dict(GITHUB_REPOSITORY='maalls/video-publisher',GITHUB_REF='refs/heads/main',
                  GITHUB_EVENT_NAME='schedule',VP_STATE_TOKEN='canary',VP_STATE_KEY='invalid')
        for change in ({'GITHUB_REF':'refs/pull/1/merge'},{'GITHUB_EVENT_NAME':'pull_request'},
                       {'GITHUB_REPOSITORY':'fork/repo'}):
            with patch('video_publisher.durable_state.GitHubStateStore') as store:
                with self.assertRaises(StateError):load_state_session({**base,**change})
                store.assert_not_called()

    def test_workflow_gates_and_no_secret_artifacts(self):
        text=(ROOT/'.github/workflows/production.yml').read_text()
        self.assertIn("vars.ENABLE_PRODUCTION == 'true'",text)
        self.assertIn('environment: publisher-production',text)
        self.assertIn('contents: read',text)
        self.assertNotIn('pull_request',text)
        self.assertNotIn('actions/cache',text)
        self.assertNotIn('upload-artifact',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('default: preflight',text)

    def test_bootstrap_refuses_activation(self):
        text=(ROOT/'scripts/bootstrap_private_state.py').read_text()
        self.assertIn('grant.youtube_enabled or grant.tiktok_enabled or grant.costs_confirmed',text)
        self.assertIn('os.O_EXCL',text)
        self.assertIn("'secret','set'",text)
        self.assertNotIn('print(key',text)

    def test_daily_uses_no_static_oauth_override(self):
        text=(ROOT/'scripts/run_daily_production.py').read_text()
        self.assertNotIn('YOUTUBE_TOKEN_JSON',text)
        self.assertIn("session.state['tokens']",text)
        self.assertIn('session.begin_refresh',text)
