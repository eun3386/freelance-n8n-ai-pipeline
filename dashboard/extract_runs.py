#!/usr/bin/env python3
"""n8n 의 실행 기록(SQLite)에서 실행별 지표를 뽑아 dashboard/runs.json 으로 저장한다.

  docker cp n8n-portfolio:/home/node/.n8n/database.sqlite* /tmp/n8ndb/
  python3 dashboard/extract_runs.py /tmp/n8ndb/database.sqlite midFailTest0001=목업 realLlmTest0002=Gemini
"""
import json, sqlite3, sys, os
from datetime import datetime, timezone, timedelta


def unflatten(arr):  # flatted 형식 복원
    cache = {}

    def val(x):
        return res(int(x)) if isinstance(x, str) else x

    def res(i):
        if i in cache:
            return cache[i]
        v = arr[i]
        if isinstance(v, dict):
            out = cache[i] = {}
            for k, x in v.items():
                out[k] = val(x)
            return out
        if isinstance(v, list):
            out = cache[i] = []
            for x in v:
                out.append(val(x))
            return out
        return v
    return res(0)


def items(run_data, node, port=0):
    runs = run_data.get(node)
    if not runs:
        return []
    out = []
    for r in runs:
        main = (r.get('data') or {}).get('main') or []
        if len(main) > port and main[port]:
            out += [i['json'] for i in main[port] if i]
    return out


def main(db, specs):
    con = sqlite3.connect(db)
    rows = []
    for spec in specs:
        wid, kind = spec.split('=')
        for eid, status, started, stopped in con.execute(
                "select id,status,startedAt,stoppedAt from execution_entity where workflowId=? order by id", (wid,)):
            data = con.execute("select data from execution_data where executionId=?", (eid,)).fetchone()
            rd = unflatten(json.loads(data[0]))['resultData']['runData']
            t = datetime.fromisoformat(started.replace(' ', 'T')).replace(tzinfo=timezone.utc)
            rows.append({
                'at': t.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M'),
                'kind': kind, 'status': status,
                'fetched': len(items(rd, 'RSS 수집')),
                'matched': len(items(rd, '키워드 필터 + 중복 제거')),
                'published': len(items(rd, '워드프레스 발행')),
                'isolated': len(items(rd, 'LLM 요약/작성', 1)),
                'titles': [i['title'] for i in items(rd, '글 포맷 정리')],
            })
    rows.sort(key=lambda r: r['at'])
    out = os.path.join(os.path.dirname(__file__), 'runs.json')
    json.dump(rows, open(out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
