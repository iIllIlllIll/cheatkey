import requests
import time
from datetime import datetime, timezone, timedelta
from binance.client import Client
from binance.enums import *
import matplotlib
matplotlib.use('Agg')  # 서버 환경에서 GUI 없이 사용
import sqlite3
import mplfinance as mpf
import pandas as pd
import numpy as np

import hmac
import hashlib
import urllib.parse
base_url = 'https://fapi.binance.com'


from init_functions import *


key_file_path = "keys.json"
with open(key_file_path, "r") as file:
    data = json.load(file)

api_key = data["api_key"]
api_secret = data["api_secret"]

client = Client(api_key, api_secret)

MAX_ORDER_AGE = 180 # 오래된 주문 기준 시간 (초)
def cancel_old_orders(symbol: str):
    global MAX_ORDER_AGE
    """
    활성화된 오래된 주문 취소 함수
    """
    try:
        # 활성화된 주문 목록 조회
        open_orders = client.futures_get_open_orders(symbol=symbol)
        now_timestamp = datetime.now(timezone.utc)  # 타임존 인식 객체로 변경

        if open_orders == []:
            return 0
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
                
                return None

    except Exception as e:
        print(f"오래된 주문 취소 중 오류 발생: {e}")
        message(f"오래된 주문 취소 중 오류 발생: {e}")

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

def execute_market_order_usdt(symbol, usdt_amount, leverage, side):
    """
    :param symbol:    거래 종목 (e.g. 'BTCUSDT')
    :param usdt_amount:  사용할 USDT 금액 (예: 50 → 50 USDT 어치 주문)
    :param leverage:  설정할 레버리지 (예: 10)
    :param side:      주문 방향 ('BUY' : 롱, 'SELL' : 숏)
    """
    # 0. 입력값 유효성 검사
    if usdt_amount <= 0:
        print("사용할 USDT 금액은 0보다 커야 합니다.")
        return

    # 1. 현재 시장가(매도 호가) 조회
    current_price = get_current_market_price(symbol)
    if current_price is None:
        print("현재 시장가를 가져올 수 없습니다.")
        return

    # 2. 최소 주문 수량(Lot size) 조회
    min_qty = get_min_order_quantity(symbol)

    # 3. 주문 수량 계산: (USDT 금액 / 현재 시장가) * 레버리지
    raw_size = (usdt_amount / current_price) * leverage

    # 4. stepSize 단위에 맞게 내림 처리
    size = round_quantity_to_step_size(symbol, raw_size)

    # 5. 최소 수량 이상일 때만 주문
    if size >= min_qty:
        order = place_market_order(symbol, size, leverage, side)
        print(f"{symbol} {side} 시장가 주문 요청: 수량={size}")
        return order
    else:
        print(f"계산된 주문 수량({size})이 최소 수량({min_qty})보다 적습니다.")



def place_market_order(symbol: str, quantity: float, leverage: int, side: str):
    """
    시장가 주문을 실행하고 Binance API의 전체 응답 딕셔너리를 반환합니다.
    실패 시에는 RuntimeError를 발생시킵니다.
    """
    # 레버리지 설정 (이 함수는 성공/실패 여부를 반환하도록 가정합니다)
    set_leverage(symbol, leverage) # 이 함수가 에러를 발생시키지 않고 처리하도록 되어 있어야 함

    # 수량을 심볼별 stepSize 단위에 맞게 재조정
    adjusted_quantity = round_quantity_to_step_size(symbol, quantity)
    
    if adjusted_quantity <= 0:
        raise ValueError(f"Adjusted quantity {adjusted_quantity} is zero or negative for {symbol}.")

    # 헤지 모드인 경우, positionSide 설정 (side가 'BUY'이면 LONG, 'SELL'이면 SHORT)
    # Binance API는 'BUY'/'SELL'에 따라 positionSide를 'LONG'/'SHORT'로 명시하는 것이 일반적입니다.
    position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'
    
    try:
        order_response = client.futures_create_order(
            symbol=symbol,
            side=side,  # 'BUY' 또는 'SELL'
            type='MARKET',
            quantity=adjusted_quantity, # 조정된 수량 사용
            positionSide=position_side  # 헤지 모드에서 롱/숏 포지션 구분
        )
        print(f"DEBUG: Binance Market order placed: {order_response}")
        return order_response # 성공 시 전체 응답 반환

    except Exception as e:
        # Binance API 오류 메시지에서 필요한 정보를 추출하여 RuntimeError 발생
        # Binance 오류는 JSON 형식으로 오류 코드를 포함하는 경우가 많습니다.
        error_msg = str(e)
        if hasattr(e, 'code') and hasattr(e, 'msg'):
            error_info = f"Binance API Error {e.code}: {e.msg}"
        else:
            error_info = f"Binance API Error: {error_msg}"
        
        print(f"ERROR: {error_info}")
        raise RuntimeError(error_info)

def place_limit_order(symbol: str, price: float, quantity: float, leverage: int, side: str):
    """
    지정가 주문을 실행하고 Binance API의 전체 응답 딕셔너리를 반환합니다.
    실패 시에는 RuntimeError를 발생시킵니다.
    """
    # 레버리지 설정
    set_leverage(symbol, leverage)

    # 가격은 티크 사이즈에 맞게 반올림
    adjusted_price = round_price_to_tick_size(symbol, price)
    # 수량은 심볼별 step size에 맞게 반올림
    adjusted_quantity = round_quantity_to_step_size(symbol, quantity)

    if adjusted_quantity <= 0:
        raise ValueError(f"Adjusted quantity {adjusted_quantity} is zero or negative for {symbol}.")
    if adjusted_price <= 0:
        raise ValueError(f"Adjusted price {adjusted_price} is zero or negative for {symbol}.")

    # Binance 지정가 주문은 positionSide를 명시하지 않아도 되는 경우가 많지만, 헤지 모드에서는 명시하는 것이 좋습니다.
    # Binance API 문서에 따라 positionSide는 생략하거나 명시합니다.
    position_side = 'LONG' if side.upper() == 'BUY' else 'SHORT'

    try:
        order_response = client.futures_create_order(
            symbol=symbol,
            side=side,  # 'BUY' (롱) 또는 'SELL' (숏)
            type='LIMIT',
            timeInForce='GTC',  # Good Till Cancelled
            price=adjusted_price, # 조정된 가격 사용
            quantity=adjusted_quantity, # 조정된 수량 사용
            positionSide=position_side # 헤지 모드에서 롱/숏 포지션 구분
        )
        print(f"DEBUG: Binance Limit order placed: {order_response}")
        return order_response # 성공 시 전체 응답 반환

    except Exception as e:
        error_msg = str(e)
        if hasattr(e, 'code') and hasattr(e, 'msg'):
            error_info = f"Binance API Error {e.code}: {e.msg}"
        else:
            error_info = f"Binance API Error: {error_msg}"
        
        print(f"ERROR: {error_info}")
        raise RuntimeError(error_info)



def get_current_market_price(symbol):
    """
    현재 시장가(매도 호가)를 가져오는 함수입니다.
    """
    ticker = client.futures_orderbook_ticker(symbol=symbol)
    if ticker and 'askPrice' in ticker:
        return float(ticker['askPrice'])
    else:
        return None



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
                    positionSide=position_side
                )
                print(f"Position for {symbol} closed: {order}")
                return order
        print(f"No open position for {symbol} matching side '{side}'.")
        return 'no_order'
    except Exception as e:
        print(f"An error occurred: {e}")


def close_usdt(symbol, leverage, usdt, side='all'):
    try:
        # 1) 현재 오픈된 포지션 정보 가져오기
        positions = client.futures_position_information(symbol=symbol)
        # 2) 해당 심볼의 stepSize 조회
        info = client.futures_exchange_info()["symbols"]
        sym = next(s for s in info if s["symbol"] == symbol)
        # 필터 인덱스는 2가 LOT_SIZE 필터
        step_size = float(sym["filters"][2]["stepSize"])
        # 소수점 자릿수 계산
        decimals = int(round(-math.log10(step_size), 0))

        for position in positions:
            pos_amt = float(position['positionAmt'])
            if pos_amt == 0:
                continue

            # side 필터 적용
            if side != 'all':
                if side == 'long' and pos_amt <= 0:
                    continue
                if side == 'short' and pos_amt >= 0:
                    continue

            # 청산 주문 방향
            order_side = 'SELL' if pos_amt > 0 else 'BUY'
            position_side = 'LONG' if pos_amt > 0 else 'SHORT'
            entryprice = float(position['entryPrice'])
            usdt_value = float(usdt)

            # 지정 USDT 가치로 청산할 원래 수량 (float)
            raw_qty = abs(usdt_value * leverage / entryprice)

            # stepSize 단위로 내림(floor) 처리
            qty_floor = math.floor(raw_qty / step_size) * step_size
            # 소수점 자릿수 맞추기
            quantitytoclose = round(qty_floor, decimals)
            if quantitytoclose <= 0:
                print(f"[close_usdt] stepSize ({step_size}) 단위로 내림 후 수량이 0이므로 건너뜁니다.")
                continue

            # 3) 청산 주문 생성
            order = client.futures_create_order(
                symbol=symbol,
                side=order_side,
                type='MARKET',
                quantity=quantitytoclose,
                positionSide=position_side
            )
            print(f"Position for {symbol} closed: {order}")
            return order

        print(f"No open position for {symbol} matching side '{side}'.")
    except Exception as e:
        print(f"An error occurred: {e}")

def close_pct(symbol: str, pct: float, side: str = 'all'):
    """
    현재 포지션의 지정 퍼센트만큼 청산합니다.
      - symbol: 거래 심볼 (예: 'XRPUSDT')
      - pct: 0~100 사이의 퍼센트 값 (예: 50 → 50% 청산)
      - side: 'all' (기본), 'long', 또는 'short'
    """
    try:
        # 1) 현재 오픈된 포지션 정보 가져오기
        positions = client.futures_position_information(symbol=symbol)
        # 2) 심볼의 stepSize 조회 (Lot Size 필터)
        info = client.futures_exchange_info()["symbols"]
        sym = next(s for s in info if s["symbol"] == symbol)
        step_size = float(sym["filters"][2]["stepSize"])
        # 소수점 자릿수 계산
        decimals = int(round(-math.log10(step_size), 0))

        for position in positions:
            pos_amt = float(position['positionAmt'])
            if pos_amt == 0:
                continue

            # side 필터: 'long'은 pos_amt>0, 'short'은 pos_amt<0
            if side != 'all':
                if side == 'long' and pos_amt <= 0:
                    continue
                if side == 'short' and pos_amt >= 0:
                    continue

            # 청산 주문 방향 결정: 롱 포지션 → SELL, 숏 포지션 → BUY
            order_side = 'SELL' if pos_amt > 0 else 'BUY'
            position_side = 'LONG' if pos_amt > 0 else 'SHORT'

            # 청산할 계약 수량 = 현재 포지션 수량 * (pct/100)
            raw_qty = abs(pos_amt) * (pct / 100.0)

            # stepSize 단위로 내림(floor) 처리
            qty_floor = math.floor(raw_qty / step_size) * step_size
            # 소수점 자릿수 맞추기
            quantity_to_close = round(qty_floor, decimals)
            if quantity_to_close <= 0:
                print(f"[close_pct] 계산된 수량이 0이므로 건너뜁니다 (symbol={symbol}, pct={pct}%).")
                continue

            # 3) 청산 주문 생성 (reduceOnly=True, 헤지 모드 고려 시 positionSide 사용)
            order = client.futures_create_order(
                symbol=symbol,
                side=order_side,
                type='MARKET',
                quantity=quantity_to_close,
                positionSide=position_side
            )
            print(f"Position for {symbol} partially closed ({pct}%): {order}")
            return order

        print(f"No open position for {symbol} matching side '{side}'.")
    except Exception as e:
        print(f"An error occurred in close_pct: {e}")



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
    
def cheatkey(symbol,
             interval: str = '5m',
             threshold: float = CHEATKEY_THRESHOLD,
             lookback_n: int = CHEATKEY_LOOKBACK,
             use_time_filter: bool = CHEATKEY_TIMEFILTER,
             side: str = "long") -> bool:
    try:
        # --- 데이터 로드 & EMA 계산 ---
        # 1) 데이터 로드
        limit = max(lookback_n + 2, 50)
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'open_time','open','high','low','close','volume',
            'close_time','quote_asset_volume','number_of_trades',
            'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
        ])

        # 2) 타입 변환 & 시간 변환
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)

        # 3) EMA 계산
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()

        idx = len(df) - 1

        # --- 1) 시간 필터: 무조건 0,15,30,45분에만 실행 ---
        if use_time_filter:
            minute = df.at[idx, "open_time"].minute
            if minute not in (0,5, 15,20, 30,35, 45,50):
                return False

        # --- 이하 기존 로직 (slope / noise / candle / diff) ---
        # 2) 인덱스 유효성
        if idx < lookback_n + 1:
            return False

        # 3) EMA 및 기울기
        c12, c26 = df.at[idx,'ema12'], df.at[idx,'ema26']
        p12, p26 = df.at[idx-1,'ema12'], df.at[idx-1,'ema26']
        slope12, slope26 = c12-p12, c26-p26
        if side=="long" and (slope12<=0 or slope26<=0): return False
        if side=="short" and (slope12>=0 or slope26>=0): return False

        # 4) 노이즈 필터
        start = idx-lookback_n+1
        for j in range(start, idx+1):
            prev12, prev26 = df.at[j-1,'ema12'], df.at[j-1,'ema26']
            curr12, curr26 = df.at[j,  'ema12'], df.at[j,  'ema26']
            if side=="long"  and prev12>prev26 and curr12<curr26: return False
            if side=="short" and prev12<prev26 and curr12>curr26: return False

        # 5) 캔들 조건
        o, c = df.at[idx,'open'], df.at[idx,'close']
        block = df.iloc[start:idx+1]
        if side=="long":
            if not (c12<c26 and c>o and all(block['ema12']<block['ema26'])):
                return False
        else:
            if not (c12>c26 and c<o and all(block['ema12']>block['ema26'])):
                return False

        # 6) EMA 차이 감소 & 임계값
        curr_diff, prev_diff = abs(c12-c26), abs(p12-p26)
        if curr_diff < prev_diff and curr_diff <= threshold:
            return True
        return False

    except Exception as e:
        print(f"cheatkey error: {e}")
        return False

def emacross(symbol,
             ema12_period: int = 12,
             ema26_period: int = 26,
             interval: str = '5m',
             side: str = "long",
             use_candle_condition: bool = False) -> bool:
    """
    EMA 골든/데드 크로스 신호.
    
    Parameters:
    - symbol: 거래 심볼 (예: "XRPUSDT")
    - ema12_period: 단기 EMA 기간
    - ema26_period: 장기 EMA 기간
    - interval: 캔들 간격 (기본 '5m')
    - side: "long" (골든크로스) 또는 "short" (데드크로스)
    - use_candle_condition: True 면 양봉/음봉 조건 적용
    
    Returns:
    - bool: 진입/청산 신호 발생 여부
    """
    try:
        # 1) 데이터 가져오기
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=50)
        df = pd.DataFrame(klines, columns=[
            'open_time','open','high','low','close','volume',
            'close_time','quote_asset_volume','number_of_trades',
            'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
        ])
        
        # 2) 타입 변환
        df['open']  = df['open'].astype(float)
        df['close'] = df['close'].astype(float)
        
        # 3) EMA 계산
        df['ema12'] = df['close'].ewm(span=ema12_period, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=ema26_period, adjust=False).mean()
        
        # 4) 직전과 현재 EMA
        prev12, prev26 = df.iloc[-2][['ema12','ema26']]
        curr12, curr26 = df.iloc[-1][['ema12','ema26']]
        
        # 5) 교차 여부 판단
        if side == "long":
            crossed = (prev12 < prev26) and (curr12 > curr26)
        elif side == "short":
            crossed = (prev12 > prev26) and (curr12 < curr26)
        else:
            raise ValueError("side는 'long' 또는 'short'이어야 합니다.")
        
        if not crossed:
            return False
        
        # 6) 선택적 캔들 조건
        if use_candle_condition:
            o = df.iloc[-1]['open']
            c = df.iloc[-1]['close']
            if side == "long" and c <= o:
                return False
            if side == "short" and c >= o:
                return False
        
        return True
    
    except Exception as e:
        print(f"emacross error: {e}")
        return False


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


def cheatkey_value(symbol, interval='5m', ema12_period=12, ema26_period=26):
    """
    최근 3개월 봉들 중 EMA12와 EMA26이 교차하는 봉 바로 전 봉의 EMA 차이(절대값)들에 대해
    90번째 백분위수(상위 90% 값)를 계산하여 반환합니다.
    
    :param symbol: 거래 심볼 (예: 'BTCUSDT')
    :param interval: 캔들 간격 (예: '5m')
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


def candle(symbol: str, side: str, interval: str = "5m") -> bool:
    """
    Binance: 가장 최근 interval 봉을 가져와
      - side=="long"  → 종가 > 시가 일 때 True
      - side=="short" → 종가 < 시가 일 때 True
    """
    klines = get_candles(symbol, interval, 1)  # 마지막 1개 봉 조회 :contentReference[oaicite:0]{index=0}
    if not klines:
        raise RuntimeError(f"No candle data for {symbol} {interval}")
    # klines[0] = [open_time, open, high, low, close, volume, ...]
    o = float(klines[0][1])
    c = float(klines[0][4])
    if side.lower() == "long":
        return c > o
    elif side.lower() == "short":
        return c < o
    else:
        raise ValueError("side must be 'long' or 'short'")
    

