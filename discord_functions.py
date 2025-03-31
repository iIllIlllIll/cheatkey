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
import json
import sys
from functions import *
import re

# 초기설정
symbol = "XRPUSDT"
sell_price = 0  # 마지막 판매 가격

date_diff_setting = 3

count = 0


long_target_pnl = 10
long_stoploss_pnl = 10
long_pullback_pnl = 3
long_leverage = 5
long_pct = 50
long_holding = False

short_target_pnl = 20
short_stoploss_pnl = 10
short_pullback_pnl = 5
short_leverage = 10
short_pct = 50
short_holding = False

cheat_value = 0

variable_list = {
    "long_target_pnl",
    "long_stoploss_pnl",
    "long_pullback_pnl",
    "long_leverage",
    "long_pct",
    "short_target_pnl",
    "short_stoploss_pnl",
    "short_pullback_pnl",
    "short_leverage",
    "short_pct",
    "cheat_value"
}

# 전략 실행 상태
is_running = False
waiting = False
Aicommand = False  




# 최고 수익률 기록
long_max_pnl = 0
long_min_pnl = 0
short_max_pnl = 0
short_max_pnl = 0



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
        await ctx.send("데이터베이스 파일을 전송합니다.", file=discord.File(DB_PATH))
    except Exception as e:
        await ctx.send(f"데이터베이스 전송 실패: {e}")

@bot.command(name="exportexcel")
async def exportexcel(ctx):
    """
    데이터베이스의 데이터를 엑셀 파일로 변환하여 Discord 메시지에 첨부하여 전송합니다.
    """
    try:
        # DB 연결 및 데이터 읽기
        conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
        response = geminaiclient.models.generate_content(
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


@bot.command(name='tendency')
async def tendency(ctx):
    candles = get_candles(symbol,interval='5m',candle_count=100)  # 필요한 경우 조정 가능
    file_path = create_tendency_chart(candles)
    
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
async def close_positions(ctx):
    global savemode
    await ctx.send("정말 하시겠습니까? [Y/n]")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['y', 'n']

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content.lower() == 'y':
            global is_running
            is_running = False
            close(symbol)
            savemode = True
            await ctx.send(f"{symbol} 포지션이 모두 청산되었습니다.")
        else:
            await ctx.send("포지션 청산이 취소되었습니다.")
    except asyncio.TimeoutError:
        await ctx.send("시간 초과로 포지션 청산이 취소되었습니다.")


@bot.command(name='symbol')
async def set_symbol(ctx, value: str):
    global symbol, cheat_value
    try:
        # Binance 선물 심볼 정보 가져오기
        exchange_info = client.futures_exchange_info()
        # 대소문자 구분 없이 비교하기 위해 입력 값을 대문자로 변환
        value = value.upper()
        sym_info = next((s for s in exchange_info['symbols'] if s['symbol'] == value), None)
        if not sym_info:
            await ctx.send(f"심볼 **{value}**은(는) Binance 선물에 존재하지 않습니다. 기존 심볼 **{symbol}**은 변경되지 않습니다.")
            return
        
        # 심볼 업데이트
        symbol = sym_info['symbol']
        # 심볼 정보 예시 (필요에 따라 더 추가 가능)
        info_str = (
            f"**Symbol 정보**\n"
            f"심볼: **{sym_info['symbol']}**\n"
            f"Base Asset: **{sym_info.get('baseAsset', 'N/A')}**\n"
            f"Quote Asset: **{sym_info.get('quoteAsset', 'N/A')}**\n"
            f"Price Precision: **{sym_info.get('pricePrecision', 'N/A')}**"
        )
        await ctx.send(f"심볼이 **{symbol}**(으)로 설정되었습니다.\n{info_str}")
        cheat_value = cheatkey_value(symbol)
        await ctx.send(f"cheatkey value 설정 완료.\n")
    except Exception as e:
        await ctx.send(f"심볼 설정 중 오류 발생: {e}")


@bot.command(name='waiting')
async def wait_(ctx):
    global waiting
    if waiting == False:
        waiting = True
    else:
        waiting = False
    await ctx.send(f"waiting가 {waiting}로 설정되었습니다")

@bot.command(name='cheat_value')
async def cheat_value_(ctx):
    global cheat_value, symbol
    await ctx.send(f"잠시만 기다려주세요")
    cheat_value = cheatkey_value(symbol)
    await ctx.send(f"cheat_value {cheat_value}로 설정되었습니다")

@bot.command(name='setting')
async def setting(ctx):
    global waiting, symbol
    global long_target_pnl, long_stoploss_pnl, long_pullback_pnl, long_leverage, long_pct
    global short_target_pnl, short_stoploss_pnl, short_pullback_pnl, short_leverage, short_pct

    embed = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    embed.add_field(name="symbol", value=f"{symbol}", inline=True)
    embed.add_field(name="waiting", value=f"{waiting}", inline=True)
    embed.add_field(name="", value=f"", inline=True)
    embed.add_field(name="🟩target_pnl", value=f"{long_target_pnl}", inline=True)
    embed.add_field(name="🟩stoploss_pnl", value=f"{long_stoploss_pnl}", inline=True)
    embed.add_field(name="🟩pullback_pnl", value=f"{long_pullback_pnl}", inline=True)
    embed.add_field(name="🟩초기 투자비용 비율", value=f"{long_pct}", inline=True)
    embed.add_field(name="🟩레버리지", value=f"{long_leverage}", inline=True)
    embed.add_field(name="", value=f"", inline=True)
    embed.add_field(name="🟥target_pnl", value=f"{short_target_pnl}", inline=True)
    embed.add_field(name="🟥stoploss_pnl", value=f"{short_stoploss_pnl}", inline=True)
    embed.add_field(name="🟥pullback_pnl", value=f"{short_pullback_pnl}", inline=True)
    embed.add_field(name="🟥초기 투자비용 비율", value=f"{short_pct}", inline=True)
    embed.add_field(name="🟥레버리지", value=f"{short_leverage}", inline=True)
    embed.add_field(name="", value=f"", inline=True)
    

    await ctx.send(embed=embed)

@bot.command(name='buy') # 현재가격으로 구매 : !buy 구매수량(달러)
async def buycommand(ctx,value: float):
    global is_running, sell_price, sell_date, count, order, long_leverage
    
    current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
    current_price = float(current_price_info['price'])
    inv_amount = value  # 투입할 금액

    order_price = round(current_price*1.001, 1)
    inv_size = round(inv_amount / current_price * long_leverage, 3)
    order = place_limit_order(symbol, order_price,quantity=inv_size, leverage=long_leverage,side='BUY')
    message(f"[명령어]매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}\n레버리지 : {long_leverage}")
    await ctx.send(f"주문완료")


@bot.command(name='check_order')
async def check_order(ctx):
    global order
    await ctx.send(f"order : {order}")


@bot.command(name="database")
async def database(ctx, action: str, *args):
    if action == "show":
        try:
            limit = int(args[0]) if args else None
            data = fetch_from_db(limit)
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
        data = fetch_from_db()
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

    elif action == "clear":
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS data")
        conn.commit()
        conn.close()
        init_db()
        await ctx.send("데이터베이스가 초기화되었습니다.")

    else:
        await ctx.send("알 수 없는 명령어입니다. 사용 가능한 명령어: show, all, clear")

@bot.command(name="save")
async def save(ctx, date: str, side: str, result: str, leverage: float, realized_profit: float, roi: float, inv_amount: float, count_value:float, max_pnl:float, min_pnl:float, time:str):
    try:
        save_to_db(date, side, result, leverage, realized_profit, roi, inv_amount, count_value, max_pnl, min_pnl, time)
        await ctx.send(f"데이터가 저장되었습니다.")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")

@bot.command(name='helpme')
async def helpme(ctx):

    await ctx.send('''
                   
  analyze     저장된 일정 데이터에 대해 AI 분석을 배치(10개씩)로 수행하여 각 일정의 비트코인 가격 영향 예측 결과를 새로...
  buy         현재가로 롱포지션 구매
  cheat_value cheat_value 변수 새로고침
  check_order order변수 보기
  cheerme     랜덤으로 코인/주식 관련 명언을 보여줍니다.
  close       포지션 강제청산
  credit      크레딧 보기
  database    데이터베이스 조회 ( all show clear )
  exportdb    데이터베이스 파일(DB 형태)을 Discord 메시지에 첨부하여 전송합니다.
  exportexcel 데이터베이스의 데이터를 엑셀 파일로 변환하여 Discord 메시지에 첨부하여 전송합니다.
  hedge       Binance Futures의 헤지 모드를 조회하거나 토글하는 명령어.
  help        명령어 설명 
  helpme      명령어 설명
  profit      !profit 명령어: 지정한 기간 동안의 총 순수익, 평균 ROI, 수익 및 손실 건수와 수익 비율을 알려줍니다.
  save        데이터 저장 명령어어
  schedule    일정 조회 명령어.
  setting     세팅값 조회 명령어
  start       실행 명령어
  status      현재 상태 조회 명령어
  stop        일시정지 명령어
  symbol      심볼 수정 명령어
  tendency    최근 차트 보기(5분봉)
  update      패치노트 보기
  upload      파일 업로드 명령어.
  waiting     waiting변수 토글
                   
''')
    

@bot.command(name='credit')
async def credit(ctx):
    await ctx.send('''

    CHEATKEY
    ver 1.1
    latest update 2025-03-29

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

@bot.command()
async def hedge(ctx, mode: str = None):
    """
    Binance Futures의 헤지 모드를 조회하거나 토글하는 명령어.
    
    사용법:
      !hedge           -> 현재 포지션 모드를 조회합니다.
      !hedge on        -> 헤지 모드 활성화 (롱/숏 포지션 별도 관리)
      !hedge off       -> 원웨이 모드 활성화 (포지션 통합 관리)
    """
    # 인자가 없으면 현재 모드 조회
    if mode is None:
        result = get_position_mode()
        if result.get("msg") == "success" or result.get("code") == 200:
            if result.get("dualSidePosition") is True:
                await ctx.send("현재 모드: 헤지 모드 (롱/숏 포지션 별도 관리)")
            else:
                await ctx.send("현재 모드: 원웨이 모드 (포지션 통합 관리)")
        else:
            await ctx.send(f"포지션 모드 조회 실패: {result}")
        return

    # 인자가 있는 경우, on/off 토글 실행
    mode = mode.lower()
    if mode not in ["on", "off"]:
        await ctx.send("사용법: !hedge on / !hedge off")
        return

    dual = True if mode == "on" else False
    result = change_position_mode(dual)
    
    # 성공 응답 체크: Binance API는 {'code': 200, 'msg': 'success'}를 반환할 수 있음.
    if result.get("msg") == "success" or result.get("code") == 200:
        mode_str = "헤지 모드" if dual else "원웨이 모드"
        await ctx.send(f"{mode_str}로 설정되었습니다. 응답: {result}")
    else:
        await ctx.send(f"헤지 모드 토글 실패: {result}")

@bot.command(name='status')
async def get_status(ctx):
    global is_running, long_holding, short_holding, count, order, long_leverage, short_leverage

    order = get_latest_order(symbol)
    order_id = order['orderId']
    order = check_order_status(symbol, order_id)

    current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
    current_price = float(current_price_info['price'])

    long_position_info = get_futures_position_info(symbol,'long')
    short_position_info = get_futures_position_info(symbol,'short')

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

    blnc = get_futures_asset_balance()

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
    global long_target_pnl, long_stoploss_pnl, long_pullback_pnl, long_leverage, long_pct
    global short_target_pnl, short_stoploss_pnl, short_pullback_pnl, short_leverage, short_pct, cheat_value

    if message.author.bot:
        return

    # set_help 명령어: 변경 가능한 변수 목록 보여주기
    if message.content.strip() == "set_help":
        var_names = "\n".join(sorted(variable_list))
        help_msg = f"변경 가능한 변수 목록:\n{var_names}\n\n사용법: set_<변수명> <값>"
        await message.channel.send(help_msg)
        return

    # set_ 명령어 처리 (예: set_long_target_pnl 15)
    if message.content.startswith("set_"):
        try:
            parts = message.content.split()
            if len(parts) != 2:
                await message.channel.send("사용법: set_{변수명} <값>")
                return

            command = parts[0]  # 예: set_long_target_pnl
            value = int(parts[1])
            var_name = command[4:]  # 'set_' 제거 → 예: long_target_pnl

            if var_name not in variable_list:
                await message.channel.send("존재하지 않는 변수입니다. 'set_help'로 사용 가능한 변수명을 확인하세요.")
                return

            # 변수 업데이트
            if var_name == "long_target_pnl":
                long_target_pnl = value
            elif var_name == "long_stoploss_pnl":
                long_stoploss_pnl = value
            elif var_name == "long_pullback_pnl":
                long_pullback_pnl = value
            elif var_name == "long_leverage":
                long_leverage = value
            elif var_name == "long_pct":
                long_pct = value
            elif var_name == "short_target_pnl":
                short_target_pnl = value
            elif var_name == "short_stoploss_pnl":
                short_stoploss_pnl = value
            elif var_name == "short_pullback_pnl":
                short_pullback_pnl = value
            elif var_name == "short_leverage":
                short_leverage = value
            elif var_name == "short_pct":
                short_pct = value
            elif var_name == "cheatkey_value":
                cheat_value = value

            await message.channel.send(f"{var_name}가 {value}로 업데이트되었습니다.")
        except Exception as e:
            await message.channel.send("명령어 사용에 오류가 있습니다. 올바른 형식: set_{변수명} <값>")
    await bot.process_commands(message)



## 기본 전략
async def start_trading_strategy():
    global is_running, sell_price, sell_date, count, order, waiting, Aicommand
    global loss_amount, savemode
    global long_target_pnl, long_stoploss_pnl, long_pullback_pnl, long_leverage, long_pct, long_holding
    global short_target_pnl, short_stoploss_pnl, short_pullback_pnl, short_leverage, short_pct, short_holding, cheat_value

    sell_date = datetime.today()
    sell_price = 0
    last_buy_date = datetime.today()
    
    current_price = None
    blnc = 0
    long_inv_amount = 0
    short_inv_amount = 0
    long_unrealizedProfit = 0
    short_unrealizedProfit = 0
    long_pnl = 0
    short_pnl = 0

    loss_amount = 0


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



    long_position_list = []
    short_position_list = []
    long_buytime_list = []
    short_buytime_list = []


    print("Trading strategy started")
    message("자동매매를 시작합니다")


    while is_running:
        try:

            # 매수상태 체킹 코드

            order = get_latest_order(symbol)
            order_id = order['orderId']
            order = check_order_status(symbol, order_id)

            current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
            current_price = float(current_price_info['price'])

            long_position_info = get_futures_position_info(symbol,'long')
            short_position_info = get_futures_position_info(symbol,'short')

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
                long_buytime_list = []
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
                short_buytime_list = []
                order = None
                waiting = False
            
            
            cancel_old_orders(client, symbol)
            now = datetime.now()
            if now.day == 1 and now.hour == 0 and now.minute == 0:
                cheat_value = cheatkey_value(symbol)

                

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

            blnc = get_futures_asset_balance()


            ###매수알고리즘

            if order is None:
                current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
                current_price = float(current_price_info['price'])
                if long_holding is False:
                    if cheatkey(symbol, ema12_period=12, ema26_period=26, interval='15m', threshold=cheat_value, side='long') is True:
                        if short_holding is False:
                            long_percentage = long_pct # %
                        else:
                            long_percentage = 100*long_pct/(100-long_pct) # %
                        iquantity = calculate_order_quantity(long_percentage)
                        order = execute_market_order(symbol,long_percentage*0.99,long_leverage,'BUY')
                        msg_long = f'''
## 🚀 매수주문완료
```
포지션 : 🟩LONG
현재가격 : {current_price}
레버리지 : {short_leverage}
매수금액 : {iquantity}
```
'''
                        message(msg_long)
                        long_buytime_list.append(now)

                if short_holding is False:
                    if cheatkey(symbol, ema12_period=12, ema26_period=26, interval='15m', threshold=cheat_value, side='short') is True:
                        if long_holding is False:
                            short_percentage = short_pct # %
                        else:
                            short_percentage = 100*short_pct/(100-short_pct) # %
                        iquantity = calculate_order_quantity(short_percentage)
                        order = execute_market_order(symbol,short_percentage*0.99,short_leverage,'SELL')
                        msg_short = f'''
## 🚀 매수주문완료
```
포지션 : 🟥SHORT
현재가격 : {current_price}
레버리지 : {short_leverage}
매수금액 : {iquantity}
```
'''
                        message(msg_short)
                        short_buytime_list.append(now)
            
            # min, max pnl 갱신 longshort
            if long_holding is True:
                if long_pnl < long_min_pnl:
                    long_min_pnl = long_pnl

                if long_pnl > long_max_pnl:
                    long_max_pnl = long_pnl

                if long_buytime_list:
                    time_diff = now - long_buytime_list[0]
                else:
                    long_buytime_list.append(now)
                    time_diff = now - long_buytime_list[0]
            if short_holding is True:
                if short_pnl < short_min_pnl:
                    short_min_pnl = short_pnl

                if short_pnl > short_max_pnl:
                    short_max_pnl = short_pnl

                if short_buytime_list:
                    long_time_diff = now - short_buytime_list[0]
                else:
                    short_buytime_list.append(now)
                    short_time_diff = now - short_buytime_list[0]


            if order is None:
                if long_holding is True:
                    # 익절
                    if long_pnl >= long_target_pnl:
                        order = close(symbol,side='long')
                        long_savemode = True
                    if long_pnl >= long_pullback_pnl and long_max_pnl >= long_pullback_pnl+2 and (long_time_diff.total_seconds()/60) >= 15:
                        order = close(symbol,side='long')
                        long_savemode = True
                    # 손절
                    if long_pnl <= -long_stoploss_pnl:
                        order = close(symbol,side='long')
                        long_savemode = True

                elif short_holding is True:
                    # 익절
                    if short_pnl >= short_target_pnl:
                        order = close(symbol,side='short')
                        short_savemode = True
                    if short_pnl >= short_pullback_pnl and short_max_pnl >= short_pullback_pnl+2 and (short_time_diff.total_seconds()/60) >= 15:
                        order = close(symbol,side='short')
                        short_savemode = True
                    # 손절
                    if short_pnl <= -short_stoploss_pnl:
                        order = close(symbol,side='short')
                        short_savemode = True

            
                


            ########## 결과 저장하기 & 디코메세지 보내기
            if long_savemode is True:
                result = 'profit' if long_pnl >= 0 else 'loss'
                time_diff = str(now - long_buytime_list[0])
                count = 0
                save_to_db(now, 'long', result, long_leverage, long_unrealizedProfit, long_pnl, long_inv_amount, count, long_max_pnl, long_min_pnl, time_diff)

                long_position_list = ['long',long_buytime_list,now]
                
                candle_count = required_candle_count(long_position_list,'5m')
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

                candles = get_candles(symbol,interval,candle_count)

                file_path = create_tendency_chart(candles,long_position_list,interval)
                result_ = '🟢profit' if long_pnl > 0 else '🔴loss'
                side_ = '🟩LONG'
                msg = f'''
                # 📊 POSITION RESULT
                ```
                DATE                 :  {now}
                SIDE                 :  {side_}
                Result               :  {result_}
                Leverage             :  {long_leverage}
                REALIZED PROFIT      :  {long_unrealizedProfit}
                ROI                  :  {long_pnl}%
                Invest Amount        :  {long_inv_amount}
                Max Pnl              :  {long_max_pnl}%
                Min Pnl              :  {long_min_pnl}%
                Holding time         :  {time_diff}
                ```
                '''

                message_data(msg,file_path)

                # 초기화
                long_max_pnl = 0
                long_min_pnl = 0
                long_buytime_list = []
                long_savemode = False

            if short_savemode is True:
                result = 'profit' if short_pnl >= 0 else 'loss'
                time_diff = str(now - short_buytime_list[0])
                count = 0
                save_to_db(now, 'short', result, short_leverage, short_unrealizedProfit, short_pnl, short_inv_amount, count, short_max_pnl, short_min_pnl, time_diff)

                short_position_list = ['short',short_buytime_list,now]
                
                candle_count = required_candle_count(short_position_list,'5m')
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

                candles = get_candles(symbol,interval,candle_count)

                file_path = create_tendency_chart(candles,short_position_list,interval)
                result_ = '🟢profit' if short_pnl > 0 else '🔴loss'
                side_ = '🟥SHORT'
                msg = f'''
                # 📊 POSITION RESULT
                ```
                DATE                 :  {now}
                SIDE                 :  {side_}
                Result               :  {result_}
                Leverage             :  {short_leverage}
                REALIZED PROFIT      :  {short_unrealizedProfit}
                ROI                  :  {short_pnl}%
                Invest Amount        :  {short_inv_amount}
                Max Pnl              :  {short_max_pnl}%
                Min Pnl              :  {short_min_pnl}%
                Holding time         :  {time_diff}
                ```
                '''

                message_data(msg,file_path)

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
                blnc = get_futures_asset_balance()




                msg = f'''
# 🪙 STATUS
```
현재 가격 : {current_price}
잔액 : {blnc}
주문 상태 : {order}

# 🟩LONG 
LONG 상태 : {long_status}
LONG pnl : {long_pnl}
현재 수익 : {long_unrealizedProfit}
매수금액 : {long_inv_amount}
현재금액 : {long_inv_amount + long_unrealizedProfit}
레버리지 : {long_leverage}

# 🟥SHORT
SHORT 상태 : {short_status}
SHORT pnl : {short_pnl}
현재 수익 : {short_unrealizedProfit}
매수금액 : {short_inv_amount}
현재금액 : {short_inv_amount + short_unrealizedProfit}
레버리지 : {short_leverage}
```
                '''
                message(msg)
                await asyncio.sleep(60)

            await asyncio.sleep(10)
            noerror = 0
        except Exception as e:
            error_log = f"""
            오류 발생: {e}
            위치: {traceback.format_exc()}
            현재 상태:
            current_price: {current_price}
            sell_price: {sell_price}
            """
            noerror += 1
            if noerror == 10:
                is_running = False
                message("오류 반복으로 인해 자동매매가 중단되었습니다")
            message(error_log)
