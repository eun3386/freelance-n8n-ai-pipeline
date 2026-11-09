#!/usr/bin/env python3
"""운영용 워크플로우에서 외부 서비스 노드를 목업 서버 호출로 바꾼 테스트본을 만든다.
  python3 n8n/make_test_variant.py   ->  n8n/ai-content-pipeline.test.workflow.json
"""
import json, os, re

HERE = os.path.dirname(__file__)
MOCK = 'http://host.docker.internal:8100'
w = json.load(open(os.path.join(HERE, 'ai-content-pipeline.workflow.json')))
w['name'] = '(테스트·목업) ' + w['name']


def http(url, body_expr):
    return {'method': 'POST', 'url': url, 'sendBody': True, 'specifyBody': 'json', 'jsonBody': body_expr, 'options': {}}


def to_concat(text):
    # 'a {{ x }} b' -> "a " + (x) + " b"  (템플릿 리터럴은 n8n 표현식 파서가 못 읽는 경우가 있어 쓰지 않는다)
    parts = re.split(r'\{\{(.*?)\}\}', text)
    out = []
    for i, part in enumerate(parts):
        out.append('(' + part.strip() + ')' if i % 2 else json.dumps(part, ensure_ascii=False))
    return ' + '.join(out)


w['id'] = os.environ.get('TEST_WF_ID', 'portfolioMockTest01')  # 고정 ID: 다시 import 하면 새로 생기지 않고 덮어쓴다
for n in w['nodes']:
    t = n['type'].split('.')[-1]
    if n['name'] == 'LLM 요약/작성':
        if not os.environ.get('REAL_LLM'):  # REAL_LLM=1 이면 LLM 은 실제 Gemini 를 호출하고 워드프레스·슬랙만 목업
            n['parameters']['url'] = MOCK + '/v1beta/models/mock:generateContent'
    elif t == 'wordpress':
        n['type'] = 'n8n-nodes-base.httpRequest'
        n['typeVersion'] = 4.2
        n['parameters'] = http(MOCK + '/wp', '={{ JSON.stringify({title: $json.title, content: $json.html}) }}')
        n.pop('credentials', None)
    elif t == 'slack':
        text = to_concat(n['parameters']['text'].lstrip('='))
        n['type'] = 'n8n-nodes-base.httpRequest'
        n['typeVersion'] = 4.2
        n['parameters'] = http(MOCK + '/slack', '={{ JSON.stringify({text: ' + text + '}) }}')
        n.pop('credentials', None)

# CLI(n8n execute)로 돌릴 수 있도록 테스트본에만 수동 시작 노드를 추가
w['nodes'].append({'id': 'test-start', 'name': '테스트 시작', 'type': 'n8n-nodes-base.executeWorkflowTrigger',
                   'typeVersion': 1.1, 'position': [-200, 300],
                   'parameters': {'inputSource': 'passthrough'}})
w['connections']['테스트 시작'] = {'main': [[{'node': 'RSS 수집', 'type': 'main', 'index': 0}]]}

out = os.path.join(HERE, 'ai-content-pipeline.test.workflow.json')
json.dump(w, open(out, 'w'), ensure_ascii=False, indent=2)
print('wrote', out)
