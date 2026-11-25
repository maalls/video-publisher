import http.server,time,socketserver
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/hold"):
            time.sleep(float(self.path.split("=")[-1]) if "=" in self.path else 12)
            self.send_response(200);self.send_header("Content-Type","text/javascript");self.end_headers();self.wfile.write(b"");return
        return super().do_GET()
    def log_message(self,*a):pass
socketserver.ThreadingTCPServer.allow_reuse_address=True
socketserver.ThreadingTCPServer(("127.0.0.1",18765),H).serve_forever()
