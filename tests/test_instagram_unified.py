import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import threading
import socket
import urllib.request
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'tales'))
import instagram_unified as m

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = {'api_version': 'v27.0', 'expected_username': 'example.test', 'config_id': '777', 'meta_app_id': '12345', 'meta_app_secret': 'fake-client-secret', 'approved_permissions': sorted(m.SCOPES), 'messaging_permission_approved': True}
        self.token_path = self.root/'token.json'
        self.token = {'access_token': 'test-not-real', 'issued_at': time.time()-90000,
                      'expires_at': time.time()+864000, 'user_id': '123', 'username': 'example.test', 'client_business_id': '555', 'config_id': '777'}
        m.save(self.token_path, self.token)
        self.user = {'user_id': '123', 'username': 'example.test', 'client_business_id': '555', 'config_id': '777'}
        self.journal = self.root/'reel.json'
        self.record = {**self.user, 'phase': 'container_created', 'container_id': '456',
                       'plan_sha256': 'plan', 'caption': 'Texte approuve', 'is_ai_generated': True}
    def tearDown(self):
        self.tmp.cleanup()
    def args(self, action, **kwargs):
        return argparse.Namespace(action=action, state_dir=str(self.root), journal=str(self.journal),
                                  execute=True, confirm_plan='plan', **kwargs)
    def test_private_save(self):
        self.assertEqual(self.token_path.stat().st_mode & 0o777, 0o600)
    def test_open_secret_rejected(self):
        self.token_path.chmod(0o644)
        with self.assertRaises(m.Stop): m.load(self.token_path)
    def test_response_formats(self):
        self.assertEqual(m.one({'data':[{'user_id':'123'}]})['user_id'], '123')
        with self.assertRaises(m.Stop): m.one({'data':[]})
    def test_wrong_username(self):
        with patch.object(m,'api',side_effect=[{'client_business_id':'555'}, {'data':[{'id':'123','username':'other'}]}]):
            with self.assertRaises(m.Stop): m.identity(self.config,'test')
    def test_wrong_id_binding(self):
        with patch.object(m,'inspect_token',return_value={}), patch.object(m,'identity',return_value={'user_id':'999','username':'example.test','client_business_id':'555'}):
            with self.assertRaises(m.Stop): m.checked(self.config,self.token_path)
    def test_expired_no_api(self):
        m.save(self.token_path,{**self.token,'expires_at':0})
        with patch.object(m,'identity') as call:
            with self.assertRaises(m.Stop): m.checked(self.config,self.token_path)
            call.assert_not_called()
    def test_refresh_too_young(self):
        m.save(self.token_path,{**self.token,'issued_at':time.time()})
        with patch.object(m,'identity',return_value=self.user), patch.object(m,'request') as call:
            with self.assertRaises(m.Stop): m.refresh(self.config,self.token_path)
            call.assert_not_called()
    def test_status_wrong_account(self):
        m.save(self.journal,{**self.record,'user_id':'999'})
        with self.assertRaises(m.Stop): m.status(self.config,self.token,self.journal)
    def test_publish_not_ready(self):
        m.save(self.journal,self.record)
        with patch.object(m,'checked',return_value=(self.token,self.user)), patch.object(m,'api',return_value={'status_code':'IN_PROGRESS'}) as call:
            with self.assertRaises(m.Stop): m.reel(self.args('publish'),self.config,self.token_path)
            self.assertEqual(call.call_count,1)
            self.assertEqual(m.load(self.journal)['phase'],'container_created')
    def test_ambiguous_publish_never_repeated(self):
        m.save(self.journal,self.record)
        def fake(config,path,token,params=None,post=False):
            if post: raise m.Stop('Ambiguous simulation')
            return {'status_code':'FINISHED'}
        with patch.object(m,'checked',return_value=(self.token,self.user)), patch.object(m,'api',side_effect=fake) as call:
            with self.assertRaises(m.Stop): m.reel(self.args('publish'),self.config,self.token_path)
            self.assertEqual(m.load(self.journal)['phase'],'publish_intent')
            before=call.call_count
            with self.assertRaises(m.Stop): m.reel(self.args('publish'),self.config,self.token_path)
            self.assertEqual(call.call_count,before)
    def test_success_publish(self):
        m.save(self.journal,self.record)
        responses=[{'status_code':'FINISHED'},{'id':'789'},{'status_code':'PUBLISHED'},
                   {'id':'789','permalink':'https://example.invalid/reel/test','caption':'Texte approuve','media_product_type':'REELS','is_ai_generated':True}]
        with patch.object(m,'checked',return_value=(self.token,self.user)), patch.object(m,'api',side_effect=responses), contextlib.redirect_stdout(io.StringIO()):
            m.reel(self.args('publish'),self.config,self.token_path)
        self.assertEqual(m.load(self.journal)['media_id'],'789')
    def test_plan_confirmation_required(self):
        m.save(self.journal,self.record)
        args=self.args('publish');args.confirm_plan='wrong'
        with patch.object(m,'checked',return_value=(self.token,self.user)), patch.object(m,'api') as call:
            with self.assertRaises(m.Stop): m.reel(args,self.config,self.token_path)
            call.assert_not_called()
    def test_create_existing_never_repeated(self):
        spec={**self.record,'sha256':'abc'}
        target=self.root/'reel-123-abc.json';m.save(target,spec)
        with patch.object(m,'checked',return_value=(self.token,self.user)), patch.object(m,'plan',return_value=spec), patch.object(m,'api') as call:
            with self.assertRaises(m.Stop): m.reel(self.args('create'),self.config,self.token_path)
            call.assert_not_called()
    def test_oauth_callback_exchange_private(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
        cfg={**self.config,'redirect_uri':'https://callback.example.invalid/instagram/callback/',
             'meta_app_id':'12345','meta_app_secret':'fake-client-secret'}
        output=io.StringIO(); errors=[]
        def run():
            try: m.authorize(cfg,self.token_path,port)
            except Exception as exc: errors.append(exc)
        replies=[{'access_token':'fake-suat'}]
        def exchange(url, params=None, **kwargs):
            self.assertEqual(params['redirect_uri'], cfg['redirect_uri'])
            return replies.pop(0)
        with patch.object(m.secrets,'token_urlsafe',return_value='test-state'), patch.object(m,'request',side_effect=exchange), patch.object(m,'inspect_token',return_value={'expires_at':0,'permissions':sorted(m.SCOPES)}), patch.object(m,'identity',return_value=self.user), contextlib.redirect_stdout(output):
            thread=threading.Thread(target=run);thread.start()
            for attempt in range(100):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:%s/instagram/callback/?state=test-state&code=fake-code'%port,timeout=1) as response:
                        self.assertEqual(response.status,200)
                    break
                except OSError: time.sleep(.01)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(m.load(self.token_path)['access_token'],'fake-suat')
        self.assertIn('config_id=777',output.getvalue())
        self.assertIn('prompt=login',output.getvalue())
        self.assertNotIn('fake-client-secret',output.getvalue())
        self.assertNotIn('fake-suat',output.getvalue())
    def test_multiple_accounts_blocked(self):
        with patch.object(m,'api',side_effect=[{'client_business_id':'555'},{'data':[{'id':'123','username':'example.test'},{'id':'999','username':'private'}]}]):
            with self.assertRaises(m.Stop): m.identity(self.config,'test')
    def test_token_excess_permissions_blocked(self):
        data={'data':{'is_valid':True,'app_id':'12345','scopes':sorted(m.SCOPES|{'business_management'}),'expires_at':0}}
        with patch.object(m,'api',return_value=data):
            with self.assertRaises(m.Stop): m.inspect_token(self.config,'test')
    def test_token_nonexpiring_documented(self):
        data={'data':{'is_valid':True,'app_id':'12345','scopes':sorted(m.SCOPES),'expires_at':0}}
        with patch.object(m,'api',return_value=data):
            self.assertEqual(m.inspect_token(self.config,'test')['expires_at'],0)
    def test_messages_permission_approval_gate(self):
        with self.assertRaises(m.Stop): m.authorize({**self.config,'messaging_permission_approved':False},self.token_path,8767)
    def test_main_no_network_help(self):
        with self.assertRaises(SystemExit) as exc, contextlib.redirect_stdout(io.StringIO()): m.main(['--help'])
        self.assertEqual(exc.exception.code,0)

if __name__=='__main__': unittest.main()
