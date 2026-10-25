'''
模拟 Upstash Redis REST 接口, 用于验证 storage.UpstashStorage

- POST /  body: ["SET", key, value] / ["GET", key]
- 数据落在 JSON 文件里, 模拟 "外部 KV 在应用重启后依然存在"
'''
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

PERSIST = os.path.join(tempfile.gettempdir(), 'mock_upstash_store.json')
STORE = {}
if os.path.exists(PERSIST):
    with open(PERSIST, 'r', encoding='utf-8') as f:
        STORE = json.load(f)


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, payload: dict):
        out = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        if self.headers.get('Authorization') != 'Bearer mock-token':
            self._reply(401, {'error': 'unauthorized'})
            return
        length = int(self.headers.get('Content-Length') or 0)
        try:
            cmd = json.loads(self.rfile.read(length) or b'[]')
        except Exception:
            self._reply(400, {'error': 'bad json'})
            return
        op = str(cmd[0]).upper() if cmd else ''
        print(f'[mock] {op} {cmd[1] if len(cmd) > 1 else ""}', flush=True)  # 便于统计命令数
        if op == 'SET' and len(cmd) == 3:
            STORE[cmd[1]] = cmd[2]
            with open(PERSIST, 'w', encoding='utf-8') as f:
                json.dump(STORE, f, ensure_ascii=False)
            self._reply(200, {'result': 'OK'})
        elif op == 'GET' and len(cmd) == 2:
            self._reply(200, {'result': STORE.get(cmd[1])})
        else:
            self._reply(400, {'error': f'unsupported command: {cmd!r}'})

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print(f'mock upstash on 127.0.0.1:9099 (store: {PERSIST})', flush=True)
    HTTPServer(('127.0.0.1', 9099), Handler).serve_forever()
