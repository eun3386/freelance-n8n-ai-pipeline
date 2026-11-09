#!/usr/bin/env python3
"""n8n 워크플로우 테스트용 목업 서버 (표준 라이브러리만 사용).

  POST /v1beta/models/<모델>:generateContent  Gemini API 형식 응답 (고정된 테스트 문구)
                     요청 본문에 FAIL_MARK 가 있으면 500 (실패 격리 검증용)
  POST /wp           워드프레스 발행 수신
  POST /slack        슬랙 알림 수신
  GET  /received     지금까지 받은 /wp, /slack 요청 목록

실제 AI가 쓴 글이 아닙니다. 흐름 검증 전용입니다.
"""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAIL_MARK = os.environ.get('FAIL_MARK', 'example.com/a4')
OUT = os.path.join(os.path.dirname(__file__), 'out', 'received.jsonl')
os.makedirs(os.path.dirname(OUT), exist_ok=True)
seq = 0
lock = threading.Lock()


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('content-length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == '/received':
            rows = [json.loads(l) for l in open(OUT)] if os.path.exists(OUT) else []
            return self._send(200, rows)
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        global seq
        raw = self.rfile.read(int(self.headers.get('content-length', 0))).decode()
        if self.path.startswith('/v1beta/models/') and self.path.endswith(':generateContent'):
            if FAIL_MARK in raw:
                return self._send(500, {'type': 'error', 'error': {'code': 500, 'status': 'INTERNAL', 'message': 'mock: 의도된 실패'}})
            title = raw.split('제목: ')[-1].split('\\n')[0][:60]
            text = f'[목업] {title}\n이 글은 목업 서버가 만든 고정 문구입니다.\n핵심 포인트 3개는 실제 모델 호출 시 채워집니다.'
            return self._send(200, {'candidates': [{'content': {'role': 'model', 'parts': [{'text': text}]}, 'finishReason': 'STOP'}]})
        if self.path in ('/wp', '/slack'):
            body = json.loads(raw or '{}')
            with lock:
                seq += 1
                n = seq
                with open(OUT, 'a') as f:
                    f.write(json.dumps({'n': n, 'path': self.path, 'body': body}, ensure_ascii=False) + '\n')
            if self.path == '/wp':
                return self._send(201, {'id': 1000 + n, 'title': {'rendered': body.get('title', '')}})
            return self._send(200, {'ok': True})
        self._send(404, {'error': 'not found'})

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
