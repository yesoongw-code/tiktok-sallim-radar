
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="살림템 TikTok Radar",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 살림템 TikTok Radar")
st.caption("실제 Apify 데이터 분석 · 추가 API 비용 없음")

DAYS = 90
MIN_VIEWS = 10000


def get_value(data, path):
    value = data
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def first(data, paths):
    for path in paths:
        value = get_value(data, path)
        if value is not None and value != "":
            return value
    return None


def number(value):
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def parse_date(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(
                value / 1000 if value > 1e12 else value,
                tz=timezone.utc
            )
        if isinstance(value, str) and value.isdigit():
            return parse_date(int(value))
        result = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(result):
            return None
        return result.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


def safe_url(value, video=False):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return None
    if video:
        if host not in ("tiktok.com", "www.tiktok.com"):
            return None
        if "/video/" not in parsed.path and "/photo/" not in parsed.path:
            return None
    else:
        if not (
            host.endswith(".tiktokcdn.com")
            or host.endswith(".tiktokcdn-us.com")
        ):
            return None
    return value


def normalize(item):
    if not isinstance(item, dict):
        return None

    views = number(first(item, [
        "playCount", "stats.playCount", "videoViews", "views"
    ]))
    date = parse_date(first(item, [
        "createTimeISO", "createTime", "publishedAt"
    ]))
    link = safe_url(first(item, [
        "webVideoUrl", "videoUrl", "url"
    ]), video=True)

    if views is None or date is None or not link:
        return None

    thumbnail = safe_url(first(item, [
        "videoMeta.coverUrl",
        "videoMeta.originalCoverUrl"
    ]))

    return {
        "date": date,
        "views": views,
        "author": first(item, [
            "authorMeta.name", "authorMeta.nickName",
            "author.uniqueId"
        ]) or "미확인",
        "title": first(item, [
            "text", "desc", "caption", "title"
        ]) or "설명 없음",
        "thumbnail": thumbnail,
        "link": link,
        "likes": number(item.get("diggCount")) or 0,
        "shares": number(item.get("shareCount")) or 0,
        "comments": number(item.get("commentCount")) or 0
    }


uploaded = st.file_uploader(
    "Apify JSON 파일 업로드",
    type=["json", "csv"]
)

st.info("최근 90일 · 조회수 1만 이상 · 일평균 조회수순")

if uploaded is None:
    st.stop()

try:
    if uploaded.name.lower().endswith(".json"):
        raw = json.load(uploaded)
        if isinstance(raw, dict):
            raw = raw.get("items", raw.get("data", raw.get("results", [])))
    else:
        raw = pd.read_csv(uploaded).to_dict("records")

    if not isinstance(raw, list):
        st.error("영상 목록 데이터가 아니야.")
        st.stop()
except Exception as error:
    st.error(f"파일 오류: {error}")
    st.stop()

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=DAYS)
results = {}

for raw_item in raw:
    item = normalize(raw_item)
    if not item:
        continue

    if not cutoff <= item["date"] <= now:
        continue
    if item["views"] < MIN_VIEWS:
        continue

    days = max(
        (now - item["date"]).total_seconds() / 86400,
        1
    )
    item["daily"] = round(item["views"] / days)
    item["days"] = round(days, 1)
    results[item["link"]] = item

videos = sorted(
    results.values(),
    key=lambda x: x["daily"],
    reverse=True
)

c1, c2, c3 = st.columns(3)
c1.metric("수집 영상", len(raw))
c2.metric("조건 충족", len(videos))
c3.metric("최소 조회수", "10,000")

st.caption(
    "일평균 조회수는 누적 조회수를 게시 후 경과일수"
    "(최소 1일)로 나눈 추정치입니다. "
    "실제 일별 증가량은 아닙니다."
)

st.subheader("🔥 급상승 후보 TOP 20")

if not videos:
    st.warning("조건에 맞는 영상이 없어.")
    st.stop()

for rank, video in enumerate(videos[:20], 1):
    with st.container(border=True):
        left, right = st.columns([1, 3])

        with left:
            if video["thumbnail"]:
                st.image(
                    video["thumbnail"],
                    use_container_width=True
                )
            else:
                st.write("썸네일 없음")

        with right:
            st.markdown(f"### {rank}위 · @{video['author']}")
            st.write(str(video["title"])[:180])

            st.markdown(
                f"**조회수:** {video['views']:,}회  \n"
                f"**일평균 추정:** {video['daily']:,}회  \n"
                f"**게시일:** {video['date']:%Y-%m-%d}  \n"
                f"**좋아요:** {video['likes']:,} · "
                f"**공유:** {video['shares']:,} · "
                f"**댓글:** {video['comments']:,}"
            )

            st.link_button(
                "🎬 틱톡 원본 영상 열기",
                video["link"]
            )

rows = []
for video in videos:
    rows.append({
        "게시일": video["date"].strftime("%Y-%m-%d"),
        "계정": video["author"],
        "영상 설명": video["title"],
        "조회수": video["views"],
        "일평균 조회수": video["daily"],
        "좋아요": video["likes"],
        "공유": video["shares"],
        "댓글": video["comments"],
        "원본 링크": video["link"]
    })

df = pd.DataFrame(rows)

st.download_button(
    "📥 CSV 다운로드",
    data=df.to_csv(index=False).encode("utf-8-sig"),
    file_name="sallim_radar.csv",
    mime="text/csv"
)

st.caption(
    "썸네일은 TikTok 제공 주소를 사용하므로 "
    "주소가 만료되면 표시되지 않을 수 있어요."
)
