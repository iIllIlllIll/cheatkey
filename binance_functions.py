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

def place_limit_order(symbol: str,
                      side: str,
                      quantity: float,
                      price: float,
                      leverage: int,
                      position_side: str) -> dict:
    """
    position_side: 'LONG' 또는 'SHORT'
    """
    params = {
        "symbol":       symbol,
        "side":         side,
        "type":         "LIMIT",
        "timeInForce":  "GTC",
        "quantity":     quantity,
        "price":        price,
        "positionSide": position_side
    }

    client.futures_change_leverage(symbol=symbol, leverage=leverage)
    return client.futures_create_order(**params)


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


# binance_functions.py

import time
from binance.exceptions import BinanceAPIException

# (기존 코드 생략)

tick_size_map = {}
try:
    exch_info = client.futures_exchange_info()
    for s in exch_info['symbols']:
        # PRICE_FILTER에서 tickSize 추출
        for f in s['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick_size_map[s['symbol']] = float(f['tickSize'])
                break
except Exception as e:
    # 로드 실패 시 빈 딕셔너리 유지
    print(f"Tick size 로드 실패: {e}")

def ensure_limit_order_filled(symbol: str,
                              side: str,
                              usdt_amount: float,
                              price: float,
                              leverage: int,
                              position_side: str,
                              max_wait: float = 120,
                              retry_interval: float = 10,
                              cancel_after: float = 30) -> bool:
    """
    헷지모드 대응:
    - position_side ('LONG'|'SHORT')
    """
    # 1) USDT → 계약 수량 환산
    raw_qty   = usdt_amount / price * leverage
    total_qty = round_qty(symbol, raw_qty)
    if total_qty <= 0:
        message(f"`[{symbol}] USDT 환산 수량이 0이하입니다.`")
        return False

    t_start = time.time()
    t_order = t_start
    tick    = tick_size_map[symbol]
    prec    = int(-math.log10(tick))

    # 2) 첫 지정가 주문 (헷지모드용 positionSide, reduceOnly)
    try:
        order = place_limit_order(
            symbol=symbol,
            side=side,
            quantity=total_qty,
            price=price,
            leverage=leverage,
            position_side=position_side
        )
    except BinanceAPIException as e:
        message(f"`[{symbol}] 주문 실패 ❌: {e.message}`")
        return False

    order_id = order['orderId']

    # 3) 폴링 & 재주문 루프
    while True:
        info     = client.futures_get_order(symbol=symbol, orderId=order_id)
        executed = float(info.get('executedQty', 0))
        remaining= total_qty - executed

        if executed >= total_qty:
            message(f"`[{symbol}] 전량 체결 완료 ✅ (ID={order_id}) executed={executed}`")
            return True
        if 0 < executed < total_qty:
            message(f"`[{symbol}] 부분 체결 완료 ☑️ ID={order_id} executed={executed}, rem={remaining}`")

        now = time.time()
        if now - t_start > max_wait:
            message(f"`[{symbol}] 타임아웃 ⛔ {max_wait}s 미체결 → 실패`")
            return False

        if now - t_order > cancel_after:
            client.futures_cancel_order(symbol=symbol, orderId=order_id)

            if remaining > 0:
                # 호가 재계산
                book     = client.futures_order_book(symbol=symbol, limit=5)
                best_bid = float(book['bids'][0][0])
                best_ask = float(book['asks'][0][0])
                new_price = round((best_bid + tick) if side=="BUY" else (best_ask - tick), prec)

                order = place_limit_order(
                    symbol=symbol,
                    side=side,
                    quantity=remaining,
                    price=new_price,
                    leverage=leverage,
                    position_side=position_side
                )
                order_id = order['orderId']
                t_order  = now

        time.sleep(retry_interval)


def close_limit(symbol: str,
                side: str,
                leverage: int,
                max_wait: float = 120,
                retry_interval: float = 10,
                cancel_after: float = 30) -> bool:
    """
    포지션 잔량이 완전히 0이 될 때까지 지정가→체결 보증 반복.
    Dust(잔량 < stepSize) 단계에서는 시장가 주문으로 마무리 청산.
    """
    position_side = 'LONG' if side=='long' else 'SHORT'
    order_side    = 'SELL' if side=='long' else 'BUY'

    while True:
        # 1) 남은 포지션 수량 조회
        pos_info = client.futures_position_information(symbol=symbol)
        qty = 0.0
        for p in pos_info:
            if p['symbol']==symbol and p['positionSide']==position_side:
                qty = abs(float(p['positionAmt']))
                break

        # 완전 청산 완료
        if qty <= 0:
            message(f"`[{symbol}] 포지션 청산 완료 ✅`")
            return True

        # 2) stepSize, minQty 조회 (LOT_SIZE 필터에서)
        info     = client.futures_exchange_info()
        sym      = next(s for s in info['symbols'] if s['symbol']==symbol)
        lot      = next(f for f in sym['filters'] if f['filterType']=='LOT_SIZE')
        step     = float(lot['stepSize'])
        min_qty  = float(lot['minQty'])
        prec_qty = int(round(-math.log10(step), 0))

        # 3) 청산 주문 단가 계산 (호가창 기반)
        book = client.futures_order_book(symbol=symbol, limit=5)
        tick = tick_size_map[symbol]
        prec = int(round(-math.log10(tick), 0))
        if side=='long':
            px = float(book['asks'][0][0]) - tick
        else:
            px = float(book['bids'][0][0]) + tick
        limit_price = round(px, prec)

        # 4) Dust 체크: 남은 qty가 최소수량 미만이면 시장가로 마무리
        if qty < min_qty:
            try:
                client.futures_change_leverage(symbol=symbol, leverage=leverage)
                client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=qty,
                    positionSide=position_side
                )
                return True
            except BinanceAPIException as e:
                message(f"`[{symbol}] Dust 시장가 청산 실패: {e.message}`")
                return False

        # 5) 남은 전체 포지션 지정가 체결 보증
        usdt_amount = qty * limit_price / leverage
        success = ensure_limit_order_filled(
            symbol=symbol,
            side=order_side,
            usdt_amount=usdt_amount,
            price=limit_price,
            leverage=leverage,
            position_side=position_side,
            max_wait=max_wait,
            retry_interval=retry_interval,
            cancel_after=cancel_after
        )
        if not success:
            message(f"`[{symbol}] 지정가 청산 실패 ❌`")
            return False

        # 6) 아주 짧게 대기 후 반복
        time.sleep(1)



def close_limit_usdt(symbol: str,
                     side: str,
                     usdt_amount: float,
                     leverage: int,
                     max_wait: float = 120,
                     retry_interval: float = 10,
                     cancel_after: float = 30) -> bool:
    """
    USDT 단위 청산 → 포지션이 남아있으면 재시도
    """
    position_side = 'LONG' if side=='long' else 'SHORT'
    order_side    = 'SELL' if side=='long' else 'BUY'

    while True:
        # 1) 남은 포지션 수량 조회
        pos_info = client.futures_position_information(symbol=symbol)
        qty = 0.0
        for p in pos_info:
            if p['symbol']==symbol and p['positionSide']==position_side:
                qty = abs(float(p['positionAmt']))
                break

        if qty <= 0:
            message(f"`[{symbol}] 포지션 청산 완료 ✅`")
            return True

        # 2) 단가 계산
        book = client.futures_order_book(symbol=symbol, limit=5)
        tick = tick_size_map[symbol]
        prec = int(round(-math.log10(tick), 0))
        if side=='long':
            px = float(book['asks'][0][0]) - tick
        else:
            px = float(book['bids'][0][0]) + tick
        limit_price = round(px, prec)

        # 3) 요청받은 USDT 기준 재계산
        #    (매번 usdt_amount 고정 → 원하는 만큼 반복 청산)
        success = ensure_limit_order_filled(
            symbol=symbol,
            side=order_side,
            usdt_amount=usdt_amount,
            price=limit_price,
            leverage=leverage,
            position_side=position_side,
            max_wait=max_wait,
            retry_interval=retry_interval,
            cancel_after=cancel_after
        )
        if not success:
            message(f"`[{symbol}] USDT 청산 중 오류 발생 ❌`")
            return False

        # 남은 포지션이 다시 너무 작으면 종료
        if qty * limit_price / leverage < tick:
            return True

        time.sleep(1)


def override_atr(
                              symbol: str,
                              atr_period: int,
                              atr_pct_threshold: float) -> bool:
    """
    바이낸스에서 symbol의 30분봉을 받아와,
    가장 최근에 완결된 봉(=API가 반환하는 두 번째 마지막 candle)의 ATR%를 계산한 뒤
    ATR% ≤ atr_pct_threshold 이면 True, 아니면 False 반환.

    client: Binance futures client (e.g. from binance.client.Client)
    symbol: 거래 심볼, 예: "XRPUSDT"
    atr_period: ATR 계산에 사용할 기간 (e.g. 14)
    atr_pct_threshold: 임계 ATR% (e.g. 1.0)
    """
    # 1) ATR 계산용으로 (atr_period + 2)개의 30분봉을 조회
    klines = client.futures_klines(
        symbol=symbol,
        interval='30m',
        limit=atr_period * 50
    )

    # 2) DataFrame으로 변환
    df = pd.DataFrame(klines, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','num_trades',
        'taker_buy_base','taker_buy_quote','ignore'
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)

    # 3) True Range 계산
    high_low        = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close  = (df['low']  - df['close'].shift(1)).abs()
    df['tr']        = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    # 4) ATR 및 ATR% 계산
    df['atr']         = df['tr'].rolling(window=atr_period).mean()
    df['atr_pct']     = df['atr'] / df['close'] * 100

    # 5) 가장 최근 완결된 30분봉은 df.iloc[-2]
    if len(df) < atr_period + 2:
        # 데이터가 충분치 않으면 기본 False
        return False

    atr_pct_val = df['atr_pct'].iat[-2]
    return atr_pct_val <= atr_pct_threshold

def round_qty(symbol: str, raw_qty: float) -> float:
    """
    raw_qty를 해당 심볼의 LOT_SIZE.stepSize 단위로 내림(버림)하고,
    필요 소수점 자리수에 맞춰 반올림하여 반환합니다.
    예) stepSize=0.001, raw_qty=1.23456 → qty=1.234
    """
    # 1) 거래소 정보에서 심볼 필터 가져오기
    info = client.futures_exchange_info()
    sym_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
    if sym_info is None:
        raise ValueError(f"Symbol not found in exchange_info: {symbol}")

    # 2) LOT_SIZE 필터에서 stepSize 추출
    lot_filter = next((f for f in sym_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
    if lot_filter is None:
        raise ValueError(f"LOT_SIZE filter not found for symbol: {symbol}")
    step_size = float(lot_filter['stepSize'])

    # 3) 몇 자리 소수점까지 써야 하는지 계산
    precision = int(round(-math.log10(step_size), 0))

    # 4) raw_qty를 step_size 단위로 내림 (floor)
    qty = math.floor(raw_qty / step_size) * step_size

    # 5) precision에 맞춰 반올림하여 반환
    return round(qty, precision)

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
    
def cheatkey(
    symbol,
    interval: str = '5m',
    threshold: float = CHEATKEY_THRESHOLD,
    lookback_n: int = CHEATKEY_LOOKBACK,
    use_time_filter: bool = CHEATKEY_TIMEFILTER,
    side: str = "long"
) -> bool:
    try:
        # --- 데이터 로드 & EMA 계산 ---
        limit = max(lookback_n * 5, 50 * 10)
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'open_time','open','high','low','close','volume',
            'close_time','quote_asset_volume','number_of_trades',
            'taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'
        ])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()

        # --- 직전 완전 종료된 5분봉 인덱스 ---
        idx = len(df) - 2

        # 1) 시간 필터: 직전 봉의 open_time.minute 가 0,15,30,45 인지
        if use_time_filter:
            minute = df.at[idx, "open_time"].minute
            if minute not in (0, 15, 30, 45):
                return False

        # 2) 인덱스 유효성 확인
        if idx < lookback_n + 1:
            return False

        # 3) EMA slope 필터
        c12, c26 = df.at[idx, 'ema12'], df.at[idx, 'ema26']
        p12, p26 = df.at[idx-1, 'ema12'], df.at[idx-1, 'ema26']
        print(c12, c26)
        print(df.at[idx, "open_time"].minute)
        slope12, slope26 = c12 - p12, c26 - p26
        # if side == "long" and (slope12 <= 0 or slope26 <= 0):
        #     return False
        # if side == "short" and (slope12 >= 0 or slope26 >= 0):
        #     return False

        # 4) 노이즈 필터
        start = idx - lookback_n + 1
        for j in range(start, idx + 1):
            prev12, prev26 = df.at[j-1, 'ema12'], df.at[j-1, 'ema26']
            curr12, curr26 = df.at[j,   'ema12'], df.at[j,   'ema26']
            
            print(df.at[j, "open_time"].minute)
            print(curr12, curr26)
            print(prev12, prev26)
            if side == "long" and prev12 > prev26 and curr12 < curr26:
                return False
            if side == "short" and prev12 < prev26 and curr12 > curr26:
                return False

        # 5) 캔들 필터
        o, c = df.at[idx, 'open'], df.at[idx, 'close']
        block = df.iloc[start:idx+1]
        if side == "long":
            if not (c12 < c26 and c > o and all(block['ema12'] < block['ema26'])):
                return False
        else:
            if not (c12 > c26 and c < o and all(block['ema12'] > block['ema26'])):
                return False

        # 6) EMA 차이 필터 (직전 봉 대비 차이 감소 & threshold 이하)
        curr_diff = abs(c12 - c26)
        prev_diff = abs(p12 - p26)
        if curr_diff < prev_diff and curr_diff <= threshold:
            return True

        return False

    except Exception as e:
        print(f"cheatkey error: {e}")
        return False


def emacross(
    symbol: str,
    ema12_period: int = 12,
    ema26_period: int = 26,
    interval: str = '5m',
    side: str = "long",
    use_candle_condition: bool = False
) -> bool:
    """
    EMA 골든/데드 크로스 신호 (직전 완전 종료된 봉 사용).

    - 항상 ‘마지막으로 완전 종료된’ 5분봉(idx = -2)과
      그 이전 봉(idx = -3)을 검사합니다.
    """
    try:
        # 1) 데이터 가져오기
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=250)
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

        # 4) 인덱스 설정: -1은 아직 진행 중인 봉이므로, -2와 -3 사용
        curr_idx = len(df) - 2   # 마지막 완전 종료된 봉
        prev_idx = curr_idx - 1  # 그 이전 봉

        # 5) EMA 값 가져오기
        prev12, prev26 = df.at[prev_idx, 'ema12'], df.at[prev_idx, 'ema26']
        curr12, curr26 = df.at[curr_idx, 'ema12'], df.at[curr_idx, 'ema26']

        # 6) 교차 여부 판단
        if side == "long":
            crossed = (prev12 < prev26) and (curr12 > curr26)
        elif side == "short":
            crossed = (prev12 > prev26) and (curr12 < curr26)
        else:
            raise ValueError("side는 'long' 또는 'short'이어야 합니다.")
        if not crossed:
            return False

        # 7) 선택적 캔들 조건 (바로 직전 완전 종료된 봉 사용)
        if use_candle_condition:
            o = df.at[curr_idx, 'open']
            c = df.at[curr_idx, 'close']
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
    

