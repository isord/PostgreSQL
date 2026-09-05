import csv
import io
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import psycopg2

XML_PATH = "data/CORPCODE.xml"
CHUNK_SIZE = 10_000


def load_env(path=".env"):
    """의존성 없이 .env를 읽어 환경변수로 올린다."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def parse_date(raw):
    """'20170630' -> date. 빈 값이나 형식 오류는 None."""
    raw = (raw or "").strip()
    if len(raw) != 8:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def iter_rows(path):
    """XML을 스트리밍으로 읽어 한 건씩 내보낸다."""
    context = ET.iterparse(path, events=("end",))
    _, root = next(ET.iterparse(path, events=("start",)))

    for event, elem in context:
        if elem.tag != "list":
            continue

        def text(tag):
            node = elem.find(tag)
            return (node.text or "").strip() if node is not None else ""

        corp_code = text("corp_code")
        corp_name = text("corp_name")
        stock_code = text("stock_code")

        if corp_code and corp_name:
            yield (
                corp_code,
                corp_name,
                text("corp_eng_name") or None,
                stock_code or None,          # 공백 -> NULL
                parse_date(text("modify_date")),
            )

        # 처리한 노드를 즉시 해제. 이걸 안 하면 메모리에 계속 쌓인다.
        elem.clear()
        root.clear()


def copy_chunk(cur, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    buf.seek(0)

    cur.copy_expert(
        "COPY corp_master "
        "(corp_code, corp_name, corp_eng_name, stock_code, modify_date) "
        "FROM STDIN WITH (FORMAT csv)",
        buf,
    )


def main():
    load_env()

    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )
    cur = conn.cursor()

    total = 0
    skipped = 0
    seen = set()
    chunk = []

    started = time.perf_counter()

    for row in iter_rows(XML_PATH):
        # 원본에 고유번호 중복이 있으면 PK 위반으로 배치 전체가 죽는다.
        if row[0] in seen:
            skipped += 1
            continue
        seen.add(row[0])

        chunk.append(row)

        if len(chunk) >= CHUNK_SIZE:
            copy_chunk(cur, chunk)
            conn.commit()
            total += len(chunk)
            print(f"  {total:,}건 적재 ({time.perf_counter() - started:.1f}s)")
            chunk.clear()

    if chunk:
        copy_chunk(cur, chunk)
        conn.commit()
        total += len(chunk)

    elapsed = time.perf_counter() - started

    cur.close()
    conn.close()

    print("-" * 40)
    print(f"적재 건수   : {total:,}")
    print(f"중복 제외   : {skipped:,}")
    print(f"소요 시간   : {elapsed:.2f}초")
    print(f"처리 속도   : {total / elapsed:,.0f} rows/sec")


if __name__ == "__main__":
    main()