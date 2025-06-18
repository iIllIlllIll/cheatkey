import discord
import time
from datetime import datetime, timedelta
from binance.enums import *
import asyncio
import matplotlib
matplotlib.use('Agg')  # 서버 환경에서 GUI 없이 사용
import sqlite3
import mplfinance as mpf
import os, random
import traceback
import io, json
import sys
# from functions import *
import functions as f
import re
import ast
import pytz
import pandas as pd
import math
from colorama import Fore, Style
from bs4 import BeautifulSoup

from init_functions import *

# 초기설정
SUPPORTED_EXCHANGES = ["binance", "bybit"]

symbol = "XRPUSDT"
count = 0

long_holding = False
short_holding = False

variable_list = [
    "CHEATKEY_THRESHOLD",
    "CHEATKEY_LOOKBACK",
    "CHEATKEY_TIMEFILTER",
    "long_leverage",
    "short_leverage",
    "LONG_TP_PNL",
    "SHORT_TP_PNL",
    "LONG_SL_PNL",
    "SHORT_SL_PNL",
    "LONG_ADD_SL_PNL",
    "SHORT_ADD_SL_PNL",
    "LONG_PARTIAL_EXIT_PNL",
    "SHORT_PARTIAL_EXIT_PNL",
    "LONG_ADD_BUY_PNL",
    "SHORT_ADD_BUY_PNL",
    "DIVIDE_VALUE",
    "ADD_BUY_CANDLE_CONDITION",
    "PARTIAL_EXIT_MODE",
    "EXIT_MODE",
    "EXIT_FULL_CONDITION",
    "FIRST_OPPOSITE_EXIT",
    "FIRST_OPPOSITE_EXIT_PNL",
    "USE_TIMEOUT_CROSS",
    "TIMEOUT_CROSS_BARS",
    "TIMEOUT_SELL_PNL",
    "MACRO_EMA_FILTER",
    "MACRO_EMA_PERIOD",
    "SLOPE_EXIT",
    "SLOPE_EXIT_LOOKBACK",
    "SLOPE_EXIT_COOLDOWN_BARS",
    "SLOPE_EXIT_PNL_THRESHOLD"

]


# 플랑크톤 매매법 변수

## 치트키 관련 변수
CHEATKEY_THRESHOLD = 0.001
CHEATKEY_LOOKBACK = 6
CHEATKEY_TIMEFILTER = True


long_leverage = 10
short_leverage = 10

LONG_TP_PNL = 15 # 익절 퍼센트
SHORT_TP_PNL = 15

LONG_SL_PNL = -10 # 손절 퍼센트
SHORT_SL_PNL = -10

LONG_ADD_SL_PNL = [-15,-15,-15] # 추가매수 후 손절 퍼센트
SHORT_ADD_SL_PNL = [-15,-15,-15]

LONG_PARTIAL_EXIT_PNL = 10 # 부분익절 퍼센트
SHORT_PARTIAL_EXIT_PNL = 10

LONG_ADD_BUY_PNL = -7 # 첫 추가매수 트리거 퍼센트
SHORT_ADD_BUY_PNL = -7

DIVIDE_VALUE = 3 # 분할 지수 2^value
TOTAL_PARTS = 2 ** DIVIDE_VALUE


ADD_BUY_CANDLE_CONDITION = False # 추가매수 시 캔들 방향 조건 결정

PARTIAL_EXIT_MODE = 'added' # 부분익절 시 전체 매도할지, 추가매수 분량만 매도할지 결정 ( all, added, None )

## 반대신호 매도 ExitAdd
EXIT_MODE = 'all' # 매도 분량 조건 ( all, added , None )
EXIT_FULL_CONDITION = 'always' # 수익률 양일때만 매도하기, 또는 아무때나 매도하기 ( profit_only, always )
FIRST_OPPOSITE_EXIT = True
FIRST_OPPOSITE_EXIT_PNL = 0
EXITMODE_TIMEFILTER = False

## 타임아웃 매도 TimeoutExit
USE_TIMEOUT_CROSS = False # 타임아웃 조건 사용 여부
TIMEOUT_CROSS_BARS = 30 # 타임아웃 봉 개수
TIMEOUT_SELL_PNL = 0 #  타임아웃 시 마지막 PNL 매도 조건

MACRO_EMA_FILTER = True
MACRO_EMA_PERIOD = 100

SLOPE_EXIT = True
SLOPE_EXIT_LOOKBACK = 1
SLOPE_EXIT_COOLDOWN_BARS = 20
SLOPE_EXIT_PNL_THRESHOLD = 5




# 전략 실행 상태
is_running = False
waiting = False
Aicommand = False  


noerror = 0

bot = f.bot
client = f.client

@bot.group(name="exchange", invoke_without_command=True)
async def exchange(ctx):
    """거래소 설정 관련 명령어 그룹입니다. subcommand로 list, set 을 지원합니다."""
    await ctx.send("사용법: `!exchange list` 또는 `!exchange set <exchange_name>`")

@exchange.command(name="list")
async def exchange_list(ctx):
    """지원하는 거래소 목록을 보여줍니다."""
    await ctx.send("🔄 **지원 거래소 목록**\n" + "\n".join(f"- `{e}`" for e in SUPPORTED_EXCHANGES))

@exchange.command(name="set")
async def exchange_set(ctx, name: str):
    name = name.lower()
    if name not in SUPPORTED_EXCHANGES:
        return await ctx.send("잘못된 거래소 이름입니다…")
    # 여기서 모듈 변수 건드리기
    f.EXCHANGE = name
    await ctx.send(f"✅ 거래소가 `{name}` 로 변경되었습니다.")

@exchange.command(name="current")
async def exchange_current(ctx):
    """현재 설정된 거래소를 보여줍니다."""
    await ctx.send(f"🔔 현재 사용 중인 거래소: `{f.EXCHANGE}`")



# 일정 파일 저장 경로 (절대 경로 사용 권장)
SCHEDULE_FILE = os.path.join(os.getcwd(), "events.txt")
# 전역 변수에 로드한 일정 데이터 저장 (리로드 시 사용)
schedule_data = None

long_savemode = False
short_savemode = False

# 명언 데이터베이스 파일 경로 (한 줄에 하나씩 명언이 저장되어 있음)
QUOTE_DB = os.path.join(os.getcwd(), "cheerme_quotes.txt")

# 파일이 없으면 새로 생성 (빈 파일 또는 기본 메시지로 초기화 가능)
if not os.path.exists(QUOTE_DB):
    with open(QUOTE_DB, "w", encoding="utf-8") as f:
        f.write("")  # 빈 파일로 생성
    print(f"{QUOTE_DB} 파일이 존재하지 않아 새로 생성했습니다.")

@bot.group(invoke_without_command=True)
async def cheerme(ctx):
    """랜덤으로 코인/주식 관련 명언을 보여줍니다."""
    try:
        with open(QUOTE_DB, "r", encoding="utf-8") as f:
            quotes = [line.strip() for line in f if line.strip()]
        if not quotes:
            await ctx.send("명언 데이터베이스에 명언이 없습니다. `!cheerme upload`로 추가해주세요.")
        else:
            quote = random.choice(quotes)
            await ctx.send(quote)
    except Exception as e:
        await ctx.send(f"명언을 불러오는 데 실패했습니다: {e}")

@cheerme.command(name="help")
async def cheerme_help(ctx):
    """명령어 사용법을 보여줍니다."""
    help_msg = (
        "**!cheerme 명령어 사용법**\n\n"
        "`!cheerme help` - 명령어 사용법을 보여줍니다.\n"
        "`!cheerme` - 데이터베이스에 저장된 명언 중 랜덤으로 하나를 보여줍니다.\n"
        "`!cheerme all` - 모든 명언들을 10개씩 묶어서 보여줍니다.\n"
        "`!cheerme export` - 명언 데이터베이스 파일(txt)을 첨부하여 전송합니다.\n"
        "`!cheerme upload` - 새로운 명언 데이터베이스 파일을 업로드합니다."
    )
    await ctx.send(help_msg)

@cheerme.command(name="all")
async def cheerme_all(ctx):
    """모든 명언을 10개씩 묶어서 보여줍니다."""
    try:
        with open(QUOTE_DB, "r", encoding="utf-8") as f:
            quotes = [line.strip() for line in f if line.strip()]
        if not quotes:
            await ctx.send("명언 데이터베이스에 명언이 없습니다.")
            return
        # 10개씩 묶기
        chunks = [quotes[i:i+10] for i in range(0, len(quotes), 10)]
        for chunk in chunks:
            msg = "\n".join(chunk)
            await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"명언을 불러오는 데 실패했습니다: {e}")

@cheerme.command(name="export")
async def cheerme_export(ctx):
    """명언 데이터베이스 파일(txt)을 Discord 메시지에 첨부하여 전송합니다."""
    try:
        await ctx.send("데이터베이스 파일을 전송합니다.", file=discord.File(QUOTE_DB))
    except Exception as e:
        await ctx.send(f"파일 전송 실패: {e}")

@cheerme.command(name="upload")
async def cheerme_upload(ctx):
    """새로운 명언 데이터베이스 파일을 업로드합니다."""
    if not ctx.message.attachments:
        await ctx.send("업로드할 파일을 첨부해주세요!")
        return
    attachment = ctx.message.attachments[0]
    try:
        content = await attachment.read()
        with open(QUOTE_DB, "wb") as f:
            f.write(content)
        await ctx.send("파일이 성공적으로 업로드되었습니다!")
    except Exception as e:
        await ctx.send(f"파일 업로드 실패: {e}")

@cheerme.command(name="add")
async def cheerme_add(ctx, *, quote: str):
    """입력받은 명언을 데이터베이스에 추가합니다."""
    try:
        with open(QUOTE_DB, "a", encoding="utf-8") as f:
            f.write(quote + "\n")
        await ctx.send("명언이 성공적으로 추가되었습니다!")
    except Exception as e:
        await ctx.send(f"명언 추가 실패: {e}")



@bot.command(name="exportdb")
async def exportdb(ctx):
    """
    데이터베이스 파일(DB 형태)을 Discord 메시지에 첨부하여 전송합니다.
    """
    try:
        await ctx.send("데이터베이스 파일을 전송합니다.", file=discord.File(f.DB_PATH))
    except Exception as e:
        await ctx.send(f"데이터베이스 전송 실패: {e}")

@bot.command(name="exportexcel")
async def exportexcel(ctx):
    """
    데이터베이스의 데이터를 엑셀 파일로 변환하여 Discord 메시지에 첨부하여 전송합니다.
    """
    try:
        # DB 연결 및 데이터 읽기
        conn = sqlite3.connect(f.DB_PATH)
        df = pd.read_sql_query("SELECT * FROM data", conn)
        conn.close()

        # 엑셀 파일로 저장 (파일명: data_export.xlsx)
        excel_file = "data_export.xlsx"
        df.to_excel(excel_file, index=False)

        # 파일 전송
        await ctx.send("엑셀 파일을 전송합니다.", file=discord.File(excel_file))
        # 전송 후 임시 파일 삭제 (필요 시)
        os.remove(excel_file)
    except Exception as e:
        await ctx.send(f"엑셀 파일 전송 실패: {e}")


def compute_profit_stats(period):
    """
    지정된 기간 동안의 데이터를 조회하여,
      - 총 순수익 (수익은 profit, 손실은 loss로 처리)
      - 평균 ROI (ROI의 평균)
      - profit, loss 건수 및 profit 건수의 비율(%)
    을 계산하여 딕셔너리로 반환합니다.
    기간 형식은 "all" 또는 "[숫자][d/W/M/Y]" 형태 (예: "1d", "3d", "1W", "1M", "1Y").
    """
    conn = sqlite3.connect(f.DB_PATH)
    cursor = conn.cursor()
    
    if period.lower() != "all":
        m = re.match(r"(\d+)([dWMYwmwy])", period)
        if not m:
            conn.close()
            raise ValueError("기간 형식이 올바르지 않습니다. 예: 1d, 1W, 1M, 1Y, 3d 등")
        num = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "d":
            delta = timedelta(days=num)
        elif unit == "w":
            delta = timedelta(weeks=num)
        elif unit == "m":
            delta = timedelta(days=30*num)  # 한달은 약 30일
        elif unit == "y":
            delta = timedelta(days=365*num)  # 1년은 365일
        else:
            delta = timedelta(days=num)
        threshold_date = (datetime.now() - delta).strftime("%Y-%m-%d")
        query = "SELECT date, result, pnl, roi FROM data WHERE date >= ?"
        cursor.execute(query, (threshold_date,))
    else:
        query = "SELECT date, result, pnl, roi FROM data"
        cursor.execute(query)
        
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    net_profit = 0.0
    total_roi = 0.0
    roi_count = 0
    profit_count = 0
    loss_count = 0
    
    for row in rows:
        date_str, result, pnl, roi = row
        # result: "profit" or "loss"
        net_profit += pnl
        if result.lower() == "profit":
            profit_count += 1
        elif result.lower() == "loss":
            loss_count += 1
        try:
            total_roi += float(roi)
            roi_count += 1
        except Exception:
            pass
            
    avg_roi = total_roi / roi_count if roi_count > 0 else 0.0
    total_count = profit_count + loss_count
    profit_ratio = (profit_count / total_count * 100) if total_count > 0 else 0.0
    
    stats = {
        "net_profit": net_profit,
        "avg_roi": avg_roi,
        "profit_count": profit_count,
        "loss_count": loss_count,
        "profit_ratio": profit_ratio,
        "total_count": total_count
    }
    return stats

@bot.command(name="profit")
async def profit(ctx, period: str = None):
    """
    !profit 명령어: 지정한 기간 동안의 총 순수익, 평균 ROI, 수익 및 손실 건수와 수익 비율을 알려줍니다.
    
    사용법:
      !profit all    → 전체 데이터에 대해 계산
      !profit 1M     → 최근 1달 동안의 데이터
      !profit 1W     → 최근 1주일 동안의 데이터
      !profit 1Y     → 최근 1년 동안의 데이터
      !profit 3d     → 최근 3일 동안의 데이터
    
    인수를 생략하면 사용법 안내 메시지를 보냅니다.
    """
    if period is None:
        await ctx.send("사용법: `!profit <기간>`\n예: `!profit all`, `!profit 1M`, `!profit 1W`, `!profit 1Y`, `!profit 3d`")
        return
    try:
        stats = compute_profit_stats(period)
        if stats is None:
            await ctx.send("해당 기간에 해당하는 데이터가 없습니다.")
            return
        msg = (
            f"## 🔥 매매내역분석 🚀\n\n"
            f"**📊 기간: {period}**\n\n"
            f"💰 **총 순수익 :** `{stats['net_profit']}`\n"
            f"📈 **평균 ROI :** `{stats['avg_roi']:.2f}%`\n\n"
            f"✅ **수익 건수 :** `{stats['profit_count']}건`\n"
            f"❌ **손실 건수 :** `{stats['loss_count']}건`\n"
            f"🔄 **수익 비율 :** `{stats['profit_ratio']:.2f}%` (전체 `{stats['total_count']}건` 중)\n"
        )
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"오류 발생: {e}")




def load_schedule():
    """저장된 파일에서 일정 데이터를 로드합니다."""
    global schedule_data
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            schedule_data = json.load(f)
        print(f"파일 로드 성공: {SCHEDULE_FILE}, 항목 수: {len(schedule_data)}")
    except Exception as e:
        print(f"파일 로드 실패: {e}")
        schedule_data = None

def save_schedule():
    """변경된 schedule_data를 파일에 저장합니다."""
    global schedule_data
    try:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=2)
        print("일정 데이터 저장 완료")
    except Exception as e:
        print(f"일정 데이터 저장 실패: {e}")

def parse_date_range(date_range_text):
    """
    날짜 범위 문자열을 여러 포맷으로 시도하여 시작일과 종료일을 반환합니다.
    예: "2025-03-09 - 2025-03-15" 또는 "2025/03/09 - 2025/03/15"
    """
    start_str, end_str = date_range_text.split(" - ")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            start_date = datetime.strptime(start_str, fmt).date()
            end_date = datetime.strptime(end_str, fmt).date()
            return start_date, end_date
        except Exception:
            continue
    raise ValueError(f"날짜 범위 파싱 실패: {date_range_text}")

def extract_json(text):
    """
    응답 텍스트에서 코드 블록(```json ... ```) 내의 JSON 데이터를 추출합니다.
    코드 블록이 없으면, 첫 번째 '['와 마지막 ']' 사이의 문자열을 반환합니다.
    """
    import re
    pattern = re.compile(r"```json\s*(\[[\s\S]*?\])\s*```", re.MULTILINE)
    match = pattern.search(text)
    if match:
        json_text = match.group(1)
        return json_text
    else:
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            return text[start:end+1]
        else:
            raise ValueError("JSON 데이터를 추출할 수 없습니다.")

def analyze_events_impact_batch(events_batch):
    """
    여러 이벤트(최대 10개씩)의 정보를 바탕으로 AI 분석을 한 번만 요청합니다.
    각 이벤트에 대해 예상 영향력(-100 ~ +100)(긍정적이고, 영향력이 클수록 +100)(부정적이고 영향력이 클수록 -100)과 한 줄 요약을 반환하는 JSON 배열을 받아옵니다.
    반환 예시: [{"expect": "70", "reason": "긍정적 영향"}, ...]
    만약 API 응답이 빈 문자열이거나 파싱에 실패하면, 해당 배치의 모든 이벤트에 대해 기본 결과를 반환합니다.
    """
    prompt = (
        "다음 이벤트들이 비트코인 가격에 미칠 영향을 예측해줘. "
        "각 이벤트에 대해 예상 영향력(-100 ~ +100)(긍정적이고, 영향력이 클수록 +100)(부정적이고 영향력이 클수록 -100)을 나타내고 "
        "한 줄로 요약해줘. 응답은 반드시 JSON 배열 형식으로 반환되어야 하며, "
        "각 결과는 {\"expect\": \"값\", \"reason\": \"요약\"} 형태여야 하고, 입력 순서와 동일해야 해.\n\n"
    )
    for i, event in enumerate(events_batch, start=1):
        title = event.get("Event", "정보 없음")
        currency = event.get("Currency", "정보 없음")
        actual = event.get("Actual", "")
        forecast = event.get("Forecast", "")
        previous = event.get("Previous", "")
        prompt += f"이벤트 {i}:\n"
        prompt += f"  이벤트: {title}\n"
        prompt += f"  통화: {currency}\n"
        prompt += f"  실제: {actual}\n"
        prompt += f"  예측: {forecast}\n"
        prompt += f"  이전: {previous}\n\n"
    
    try:
        response = f.geminaiclient.models.generate_content(
            model="gemini-2.0-flash", contents=[prompt]
        )
        text = response.text.strip()
        print("Gemini API 응답 디버그:", text)
        if not text:
            raise ValueError("응답이 비어 있음")
        # 추출: 응답이 코드 블록 형식이라면 JSON 부분만 추출
        try:
            json_text = extract_json(text)
        except Exception as e:
            print(f"JSON 추출 오류: {e} - 전체 텍스트: {text}")
            json_text = text  # 추출 실패 시 전체 텍스트로 처리
        analysis_list = json.loads(json_text)
        parsed_analysis_list = []
        for item in analysis_list:
            if isinstance(item, str):
                try:
                    parsed_item = json.loads(item.strip())
                    parsed_analysis_list.append(parsed_item)
                except Exception as e:
                    print(f"분석 응답 항목 파싱 오류: {e} - 원본 항목: {item}")
                    parsed_analysis_list.append({"expect": "N/A", "reason": f"❌ 파싱 오류: {e}"})
            else:
                parsed_analysis_list.append(item)
        if not isinstance(parsed_analysis_list, list) or len(parsed_analysis_list) != len(events_batch):
            raise ValueError("응답 형식이 올바르지 않습니다.")
        return parsed_analysis_list
    except Exception as e:
        print(f"AI 분석 오류: {e}")
        return [{"expect": "N/A", "reason": f"❌ API 오류: {e}"} for _ in events_batch]

def update_schedule_with_analysis():
    """
    저장된 일정 데이터의 모든 이벤트에 대해 AI 분석을 배치(10개씩)로 수행하여 'Prediction' 필드를 새로 갱신하고 파일을 업데이트합니다.
    (이미 분석 결과가 있더라도 새로 분석합니다.)
    """
    global schedule_data
    if schedule_data is None:
        print("일정 데이터가 없습니다.")
        return
    batch_size = 10
    events_to_analyze = schedule_data  # 모든 이벤트 대상으로 재분석
    for i in range(0, len(events_to_analyze), batch_size):
        batch = events_to_analyze[i:i+batch_size]
        analysis_results = analyze_events_impact_batch(batch)
        for event, analysis in zip(batch, analysis_results):
            event["Prediction"] = analysis
            print(f"이벤트 '{event.get('Event', '정보 없음')}' 분석 결과 갱신: {analysis}")
    save_schedule()

def get_prediction(e):
    """Prediction 필드가 문자열이면 추가로 JSON 파싱을 시도합니다."""
    pred = e.get("Prediction", {"expect": "N/A", "reason": "분석 결과 없음"})
    if isinstance(pred, str):
        try:
            pred = json.loads(pred.strip())
        except Exception as ex:
            print(f"Prediction 파싱 오류: {ex} - 원본: {pred}")
            pred = {"expect": pred.strip(), "reason": "파싱 오류"}
    return pred

@bot.command(name="upload")
async def upload_f(ctx):
    """
    파일 업로드 명령어.
    !upload 명령어와 함께 파일을 첨부하면 해당 파일을 SCHEDULE_FILE로 저장합니다.
    """
    if not ctx.message.attachments:
        await ctx.send("파일을 첨부해주세요!")
        return
    attachment = ctx.message.attachments[0]
    try:
        content = await attachment.read()
        with open(SCHEDULE_FILE, "wb") as f:
            f.write(content)
        load_schedule()
        await ctx.send("파일이 저장되었습니다!")
    except Exception as e:
        await ctx.send(f"파일 저장 오류: {e}")

@bot.command(name="analyze")
async def analyze_f(ctx):
    """
    저장된 일정 데이터에 대해 AI 분석을 배치(10개씩)로 수행하여 각 일정의 비트코인 가격 영향 예측 결과를 새로 갱신합니다.
    완료 후 업데이트된 파일을 저장합니다.
    """
    load_schedule()
    if schedule_data is None:
        await ctx.send("저장된 일정 파일이 없습니다. 먼저 !upload 명령어로 파일을 업로드하세요.")
        return
    await ctx.send("AI 분석을 시작합니다. 잠시만 기다려주세요...")
    update_schedule_with_analysis()
    await ctx.send("AI 분석이 완료되어 일정 데이터에 결과가 갱신되었습니다.")

@bot.command(name="schedule")
async def schedule_f(ctx, arg: str = None):
    """
    일정 조회 명령어.
    
    사용법:
    !schedule             → 사용법 안내 및 현재 저장된 일정의 날짜 범위를 보여줌.
    !schedule today       → 오늘 일정과 AI 분석 결과만 보여줌.
    !schedule all         → 전체 일정을 날짜별로 나누어 AI 분석 결과와 함께 보여줌.
    """
    load_schedule()
    if schedule_data is None:
        await ctx.send("저장된 일정 파일이 없습니다. 먼저 !upload 명령어로 파일을 업로드하세요.")
        return

    events = []
    for event in schedule_data:
        try:
            event_dt = datetime.fromisoformat(event["Datetime"])
            event["ParsedDatetime"] = event_dt
            events.append(event)
        except Exception as e:
            print(f"이벤트 파싱 오류: {e}")
            continue
    def get_emoji(prediction):
        """
        prediction 딕셔너리의 'expect' 값이 양수이면 초록, 음수이면 빨강, 0이면 중립 이모지를 반환합니다.
        예외 발생 시 빈 문자열을 반환합니다.
        """
        try:
            val_str = prediction.get('expect', '0')
            # 만약 값에 '%' 기호가 있다면 제거합니다.
            val_str_clean = val_str.replace('%', '').strip()
            # 부호(+, -)와 숫자, 소수점만 남깁니다.
            value = float(val_str_clean)
            if value > 0:
                return "🟢"
            elif value < 0:
                return "🔴"
            else:
                return "⚪"
        except Exception as e:
            return ""

    def format_event(e):
        """
        이벤트 정보를 포맷팅하여 반환합니다. AI 분석 결과에 따라 적절한 이모지를 추가합니다.
        """
        dt_str = e["ParsedDatetime"].strftime("%Y-%m-%d %H:%M")
        prediction = get_prediction(e)
        emoji = get_emoji(prediction)
        return (f"**{dt_str}** - {e['Currency']} - {e['Event']}\n"
                f"실제: {e['Actual']}, 예측: {e['Forecast']}, 이전: {e['Previous']}\n"
                f"**🤖AI 분석:** {emoji} 예상 영향: {prediction.get('expect')}%, 이유: {prediction.get('reason')}")

    if arg is None or arg.lower() not in ["today", "all"]:
        if events:
            dates = [e["ParsedDatetime"].date() for e in events]
            min_date = min(dates)
            max_date = max(dates)
            msg = (
                "사용법:\n"
                "`!schedule today` - 오늘 일정\n"
                "`!schedule all`   - 전체 일정 (하루 단위로 메시지 전송)\n\n"
                f"현재 저장된 일정은 {min_date}부터 {max_date}까지입니다."
            )
        else:
            msg = "일정 데이터가 없습니다."
        await ctx.send(msg)
    elif arg.lower() == "today":
        kst = pytz.timezone("Asia/Seoul")
        today = datetime.now(kst).date()
        today_events = [e for e in events if e["ParsedDatetime"].date() == today]
        if not today_events:
            await ctx.send("오늘 일정이 없습니다.")
            return
        today_events.sort(key=lambda x: x["ParsedDatetime"])
        msg_lines = ["##**오늘 일정:**"]
        for e in today_events:
            msg_lines.append(format_event(e))
        await ctx.send("\n\n".join(msg_lines))
    elif arg.lower() == "all":
        if not events:
            await ctx.send("저장된 일정이 없습니다.")
            return
        events_by_date = {}
        for e in events:
            date = e["ParsedDatetime"].date()
            events_by_date.setdefault(date, []).append(e)
        for date in sorted(events_by_date.keys()):
            day_events = events_by_date[date]
            day_events.sort(key=lambda x: x["ParsedDatetime"])
            msg_lines = [f"##**{date} 일정:**"]
            for e in day_events:
                msg_lines.append(format_event(e))
            await ctx.send("\n\n".join(msg_lines))
    else:
        await ctx.send("올바른 인수를 입력하세요: `today`, `all` 또는 인수 없이 사용하세요.")

@bot.command(name='cheat_value')
async def cheat_value_(ctx):
    global cheat_value, symbol
    await ctx.send(f"잠시만 기다려주세요")
    cheat_value = cheatkey_value(symbol,interval='5m')
    await ctx.send(f"cheat_value {cheat_value}입니다")



@bot.command(name='tendency')
async def tendency(ctx):
    candles = f.get_candles(symbol,interval='5m',candle_count=100)  # 필요한 경우 조정 가능
    file_path = f.create_tendency_chart(candles)
    
    # 이미지 파일을 디스코드에 전송
    await ctx.send(file=discord.File(file_path))
    
    # 사용 후 이미지 파일 삭제
    os.remove(file_path)

@bot.command(name='start')
async def start(ctx):
    global is_running
    if not is_running:
        is_running = True
        await ctx.send("자동매매를 시작합니다")
        bot.loop.create_task(start_trading_strategy())
    else:
        await ctx.send("자동매매가 이미 실행 중입니다")

@bot.command(name='stop')
async def stop(ctx):
    global is_running
    if is_running:
        is_running = False
        await ctx.send("자동매매가 중단되었습니다")
    else:
        await ctx.send("자동매매가 실행 중이 아닙니다")

@bot.command(name='close')
async def close_positions(ctx, side: str = "all"):
    """
    사용 예시:
      !close long   → 롱 포지션만 청산
      !close short  → 숏 포지션만 청산
      !close all    → 전체 포지션 청산
    """
    await ctx.send(f"{side} 포지션을 정말로 청산하시겠습니까? (y/n)")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    msg = await bot.wait_for('message', check=check)
    if msg.content.lower() == 'y':
        global is_running
        is_running = False

        # 실제로 close 함수 호출, 반환값을 확인
        result = f.close(symbol, side=side)

        # 결과에 따라 응답 분기
        if isinstance(result, dict) and (result.get("retCode") == 0 or result.get('status') == 'NEW'):
            if f.EXCHANGE == 'bybit':
                await ctx.send(f"✅ {symbol}의 `{side}` 포지션 청산 요청 완료 😎: {result.get('retMsg')}")
            elif f.EXCHANGE == 'binance':
                await ctx.send(f"✅ {symbol}의 `{side}` 포지션 청산 요청 완료 😎")
        elif result == 'no_order':
            await ctx.send(f"✅ {symbol}의 `{side}` 포지션이 없습니다")
        else:
            # retCode가 0이 아닐 때는 오류로 간주
            err_msg = result.get("retMsg") if isinstance(result, dict) else str(result)
            await ctx.send(f"❌ 청산 중 오류 발생: {err_msg}")



@bot.command(name='symbol')
async def set_symbol(ctx, value: str):
    """
    !symbol <심볼>  → Binance Futures 또는 Bybit USDT 페어 심볼을 변경합니다.
    """
    global symbol
    exch = f.EXCHANGE.lower()
    value = value.upper()

    try:
        if exch == 'binance':
            # Binance 선물 심볼 정보 가져오기
            info = client.futures_exchange_info()  
            sym_info = next((s for s in info['symbols'] if s['symbol'] == value), None)
            if not sym_info:
                return await ctx.send(
                    f"❌ 심볼 `{value}` 은(는) Binance Futures에 없습니다. "
                    f"기존 심볼 `{symbol}` 은(는) 유지됩니다."
                )

            # 업데이트 및 메시지
            symbol = sym_info['symbol']
            info_str = (
                f"**Symbol 정보 (Binance)**\n"
                f"• 심볼: **{symbol}** \n"
                f"• Base Asset: **{sym_info.get('baseAsset','N/A')}**\n"
                f"• Quote Asset: **{sym_info.get('quoteAsset','N/A')}**\n"
                f"• Price Precision: **{sym_info.get('pricePrecision','N/A')}**"
            )
            await ctx.send(f"✅ 심볼이 `{symbol}` 으로 설정되었습니다.\n{info_str}")

        elif exch == 'bybit':
            # Bybit USDT 페어 심볼 정보 가져오기
            try:
                info = f.get_symbol_info(value)
            except Exception:
                return await ctx.send(
                    f"❌ 심볼 `{value}` 은(는) Bybit USDT 페어에 없습니다. "
                    f"기존 심볼 `{symbol}` 은(는) 유지됩니다."
                )

            # 업데이트 및 메시지
            symbol = value
            info_str = (
                f"**Symbol 정보 (Bybit)**\n"
                f"• 심볼: **{symbol}**\n"
                f"• Tick Size: **{info.get('tickSize','N/A')}**\n"
                f"• Qty Step: **{info.get('qtyStep','N/A')}**"
            )
            await ctx.send(f"✅ 심볼이 `{symbol}` 으로 설정되었습니다.\n{info_str}")

        else:
            await ctx.send(f"지원하지 않는 거래소입니다: `{f.EXCHANGE}`")

    except Exception as e:
        await ctx.send(f"⚠️ 심볼 설정 중 예외 발생: {e}")

@bot.command(name='waiting')
async def wait_(ctx):
    global waiting
    if waiting == False:
        waiting = True
    else:
        waiting = False
    await ctx.send(f"waiting가 {waiting}로 설정되었습니다")

# settings 저장 폴더 생성
SETTINGS_DIR = os.path.join(os.getcwd(), "settings")
if not os.path.isdir(SETTINGS_DIR):
    os.makedirs(SETTINGS_DIR)

@bot.group(name="setting", invoke_without_command=True)
async def setting(ctx):
    # 하위 명령이 없을 때 호출됩니다.
    await ctx.send("⚙️ 설정 조회: `!setting show`")

@setting.command(name="show")
async def setting_show(ctx):
    """
    현재 설정을 9개씩 묶어서 페이지별로 표시합니다.
    사용법: !setting show
    """
    # (1) 표시할 변수 목록 (이름, 값) 튜플로 준비
    items = [
        ("symbol",                  symbol),
        ("waiting",                 waiting),
        ("DIVIDE_VALUE",            DIVIDE_VALUE),
        ("🟩LONG_TP_PNL",           LONG_TP_PNL),
        ("🟩LONG_SL_PNL",           LONG_SL_PNL),
        ("🟩LONG_ADD_SL_PNL",       LONG_ADD_SL_PNL),
        ("🟩LONG_PARTIAL_EXIT_PNL", LONG_PARTIAL_EXIT_PNL),
        ("🟩LONG_ADD_BUY_PNL",      LONG_ADD_BUY_PNL),
        ("🟩레버리지 (long)",        long_leverage),
        ("🟥SHORT_TP_PNL",          SHORT_TP_PNL),
        ("🟥SHORT_SL_PNL",          SHORT_SL_PNL),
        ("🟥SHORT_ADD_SL_PNL",      SHORT_ADD_SL_PNL),
        ("🟥SHORT_PARTIAL_EXIT_PNL",SHORT_PARTIAL_EXIT_PNL),
        ("🟥SHORT_ADD_BUY_PNL",     SHORT_ADD_BUY_PNL),
        ("🟥레버리지 (short)",       short_leverage),
        ("CHEATKEY_THRESHOLD",      CHEATKEY_THRESHOLD),
        ("CHEATKEY_LOOKBACK",       CHEATKEY_LOOKBACK),
        ("CHEATKEY_TIMEFILTER",     CHEATKEY_TIMEFILTER),
        ("ADD_BUY_CANDLE_CONDITION",ADD_BUY_CANDLE_CONDITION),
        ("PARTIAL_EXIT_MODE",       PARTIAL_EXIT_MODE),
        ("EXIT_MODE",               EXIT_MODE),
        ("EXIT_FULL_CONDITION",     EXIT_FULL_CONDITION),
        ("FIRST_OPPOSITE_EXIT",     FIRST_OPPOSITE_EXIT),
        ("FIRST_OPPOSITE_EXIT_PNL", FIRST_OPPOSITE_EXIT_PNL),
        ("EXITMODE_TIMEFILTER",     EXITMODE_TIMEFILTER),
        ("USE_TIMEOUT_CROSS",       USE_TIMEOUT_CROSS),
        ("TIMEOUT_CROSS_BARS",      TIMEOUT_CROSS_BARS),
        ("TIMEOUT_SELL_PNL",        TIMEOUT_SELL_PNL),
        ("MACRO_EMA_FILTER",        MACRO_EMA_FILTER),
        ("MACRO_EMA_PERIOD",        MACRO_EMA_PERIOD),
        ("SLOPE_EXIT",              SLOPE_EXIT),
        ("SLOPE_EXIT_PNL_THRESHOLD",SLOPE_EXIT_PNL_THRESHOLD),
        ("SLOPE_EXIT_COOLDOWN_BARS",SLOPE_EXIT_COOLDOWN_BARS),
        ("SLOPE_EXIT_LOOKBACK",     SLOPE_EXIT_LOOKBACK)
    ]

    # (2) 9개씩 페이지 분할
    per_page = 9
    total_pages = math.ceil(len(items) / per_page)

    for page in range(total_pages):
        start = page * per_page
        chunk = items[start:start + per_page]

        embed = discord.Embed(
            title=f"Trading Bot Settings (Page {page+1}/{total_pages})",
            color=discord.Color.blue()
        )
        for name, val in chunk:
            embed.add_field(name=name, value=str(val), inline=True)

        await ctx.send(embed=embed)

@setting.command(name="list")
async def setting_list(ctx):
    """저장된 세팅 목록을 보여줍니다."""
    files = sorted(f for f in os.listdir(SETTINGS_DIR) if f.endswith(".json"))
    if not files:
        return await ctx.send("저장된 세팅이 없습니다.")
    lines = []
    for i, fname in enumerate(files, start=1):
        path = os.path.join(SETTINGS_DIR, fname)
        try:
            data = json.load(open(path, encoding="utf-8"))
            title = data.get("title", "제목 없음")
            desc  = data.get("description", "설명 없음")
        except Exception:
            title, desc = fname, "파싱 오류"
        lines.append(f"{i}. **{title}** — {desc}")
    await ctx.send("**저장된 세팅 목록:**\n" + "\n".join(lines))

@setting.command(name="apply")
async def setting_apply(ctx, idx: int):
    """저장된 세팅을 적용합니다: !setting apply <번호>"""
    files = sorted(f for f in os.listdir(SETTINGS_DIR) if f.endswith(".json"))
    if idx < 1 or idx > len(files):
        return await ctx.send("올바른 번호를 입력하세요.")
    path = os.path.join(SETTINGS_DIR, files[idx-1])
    data = json.load(open(path, encoding="utf-8"))
    vals = data.get("values", {})
    applied = []
    for k, v in vals.items():
        if k in globals():
            globals()[k] = v
            applied.append(k)
    await ctx.send(f"**{data.get('title','')}** 세팅을 적용했습니다.\n업데이트된 변수: {', '.join(applied)}")

@setting.command(name="upload")
async def setting_upload(ctx):
    """JSON 파일을 업로드하여 새로운 세팅으로 저장합니다."""
    if not ctx.message.attachments:
        return await ctx.send("세팅 JSON 파일을 첨부해주세요.")
    attachment = ctx.message.attachments[0]
    content = await attachment.read()
    try:
        data = json.loads(content)
    except Exception:
        return await ctx.send("유효한 JSON 파일이 아닙니다.")
    title = data.get("title")
    if not title:
        return await ctx.send("JSON에 `title` 필드가 필요합니다.")
    fname = f"{title}.json"
    path = os.path.join(SETTINGS_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    await ctx.send(f"세팅 **{title}** 을(를) 저장했습니다.")

@setting.command(name="format")
async def setting_format(ctx):
    """
    빈 설정 JSON 템플릿을 전송합니다.
    title, description 다음에 variable_list 순서대로 values 필드가 생성됩니다.
    """
    # 1) 기본 구조 생성
    template = {
        "title":       "세팅 제목을 입력하세요",
        "description": "세팅 설명을 입력하세요",
        "values":      {}
    }

    # 2) 변수들(variable_list) 순서대로 None 값으로 채움
    for var in variable_list:
        template["values"][var] = None

    # 3) JSON 직렬화 후 BytesIO 로 감싸기
    buf = io.BytesIO(json.dumps(template, ensure_ascii=False, indent=2).encode("utf-8"))

    # 4) 파일로 보내기
    await ctx.send(
        "아래 템플릿을 수정하신 뒤 `!setting upload` 로 업로드해 주세요.",
        file=discord.File(buf, filename="setting_template.json")
    )

@setting.command(name="edit")
async def setting_edit(ctx, idx: int):
    """저장된 세팅 파일을 전송합니다: !setting edit <번호>"""
    files = sorted(f for f in os.listdir(SETTINGS_DIR) if f.endswith(".json"))
    if idx < 1 or idx > len(files):
        return await ctx.send("올바른 번호를 입력하세요.")
    path = os.path.join(SETTINGS_DIR, files[idx-1])
    await ctx.send(f"{files[idx-1]} 파일을 전송합니다.", file=discord.File(path))

@setting.command(name="delete")
async def setting_delete(ctx, idx: int):
    """
    저장된 세팅 파일을 삭제합니다.
    사용법: !setting delete <번호>
    """
    files = sorted(f for f in os.listdir(SETTINGS_DIR) if f.endswith(".json"))
    if not files:
        return await ctx.send("저장된 세팅이 없습니다. 먼저 `!setting list` 로 확인하세요.")
    
    # 1-based 인덱스를 0-based로 변환
    if idx < 1 or idx > len(files):
        return await ctx.send(f"올바른 번호를 입력하세요: 1 ~ {len(files)}")
    
    fname = files[idx - 1]
    path = os.path.join(SETTINGS_DIR, fname)
    
    try:
        os.remove(path)
        await ctx.send(f"✅ 설정 #{idx} 파일 **{fname}** 을(를) 삭제했습니다.")
    except Exception as e:
        await ctx.send(f"❌ 파일 삭제 중 오류 발생: {e}")


@setting.command(name="vars")
async def setting_vars(ctx):
    """
    설정 가능한 모든 변수와 그 설명을 출력합니다.
    사용법: !setting vars
    """
    help_lines = [
        "**### 치트키 관련 변수**",
        f"`CHEATKEY_THRESHOLD` ({CHEATKEY_THRESHOLD}): EMA 차이 임계값. 이 값 이하로 EMA 간격이 축소될 때 진입 신호를 감지합니다.",
        f"`CHEATKEY_LOOKBACK` ({CHEATKEY_LOOKBACK}): 노이즈 필터용 과거 봉 개수. 해당 기간 내 반대 방향 교차가 없어야 진입신호로 인정합니다.",
        f"`CHEATKEY_TIMEFILTER` ({CHEATKEY_TIMEFILTER}): `True`면 0/15/30/45분에만 신호를 체크합니다.",

        "\n**### 레버리지 설정**",
        f"`long_leverage` ({long_leverage}): 롱 포지션에 사용할 레버리지 배수",
        f"`short_leverage` ({short_leverage}): 숏 포지션에 사용할 레버리지 배수",

        "\n**### TP/SL (익절·손절) 설정**",
        f"`LONG_TP_PNL` ({LONG_TP_PNL}%): 롱 포지션 익절 목표 퍼센트",
        f"`SHORT_TP_PNL` ({SHORT_TP_PNL}%): 숏 포지션 익절 목표 퍼센트",
        f"`LONG_SL_PNL` ({LONG_SL_PNL}%): 롱 포지션 손절 기준 퍼센트 (음수 입력)",
        f"`SHORT_SL_PNL` ({SHORT_SL_PNL}%): 숏 포지션 손절 기준 퍼센트 (음수 입력)",

        "\n**### 추가매수 후 손절 설정**",
        f"`LONG_ADD_SL_PNL` ({LONG_ADD_SL_PNL}): 추가매수 1/2/3차수 별 손절 퍼센트 리스트",
        f"`SHORT_ADD_SL_PNL` ({SHORT_ADD_SL_PNL}): 숏 추가매수 1/2/3차수 별 손절 퍼센트 리스트",

        "\n**### 부분익절 설정**",
        f"`LONG_PARTIAL_EXIT_PNL` ({LONG_PARTIAL_EXIT_PNL}%): 롱 추가매수 물량 부분 익절 트리거 퍼센트",
        f"`SHORT_PARTIAL_EXIT_PNL` ({SHORT_PARTIAL_EXIT_PNL}%): 숏 추가매수 물량 부분 익절 트리거 퍼센트",
        f"`PARTIAL_EXIT_MODE` ({PARTIAL_EXIT_MODE}): 부분익절 시 `all`=전체 청산, `added`=추가매수 물량만 청산, `None`=비활성",

        "\n**### 첫 추가매수 트리거 설정**",
        f"`LONG_ADD_BUY_PNL` ({LONG_ADD_BUY_PNL}%): 롱 첫 추가매수 진입 최소 PnL 트리거 (%)",
        f"`SHORT_ADD_BUY_PNL` ({SHORT_ADD_BUY_PNL}%): 숏 첫 추가매수 진입 최소 PnL 트리거 (%)",
        f"`ADD_BUY_CANDLE_CONDITION` ({ADD_BUY_CANDLE_CONDITION}): 추가매수 시 캔들 조건 사용 여부(True=양봉/음봉 확인)",

        "\n**### 분할 매수 설정**",
        f"`DIVIDE_VALUE` ({DIVIDE_VALUE}): 자산 분할 지수 (2^value 분할)",
        f"`TOTAL_PARTS` ({TOTAL_PARTS}): 분할 파트 총 개수",

        "\n**### 반대신호 매도 (ExitAdd) 설정**",
        f"`EXIT_MODE` ({EXIT_MODE}): 반대신호 발생 시 `all`=전체 청산, `added`=추가매수 물량만 청산, `None`=비활성",
        f"`EXIT_FULL_CONDITION` ({EXIT_FULL_CONDITION}): `profit_only`=수익일 때만 전량 청산, `always`=수익/손실 구분 없이 전량 청산",
        f"`FIRST_OPPOSITE_EXIT` ({FIRST_OPPOSITE_EXIT}): `True`일 때 초기매수 상태에서도 EXIT MODE 적용"
        f"`FIRST_OPPOSITE_EXIT_PNL` ({FIRST_OPPOSITE_EXIT_PNL}): FIRST_OPPOSITE_EXIT `True`일 때 pnl 임계값"
        f"`EXITMODE_TIMEFILTER` ({EXITMODE_TIMEFILTER}): EXIT MODE cheatkey TIMEFILTER 설정 true : false"
        "\n**### 타임아웃 매도 (TimeoutExit) 설정**",
        f"`USE_TIMEOUT_CROSS` ({USE_TIMEOUT_CROSS}): 타임아웃 매도 기능 사용 여부",
        f"`TIMEOUT_CROSS_BARS` ({TIMEOUT_CROSS_BARS}): 초기진입 후 교차 신호 없이 경과시킬 최대 봉 개수",
        f"`TIMEOUT_SELL_PNL` ({TIMEOUT_SELL_PNL}%): 타임아웃 시점에 PnL이 이 이상일 때만 청산",
        
        "\n**### 거시 EMA Filter (MACRO_EMA) 설정**",
        f"`MACRO_EMA_FILTER` ({MACRO_EMA_FILTER}): 거시 EMA 필터 설정 `True`면 적용",
        f"`MACRO_EMA_PERIOD` ({MACRO_EMA_PERIOD}): 거시 EMA PERIOD 설정"

        "\n**### SLOPE EXIT 모드 (SLOPE EXIT) 설정**",
        f"`SLOPE_EXIT` ({SLOPE_EXIT}): EMA 기울기 기반 탈출 모드 설정 `True`면 적용",
        f"`SLOPE_EXIT_PNL_THRESHOLD` ({SLOPE_EXIT_PNL_THRESHOLD}): SLOPE EXIT 모드 매도 pnl 임계값",
        f"`SLOPE_EXIT_COOLDOWN_BARS` ({SLOPE_EXIT_COOLDOWN_BARS}): 매수 후 SLOPE EXIT 모드 적용 안할 봉 개수 (5 : 25분)"
        f"`SLOPE_EXIT_LOOKBACK` ({SLOPE_EXIT_LOOKBACK}): SLOPE EXIT 모드에서 기울기 변화 검사할 봉 개수 (2 : 이전 봉 2개 검사)"
    ]

    # Discord 메시지 최대 길이 고려하여 1900자 단위로 분할 전송
    chunk = ""
    for line in help_lines:
        if len(chunk) + len(line) + 1 > 1900:
            await ctx.send(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await ctx.send(chunk)

@setting.command(name="help")
async def setting_help(ctx):
    """setting 그룹 명령어 사용법을 보여줍니다."""
    help_msg = (
        "**!setting 명령어 사용법**\n"
        "`!setting show`             → 현재 설정값 조회\n"
        "`!setting list`             → 저장된 세팅 목록 조회\n"
        "`!setting apply <번호>`      → 저장된 세팅 적용\n"
        "`!setting upload`           → JSON 파일 첨부하여 세팅 저장\n"
        "`!setting format`           → JSON 템플릿 전송\n"
        "`!setting edit <번호>`       → 저장된 세팅 파일 내려받기\n"
        "`!setting vars`             → 세팅 관련 변수 설명\n"
        "`!setting help`             → 이 도움말 보기\n"
        "`!setting delete <번호>`     → 세팅 지우기"
    )
    await ctx.send(help_msg)


@bot.command(name='order')  # 사용법: !order BUY 100 또는 !order SELL 50
async def ordercommand(ctx, side: str, value: float):
    global is_running, count, order, long_leverage, short_leverage, symbol # 필요한 전역 변수 유지

    side = side.upper()
    if side not in ('BUY', 'SELL'):
        return await ctx.send("잘못된 사이드입니다. `BUY` 또는 `SELL`을 입력하세요.")

    try:
        # 현재가 조회 (V5 호환 함수 사용)
        current_price = f.get_current_market_price(symbol=symbol)
        inv_amount = value  # 투입할 달러 금액

        # 주문 가격 (시장가 주문에서는 실제 사용되지 않지만 정보성 메시지용)
        if side == 'BUY':
            order_price = f.round_price(symbol, current_price * 1.001) # round_price 적용
            leverage = long_leverage
        else:  # SELL
            order_price = f.round_price(symbol, current_price * 0.999) # round_price 적용
            leverage = short_leverage

        # 주문 수량 계산 (라운딩 전)
        order_size_raw = inv_amount / current_price * leverage 

        # 실제 주문 호출 (f.place_market_order가 내부적으로 EXCHANGE에 따라 분기)
        # Bybit인 경우: API 응답 딕셔너리를 반환
        # Binance인 경우: 성공 시 결과, 오류 시 RuntimeError 발생
        order_response = f.place_market_order(
            symbol=symbol,
            quantity=order_size_raw,
            leverage=leverage,
            side=side
        )

        # --- Bybit Exchange에 특화된 오류 처리 ---
        if f.EXCHANGE == 'bybit':
            ret_code = order_response.get("retCode")
            ret_msg = order_response.get("retMsg")

            if ret_code == 0:
                # Bybit 주문 성공
                adjusted_qty_for_msg = f.round_qty(symbol, order_size_raw)
                msg = (
                    f"[명령어]{'매수' if side=='BUY' else '매도'} 주문 완료 ✅\n"
                    f"거래소: Bybit\n"
                    f"현재가격 : {current_price}\n"
                    f"주문사이드 : {side}\n"
                    f"투입금액 : {inv_amount} USDT\n"
                    f"레버리지 : {leverage}배\n"
                    f"주문 수량 : {adjusted_qty_for_msg}"
                )
                f.message(msg)
                await ctx.send(f"주문이 성공적으로 전송되었습니다!\n{msg}")

            elif ret_code == 110007:
                # Bybit 자산 부족 오류
                error_msg = (
                    f"⚠️ **Bybit 자산 부족 오류!** ⚠️\n"
                    f"주문을 체결하기 위한 계정 잔고가 부족합니다.\n"
                    f"Bybit 계정의 사용 가능한 잔고를 확인해주세요.\n"
                    f"({ret_msg})"
                )
                f.message(error_msg)
                await ctx.send(error_msg)

            elif ret_code == 110043:
                # Bybit 레버리지 미변경 (정보성) - 주문은 성공했을 가능성이 높음
                adjusted_qty_for_msg = f.round_qty(symbol, order_size_raw)
                msg = (
                    f"[명령어]{'매수' if side=='BUY' else '매도'} 주문 완료 ✅ (레버리지 변경 없음)\n"
                    f"거래소: Bybit\n"
                    f"현재가격 : {current_price}\n"
                    f"주문사이드 : {side}\n"
                    f"투입금액 : {inv_amount} USDT\n"
                    f"레버리지 : {leverage}배\n"
                    f"주문 수량 : {adjusted_qty_for_msg}"
                )
                f.message(msg)
                await ctx.send(f"주문이 성공적으로 전송되었습니다!\n{msg}")
                
            else:
                # 그 외 예상치 못한 Bybit API 오류
                error_msg = (
                    f"❌ **Bybit API 오류 발생!** ❌\n"
                    f"주문 전송 중 알 수 없는 오류가 발생했습니다.\n"
                    f"오류 코드: `{ret_code}`\n"
                    f"오류 메시지: `{ret_msg}`\n"
                    f"자세한 내용은 로그를 확인해주세요."
                )
                f.message(error_msg)
                await ctx.send(error_msg)

        # --- Binance Exchange 처리 (기존 오류 처리 방식 유지) ---
        elif f.EXCHANGE == 'binance':
            # Binance 함수는 성공 시 True/Dict, 실패 시 Exception을 발생시킨다고 가정
            # order_response 자체가 성공 결과이므로 추가적인 retCode 체크는 필요 없음.
            # 만약 Binance도 특정 응답 딕셔너리를 반환한다면 위 Bybit처럼 처리 가능
            adjusted_qty_for_msg = f.round_qty(symbol, order_size_raw) # 라운딩 함수는 공통 사용 가능
            msg = (
                f"[명령어]{'매수' if side=='BUY' else '매도'} 주문 완료 ✅\n"
                f"거래소: Binance\n"
                f"현재가격 : {current_price}\n"
                f"주문사이드 : {side}\n"
                f"투입금액 : {inv_amount} USDT\n"
                f"레버리지 : {leverage}배\n"
                f"주문 수량 : {adjusted_qty_for_msg}"
            )
            f.message(msg)
            await ctx.send(f"주문이 성공적으로 전송되었습니다!\n{msg}")

        else:
            # 예상치 못한 EXCHANGE 값
            error_msg = f"❌ **설정 오류!** ❌\n알 수 없는 거래소 설정(`EXCHANGE={f.EXCHANGE}`)입니다."
            f.message(error_msg)
            await ctx.send(error_msg)


    except ValueError as e:
        # round_qty 등에서 발생한 수량/가격 유효성 검사 오류
        error_msg = f"❗ **주문 데이터 오류:** {e}"
        f.message(error_msg)
        await ctx.send(error_msg)
    except RuntimeError as e:
        # bybit_functions.bybit_request 또는 binance_functions에서 발생한 일반적인 API 통신 오류
        error_msg = f"🔥 **API 통신 오류!** 🔥\nAPI 요청 중 문제가 발생했습니다.\n자세한 내용: `{e}`"
        f.message(error_msg)
        await ctx.send(error_msg)
    except Exception as e:
        # 예상치 못한 기타 오류
        error_msg = f"🚨 **예상치 못한 오류 발생!** 🚨\n봇 실행 중 오류가 발생했습니다.\n자세한 내용: `{e}`"
        f.message(error_msg)
        await ctx.send(error_msg)



@bot.command(name='check_order')
async def check_order(ctx):
    global order
    await ctx.send(f"order : {order}")


@bot.command(name="database")
async def database(ctx, action: str, *args):
    if action == "show":
        try:
            limit = int(args[0]) if args else None
            data = f.fetch_from_db(limit)
            if data:
                response = "\n".join([
                    f"DATE : {row[0]} | SIDE : {row[1]} | RESULT : {row[2]} | LEVERAGE : {row[3]} | REALIZED PROFIT : {row[4]} | PNL: {row[5]:.2f}% | INVEST AMOUNT : {row[6]:.2f} | COUNT : {row[7]} | MAX PNL : {row[8]:.2f} | MIN PNL : {row[9]:.2f} | HOLDING TIME : {row[10]}"
                    for row in data
                ])
            else:
                response = "데이터가 없습니다."
        except ValueError:
            response = "숫자를 입력해주세요."
        
        # 메시지가 2000자를 초과하면 분할하여 전송
        if len(response) > 2000:
            for i in range(0, len(response), 2000):
                await ctx.send(response[i:i+2000])
        else:
            await ctx.send(response)

    elif action == "all":
        data = f.fetch_from_db()
        if data:
            response = "\n".join([
                f"DATE : {row[0]} | SIDE : {row[1]} | RESULT : {row[2]} | LEVERAGE : {row[3]} | REALIZED PROFIT : {row[4]} | PNL: {row[5]:.2f}% | INVEST AMOUNT : {row[6]:.2f} | COUNT : {row[7]} | MAX PNL : {row[8]:.2f} | MIN PNL : {row[9]:.2f} | HOLDING TIME : {row[10]}"
                for row in data
            ])
        else:
            response = "데이터가 없습니다."
        
        # 메시지가 2000자를 초과하면 분할하여 전송
        if len(response) > 2000:
            for i in range(0, len(response), 2000):
                await ctx.send(response[i:i+2000])
        else:
            await ctx.send(response)

    else:
        await ctx.send("알 수 없는 명령어입니다. 사용 가능한 명령어: show, all")

@bot.command(name="save")
async def save(ctx, date: str, side: str, result: str, leverage: float, realized_profit: float, roi: float, inv_amount: float, count_value:float, max_pnl:float, min_pnl:float, time:str):
    try:
        f.save_to_db(date, side, result, leverage, realized_profit, roi, inv_amount, count_value, max_pnl, min_pnl, time)
        await ctx.send(f"데이터가 저장되었습니다.")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")

@bot.command(name='helpme')
async def helpme(ctx):

    await ctx.send('''
                   
  analyze     저장된 일정 데이터에 대해 AI 분석을 배치(10개씩)로 수행하여 각 일정의 비트코인 가격 영향 예측
  check_order order변수 상태 보기
  cheerme     랜덤으로 코인/주식 관련 명언을 보여줍니다
  close       포지션 강제청산
  credit      크레딧 보기
  database    데이터베이스 조회 ( all show )
  exportdb    데이터베이스 파일(DB 형태)을 Discord 메시지에 첨부하여 전송합니다.
  exportexcel 데이터베이스의 데이터를 엑셀 파일로 변환하여 Discord 메시지에 첨부하여 전송합니다.
  exchange    거래소를 변경합니다. (binance, bybit)
  hedge       헤지 모드를 조회하거나 토글하는 명령어.
  help        명령어 설명 
  helpme      명령어 설명
  order       사용법: !order BUY 100 또는 !order SELL 50
  profit      !profit 명령어: 지정한 기간 동안의 총 순수익, 평균 ROI, 수익 및 손실 건수와 수익 비율을 알려줍니다.
  save        데이터 저장 명령어
  schedule    일정 조회 명령어
  setting     세팅값 조회 명령어
  start       실행 명령어
  status      현재 상태 조회 명령어
  stop        일시정지 명령어
  symbol      심볼 수정 명령어
  tendency    최근 차트 보기 (5분봉)
  update      패치노트 보기
  upload      파일 업로드 명령어
  waiting     waiting변수 토글
                   
''')
    

@bot.command(name='credit')
async def credit(ctx):
    await ctx.send('''

    CHEATKEY
    ver 2.0
    latest update 2025-05-30

''')

@bot.command(name='update')
async def update(ctx):
    with open("PATCHNOTE.txt", "r",encoding="utf-8") as file:
        text = file.read()
        await ctx.send(f"```{text}```")

@bot.event
async def on_ready():
    # 로딩 애니메이션: "로딩중..." 메시지와 회전하는 화살표
    os.system("cls" if os.name == "nt" else "clear")
    spinner = ['|', '/', '-', '\\']
    print(f"{Fore.LIGHTBLACK_EX}Loading ...", end=" ", flush=True)
    for i in range(20):  # 반복 횟수를 조절하여 애니메이션 지속 시간 결정 (약 2초)
        sys.stdout.write(f"{Fore.LIGHTBLACK_EX}{spinner[i % len(spinner)]}{Style.RESET_ALL}")
        sys.stdout.flush()
        time.sleep(0.1)
        sys.stdout.write('\b')

    os.system("cls" if os.name == "nt" else "clear")

    art = f'''{Fore.LIGHTGREEN_EX}
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  .g8"""bgd `7MMF'  `7MMF'`7MM"""YMM        db   MMP""MM""YMM `7MMF' `YMM' `7MM"""YMM `YMM'   `MM'│
│.dP'     `M   MM      MM    MM    `7       ;MM:  P'   MM   `7   MM   .M'     MM    `7   VMA   ,V  │
│dM'       `   MM      MM    MM   d        ,V^MM.      MM        MM .d"       MM   d      VMA ,V   │
│MM            MMmmmmmmMM    MMmmMM       ,M  `MM      MM        MMMMM.       MMmmMM       VMMP    │
│MM.           MM      MM    MM   Y  ,    AbmmmqMA     MM        MM  VMA      MM   Y  ,     MM     │
│`Mb.     ,'   MM      MM    MM     ,M   A'     VML    MM        MM   `MM.    MM     ,M     MM     │
│  `"bmmmd'  .JMML.  .JMML..JMMmmmmMMM .AMA.   .AMMA..JMML.    .JMML.   MMb..JMMmmmmMMM   .JMML.   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
'''
    print(art)
    
    time.sleep(0.5)
    print(f"{Fore.GREEN}We have logged in as {bot.user}{Style.RESET_ALL}")

@bot.command(name="hedge")
async def hedge(ctx, mode: str = None, target: str = None):
    """
    !hedge               -> 현재 포지션 모드 조회
    !hedge on [심볼]     -> 헤지 모드 활성화
    !hedge off [심볼]    -> 원웨이 모드 활성화
    """
    # 조회
    if mode is None:
        if f.EXCHANGE == "binance":
            res = f.get_position_mode()
        else:  # bybit
            if not target:
                return await ctx.send("Bybit는 심볼이 필요합니다: `!hedge <심볼>`")
            res = f.get_position_mode(symbol=target)

        is_hedge = res.get("dualSidePosition", False) or res.get("mode", 0) == 3
        txt = "헤지 모드 (롱/숏 분리)" if is_hedge else "원웨이 모드 (롱/숏 통합)"
        return await ctx.send(f"현재 모드: **{txt}**\n(raw: {res})")

    # on/off 파싱
    m = mode.lower()
    if m not in ("on", "off"):
        return await ctx.send("사용법: `!hedge on [심볼]` 또는 `!hedge off [심볼]`")
    hedge_on = (m == "on")

    # 모드 변경
    if f.EXCHANGE == "binance":
        result = f.change_position_mode(hedge_on)
        if result.get("dualSidePosition") == hedge_on or result.get("code") in (0, 200):
            return await ctx.send(f"✅ Binance에서 {'`HEDGE MODE`' if hedge_on else '`ONEWAY MODE`'} 으로 변경되었습니다.")
        else:
            return await ctx.send(f"❌ Binance 모드 변경 실패: {result}")

    # Bybit
    if not target:
        return await ctx.send("Bybit 변경 시 심볼이 필요합니다: `!hedge on/off <심볼>`")
    result = f.change_position_mode(hedge_on, symbol=target)
    code = result.get("retCode")
    if code == 0:
        return await ctx.send(f"✅ {target}의 포지션 모드가 {'`HEDGE MODE`' if hedge_on else '`ONEWAY MODE`'} 으로 변경되었습니다.")
    elif code == 110025:
        return await ctx.send(f"ℹ️ 이미 {'`HEDGE MODE`' if hedge_on else '`ONEWAY MODE`'} 입니다.")
    else:
        return await ctx.send(f"❌ Bybit 모드 변경 실패: {result}")



@bot.command(name='status')
async def get_status(ctx):
    global is_running, long_holding, short_holding, count, order, long_leverage, short_leverage

    order = f.get_latest_order(symbol)
    order_id = order['orderId'] if order else None
    order = f.check_order_status(symbol, order_id) if order else None

    current_price_info = f.get_symbol_ticker(symbol=f"{symbol}")
    current_price = float(current_price_info['price'])

    long_position_info = f.get_futures_position_info(symbol,'long')
    short_position_info = f.get_futures_position_info(symbol,'short')

    long_unrealizedProfit = float(long_position_info['unRealizedProfit'])
    short_unrealizedProfit = float(short_position_info['unRealizedProfit'])

    long_positionAmt = float(long_position_info['positionAmt'])  # 포지션 수량
    short_positionAmt = float(short_position_info['positionAmt'])  # 포지션 수량

    long_entryprice = float(long_position_info['entryPrice'])  # 진입가격
    long_inv_amount = abs(long_positionAmt) * long_entryprice / long_leverage
    short_entryprice = float(short_position_info['entryPrice'])  # 진입가격
    short_inv_amount = abs(short_positionAmt) * short_entryprice / short_leverage

    if long_inv_amount != 0:
        long_pnl = long_unrealizedProfit / long_inv_amount * 100  # PNL
        long_status = '🟢매수중'
    else:
        long_pnl = 0
        long_status = '🔴매수대기중'
    if short_inv_amount != 0:
        short_pnl = short_unrealizedProfit / short_inv_amount * 100  # PNL
        short_status = '🟢매수중'
    else:
        short_pnl = 0
        short_status = '🔴매수대기중'

    blnc = f.get_futures_asset_balance(asset='USDT')

    embed1 = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    
    embed1.add_field(name="현재 가격", value=f"{current_price}", inline=True)
    embed1.add_field(name="잔액", value=f"{blnc} USDT", inline=True)
    embed1.add_field(name="주문 상태", value=f"{order}", inline=True)

    embed2 = discord.Embed(title="🟩LONG STATUS", color=discord.Color.blue())

    embed2.add_field(name="주문 상태", value=f"{long_status}", inline=True)
    embed2.add_field(name="LONG pnl", value=f"{long_pnl}", inline=True)
    embed2.add_field(name="💸현재 수익", value=f"{long_unrealizedProfit}", inline=True)
    embed2.add_field(name="매수 금액", value=f"{long_inv_amount}", inline=True)
    embed2.add_field(name="현재 금액", value=f"{long_inv_amount + long_unrealizedProfit}", inline=True)
    embed2.add_field(name="레버리지", value=f"{long_leverage}", inline=True)


    embed3 = discord.Embed(title="🟥SHORT STATUS", color=discord.Color.blue())

    embed3.add_field(name="주문 상태", value=f"{short_status}", inline=True)
    embed3.add_field(name="SHORT pnl", value=f"{short_pnl}", inline=True)
    embed3.add_field(name="💸현재 수익", value=f"{short_unrealizedProfit}", inline=True)
    embed3.add_field(name="매수 금액", value=f"{short_inv_amount}", inline=True)
    embed3.add_field(name="현재 금액", value=f"{short_inv_amount + short_unrealizedProfit}", inline=True)
    embed3.add_field(name="레버리지", value=f"{short_leverage}", inline=True)

    await ctx.send(embeds=[embed1, embed2, embed3])



@bot.event
async def on_message(message):
    global_vars = globals()

    if message.author.bot:
        return

    if message.content.strip() == "#set_help":
        names = "\n".join(sorted(variable_list))
        await message.channel.send(f"변경 가능한 변수:\n{names}\n\n사용법: #set <변수명> <값>")
        return

    if message.content.startswith("#set "):
        parts = message.content.split(maxsplit=2)
        if len(parts) != 3:
            return await message.channel.send("사용법: `#set <변수명> <값>`")

        _, var_name, val_str = parts
        if var_name not in variable_list:
            return await message.channel.send(
                "존재하지 않는 변수입니다. `#set_help` 로 확인하세요."
            )
        if var_name not in global_vars:
            return await message.channel.send(f"`{var_name}` 변수가 없습니다.")

        old_val = global_vars[var_name]
        try:
            # 리스트 타입 처리
            if isinstance(old_val, list):
                parsed = ast.literal_eval(val_str)
                if not isinstance(parsed, list):
                    raise ValueError("리스트 형식으로 입력하세요. 예: [1,2,3]")
                new_val = parsed

            # 불리언 타입 처리
            elif isinstance(old_val, bool):
                low = val_str.lower()
                if low in ("true", "false"):
                    new_val = (low == "true")
                else:
                    raise ValueError("불리언은 true 또는 false 로 설정해야 합니다.")

            # 정수 타입 처리
            elif isinstance(old_val, int):
                new_val = int(val_str)

            # 실수 타입 처리
            elif isinstance(old_val, float):
                new_val = float(val_str)

            # 그 외(문자열 등) 그대로
            else:
                new_val = val_str

        except Exception as e:
            return await message.channel.send(f"값 변환 오류: {e}")

        # 전역 변수에 반영
        global_vars[var_name] = new_val
        await message.channel.send(f"`{var_name}` 이(가) `{new_val}` 으로 업데이트되었습니다.")

    await bot.process_commands(message)



## 기본 전략
async def start_trading_strategy():
    global is_running, count, order, waiting, Aicommand
    global savemode, noerror
    global long_holding, short_holding

    global TOTAL_PARTS,CHEATKEY_THRESHOLD,CHEATKEY_LOOKBACK,CHEATKEY_TIMEFILTER
    global long_leverage,LONG_TP_PNL,LONG_SL_PNL,LONG_ADD_SL_PNL,LONG_PARTIAL_EXIT_PNL,LONG_ADD_BUY_PNL
    global short_leverage,SHORT_TP_PNL,SHORT_SL_PNL,SHORT_ADD_SL_PNL,SHORT_PARTIAL_EXIT_PNL,SHORT_ADD_BUY_PNL
    global DIVIDE_VALUE,ADD_BUY_CANDLE_CONDITION,PARTIAL_EXIT_MODE,EXIT_MODE,EXIT_FULL_CONDITION,USE_TIMEOUT_CROSS,TIMEOUT_CROSS_BARS,TIMEOUT_SELL_PNL
    global FIRST_OPPOSITE_EXIT, FIRST_OPPOSITE_EXIT, MACRO_EMA_FILTER, MACRO_EMA_PERIOD, EXITMODE_TIMEFILTER
    global SLOPE_EXIT, SLOPE_EXIT_COOLDOWN_BARS, SLOPE_EXIT_LOOKBACK, SLOPE_EXIT_PNL_THRESHOLD
    current_price = None
    blnc = 0
    long_inv_amount = 0
    short_inv_amount = 0
    long_unrealizedProfit = 0
    short_unrealizedProfit = 0
    long_pnl = 0
    short_pnl = 0



    long_holding = False  # 매수상태일때 True
    short_holding = False
    count = 0
    order = None
    long_max_pnl = 0
    long_min_pnl = 0
    short_max_pnl = 0
    short_min_pnl = 0

    file_path = 0
    long_savemode = False
    short_savemode = False

    long_Timeout_set = None
    short_Timeout_set = None

    long_position_list = []
    short_position_list = []
    long_buytime_list = []
    short_buytime_list = []
    long_selltime_list = []
    short_selltime_list = []
    long_pos_list = []
    short_pos_list = []


    print("Trading strategy started")
    f.message("자동매매를 시작합니다")


    while is_running:
        try:

            # 매수상태 체킹 코드

            order = f.get_latest_order(symbol)
            
            order_id = order['orderId'] if order else None
            order = f.check_order_status(symbol, order_id) if order else None

            current_price_info = f.get_symbol_ticker(symbol=f"{symbol}")
            current_price = float(current_price_info['price'])

            long_position_info = f.get_futures_position_info(symbol,'long')
            short_position_info = f.get_futures_position_info(symbol,'short')

            long_unrealizedProfit = float(long_position_info['unRealizedProfit'])
            short_unrealizedProfit = float(short_position_info['unRealizedProfit'])

            long_positionAmt = float(long_position_info['positionAmt'])  # 포지션 수량
            short_positionAmt = float(short_position_info['positionAmt'])  # 포지션 수량

            if long_position_info != 0 and float(long_position_info['positionAmt']) != 0: # 매수중
                if order is None:
                    long_holding = True
                    waiting = False
                else:
                    waiting = True
            elif float(long_position_info['positionAmt']) == 0 and order is not None: # 매수중은 아닌데 order가 None 이 아님(CANCELED or WAITING 중)
                if order and order['status'] == 'CANCELED':
                    order = None
                    waiting = False
                else:
                    waiting = True   

            else: # 매수중 아니고 order가 None임임
                long_holding = False
                order = None
                waiting = False

            if short_position_info != 0 and float(short_position_info['positionAmt']) != 0: # 매수중
                if order is None:
                    short_holding = True
                    waiting = False
                else:
                    waiting = True
            elif float(short_position_info['positionAmt']) == 0 and order is not None: # 매수중은 아닌데 order가 None 이 아님(CANCELED or WAITING 중)
                if order and order['status'] == 'CANCELED':
                    order = None
                    waiting = False
                else:
                    waiting = True   

            else: # 매수중 아니고 order가 None임임
                short_holding = False
                order = None
                waiting = False
            
            
            cancel = f.cancel_old_orders(symbol)
            if cancel == 0:
                waiting = False
            now = datetime.now()

            long_entryprice = float(long_position_info['entryPrice'])  # 진입가격
            long_inv_amount = abs(long_positionAmt) * long_entryprice / long_leverage
            short_entryprice = float(short_position_info['entryPrice'])  # 진입가격
            short_inv_amount = abs(short_positionAmt) * short_entryprice / short_leverage

            if long_inv_amount != 0:
                long_pnl = long_unrealizedProfit / long_inv_amount * 100  # PNL
            else:
                long_pnl = 0
            if short_inv_amount != 0:
                short_pnl = short_unrealizedProfit / short_inv_amount * 100  # PNL
            else:
                short_pnl = 0
            
            long_liquidation_price = long_position_info['liquidationPrice']
            short_liquidation_price = short_position_info['liquidationPrice']

            # min, max pnl 갱신 longshort
            if long_holding is True:
                if long_pnl < long_min_pnl:
                    long_min_pnl = long_pnl

                if long_pnl > long_max_pnl:
                    long_max_pnl = long_pnl
            else:
                long_buytime_list = []
                long_pos_list = []

            if short_holding is True:
                if short_pnl < short_min_pnl:
                    short_min_pnl = short_pnl

                if short_pnl > short_max_pnl:
                    short_max_pnl = short_pnl
            else:
                short_buytime_list = []
                short_pos_list = []





            blnc = f.get_futures_asset_balance(asset='USDT')


            ### 매수 로직 

            if order is None:
                current_price_info = f.get_symbol_ticker(symbol=f"{symbol}")
                current_price = float(current_price_info['price'])

                if long_holding is False and short_holding is False:
                    unit_usdt = blnc/TOTAL_PARTS # 단위 usdt 설정
                    long_Timeout_set = None
                    short_Timeout_set = None

                long_count = len(long_pos_list) if long_pos_list else 0
                short_count = len(short_pos_list) if short_pos_list else 0



                if long_holding is False:
                    if ((now.minute) % 15 == 4 or (now.minute)%15 == 5) \
                        and f.cheatkey(symbol, interval='5m', threshold=CHEATKEY_THRESHOLD, lookback_n=CHEATKEY_LOOKBACK, use_time_filter=CHEATKEY_TIMEFILTER, side='long') \
                        and (MACRO_EMA_FILTER is False or (MACRO_EMA_FILTER and current_price > get_ema_value(symbol,'5m',MACRO_EMA_PERIOD))):
                        # 롱 초기매수

                        long_qty = unit_usdt
                        order = f.execute_market_order_usdt(symbol,long_qty*0.99,long_leverage,'BUY')
                        msg_long = f'''
## 🚀 매수주문완료 #0
```
포지션 : 🟩LONG
현재가격 : {current_price}
레버리지 : {long_leverage}
매수금액 : {long_qty}
```
'''
                        msg_long_alert = f'### 🟩LONG | 매수 #0 | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매수금액 : {long_qty}'
                        f.message(msg_long)
                        f.message_alert(msg_long_alert)
                        long_buytime_list.append(now)
                        long_pos_list.append(long_qty)
                        long_Timeout_set = True

                elif long_holding is True and long_count == 1:
                    if long_pnl <= LONG_ADD_BUY_PNL and (now.minute)%5 == 0:
                        # 롱 첫 추가매수

                        long_qty = long_inv_amount
                        order = f.execute_market_order_usdt(symbol,long_qty*0.99,long_leverage,'BUY')
                        msg_long = f'''
## 🚀 매수주문완료 #{long_count}
```
포지션 : 🟩LONG
현재가격 : {current_price}
레버리지 : {long_leverage}
매수금액 : {long_qty}
```
'''
                        msg_long_alert = f'### 🟩LONG | 매수 #{long_count} | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매수금액 : {long_qty}'
                        f.message(msg_long)
                        f.message_alert(msg_long_alert)
                        long_buytime_list.append(now)
                        long_pos_list.append(long_qty)

                elif long_holding is True and long_count > 1 and long_count < 3:
                    if  (now.minute)%5 == 0 and f.emacross(symbol,side='long',use_candle_condition=ADD_BUY_CANDLE_CONDITION):
                        # 롱 추가매수

                        long_qty = long_inv_amount
                        order = f.execute_market_order_usdt(symbol,long_qty*0.99,long_leverage,'BUY')
                        msg_long = f'''
## 🚀 매수주문완료 #{long_count}
```
포지션 : 🟩LONG
현재가격 : {current_price}
레버리지 : {long_leverage}
매수금액 : {long_qty}
```
'''
                        msg_long_alert = f'### 🟩LONG | 매수 #{long_count} | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매수금액 : {long_qty}'
                        f.message(msg_long)
                        f.message_alert(msg_long_alert)
                        long_buytime_list.append(now)
                        long_pos_list.append(long_qty)


                if short_holding is False:
                    if ((now.minute) % 15 == 4 or (now.minute)%15 == 5)\
                        and f.cheatkey(symbol, interval='5m', threshold=CHEATKEY_THRESHOLD, lookback_n=CHEATKEY_LOOKBACK, use_time_filter=CHEATKEY_TIMEFILTER, side='short')\
                        and (MACRO_EMA_FILTER is False or (MACRO_EMA_FILTER and current_price < get_ema_value(symbol,'5m',MACRO_EMA_PERIOD))):
                        # 숏 초기매수

                        short_qty = unit_usdt
                        order = f.execute_market_order_usdt(symbol,short_qty*0.99,short_leverage,'SELL')
                        msg_short = f'''
## 🚀 매수주문완료 #0
```
포지션 : 🟥SHORT
현재가격 : {current_price}
레버리지 : {short_leverage}
매수금액 : {short_qty}
```
'''
                        msg_short_alert = f'### 🟥SHORT | 매수 #0 | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매수금액 : {short_qty}'
                        f.message(msg_short)
                        f.message_alert(msg_short_alert)
                        short_buytime_list.append(now)
                        short_pos_list.append(short_qty)
                        short_Timeout_set = True

                elif short_holding is True and short_count == 1:
                    if short_pnl <= SHORT_ADD_BUY_PNL and (now.minute)%5 == 0:
                        # 숏 첫 추가매수

                        short_qty = short_inv_amount
                        order = f.execute_market_order_usdt(symbol,short_qty*0.99,short_leverage,'SELL')
                        msg_short = f'''
## 🚀 매수주문완료 #{short_count}
```
포지션 : 🟥SHORT
현재가격 : {current_price}
레버리지 : {short_leverage}
매수금액 : {short_qty}
```
'''
                        msg_short_alert = f'### 🟥SHORT | 매수 #{short_count} | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매수금액 : {short_qty}'
                        f.message(msg_short)
                        f.message_alert(msg_short_alert)
                        short_buytime_list.append(now)
                        short_pos_list.append(short_qty)

                elif short_holding is True and short_count > 1 and short_count < 3:
                    if (now.minute)%5 == 0 and f.emacross(symbol,side='short',use_candle_condition=ADD_BUY_CANDLE_CONDITION):
                        # 숏 추가매수

                        short_qty = short_inv_amount
                        order = f.execute_market_order_usdt(symbol,short_qty*0.99,short_leverage,'SELL')
                        msg_short = f'''
## 🚀 매수주문완료 #{short_count}
```
포지션 : 🟥SHORT
현재가격 : {current_price}
레버리지 : {short_leverage}
매수금액 : {short_qty}
```
'''
                        msg_short_alert = f'### 🟥SHORT | 매수 #{short_count} | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매수금액 : {short_qty}'
                        f.message(msg_short)
                        f.message_alert(msg_short_alert)
                        short_buytime_list.append(now)
                        short_pos_list.append(short_qty)




            ### 매도 로직

            long_diff = now - long_buytime_list[0]
            minutes_int = float(long_diff.total_seconds() // 60)


            if order is None:
                if long_holding is True:
                    # TP Exit
                    if long_pnl >= LONG_TP_PNL:
                        order = f.close(symbol,side='long')
                        long_selltime_list.append(now)
                        long_savemode = True

                    # SL Exit
                    elif long_count == 1 and long_pnl <= LONG_SL_PNL:
                        order = f.close(symbol,side='long')
                        long_selltime_list.append(now)
                        long_savemode = True
                    
                    elif long_count > 1 and long_pnl <= LONG_ADD_SL_PNL[long_count-2]:
                        order = f.close(symbol,side='long')
                        long_selltime_list.append(now)
                        long_savemode = True

                    # Slope Exit
                    elif SLOPE_EXIT and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) and ( minutes_int > 5*SLOPE_EXIT_COOLDOWN_BARS) and ema_slope_exit(symbol,'5m',SLOPE_EXIT_LOOKBACK,'long'):
                        if  long_pnl >= SLOPE_EXIT_PNL_THRESHOLD:
                            order = f.close(symbol,side='long')
                            long_selltime_list.append(now)
                            long_savemode = True

                    # Partial Exit Add/All
                    elif long_count > 1 and long_pnl >= LONG_PARTIAL_EXIT_PNL:
                        if PARTIAL_EXIT_MODE == 'added':
                            long_qty = sum(long_pos_list[1:])
                            long_tot = sum(long_pos_list)
                            long_pct = long_qty/long_tot*100
                            order = f.close_pct(symbol,pct=long_pct,side='long')
                            long_selltime_list.append(now)
                            msg_long_alert = f'### 🟩LONG | 매도 # PARTIAL EXIT | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매도퍼센트 : {long_pct}%'
                            f.message_alert(msg_long_alert)
                            del long_pos_list[1:]
                        elif PARTIAL_EXIT_MODE == 'all':
                            order = f.close(symbol,side='long')
                            long_savemode = True

                    # Exit Add/All
                    elif ((FIRST_OPPOSITE_EXIT is False and long_count > 1 and EXIT_MODE in ('added', 'all') \
                        and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) \
                        and f.cheatkey(
                            symbol,
                            interval='5m',
                            threshold=CHEATKEY_THRESHOLD,
                            lookback_n=CHEATKEY_LOOKBACK,
                            use_time_filter=EXITMODE_TIMEFILTER,
                            side='short'
                        )) or
                    (FIRST_OPPOSITE_EXIT is True and EXIT_MODE in ('added', 'all') \
                        and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) \
                        and f.cheatkey(
                            symbol,
                            interval='5m',
                            threshold=CHEATKEY_THRESHOLD,
                            lookback_n=CHEATKEY_LOOKBACK,
                            use_time_filter=EXITMODE_TIMEFILTER,
                            side='short'
                        ))):

                        if EXIT_FULL_CONDITION == 'always':
                            if EXIT_MODE == 'added' and long_count > 1:
                                long_qty = sum(long_pos_list[1:])
                                long_tot = sum(long_pos_list)
                                long_pct = long_qty/long_tot*100
                                order = f.close_pct(symbol,pct=long_pct,side='long')
                                long_selltime_list.append(now)
                                msg_long_alert = f'### 🟩LONG | 매도 # OPPOSITE EXIT | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매도퍼센트 : {long_pct}%'
                                f.message_alert(msg_long_alert)
                                long_selltime_list.append(now)
                                del long_pos_list[1:]
                            elif EXIT_MODE == 'all' or (long_pnl > FIRST_OPPOSITE_EXIT and FIRST_OPPOSITE_EXIT is True and long_count == 1):
                                order = f.close(symbol,side='long')
                                long_savemode = True

                        elif EXIT_FULL_CONDITION == 'profit_only':
                            if long_pnl > 0:
                                if EXIT_MODE == 'added' and long_count > 1:
                                    long_qty = sum(long_pos_list[1:])
                                    long_tot = sum(long_pos_list)
                                    long_pct = long_qty/long_tot*100
                                    order = f.close_pct(symbol,pct=long_pct,side='long')
                                    long_selltime_list.append(now)
                                    msg_long_alert = f'### 🟩LONG | 매도 # OPPOSITE EXIT | 현재가격 : {current_price} | 레버리지 : {long_leverage} | 매도퍼센트 : {long_pct}%'
                                    f.message_alert(msg_long_alert)
                                    long_selltime_list.append(now)
                                    del long_pos_list[1:]
                                elif EXIT_MODE == 'all' or (long_pnl > FIRST_OPPOSITE_EXIT and FIRST_OPPOSITE_EXIT is True and long_count == 1):
                                    order = f.close(symbol,side='long')
                                    long_savemode = True

                    # Timeout Exit
                    elif USE_TIMEOUT_CROSS and long_Timeout_set is not None:
                        delta = now - long_buytime_list[0]      # datetime.timedelta
                        minutes = delta.total_seconds() / 60.0
                        if f.emacross(symbol,side='long'):
                            long_Timeout_set = None
                        elif minutes >= TIMEOUT_CROSS_BARS*5:
                            if long_pnl > TIMEOUT_SELL_PNL:
                                order = f.close(symbol,side='long')
                                long_selltime_list.append(now)
                                long_savemode = True
                                long_Timeout_set = None


            if order is None:
                if short_holding is True:
                    # TP Exit
                    if short_pnl >= SHORT_TP_PNL:
                        order = f.close(symbol, side='short')
                        short_selltime_list.append(now)
                        short_savemode = True

                    # SL Exit
                    elif short_count == 1 and short_pnl <= SHORT_SL_PNL:
                        order = f.close(symbol, side='short')
                        short_selltime_list.append(now)
                        short_savemode = True

                    elif short_count > 1 and short_pnl <= SHORT_ADD_SL_PNL[short_count-2]:
                        order = f.close(symbol, side='short')
                        short_selltime_list.append(now)
                        short_savemode = True

                    # Slope Exit
                    elif SLOPE_EXIT and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) and ( minutes_int > 5*SLOPE_EXIT_COOLDOWN_BARS) and ema_slope_exit(symbol,'5m',SLOPE_EXIT_LOOKBACK,'short'):
                        if  short_pnl >= SLOPE_EXIT_PNL_THRESHOLD:
                            order = f.close(symbol,side='short')
                            short_selltime_list.append(now)
                            short_savemode = True

                    # Partial Exit Add/All
                    elif short_count > 1 and short_pnl >= SHORT_PARTIAL_EXIT_PNL:
                        if PARTIAL_EXIT_MODE == 'added':
                            short_qty = sum(short_pos_list[1:])
                            short_tot = sum(short_pos_list)
                            short_pct = short_qty/short_tot*100
                            order = f.close_pct(symbol,pct=short_pct,side='short')
                            short_selltime_list.append(now)
                            msg_short_alert = f'### 🟥SHORT | 매도 # PARTIAL EXIT | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매도퍼센트 : {short_pct}%'
                            f.message_alert(msg_short_alert)
                            short_selltime_list.append(now)
                            del short_pos_list[1:]
                        elif PARTIAL_EXIT_MODE == 'all':
                            order = f.close(symbol, side='short')
                            short_savemode = True

                    # Exit Add/All
                    elif ((FIRST_OPPOSITE_EXIT is False and short_count > 1 and EXIT_MODE in ('added', 'all') \
                        and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) \
                        and f.cheatkey(
                            symbol,
                            interval='5m',
                            threshold=CHEATKEY_THRESHOLD,
                            lookback_n=CHEATKEY_LOOKBACK,
                            use_time_filter=EXITMODE_TIMEFILTER,
                            side='long'
                        )) or 
                    (FIRST_OPPOSITE_EXIT and EXIT_MODE in ('added', 'all') \
                        and ((now.minute) % 15 == 4 or (now.minute)%15 == 5) \
                        and f.cheatkey(
                            symbol,
                            interval='5m',
                            threshold=CHEATKEY_THRESHOLD,
                            lookback_n=CHEATKEY_LOOKBACK,
                            use_time_filter=EXITMODE_TIMEFILTER,
                            side='long'
                        ))):
                        if EXIT_FULL_CONDITION == 'always':
                            if EXIT_MODE == 'added' and short_count > 1:
                                short_qty = sum(short_pos_list[1:])
                                short_tot = sum(short_pos_list)
                                short_pct = short_qty/short_tot*100
                                order = f.close_pct(symbol,pct=short_pct,side='short')
                                short_selltime_list.append(now)
                                msg_short_alert = f'### 🟥SHORT | 매도 # OPPOSITE EXIT | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매도퍼센트 : {short_pct}%'
                                f.message_alert(msg_short_alert)
                                short_selltime_list.append(now)
                                del short_pos_list[1:]
                            elif EXIT_MODE == 'all' or (long_pnl > FIRST_OPPOSITE_EXIT and FIRST_OPPOSITE_EXIT is True and short_count == 1):
                                order = f.close(symbol, side='short')
                                short_savemode = True

                        elif EXIT_FULL_CONDITION == 'profit_only':
                            if short_pnl > 0:
                                if EXIT_MODE == 'added' and short_count > 1:
                                    short_qty = sum(short_pos_list[1:])
                                    short_tot = sum(short_pos_list)
                                    short_pct = short_qty/short_tot*100
                                    order = f.close_pct(symbol,pct=short_pct,side='short')
                                    short_selltime_list.append(now)
                                    msg_short_alert = f'### 🟥SHORT | 매도 # OPPOSITE EXIT | 현재가격 : {current_price} | 레버리지 : {short_leverage} | 매도퍼센트 : {short_pct}%'
                                    f.message_alert(msg_short_alert)
                                    short_selltime_list.append(now)
                                    del short_pos_list[1:]
                                elif EXIT_MODE == 'all' or (long_pnl > FIRST_OPPOSITE_EXIT and FIRST_OPPOSITE_EXIT is True and short_count == 1):
                                    order = f.close(symbol, side='short')
                                    short_savemode = True

                    # Timeout Exit
                    elif USE_TIMEOUT_CROSS and short_Timeout_set is not None:
                        delta = now - short_buytime_list[0]        # datetime.timedelta
                        minutes = delta.total_seconds() / 60.0
                        if f.emacross(symbol, side='short'):
                            short_Timeout_set = None
                        elif minutes >= TIMEOUT_CROSS_BARS * 5:
                            if short_pnl > TIMEOUT_SELL_PNL:
                                order = f.close(symbol, side='short')
                                short_selltime_list.append(now)
                                short_savemode = True
                                short_Timeout_set = None

    
            
                


            ########## 결과 저장하기 & 디코메세지 보내기
            if long_savemode is True:
                result = 'profit' if long_pnl >= 0 else 'loss'
                time_diff = str(now - long_buytime_list[0])
                count = len(long_buytime_list) - 1 if long_buytime_list else 0
                f.save_to_db(now, 'long', result, long_leverage, long_unrealizedProfit, long_pnl, long_inv_amount, count, long_max_pnl, long_min_pnl, time_diff)

                msg_long_alert = f'### 🟩 LONG | 매도 | 현재가격 : {current_price} | 💸 PROFIT : {long_unrealizedProfit} USDT | ROI : {long_pnl}%'
                f.message_alert(msg_long_alert)

                long_position_list = ['long',long_buytime_list,long_selltime_list]
                
                candle_count = f.required_candle_count(long_position_list,'5m')
                if candle_count >= 600:
                    candle_count /= 12
                    candle_count = int(candle_count)
                    interval = '1h'
                elif candle_count >= 300:
                    candle_count /= 3
                    candle_count = int(candle_count)
                    interval = '15m'
                else:
                    interval = '5m'

                candles = f.get_candles(symbol,interval,candle_count)

                file_path = f.create_tendency_chart(candles,long_position_list,interval)
                result_ = '🟢profit' if long_pnl > 0 else '🔴loss'
                side_ = '🟩LONG'
                msg = f'''
                # 📊 POSITION RESULT
                ```
                DATE                 :  {now}
                SIDE                 :  {side_}
                Result               :  {result_}
                Leverage             :  {long_leverage}
                Count                :  {count}
                REALIZED PROFIT      :  {long_unrealizedProfit}
                ROI                  :  {long_pnl}%
                Invest Amount        :  {long_inv_amount}
                Max Pnl              :  {long_max_pnl}%
                Min Pnl              :  {long_min_pnl}%
                Holding time         :  {time_diff}
                ```
                '''

                f.message_data(msg,file_path)

                # 초기화
                long_max_pnl = 0
                long_min_pnl = 0
                long_buytime_list = []
                long_savemode = False

            if short_savemode is True:
                result = 'profit' if short_pnl >= 0 else 'loss'
                time_diff = str(now - short_buytime_list[0])
                count = len(short_buytime_list) - 1 if short_buytime_list else 0
                f.save_to_db(now, 'short', result, short_leverage, short_unrealizedProfit, short_pnl, short_inv_amount, count, short_max_pnl, short_min_pnl, time_diff)

                msg_short_alert = f'### 🟥 SHORT | 매도 | 현재가격 : {current_price} | 💸 Profit : {short_unrealizedProfit} USDT | ROI : {short_pnl}%'
                f.message_alert(msg_short_alert)

                short_position_list = ['short',short_buytime_list,short_selltime_list]
                
                candle_count = f.required_candle_count(short_position_list,'5m')
                if candle_count >= 600:
                    candle_count /= 12
                    candle_count = int(candle_count)
                    interval = '1h'
                elif candle_count >= 300:
                    candle_count /= 3
                    candle_count = int(candle_count)
                    interval = '15m'
                else:
                    interval = '5m'

                candles = f.get_candles(symbol,interval,candle_count)

                file_path = f.create_tendency_chart(candles,short_position_list,interval)
                result_ = '🟢profit' if short_pnl > 0 else '🔴loss'
                side_ = '🟥SHORT'
                msg = f'''
                # 📊 POSITION RESULT
                ```
                DATE                 :  {now}
                SIDE                 :  {side_}
                Result               :  {result_}
                Leverage             :  {short_leverage}
                Count                :  {count}
                REALIZED PROFIT      :  {short_unrealizedProfit}
                ROI                  :  {short_pnl}%
                Invest Amount        :  {short_inv_amount}
                Max Pnl              :  {short_max_pnl}%
                Min Pnl              :  {short_min_pnl}%
                Holding time         :  {time_diff}
                ```
                '''

                f.message_data(msg,file_path)

                # 초기화
                short_max_pnl = 0
                short_min_pnl = 0
                short_buytime_list = []
                short_savemode = False

                


                        

            now = datetime.now()
            if now.minute == 10:  # 정시(00분)인지 확인
                if long_holding is False:
                    long_status = '🔴매수 대기중'
                else:
                    long_status = '🟢매수중'
                if short_holding is False:
                    short_status = '🔴매수 대기중'
                else:
                    short_status = '🟢매수중'
                blnc = f.get_futures_asset_balance(asset="USDT")
                long_count = len(long_pos_list) if long_pos_list else 0
                short_count = len(short_pos_list) if short_pos_list else 0




                msg = f'''
# 🪙 STATUS
```
현재 가격 : {current_price}
잔액 : {blnc}
주문 상태 : {order}
거래소 : {f.EXCHANGE}

# 🟩LONG 
LONG 상태 : {long_status}
LONG pnl : {long_pnl}
현재 수익 : {long_unrealizedProfit}
매수금액 : {long_inv_amount}
현재금액 : {long_inv_amount + long_unrealizedProfit}
레버리지 : {long_leverage}
Count : {long_count}

# 🟥SHORT
SHORT 상태 : {short_status}
SHORT pnl : {short_pnl}
현재 수익 : {short_unrealizedProfit}
매수금액 : {short_inv_amount}
현재금액 : {short_inv_amount + short_unrealizedProfit}
레버리지 : {short_leverage}
Count : {short_count}
```
                '''
                f.message(msg)
                await asyncio.sleep(60)

            await asyncio.sleep(10)
            noerror = 0
        except Exception as e:
            error_log = f"""
            오류 발생: {e}
            위치: {traceback.format_exc()}
            현재 상태:
            current_price: {current_price}
            """
            noerror += 1
            if noerror == 10:
                is_running = False
                f.message("## 오류 반복으로 인해 자동매매가 중단되었습니다🥹")
                print(error_log)
            f.message(error_log)
