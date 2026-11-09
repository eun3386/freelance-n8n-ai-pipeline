#!/usr/bin/env python3
"""n8n 워크플로우와 같은 흐름을 로컬에서 재현하는 파이프라인.

RSS 수집 -> 키워드 필터/중복 제거 -> LLM 요약(재시도) -> 마크다운 발행 -> 실행 로그

  python3 pipeline/run.py --demo                # 샘플 피드 + 키 없이 동작(추출 요약)
  GEMINI_API_KEY=... python3 pipeline/run.py --feed <RSS_URL>
"""
import argparse, hashlib, json, os, sqlite3, time, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def fetch_feed(src: str) -> list[dict]:
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=20) as r:
            data = r.read()
    else:
        data = Path(src).read_bytes()
    root = ET.fromstring(data)
    return [
        {"title": (i.findtext("title") or "").strip(), "link": (i.findtext("link") or "").strip(),
         "content": (i.findtext("description") or "").strip()}
        for i in root.iter("item")
    ]


def keyword_filter(items, keywords):
    kw = [k.lower() for k in keywords]
    return [i for i in items if any(k in (i["title"] + i["content"]).lower() for k in kw)]


def retry(fn, tries=3, wait=1.0):
    """n8n 'Retry On Fail' 노드 설정과 동일한 동작: 지수 백오프."""
    last = None
    for n in range(1, tries + 1):
        try:
            return fn(), n - 1
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(wait * (2 ** (n - 1)))
    raise RuntimeError(f"{tries}회 실패: {last}")


def llm_summarize(item) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:  # 키가 없으면 추출 요약으로 대체(데모용)
        return f"{item['title']}\n\n{item['content']}\n\n원문: {item['link']}"
    prompt = (f"다음 기사를 한국어 블로그 글로 작성해줘. 첫 줄은 제목, 3문단 요약 + 핵심 포인트 3개.\n\n"
              f"제목: {item['title']}\n본문: {item['content']}\n링크: {item['link']}")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"maxOutputTokens": 2000}}).encode()
    base = os.environ.get("LLM_BASE", "https://generativelanguage.googleapis.com")
    req = urllib.request.Request(f"{base}/v1beta/models/{MODEL}:generateContent", body, {
        "x-goog-api-key": key, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=str(ROOT / "fixtures" / "sample_feed.xml"))
    ap.add_argument("--keywords", default="AI,자동화,n8n")
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--demo", action="store_true", help="샘플 피드 사용")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(OUT / "seen.db")
    db.execute("create table if not exists seen(link text primary key)")

    run = {"started": datetime.now(timezone.utc).isoformat(), "fetched": 0, "matched": 0,
           "published": 0, "retries": 0, "failed": 0, "errors": []}
    items = fetch_feed(a.feed)
    run["fetched"] = len(items)
    items = keyword_filter(items, a.keywords.split(","))
    items = [i for i in items if not db.execute("select 1 from seen where link=?", (i["link"],)).fetchone()][: a.max]
    run["matched"] = len(items)

    for it in items:
        try:
            text, retries = retry(lambda: llm_summarize(it))
            run["retries"] += retries
            slug = f"{datetime.now():%Y%m%d}-{hashlib.md5(it['link'].encode()).hexdigest()[:6]}"
            (OUT / f"{slug}.md").write_text(f"# {text.splitlines()[0]}\n\n" + "\n".join(text.splitlines()[1:]), encoding="utf-8")
            db.execute("insert into seen values(?)", (it["link"],))
            run["published"] += 1
        except Exception as e:  # noqa: BLE001  -> 한 건 실패가 전체를 막지 않도록 격리
            run["failed"] += 1
            run["errors"].append({"link": it["link"], "error": str(e)})
    db.commit()

    run["finished"] = datetime.now(timezone.utc).isoformat()
    log = OUT / "runs.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    print(json.dumps(run, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
