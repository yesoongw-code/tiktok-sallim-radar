import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

st.set_page_config(page_title="살림템 TikTok Radar", page_icon="🔎", layout="wide")
st.title("🔎 살림템 TikTok Radar")
st.caption("Apify에서 내보낸 실제 데이터만 분석합니다. 앱에서 Apify를 자동 실행하거나 비용을 발생시키지 않습니다.")

DAYS = 90
MIN_VIEWS = 10000


def dig(d, path):
    cur = d
    for key in path.split('.'):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def first(d, paths):
    for p in paths:
        value = dig(d, p)
        if value is not None and value != "":
            return value
    return None


def safe_int(v):
    try:
        if isinstance(v, dict):
            return None
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def date_parse(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            n = float(value)
            if n > 1e12:
                n /= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc)
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


def valid_tiktok_url(url):
    if not isinstance(url, str):
        return False
    try:
        p = urlparse(url)
        return p.scheme == "https" and (p.hostname == "tiktok.com" or p.hostname.endswith(".tiktok.com")) and ("/video/" in p.path or "/photo/" in p.path)
    except Exception:
        return False


def normalize(row):
    if not isinstance(row, dict):
        return None
    views = safe_int(first(row, ["playCount", "videoViews", "stats.playCount", "stats.views", "item.playCount", "item.stats.playCount", "video.stats.views", "video.playCount", "views"]))
    created = date_parse(first(row, ["createTimeISO", "createTime", "create_time", "item.createTimeISO", "item.createTime", "video.createTimeISO", "video.createTime", "publishedAt", "date"] ))
    url = first(row, ["webVideoUrl", "videoUrl", "videoURL", "url", "item.webVideoUrl", "item.videoUrl", "video.webVideoUrl", "video.url"])
    # A URL must be provided by the data source, rather than guessed from an ID.
    if views is None or created is None or not valid_tiktok_url(url):
        return None
    author = first(row, ["authorMeta.name", "authorMeta.nickName", "author.uniqueId", "author.username", "item.authorMeta.name", "video.author.username", "username"])
    title = first(row, ["text", "desc", "caption", "title", "item.text", "item.desc", "video.title", "video.text"]) or "(설명 없음)"
    likes = safe_int(first(row, ["diggCount", "stats.diggCount", "item.diggCount", "item.stats.diggCount", "videoLikes", "likes"]))
    comments = safe_int(first(row, ["commentCount", "stats.commentCount", "item.commentCount", "comments"]))
    shares = safe_int(first(row, ["shareCount", "stats.shareCount", "item.shareCount", "shares"]))
    return {"게시일_UTC": created, "조회수": views, "영상": str(title)[:160], "계정": str(author or "(미확인)"), "링크": url, "좋아요": likes, "댓글": comments, "공유": shares}


uploaded = st.file_uploader("Apify Dataset의 JSON 또는 CSV 파일 업로드", type=["json", "csv"])
st.info("검색어 #쿠팡꿀템으로 Apify에서 수집한 데이터를 넣어줘. 이 앱은 **최근 90일 / 조회수 1만 이상**으로 걸러 **일평균 조회수**순 정렬해.")

if uploaded is None:
    st.markdown("**사용 순서:** Apify에서 `쿠팡꿀템` 수집 → Dataset → Export → JSON → 이 화면에 업로드")
    st.stop()

try:
    if uploaded.name.lower().endswith(".json"):
        raw = json.load(uploaded)
        if isinstance(raw, dict):
            raw = raw.get("items", raw.get("data", raw.get("results", [])))
    else:
        raw = pd.read_csv(uploaded).to_dict(orient="records")
    if not isinstance(raw, list):
        st.error("JSON은 영상 목록 배열이어야 해. Apify의 Dataset → Export → JSON으로 다시 받아줘.")
        st.stop()
except Exception as e:
    st.error(f"파일을 읽을 수 없어: {e}")
    st.stop()

items = [normalize(x) for x in raw]
items = [x for x in items if x is not None]
missing = len(raw) - len(items)
if missing:
    st.warning(f"총 {len(raw)}개 중 {missing}개는 실제 조회수·게시일·TikTok 영상 URL 중 하나가 없어 제외했어. 값을 추측해서 채우지 않아.")
if not items:
    st.error("사용 가능한 영상 데이터가 없어. Apify Dataset에 playCount, createTime, webVideoUrl이 있는지 확인해 줘.")
    st.stop()

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=DAYS)
unique = {}
for item in items:
    unique[item["링크"]] = item
selected = []
for item in unique.values():
    if item["조회수"] < MIN_VIEWS or not (cutoff <= item["게시일_UTC"] <= now):
        continue
    elapsed_days = max((now - item["게시일_UTC"]).total_seconds() / 86400, 1.0)
    item["게시후_일수"] = round(elapsed_days, 1)
    item["일평균_조회수_추정"] = round(item["조회수"] / elapsed_days)
    selected.append(item)
selected.sort(key=lambda r: r["일평균_조회수_추정"], reverse=True)

c1, c2, c3 = st.columns(3)
c1.metric("가져온 영상", len(raw))
c2.metric("조건 충족", len(selected))
c3.metric("기준", "최근 90일 · 1만+" )
st.caption("일평균 조회수 = 현재 누적 조회수 ÷ 게시 후 경과일수(최소 1일). 실제 일별 증가량이나 실시간 급상승 속도가 아닌 *근사 지표*야.")
if not selected:
    st.warning("조건에 맞는 영상이 없어. 검색 결과가 적다면 Apify에서 최대 결과 개수를 조금 늘려서 다시 수집해 봐 (비용 확인 필수).")
    st.stop()

result = pd.DataFrame(selected)
result["게시일"] = result["게시일_UTC"].dt.strftime("%Y-%m-%d")
result = result.rename(columns={"일평균_조회수_추정": "일평균 조회수(추정)", "게시후_일수": "경과일"})
cols = ["게시일", "계정", "영상", "조회수", "경과일", "일평균 조회수(추정)", "좋아요", "댓글", "공유", "링크"]
st.subheader("급상승 후보 TOP 20")
st.dataframe(result[cols].head(20), hide_index=True, use_container_width=True, column_config={"링크": st.column_config.LinkColumn("영상 링크", display_text="영상 열기"), "조회수": st.column_config.NumberColumn(format="%d"), "일평균 조회수(추정)": st.column_config.NumberColumn(format="%d")})
st.download_button("전체 필터 결과 CSV 저장", result[cols].to_csv(index=False).encode("utf-8-sig"), file_name="tiktok_sallim_radar.csv", mime="text/csv")
st.caption("원본 검색은 Apify의 검색 방식과 TikTok 접근 가능 범위에 따라 누락될 수 있어. 검색 결과 전체를 포괄하는 순위는 아니야.")
