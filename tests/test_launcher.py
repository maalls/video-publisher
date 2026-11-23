import json, os, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'tales'))
import launcher  # noqa: E402
import comfy_client as cc  # noqa: E402

EXAMPLE = ROOT / 'docs' / 'conte.example.json'


class Fake(BaseHTTPRequestHandler):
    prompts = []

    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        if self.path == '/prompt':
            Fake.prompts.append(json.loads(body))
            self._send({'prompt_id': 'p%d' % len(Fake.prompts)})
        else:
            self._send({'name': 'x'})

    def do_GET(self):
        pid = self.path.rsplit('/', 1)[1]
        wf = Fake.prompts[int(pid[1:]) - 1]['prompt']
        prefix = next(v['inputs']['filename_prefix'] for v in wf.values() if 'filename_prefix' in v.get('inputs', {}))
        if prefix.split('/')[-1].startswith('anim-'):
            outs = {'58': {'images': [{'filename': prefix.split('/')[-1] + '_00001_.mp4', 'subfolder': 'contes/x'}]}}
        else:
            outs = {'11': {'images': [{'filename': prefix.split('/')[-1] + '_00001_.png', 'subfolder': 'contes/x'}]}}
        self._send({pid: {'status': {'status_str': 'success'}, 'outputs': outs}})


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prod = Path(self.tmp.name) / 'conte99-exemple'
        (self.prod / 'musique').mkdir(parents=True)
        (self.prod / 'musique' / 'musique.mp3').write_bytes(b'x')
        self.conte = json.loads(EXAMPLE.read_text())
        (self.prod / 'conte.json').write_text(json.dumps(self.conte))

    def test_example_is_valid(self):
        self.assertEqual(launcher.validate(self.conte, self.prod), [])

    def test_validation_errors(self):
        c = json.loads(json.dumps(self.conte))
        c['plans'][1]['phrases'] = [4, 4]
        c['plans'][2]['ref'] = 'inconnu'
        errs = ' | '.join(launcher.validate(c, self.prod))
        self.assertIn('ne suivent pas', errs)
        self.assertIn('reference inconnue', errs)
        c = json.loads(json.dumps(self.conte))
        c['plans'].pop()
        self.assertIn('couvrent', ' '.join(launcher.validate(c, self.prod)))

    def test_dry_run_builds_workflows_without_comfy(self):
        env = dict(os.environ, COMFY_API='http://127.0.0.1:9')  # injoignable: un appel ferait echouer
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/tales/launcher.py'), 'run', str(self.prod), '--dry-run'],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = sorted(p.name for p in (self.prod / 'dry-run').iterdir())
        self.assertEqual(len([f for f in files if f.startswith('anim-')]), 3)
        self.assertEqual(len([f for f in files if f.startswith('ref-')]), 2)
        wf = json.loads((self.prod / 'dry-run' / '01-ruelle.workflow.json').read_text())
        self.assertIn('Djeha', wf['6']['inputs']['prompt'])
        self.assertEqual(wf['12']['inputs']['image'], 'conte99-exemple-djeha-reference.png')

    def test_voice_missing_stops_cleanly(self):
        env = dict(os.environ, GEMINI_TTS_KEY_FILE=str(Path(self.tmp.name) / 'absent.json'))
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/tales/launcher.py'), 'run', str(self.prod), '--only', 'voix'],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3)
        self.assertIn('voix manquante', r.stdout)
        self.assertIn('cle TTS', r.stdout)

    def test_fake_comfy_images_and_anims_once_only(self):
        srv = HTTPServer(('127.0.0.1', 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        Fake.prompts = []
        api = 'http://127.0.0.1:%d' % srv.server_port
        out = Path(self.tmp.name) / 'out'
        for sub in ('contes/x',):
            (out / sub).mkdir(parents=True)
        env = dict(os.environ, COMFY_API=api, COMFY_POLL='0.05', COMFY_OUTPUT=str(out))
        for f in range(1, 4):
            (out / 'contes' / 'x' / ('ref-djeha-a_00001_.png')).write_bytes(b'png')
            (out / 'contes' / 'x' / ('ref-duo-a_00001_.png')).write_bytes(b'png')
        for p in self.conte['plans']:
            (out / 'contes' / 'conte99-exemple').mkdir(parents=True, exist_ok=True)
            (out / 'contes' / 'conte99-exemple' / (p['name'] + '_00001_.png')).write_bytes(b'png')
        cmd = [sys.executable, str(ROOT / 'scripts/tales/launcher.py'), 'run', str(self.prod), '--only', 'references,images,animations']
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(Fake.prompts), 2 + 3 + 3)
        r2 = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(len(Fake.prompts), 8)  # reprise: aucun doublon
        rec = json.loads((self.prod / '01-ruelle.receipt.json').read_text())
        self.assertIn('seconds', rec)

    def test_redo_creates_new_variant(self):
        st = launcher.load_state(self.prod)
        st['variants']['img:02-emprunt'] = 1
        self.assertEqual(launcher.item('02-emprunt', st, 'img'), '02-emprunt-v1')
        self.assertEqual(launcher.item('02-emprunt', st, 'anim'), '02-emprunt')
        self.assertNotEqual(launcher.seed_for(1, 2, 0), launcher.seed_for(1, 2, 1))


class PublishGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prod = Path(self.tmp.name) / 'p'
        self.prod.mkdir()
        (self.prod / 'conte.json').write_text(EXAMPLE.read_text())
        (self.prod / 'm.mp4').write_bytes(b'video')

    def run_pub(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/tales/publish_conte.py'), str(self.prod), *args],
                              capture_output=True, text=True)

    def test_refuses_without_approval(self):
        r = self.run_pub('--at', '2999-01-01T19:00', '--execute', '--go-evidence', 'oui go vendredi')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("approved.json", r.stderr)

    def test_plan_only_and_guards(self):
        sha = launcher.sha(self.prod / 'm.mp4')
        (self.prod / 'approved.json').write_text(json.dumps({'master': 'm.mp4', 'sha256': sha}))
        r = self.run_pub('--at', '2999-01-01T19:00')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('plan seulement', r.stdout)
        self.assertIn('Kevin MacLeod', r.stdout)
        self.assertFalse((self.prod / 'publication').exists())
        r = self.run_pub('--at', '2000-01-01T19:00', '--execute', '--go-evidence', 'oui go vendredi')
        self.assertIn('passe', r.stderr)
        r = self.run_pub('--at', '2999-01-01T19:00', '--execute')
        self.assertIn('go-evidence', r.stderr)
        (self.prod / 'm.mp4').write_bytes(b'changed')
        r = self.run_pub('--at', '2999-01-01T19:00')
        self.assertIn('a change', r.stderr)


if __name__ == '__main__':
    unittest.main()


class TTSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sys.path.insert(0, str(ROOT / 'scripts' / 'tales'))

    def keyfile(self, mode=0o600, content='{"api_key": "AIzaFAKEFAKEFAKEFAKEFAKEFAKE12345"}'):
        p = Path(self.tmp.name) / 'k.json'
        p.write_text(content)
        p.chmod(mode)
        return p

    def test_key_permissions_and_format(self):
        import gemini_tts as g
        self.assertTrue(g.load_key(self.keyfile()).startswith('AIza'))
        with self.assertRaises(g.TTSError) as e:
            g.load_key(self.keyfile(0o644))
        self.assertNotIn('AIza', str(e.exception))
        with self.assertRaises(g.TTSError):
            g.load_key(self.keyfile(content='{"x": 1}'))
        with self.assertRaises(g.TTSError):
            g.load_key(Path(self.tmp.name) / 'nope.json')

    def test_request_and_response_without_leaking_key(self):
        import base64, gemini_tts as g
        seen = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen['body'], seen['key'], seen['url'] = body, self.headers.get('x-goog-api-key'), self.path
                if seen.get('fail'):
                    self.send_response(403)
                    self.end_headers()
                    return
                out = json.dumps({'steps': [{'content': [{'type': 'audio', 'data': base64.b64encode(b'RIFF....WAVE').decode()}]}]}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(out)))
                self.end_headers()
                self.wfile.write(out)
        srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        g.URL = 'http://127.0.0.1:%d/v1beta/interactions' % srv.server_port
        out = Path(self.tmp.name) / 'o.wav'
        g.synthesize('Bonjour.', out, voice='Sadaltager', style='lent', model='gemini-3.8-flash-tts', key='AIzaFAKEFAKEFAKEFAKEFAKEFAKE12345')
        self.assertEqual(out.read_bytes()[:4], b'RIFF')
        self.assertEqual(seen['body']['generation_config']['speech_config'], [{'voice': 'Sadaltager'}])
        self.assertEqual(seen['body']['input'][0]['content'][0]['annotations'][0]['style'], 'lent')
        self.assertNotIn('AIza', seen['url'])
        seen['fail'] = True
        with self.assertRaises(g.TTSError) as e:
            g.synthesize('Bonjour.', out, key='AIzaFAKEFAKEFAKEFAKEFAKEFAKE12345')
        self.assertNotIn('AIza', str(e.exception))

    def test_cut_boundaries(self):
        import cut_take  # importe align_subtitles (faster_whisper seulement a l'appel)
        segs = ['Il etait une fois un roi.', 'Il avait trois fils.', 'Fin.']
        words = [(0.0, 0.3, 'Il'), (0.3, 0.6, 'était'), (0.6, 0.8, 'une'), (0.8, 1.0, 'fois'), (1.0, 1.2, 'un'), (1.2, 1.6, 'roi.'),
                 (2.2, 2.4, 'Il'), (2.4, 2.6, 'avait'), (2.6, 2.9, 'trois'), (2.9, 3.3, 'fils.'), (4.0, 4.4, 'Fin.')]
        cuts, ratio = cut_take.boundaries(segs, [{'start': a, 'end': b, 'word': w} for a, b, w in words])
        self.assertEqual(cuts, [1.9, 3.65])
        self.assertGreater(ratio, 0.9)


    def test_service_account_detection_and_cloud_call(self):
        import gemini_tts as g
        sa = self.keyfile(content=json.dumps({'type': 'service_account', 'private_key': 'PRIVATE-KEY-XYZ', 'client_email': 'a@b.iam'}))
        kind, v = g.load_credentials(sa)
        self.assertEqual((kind, Path(v)), ('service_account', sa))
        with self.assertRaises(g.TTSError):
            g.load_key(sa)
        seen = {}
        orig = g.synth_cloud
        g.synth_cloud = lambda text, voice, style, model, path, timeout: seen.update(v=(text, voice, style, model)) or b'RIFF....WAVE'
        self.addCleanup(lambda: setattr(g, 'synth_cloud', orig))
        out = Path(self.tmp.name) / 'c.wav'
        g.synthesize('Bonjour.', out, voice='Sadaltager', style='lent', creds=(kind, v))
        self.assertEqual(seen['v'], ('Bonjour.', 'Sadaltager', 'lent', 'gemini-2.5-flash-tts'))
        with self.assertRaises(g.TTSError):
            g.synthesize('x' * 4100, out, creds=(kind, v))
