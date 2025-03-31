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
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from decimal import Decimal, ROUND_DOWN

import hmac
import hashlib
import urllib.parse
base_url = 'https://fapi.binance.com'


colorama.init(autoreset=True)

key_file_path = "keys.json"





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

GEMINI_API_KEY = data["GEMINI_API_KEY"]

# Gemini API 설정
geminaiclient = genai.Client(api_key=GEMINI_API_KEY)


client = Client(api_key, api_secret)
openaiclient = OpenAI(api_key=openai_api_key)



def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

MAX_ORDER_AGE = 180 # 오래된 주문 기준 시간 (초)
def cancel_old_orders(client: Client, symbol: str):
    global waiting, MAX_ORDER_AGE
    """
    활성화된 오래된 주문 취소 함수
    """
    try:
        # 활성화된 주문 목록 조회
        open_orders = client.futures_get_open_orders(symbol=symbol)
        now_timestamp = datetime.now(timezone.utc)  # 타임존 인식 객체로 변경

        if open_orders == []:
            waiting = False
        else:
            for order in open_orders:
                order_id = order['orderId']
                order_time = datetime.fromtimestamp(order['time'] / 1000, timezone.utc)  # UTC 타임존 설정

                # 오래된 주문 확인
                if (now_timestamp - order_time).total_seconds() > MAX_ORDER_AGE:
                    # 오래된 주문 취소
                    client.futures_cancel_order(symbol=symbol, orderId=order_id)
                    print(f"오래된 주문 취소: 주문 ID {order_id}, 생성 시간: {order_time}")
                    message(f"오래된 주문 취소: 주문 ID {order_id}, 생성 시간: {order_time}")

    except Exception as e:
        print(f"오래된 주문 취소 중 오류 발생: {e}")
        message(f"오래된 주문 취소 중 오류 발생: {e}")

DB_PATH = "data.db"


def create_tendency_chart(candles, position_list=None, candle_size=None):
    # 캔들 데이터 준비
    ohlc_data = {
        'Date': [datetime.fromtimestamp(candle[0] / 1000) for candle in candles],
        'Open': [float(candle[1]) for candle in candles],
        'High': [float(candle[2]) for candle in candles],
        'Low': [float(candle[3]) for candle in candles],
        'Close': [float(candle[4]) for candle in candles],
        'Volume': [float(candle[5]) for candle in candles],
    }
    
    df = pd.DataFrame(ohlc_data)
    df.set_index('Date', inplace=True)
    
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
        sell_date_raw = position_list[2]   # 매도일
        
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
        sell_date = to_datetime(sell_date_raw)
        
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
        nearest_sell_idx = get_nearest_index(sell_date)
        row = df.loc[nearest_sell_idx]
        offset = 0.02 * (row['High'] - row['Low'])
        if side == 'long':
            sell_marker_series[nearest_sell_idx] = row['High'] + offset
        elif side == 'short':
            sell_marker_series[nearest_sell_idx] = row['Low'] - offset
        
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





def get_candles(symbol, interval, candle_count):
    """
    symbol: 거래 심볼 (예: 'BTCUSDT')
    interval: 캔들 간격 (예: '5m', '15m', '1h' 등)
    candle_count: 반환받을 캔들 개수
    """
    # interval 단위에 따라 lookback 기간(분 단위)을 계산
    if interval.endswith('m'):
        unit = int(interval[:-1])  # 분 단위 (예: '5m' -> 5)
        total_minutes = candle_count * unit
        lookback = f"{total_minutes} minutes ago UTC"
    elif interval.endswith('h'):
        unit = int(interval[:-1])  # 시간 단위 (예: '1h' -> 1)
        total_minutes = candle_count * unit * 60
        lookback = f"{total_minutes} minutes ago UTC"
    else:
        raise ValueError("지원하지 않는 interval입니다. 예: '5m', '15m', '1h'")
    
    klines = client.get_historical_klines(symbol, interval, lookback)
    return klines[-candle_count:]

def required_candle_count(position_list, interval):
    """
    position_list: [side, [buydate, ...], selldate]
        - buydate와 selldate는 datetime 객체거나 문자열("YYYY-MM-DD HH:MM:SS" 또는 "YYYY-MM-DD HH:MM" 또는 "YYYY-MM-DD")로 제공됨
    interval: 캔들 간격 문자열 (예: '5m', '15m', '1h')
    
    반환: 차트에 포함되어야 할 총 봉 개수 (최초 매수 전 30봉 포함)
    """
    side = position_list[0].lower()
    raw_buydates = position_list[1]
    raw_selldate = position_list[2]
    
    # 문자열인 경우 datetime으로 변환하는 함수
    def to_datetime(x):
        if isinstance(x, datetime):
            return x
        fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        for fmt in fmts:
            try:
                return datetime.strptime(x, fmt)
            except ValueError:
                continue
        # 날짜만 있는 경우
        return datetime.strptime(x, "%Y-%m-%d")
    
    buy_dates = [to_datetime(dt) for dt in raw_buydates]
    sell_date = to_datetime(raw_selldate)
    
    # 매수일 중 가장 이른 시각
    earliest_buy = min(buy_dates)
    
    # sell_date가 earliest_buy보다 빠르면 오류 처리
    if sell_date < earliest_buy:
        raise ValueError("매도일(selldate)이 매수일(buydate)보다 빠를 수 없습니다.")
    
    # interval 문자열 파싱 (분 단위)
    if interval.endswith('m'):
        candle_interval = int(interval[:-1])
    elif interval.endswith('h'):
        candle_interval = int(interval[:-1]) * 60
    else:
        raise ValueError("지원하지 않는 interval입니다. 예: '5m', '15m', '1h'")
    
    # 매수일부터 매도일까지의 시간 차 (분)
    diff_minutes = (sell_date - earliest_buy).total_seconds() / 60.0
    
    # 매수부터 매도까지 몇 개의 봉이 필요한지 (봉 간격으로 나누고 올림)
    candles_between = math.ceil(diff_minutes / candle_interval) + 1  # 양 끝 포함
    
    # 매수 전 최소 30봉 추가
    total_required = 30 + candles_between
    return total_required



# 지갑 잔액 체크 함수 정의
def get_futures_asset_balance(symbol='USDT'):
    try:
        balance_info = client.futures_account_balance()
        for balance in balance_info:
            if balance['asset'] == symbol:
                return float(balance['availableBalance'])
        return 0.0
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0.0

def get_asset_balance(symbol, side='all'):
    """
    코인 잔액(격리 마진) 체크 함수

    :param symbol: 조회할 코인 심볼 (예: 'BTCUSDT')
    :param side: 'long', 'short' 또는 'all' (기본값: 'all')
                 - 'long': 롱 포지션의 격리 마진 반환
                 - 'short': 숏 포지션의 격리 마진 반환
                 - 'all': 해당 심볼의 첫 번째 포지션 격리 마진 반환
    :return: 격리 마진 (float) 또는 해당 포지션이 없으면 None
    """
    try:
        positions = client.futures_position_information()
        for position in positions:
            if position['symbol'] == symbol:
                if side.lower() != 'all':
                    # positionSide 필드가 있는 경우(헤지 모드에서) 롱/숏 구분
                    pos_side = position.get('positionSide', '').lower()
                    if pos_side != side.lower():
                        continue
                return float(position['isolatedMargin'])
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0.0

# 레버리지 설정 함수 정의
def set_leverage(symbol, leverage):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set: {response}")
    except Exception as e:
        print(f"An error occurred while setting leverage: {e}")


def execute_market_order(symbol, percentage, leverage, side):  
    """
    :param symbol: 거래 종목
    :param percentage: USDT 잔고의 몇 퍼센트를 주문에 사용할 것인지 (%)
    :param leverage: 레버리지 값
    :param side: 주문 방향 ('BUY' : 롱, 'SELL' : 숏)
    """
    # USDT 잔고의 일정 퍼센트에 해당하는 주문 금액 계산
    quantity_usdt = calculate_order_quantity(percentage)
    
    # 현재 시장가(매도 호가)를 가져옴
    current_price = get_current_market_price(symbol)
    if current_price is None:
        print("현재 시장가를 가져올 수 없습니다.")
        return
    
    # 최소 주문 수량(LOT_SIZE 필터의 minQty) 가져오기
    min_qty = get_min_order_quantity(symbol)
    
    # 주문 수량(size) 계산: (주문 금액 / 현재 시장가) * 레버리지
    size = (quantity_usdt / current_price) * leverage
    
    # 심볼에 따른 stepSize 단위에 맞게 수량 조정 (내림)
    size = round_quantity_to_step_size(symbol, size)
    
    if size >= min_qty:
        order = place_market_order(symbol, size, leverage, side)
        return order
    else:
        print(f"주문 수량이 최소 수량 ({min_qty})보다 적습니다.")


def place_market_order(symbol, quantity, leverage, side):
    # 레버리지 설정
    set_leverage(symbol, leverage)
    
    # 수량을 심볼별 stepSize 단위에 맞게 재조정
    quantity = round_quantity_to_step_size(symbol, quantity)
    
    # 헤지 모드인 경우, positionSide 설정 (side가 'BUY'이면 LONG, 'SELL'이면 SHORT)
    position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'
    
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,  # 'BUY' 또는 'SELL'
            type='MARKET',
            quantity=quantity,
            positionSide=position_side  # 헤지 모드에서 롱/숏 포지션 구분
        )
        print(f"Market order placed: {order}")
        return order
    except Exception as e:
        print(f"An error occurred: {e}")


def get_current_market_price(symbol):
    """
    현재 시장가(매도 호가)를 가져오는 함수입니다.
    """
    ticker = client.futures_orderbook_ticker(symbol=symbol)
    if ticker and 'askPrice' in ticker:
        return float(ticker['askPrice'])
    else:
        return None

def place_limit_order(symbol, price, quantity, leverage, side):
    # 레버리지 설정
    set_leverage(symbol, leverage)
    # 가격은 티크 사이즈에 맞게 반올림
    price = round_price_to_tick_size(symbol, price)
    # 수량은 심볼별 step size에 맞게 반올림
    quantity = round_quantity_to_step_size(symbol, quantity)
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,  # 'BUY' (롱) 또는 'SELL' (숏)
            type='LIMIT',
            timeInForce='GTC',  # Good Till Cancelled
            price=price,
            quantity=quantity
        )
        print(f"Order placed: {order}")
        return order
    except Exception as e:
        print(f"An error occurred: {e}")

def calculate_order_quantity(percentage):
    usdt_balance = get_futures_asset_balance()
    buy_quantity = usdt_balance * percentage / 100
    # 원시 수량은 그대로 반환하고, 이후 step size에 맞춰 반올림 처리
    return buy_quantity

# LOT_SIZE 필터에서 stepSize를 가져오는 함수
def get_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    return float(f['stepSize'])
    return None

# LOT_SIZE 필터를 이용하여 최소 주문 수량을 찾는 함수
def get_min_order_quantity(symbol):
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    return float(f['minQty'])
    return None

# 수량을 해당 심볼의 stepSize 단위에 맞게 반올림하는 함수
def round_quantity_to_step_size(symbol, quantity):
    step_size = get_step_size(symbol)
    if step_size is None or step_size == 0:
        return quantity
    # Decimal을 사용해 정확하게 아래로 반올림(ROUND_DOWN)
    quantity_dec = Decimal(str(quantity))
    step_dec = Decimal(str(step_size))
    rounded_quantity = quantity_dec.quantize(step_dec, rounding=ROUND_DOWN)
    return float(rounded_quantity)

# 주문 실행 함수 : 종목, 지정가격, 퍼센트(자산), 레버리지, 주문 방향(side)
def execute_limit_order(symbol, price, percentage, leverage, side):  
    """
    :param symbol: 거래 종목
    :param price: 주문 가격
    :param percentage: 자산의 몇 퍼센트를 주문할 것인지
    :param leverage: 레버리지 값
    :param side: 주문 방향 ('BUY' : 롱, 'SELL' : 숏)
    """
    quantity = calculate_order_quantity(percentage)
    price = round_price_to_tick_size(symbol, price)
    min_qty = get_min_order_quantity(symbol)  # 최소 주문 수량 가져오기
    if quantity >= min_qty:
        # 주문 size 계산 : (자산의 금액 / 가격) * 레버리지
        size = quantity / price * leverage
        # 심볼에 따른 step size로 수량 반올림
        size = round_quantity_to_step_size(symbol, size)
        order = place_limit_order(symbol, price, size, leverage, side)
        return order
    else:
        print(f"주문 수량이 최소 수량 ({min_qty})보다 적습니다.")

def close(symbol, side='all'):
    try:
        # 현재 오픈된 포지션 정보 가져오기
        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            pos_amt = float(position['positionAmt'])
            if pos_amt != 0:
                # side 필터 적용: all이면 모두, long이면 양수 포지션, short이면 음수 포지션
                if side != 'all':
                    if side == 'long' and pos_amt <= 0:
                        continue
                    elif side == 'short' and pos_amt >= 0:
                        continue

                # 포지션 청산: 롱이면 SELL, 숏이면 BUY로 주문 실행
                order_side = 'SELL' if pos_amt > 0 else 'BUY'
                # 헤지 모드에서 포지션을 명확히 하기 위해 positionSide 파라미터 추가
                position_side = 'LONG' if pos_amt > 0 else 'SHORT'
                quantity = abs(pos_amt)

                order = client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=quantity,
                    reduceOnly=True,
                    positionSide=position_side
                )
                print(f"Position for {symbol} closed: {order}")
                return order
        print(f"No open position for {symbol} matching side '{side}'.")
    except Exception as e:
        print(f"An error occurred: {e}")

def close_usdt(symbol, leverage, usdt, side='all'):
    try:
        # 현재 오픈된 포지션 정보 가져오기
        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            pos_amt = float(position['positionAmt'])
            if pos_amt != 0:
                # side 필터 적용: 'all'이면 모두, long이면 양수 포지션, short이면 음수 포지션만 청산
                if side != 'all':
                    if side == 'long' and pos_amt <= 0:
                        continue
                    elif side == 'short' and pos_amt >= 0:
                        continue
                
                # 포지션 청산: 롱 포지션은 SELL, 숏 포지션은 BUY
                order_side = 'SELL' if pos_amt > 0 else 'BUY'
                # 헤지 모드에서 포지션 구분을 위해 positionSide 파라미터 추가
                position_side = 'LONG' if pos_amt > 0 else 'SHORT'
                entryprice = float(position['entryPrice'])
                usdt_value = float(usdt)
                
                # 지정된 USDT 가치에 따른 청산 수량 계산
                quantitytoclose = abs(usdt_value * leverage / entryprice)
                quantitytoclose = round(quantitytoclose, 3)
                
                order = client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=quantitytoclose,
                    reduceOnly=True,
                    positionSide=position_side
                )
                print(f"Position for {symbol} closed: {order}")
                return order
        print(f"No open position for {symbol} matching side '{side}'.")
    except Exception as e:
        print(f"An error occurred: {e}")




# 포지션 정보 가져오기 함수 정의
def get_futures_position_info(symbol, side=None):
    """
    side: 'long', 'short', 또는 None (전체 포지션 정보)
    """
    try:
        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if position['symbol'] == symbol:
                pos_amt = float(position['positionAmt'])
                if side == 'long' and pos_amt > 0:
                    return position
                elif side == 'short' and pos_amt < 0:
                    return position
                elif side is None:
                    return position
        # 해당 방향의 포지션이 없는 경우 기본값 반환
        return {
            'unRealizedProfit': 0,
            'positionAmt': 0,
            'entryPrice': 0,
            'liquidationPrice': 0
        }
    except Exception as e:
        print(f"An error occurred: {e}")
        return None



# 디코 웹훅 메세지 보내기 함수 정의
def message(message):
    data = {
        "content": message,
        "username": "CHEATKEY"  # Optional: 설정하지 않으면 기본 웹훅 이름이 사용됩니다.
    }

    result = requests.post(webhook_url, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Error_msg: {err}")
    else:
        print(f"Payload delivered successfully, code {result.status_code}.")

def message_alert(message):
    data = {
        "content": message,
        "username": "CHEATKEY"  # Optional: 설정하지 않으면 기본 웹훅 이름이 사용됩니다.
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

# 주문 상태 확인 함수 정의
def check_order_status(symbol, order_id):
    try:
        order = client.futures_get_order(symbol=symbol, orderId=order_id)
        
        if order and order['status'] == 'FILLED':
            order = None

        return order
    except Exception as e:
        print(f"An error occurred: {e}")
        message(f"check_order_status : An error occurred: {e}")
        return None


# 틱 사이즈 확인 함수 정의
def get_tick_size(symbol):
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    return float(f['tickSize'])
    return None

# 틱 사이즈로 반올림 함수 정의
def round_price_to_tick_size(symbol,price):
    price = float(price)
    tick_size = get_tick_size(symbol)
    return round(price / tick_size) * tick_size

def get_latest_order(symbol):
    try:
        # 모든 주문 정보 가져오기
        orders = client.futures_get_all_orders(symbol=symbol, limit=10)

        # 주문이 없는 경우 처리
        if not orders:
            return None

        # 가장 최근 주문 정보 반환
        latest_order = orders[-1]
        return latest_order
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    

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
    
def check_spike(symbol,current_status,count5=250,count15=150):
    # 5분차트
    candles1 = get_candles(symbol, interval='5m', candle_count=count5) 
    file_path1 = create_tendency_chart(candles1)
    base64_image1 = encode_image(file_path1)
    # 15분차트
    candles2 = get_candles(symbol, interval='15m', candle_count=count15) 
    file_path2 = create_tendency_chart(candles2)
    base64_image2 = encode_image(file_path2)
    
    msg_stratagy_spike = ''
    msg_user_spike = "Now you have to do analysis with these chart data" + current_status
    response = openai_response_2(symbol,msg_stratagy_spike,msg_user_spike,base64_image1,base64_image2)

    ai_response = json.loads(response.choices[0].message.content)
    long_response = ai_response.get("long")
    short_response = ai_response.get("short")

    return long_response, short_response

def get_klines(symbol,interval='5m',limit=3):
    # [0] Open time, [1] Open, [2] High, [3] Low, [4] Close, [5] Volume,
    # [6] Close time, [7] Quote asset volume, [8] Number of trades, 
    # [9] Taker buy base asset volume, [10] Taker buy quote asset volume, [11] Ignore
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)

    return klines

def is_good_to_buy(symbol,side):
    klines = get_klines(symbol,'5m',3)
    k3 = klines[2] # 가장 최근 봉
    k2 = klines[1]
    k1 = klines[0] # 가장 나중 봉

    if side == 'long':
        if k1[1] > k1[4] and k2[1] > k2[4] and k3[1] < k3[4]: # - - +
            return True
    elif side == 'short':
        if k1[1] < k1[4] and k2[1] < k2[4] and k3[1] > k3[4]: # + + -
            return True
        

def cheatkey(symbol, ema12_period=12, ema26_period=26, interval='15m', threshold=0.0026, side="long"):
    try:
        # 지정한 간격의 최근 50개의 데이터를 가져옵니다.
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=50)
        
        # 데이터프레임으로 변환 (컬럼은 Binance API 문서 기준)
        df = pd.DataFrame(klines, columns=[
            'open_time','open','high','low','close','volume',
            'close_time','quote_asset_volume','number_of_trades',
            'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
        ])
        
        # 문자열을 float으로 변환 (종가 사용)
        df['close'] = df['close'].astype(float)
        
        # EMA 계산: pandas의 ewm 사용 (adjust=False)
        df['ema12'] = df['close'].ewm(span=ema12_period, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=ema26_period, adjust=False).mean()
        
        # 마지막 행: 현재 봉, 바로 전 행: 이전 봉
        current_ema12 = df.iloc[-1]['ema12']
        current_ema26 = df.iloc[-1]['ema26']
        previous_ema12 = df.iloc[-2]['ema12']
        previous_ema26 = df.iloc[-2]['ema26']
        
        # 현재 봉과 이전 봉의 EMA 차이 (절대값)
        current_diff = abs(current_ema12 - current_ema26)
        previous_diff = abs(previous_ema12 - previous_ema26)
        
        # side 조건: 롱이면 ema12가 ema26 아래, 숏이면 ema12가 ema26 위에 있어야 함.
        if side == "long":
            side_condition = (current_ema12 < current_ema26)
        elif side == "short":
            side_condition = (current_ema12 > current_ema26)
        else:
            print("Error: side는 'long' 또는 'short'여야 합니다.")
            return False
        
        # 전체 조건: EMA 차이 감소, 임계값 이하, side 조건 만족
        if current_diff < previous_diff and current_diff <= threshold and side_condition:
            return True
        else:
            return False
        
    except Exception as e:
        print("Error:", e)
        message("Error:", e) 
        return False


def second_analysis(symbol,leverage,side,reason):
    global msg_system_second_orig
    candles00 = get_candles(symbol, interval='5m', candle_count=50) 
    file_path00 = create_tendency_chart(candles00)
    base64_image00 = encode_image(file_path00)
    msg_system00 = msg_system_second_orig
    msg_user00 = f'''
###
side : {side}
leverage : {leverage}
previous judgment reason: {reason} 
'''
    
    response00 = openai_response(symbol,msg_system00,msg_user00,base64_image00)
    response00 = json.loads(response00.choices[0].message.content)
    responsefinal = response00.get("response")
    return responsefinal

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





def calculate_volatility(symbol='BTCUSDT',limit=50):
    """
    Binance API를 이용하여 최근 50개의 5분 봉 데이터를 가져와
    단기 최고가와 최저가 사이의 변동성(%)을 계산합니다.
    
    변동성은 (전체 최고가 - 전체 최저가) / 전체 최저가 * 100 으로 계산합니다.
    
    Parameters:
        api_key (str): Binance API Key.
        api_secret (str): Binance API Secret.
        symbol (str): 거래쌍 (예: 'BTCUSDT'). 기본값은 'BTCUSDT'.
    
    Returns:
        float: 계산된 변동성(%) 값.
    """
    
    # 최근 50개의 5분 봉 데이터 가져오기
    candles = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_5MINUTE, limit=limit)
    
    # 각 봉에서 최고가와 최저가 추출 (인덱스: [2]는 high, [3]는 low)
    highs = [float(candle[2]) for candle in candles]
    lows = [float(candle[3]) for candle in candles]
    
    overall_high = max(highs)
    overall_low = min(lows)
    
    # 변동성 계산: (전체 최고가 - 전체 최저가) / 전체 최저가 * 100
    volatility = (overall_high - overall_low) / overall_low * 100
    
    return volatility


def change_position_mode(dualSidePosition: bool):
    """
    Binance Futures 헤지 모드 토글 함수.
    
    :param dualSidePosition: True이면 헤지 모드, False이면 원웨이 모드
    :return: Binance API의 JSON 응답
    """
    endpoint = '/fapi/v1/positionSide/dual'
    timestamp = int(time.time() * 1000)
    params = {
        'dualSidePosition': str(dualSidePosition).lower(),  # 'true' 또는 'false'
        'timestamp': timestamp
    }
    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode('utf-8'),
                         query_string.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    headers = {'X-MBX-APIKEY': api_key}
    response = requests.post(url, headers=headers)
    return response.json()

def get_position_mode():
    """
    Binance Futures에서 현재 포지션 모드(헤지모드 여부)를 가져오는 함수.
    
    :return: {'dualSidePosition': True/False, ...} 형식의 JSON 응답
    """
    endpoint = '/fapi/v1/positionSide/dual'
    timestamp = int(time.time() * 1000)
    params = {
        'timestamp': timestamp
    }
    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode('utf-8'),
                         query_string.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    headers = {'X-MBX-APIKEY': api_key}
    response = requests.get(url, headers=headers)
    return response.json()


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