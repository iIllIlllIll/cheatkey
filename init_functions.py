import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
from binance.client import Client
from binance.enums import *
import matplotlib
matplotlib.use('Agg')  # 서버 환경에서 GUI 없이 사용
import sqlite3
import mplfinance as mpf
import pandas as pd
import tempfile
import os
import base64
import json
from openai import OpenAI
import numpy as np
from google import genai
import math
import colorama
from colorama import Fore, Style
from bs4 import BeautifulSoup

from decimal import Decimal, ROUND_DOWN

key_file_path = "keys.json"


CHEATKEY_THRESHOLD = 0.001
CHEATKEY_LOOKBACK = 6
CHEATKEY_TIMEFILTER = True



# JSON 파일 읽기
with open(key_file_path, "r") as file:
    data = json.load(file)

# Intents 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='#', intents=intents)

# 변수에 접근
api_key = data["api_key"]
api_secret = data["api_secret"]
openai_api_key = data['openai_api_key']
TOKEN = data['TOKEN']
webhook_url = data['webhook_url']
webhook_url_alert = data['webhook_url_alert']
webhook_url_data = data['webhook_url_data']
bybit_api_key    = data['bybit_api_key']
bybit_api_secret = data['bybit_api_secret']

GEMINI_API_KEY = data["GEMINI_API_KEY"]

# Gemini API 설정
geminaiclient = genai.Client(api_key=GEMINI_API_KEY)

client = Client(api_key, api_secret)
openaiclient = OpenAI(api_key=openai_api_key)

FOUR_H_BB_WIDTH_THRESHOLD = 0.6
USE_ATR_PERCENT = True
ATR_PERIODS = 22
BB_PERIODS = 20
BB_STDDEV = 2.0

def bb_4h_condition(
    symbol: str,
    threshold: float = FOUR_H_BB_WIDTH_THRESHOLD,
    use_atr_percent: bool = USE_ATR_PERCENT,
    atr_periods: int = ATR_PERIODS,
    bb_periods: int = BB_PERIODS,
    bb_stddev: float = BB_STDDEV
) -> bool:
    """
    Returns True if the most recently completed 4-hour bar's Bollinger Band width
    is below `threshold`. It always takes the 2nd-last bar (iloc[-2]) as the completed bar.
    """
    # 필요한 바 개수: ATR용 + BB용 + 여유
    needed = atr_periods + bb_periods + 2

    # 1) 4시간봉 klines 가져오기
    klines = client.futures_klines(
        symbol=symbol,
        interval='4h',
        limit=needed
    )
    df4 = pd.DataFrame(klines, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_av","trade_count",
        "tb_base_av","tb_quote_av","ignore"
    ])
    # 2) 타입 변환
    df4[["open","high","low","close","volume"]] = \
        df4[["open","high","low","close","volume"]].astype(float)

    # 3) True Range & ATR
    tr1 = df4["high"] - df4["low"]
    tr2 = (df4["high"] - df4["close"].shift()).abs()
    tr3 = (df4["low"]  - df4["close"].shift()).abs()
    df4["tr"]  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df4["atr"] = df4["tr"].rolling(window=atr_periods).mean()

    # 4) ATR% or ATR 값 결정
    df4["value"] = (df4["atr"] / df4["close"] * 100) if use_atr_percent else df4["atr"]

    # 5) Bollinger Bands on 'value'
    df4["bb_mid"]   = df4["value"].rolling(window=bb_periods).mean()
    df4["bb_std"]   = df4["value"].rolling(window=bb_periods).std()
    df4["bb_upper"] = df4["bb_mid"] + bb_stddev * df4["bb_std"]
    df4["bb_lower"] = df4["bb_mid"] - bb_stddev * df4["bb_std"]
    df4["bb_width"] = df4["bb_upper"] - df4["bb_lower"]

    # 6) 데이터 충분 여부 확인
    if len(df4) < needed:
        return False

    # 7) 바로 이전(완결된) 바의 BB Width 가져오기
    bbw = df4.iloc[-2]["bb_width"]

    return bbw < threshold


def candle_condition(
    symbol: str,
    interval: str,
    side: str
) -> bool:
    """
    Returns True if the most recently completed bar (previous bar) at the given
    symbol and interval matches the side:
      - side == "long": previous bar is bullish (close > open)
      - side == "short": previous bar is bearish (close < open)
    """
    # 2개 바를 가져와서, 마지막이 미완결 바, 그 앞이 완결 바가 됩니다.
    klines = client.futures_klines(
        symbol=symbol,
        interval=interval,
        limit=2
    )
    df = pd.DataFrame(klines, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_av","trade_count",
        "tb_base_av","tb_quote_av","ignore"
    ])
    # open/close를 float로 변환
    df[["open","close"]] = df[["open","close"]].astype(float)

    # 완결된 바로 이전 바
    prev = df.iloc[-2]
    o, c = prev["open"], prev["close"]

    side = side.lower()
    if side == "long":
        return c > o
    elif side == "short":
        return c < o
    else:
        raise ValueError("side must be 'long' or 'short'")



def ema_slope_exit(
    symbol: str,
    interval: str,
    lookback: int,
    side: str
) -> bool:
    """
    5분 단위로 호출해도 항상 '완전히 종료된' 막대만 검사하도록 고친 EMA slope exit.
    """
    if side not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short'")

    # lookback+2봉 이상 가져와야 마지막 1개는 미완료 봉으로 남고,
    # 그 앞의 lookback+1개를 완전 봉 검사에 쓸 수 있음
    period = max(26, lookback + 2)
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=period)
    df = pd.DataFrame(klines, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','number_of_trades',
        'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()

    # 마지막 완전 종료된 봉 인덱스
    end = len(df) - 2
    if end - lookback < 0:
        return False

    sign = -1 if side == "long" else 1
    # lookback 개수만큼 slope 체크 (완전 봉들만)
    for j in range(lookback):
        curr12 = df['ema12'].iloc[end - j]
        prev12 = df['ema12'].iloc[end - j - 1]
        curr26 = df['ema26'].iloc[end - j]
        prev26 = df['ema26'].iloc[end - j - 1]
        if sign * (curr12 - prev12) <= 0 or sign * (curr26 - prev26) <= 0:
            return False

    return True


def get_ema_value(symbol: str, interval: str, period: int) -> float:
    """
    Fetch the last `period` futures klines and calculate a single EMA for the given period.

    Args:
        client: 바이낸스/Bybit API client 인스턴스.
        symbol: 거래 심볼 (예: "XRPUSDT").
        interval: 캔들 간격 (예: "5m").
        period: EMA 기간 (예: 12).

    Returns:
        latest_ema: 가장 최근 EMA 값 (float).
    """
    # Use `period` as the kline limit
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)
    df = pd.DataFrame(klines, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','number_of_trades',
        'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
    ])

    # Ensure close prices are floats
    df['close'] = df['close'].astype(float)

    # Calculate EMA using period as span
    ema_series = df['close'].ewm(span=period, adjust=False).mean()

    # Return the most recent EMA value
    return float(ema_series.iloc[-1])

def macro_ema(
    symbol: str,
    interval: str,
    period: int,
    side: str = "long"
) -> bool:
    """
    Check whether the close price of the previous fully-closed quarter-hour bar
    (00, 15, 30, 45 minutes) is above (long) or below (short) its EMA.

    Returns True if:
      - side == "long"  and bar_close > bar_ema
      - side == "short" and bar_close < bar_ema
    Otherwise returns False.
    """
    # fetch enough bars to compute EMA and get the previous completed bar
    klines = client.futures_klines(
        symbol=symbol,
        interval=interval,
        limit=period * 5
    )
    df = pd.DataFrame(klines, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','number_of_trades',
        'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
    ])
    # convert types
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close'] = df['close'].astype(float)

    # compute EMA series
    ema_series = (
        df['close']
        .ewm(span=period, adjust=False)
        .mean()
        .round(4)
    )
    

    # only proceed if it's one of the quarter-hour bars


    prev_bar    = df.iloc[-2]
    prev_minute = prev_bar['open_time'].minute
    bar_close   = prev_bar['close']
    bar_ema     = ema_series.iloc[-2]
    print(prev_bar)
    print(prev_minute)
    print(bar_close)
    print(bar_ema)

    if prev_minute not in (0, 15, 30, 45):
        return False

    # compare according to side
    side = side.lower()
    if side == "long":
        return bar_close > bar_ema
    elif side == "short":
        return bar_close < bar_ema
    else:
        raise ValueError("side must be 'long' or 'short'")



def message(text: str):
    """
    Discord 웹훅으로 메시지를 보냅니다.
    내용이 2000자 이상인 경우 여러 번에 나눠서 전송합니다.
    """
    MAX_LEN = 2000
    # 2000자 단위로 분할
    chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]
    for idx, chunk in enumerate(chunks, start=1):
        data = {
            "content": chunk,
            "username": "CHEATKEY"
        }
        try:
            resp = requests.post(webhook_url, json=data, timeout=5)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(f"[Webhook Error] chunk {idx}/{len(chunks)}: {err}")
        except requests.exceptions.RequestException as e:
            print(f"[Request Exception] chunk {idx}/{len(chunks)}: {e}")
        else:
            print(f"[Webhook] chunk {idx}/{len(chunks)} delivered, status {resp.status_code}")

def message_alert(message):
    data = {
        "content": message,
        "username": "DATABASE"  # Optional: 설정하지 않으면 기본 웹훅 이름이 사용됩니다.
    }

    result = requests.post(webhook_url_alert, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Error: {err}")
    else:
        print(f"Payload delivered successfully, code {result.status_code}.")

def message_data(message, image_path=None):
    data = {
        "content": message,
        "username": "DATABASE"  # Optional: 지정하지 않으면 기본 웹훅 이름 사용
    }
    
    # image_path가 주어지면 multipart/form-data 방식으로 전송
    if image_path:
        with open(image_path, "rb") as f:
            files = {"file": f}
            payload = {"payload_json": json.dumps(data)}
            result = requests.post(webhook_url_data, data=payload, files=files)
    else:
        result = requests.post(webhook_url_data, json=data)
    
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Error: {err}")
    else:
        print(f"Payload delivered successfully, code {result.status_code}.")



def openai_response(symbol,msg_system,msg_user,base64_image): # symbol, system 메세지, user메세지 입력
    try:
        response = openaiclient.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                "role": "system",
                "content": [
                    {
                    "type": "text",
                    "text": f"{msg_system}"
                    }
                ]
                },
                {
                "role": "user",
                "content": [
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                    },
                    {
                    "type": "text",
                    "text": f"{msg_user}"
                    }
                ]
                }
            ],
            temperature=1,
            max_tokens=500,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={
                "type": "json_object"
            }
            )
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        message(f"An error occurred: {e}")
        return None
    

def openai_response_msg(symbol,msg_system,msg_user): # symbol, system 메세지, user메세지 입력
    try:
        response = openaiclient.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                "role": "system",
                "content": [
                    {
                    "type": "text",
                    "text": f"{msg_system}"
                    }
                ]
                },
                {
                "role": "user",
                "content": [
                    {
                    "type": "text",
                    "text": f"{msg_user}"
                    }
                ]
                }
            ],
            temperature=1,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={
                "type": "json_object"
            }
            )
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        message(f"An error occurred: {e}")
        return None


def openai_response_2(symbol,msg_system,msg_user,base64_image1,base64_image2): # symbol, system 메세지, user메세지 입력
    try:
        response = openaiclient.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                "role": "system",
                "content": [
                    {
                    "type": "text",
                    "text": f"{msg_system}"
                    }
                ]
                },
                {
                "role": "user",
                "content": [
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image1}"
                    }
                    },
                    {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image2}"
                    }
                    },
                    {
                    "type": "text",
                    "text": f"{msg_user}"
                    }
                ]
                }
            ],
            temperature=0.5,
            max_tokens=700,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={
                "type": "json_object"
            }
            )
        
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        message(f"An error occurred: {e}")
        return None
    


DB_PATH = "data.db"


def create_tendency_chart(candles, position_list=None, candle_size=None):
    # 캔들 데이터 준비
    ohlc_data = {
        'Date': [datetime.fromtimestamp(int(candle[0]) / 1000) for candle in candles],
        'Open': [float(candle[1]) for candle in candles],
        'High': [float(candle[2]) for candle in candles],
        'Low': [float(candle[3]) for candle in candles],
        'Close': [float(candle[4]) for candle in candles],
        'Volume': [float(candle[5]) for candle in candles],
    }
    
    df = pd.DataFrame(ohlc_data)
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    
    if df.empty:
        raise ValueError("DataFrame이 비어 있습니다. candles 데이터가 있는지 확인하세요.")
    
    # 스타일 설정
    mpf_style = mpf.make_mpf_style(
        base_mpf_style='charles',
        y_on_right=False,
        rc={'figure.figsize': (12, 8), 'axes.grid': True}
    )
    
    # addplot 리스트 초기화
    addplots = []
    
    if position_list is not None:
        # position_list 구조: [side, [buydate, ...], selldate]
        side = position_list[0].lower()  # 'long' 또는 'short'
        buy_dates_raw = position_list[1]  # 매수일 리스트
        sell_dates_raw = position_list[2]   # 매도일
        
        def to_datetime(x):
            if isinstance(x, datetime):
                return x
            fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
            for fmt in fmts:
                try:
                    return datetime.strptime(x, fmt)
                except ValueError:
                    pass
            return datetime.strptime(x, "%Y-%m-%d")
        
        buy_dates = [to_datetime(dt) for dt in buy_dates_raw]
        sell_dates = [to_datetime(dt) for dt in sell_dates_raw]
        
        # 매수/매도 시그널용 시리즈 (NaN으로 초기화)
        buy_marker_series = pd.Series(np.nan, index=df.index)
        sell_marker_series = pd.Series(np.nan, index=df.index)
        
        # 캔들 인덱스에서 가장 가까운 시각을 찾는 함수
        def get_nearest_index(target_dt):
            diffs = abs(df.index - target_dt)
            nearest_idx = diffs.argmin()
            return df.index[nearest_idx]
        
        # 매수 시그널 처리: 각 매수 시간에 대해 가장 가까운 봉에 표시
        for bdate in buy_dates:
            nearest_idx = get_nearest_index(bdate)
            row = df.loc[nearest_idx]
            offset = 0.02 * (row['High'] - row['Low'])
            if side == 'long':
                buy_marker_series[nearest_idx] = row['Low'] - offset
            elif side == 'short':
                buy_marker_series[nearest_idx] = row['High'] + offset
        
        # 매도 시그널 처리: sell_date에 대해 가장 가까운 봉에 표시
        sell_dates_raw = position_list[2]
        # 리스트인지 확인 후, 아니면 리스트로 감싸기
        sell_dates = sell_dates_raw if isinstance(sell_dates_raw, list) else [sell_dates_raw]

        for sdate in sell_dates:
            nearest_idx = get_nearest_index(sdate)
            row = df.loc[nearest_idx]
            offset = 0.02 * (row['High'] - row['Low'])
            if side == 'long':
                # 롱 포지션일 때 매도 마커는 봉 상단 위
                sell_marker_series[nearest_idx] = row['High'] + offset
            elif side == 'short':
                # 숏 포지션일 때 매도 마커는 봉 하단 아래
                sell_marker_series[nearest_idx] = row['Low'] - offset
        
        # 실제 값이 존재하는 경우에만 addplot 추가
        if side == 'long':
            if buy_marker_series.notna().any():
                ap_buy = mpf.make_addplot(
                    buy_marker_series,
                    type='scatter',
                    markersize=100,
                    marker='^',
                    color='g'
                )
                addplots.append(ap_buy)
            if sell_marker_series.notna().any():
                ap_sell = mpf.make_addplot(
                    sell_marker_series,
                    type='scatter',
                    markersize=100,
                    marker='v',
                    color='r'
                )
                addplots.append(ap_sell)
        elif side == 'short':
            if buy_marker_series.notna().any():
                ap_buy = mpf.make_addplot(
                    buy_marker_series,
                    type='scatter',
                    markersize=100,
                    marker='v',
                    color='r'
                )
                addplots.append(ap_buy)
            if sell_marker_series.notna().any():
                ap_sell = mpf.make_addplot(
                    sell_marker_series,
                    type='scatter',
                    markersize=100,
                    marker='^',
                    color='g'
                )
                addplots.append(ap_sell)
    
    # 차트 제목 생성: 현재 날짜와 봉 크기 정보를 포함
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    side = side.upper() if position_list is not None else 'DATA'
    if candle_size:
        title = f"{side} : {current_time_str} - {candle_size} Candles Chart"
    else:
        title = f"{side} : {current_time_str} Candles Chart"
    
    # 차트 이미지 저장 경로 설정
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, "recent_5min_candles.png")
    
    # 차트 생성
    plot_kwargs = {
        "type": 'candle',
        "style": mpf_style,
        "volume": True,
        "ylabel": '',
        "ylabel_lower": '',
        "title": title,
        "savefig": dict(fname=file_path, dpi=100, bbox_inches='tight')
    }
    
    if addplots:
        plot_kwargs["addplot"] = addplots
    
    mpf.plot(df, **plot_kwargs)
    
    return file_path

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            side TEXT NOT NULL,
            result TEXT NOT NULL,
            leverage TEXT NOT NULL,
            pnl REAL NOT NULL,
            roi REAL NOT NULL,
            inv_amount REAL NOT NULL,
            count_value REAL NOT NULL,
            max_pnl REAL NOT NULL,
            min_pnl REAL NOT NULL,
            time TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()



# 데이터 저장 함수
def save_to_db(date, side, result, leverage, realized_profit, roi, inv_amount, count_value, max_pnl, min_pnl, time):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO data (date, side, result, leverage, pnl, roi, inv_amount, count_value, max_pnl, min_pnl, time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (date, side, result, leverage, realized_profit, roi, inv_amount, count_value, max_pnl, min_pnl, time))
    conn.commit()
    conn.close()

def fetch_from_db(limit=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if limit:
        cursor.execute("SELECT date, side, result, leverage, pnl, roi, inv_amount, count_value, max_pnl, min_pnl, time FROM data ORDER BY id DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT date, side, result, leverage, pnl, roi, inv_amount, count_value, max_pnl, min_pnl, time FROM data ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows




# 캔들 가져오기

def required_candle_count(position_list, interval):
    """
    position_list: [side, [buydate1, buydate2, ...], [selldate1, selldate2, ...]]
        - buydates와 selldates는 datetime 객체이거나 문자열("YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM", 또는 "YYYY-MM-DD")로 제공됩니다.
    interval: 캔들 간격 문자열 (예: '5m', '15m', '1h')
    
    반환: 차트에 포함되어야 할 총 봉 개수 (최초 매수 전 30봉 포함)
    """
    side = position_list[0].lower()
    raw_buydates = position_list[1]
    raw_selldates = position_list[2]
    
    # 문자열인 경우 datetime으로 변환하는 헬퍼
    def to_datetime(x):
        if isinstance(x, datetime):
            return x
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(x, fmt)
            except ValueError:
                continue
        return datetime.strptime(x, "%Y-%m-%d")
    
    buy_dates = [to_datetime(dt) for dt in raw_buydates]
    sell_dates = [to_datetime(dt) for dt in raw_selldates]
    
    # 매수일 중 가장 이른 시각
    earliest_buy = min(buy_dates)
    # 매도일(들) 중 가장 늦은 시각
    latest_sell = max(sell_dates)
    
    if latest_sell < earliest_buy:
        raise ValueError("매도일(selldate)이 매수일(buydate)보다 빠를 수 없습니다.")
    
    # interval 문자열 파싱 (분 단위)
    if interval.endswith('m'):
        candle_interval = int(interval[:-1])
    elif interval.endswith('h'):
        candle_interval = int(interval[:-1]) * 60
    else:
        raise ValueError("지원하지 않는 interval입니다. 예: '5m', '15m', '1h'")
    
    # 매수일부터 매도일까지의 시간 차 (분)
    diff_minutes = (latest_sell - earliest_buy).total_seconds() / 60.0
    
    # 매수부터 매도까지 필요한 봉 개수 (interval로 나눈 뒤 올림, 양 끝 포함)
    candles_between = math.ceil(diff_minutes / candle_interval) + 1
    
    # 매수 전 최소 30봉 추가
    total_required = 30 + candles_between
    return total_required

    

    


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

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def cheatkey_value(symbol, interval='15m', ema12_period=12, ema26_period=26):
    """
    최근 3개월 봉들 중 EMA12와 EMA26이 교차하는 봉 바로 전 봉의 EMA 차이(절대값)들에 대해
    90번째 백분위수(상위 90% 값)를 계산하여 반환합니다.
    
    :param symbol: 거래 심볼 (예: 'BTCUSDT')
    :param interval: 캔들 간격 (예: '15m')
    :param ema12_period: EMA12 계산 기간 (기본값 12)
    :param ema26_period: EMA26 계산 기간 (기본값 26)
    :return: 계산된 90번째 백분위수 값, 교차 이벤트가 없으면 None 반환
    """
    # 최근 3개월 (90일) 전 타임스탬프 (밀리초 단위)
    start_time = int((datetime.utcnow() - timedelta(days=90)).timestamp() * 1000)
    end_time = int(time.time() * 1000)
    
    # Binance API를 통해 과거 데이터 (캔들) 불러오기
    # 주의: 클라이언트 인스턴스(client)는 미리 생성되어 있어야 합니다.
    klines = client.futures_historical_klines(symbol, interval, start_str=start_time, end_str=end_time)
    
    if not klines:
        print("캔들 데이터를 불러올 수 없습니다.")
        return None

    # 데이터프레임으로 변환
    df = pd.DataFrame(klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    # 종가를 float으로 변환
    df['close'] = df['close'].astype(float)
    
    # EMA 계산 (pandas ewm 사용)
    df['ema12'] = df['close'].ewm(span=ema12_period, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=ema26_period, adjust=False).mean()
    
    # EMA 차이 계산 (ema12 - ema26)
    df['diff'] = df['ema12'] - df['ema26']
    
    # 교차 이벤트 발생 시점 찾기: 바로 전 봉과 비교하여 부호가 바뀌면 교차한 것으로 판단
    crossover_diffs = []
    for i in range(1, len(df)):
        if df.loc[i-1, 'diff'] * df.loc[i, 'diff'] < 0:
            # 교차가 발생한 봉 바로 전 봉의 EMA 차이 절대값 기록
            crossover_diffs.append(abs(df.loc[i-1, 'diff']))
    
    if len(crossover_diffs) == 0:
        print("최근 3개월 동안 EMA 교차 이벤트가 없습니다.")
        return None

    # 정렬 후 90번째 백분위수(상위 90% 값)를 계산
    threshold_value = np.percentile(crossover_diffs, 90)
    return threshold_value