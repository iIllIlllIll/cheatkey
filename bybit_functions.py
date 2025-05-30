import time
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_DOWN

from init_functions import *
from urllib.parse import urlencode
from typing import Optional
import logging
logger = logging.getLogger(__name__)
from json.decoder import JSONDecodeError

# Bybit REST API base
BASE_URL = 'https://api.bybit.com'

RECV_WINDOW = 5000  # Bybit API 요청의 응답 대기 시간 (밀리초), 기본값 5000ms
HTTP_TIMEOUT = 10   # HTTP 요청의 타임아웃 (초), 필요에 따라 조절


# generate_signature 함수는 이전 수정 내용 (POST일 때 json.dumps에 separators 제거)을 유지해야 합니다.
def generate_signature(api_secret: str, timestamp: str, api_key: str, method: str, params: dict = None, json_data: dict = None) -> str:
    param_str = ""
    if method.upper() == 'POST':
        if json_data is not None:
            param_str = json.dumps(json_data) 
        else:
            param_str = ""
    else: # GET request
        if params:
            sorted_params = sorted(params.items())
            param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
        else:
            param_str = ""

    param_str = param_str.strip() # 혹시 모를 외부 공백 제거

    sign_string = str(timestamp) + str(api_key) + str(RECV_WINDOW) + str(param_str)

    hash_obj = hmac.new(api_secret.encode('utf-8'), sign_string.encode('utf-8'), hashlib.sha256)
    return hash_obj.hexdigest()


def bybit_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
    """
    Bybit API v5에 요청을 보냅니다.
    method: 'GET' 또는 'POST'
    endpoint: API 엔드포인트 (예: '/v5/market/tickers')
    params: GET 요청의 쿼리 파라미터 (딕셔너리)
    json_data: POST 요청의 JSON 바디 (딕셔너리)
    """
    url = BASE_URL + endpoint
    timestamp = str(int(time.time() * 1000))

    headers = {
        'X-BAPI-API-KEY': bybit_api_key,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-RECV-WINDOW': str(RECV_WINDOW),
        'Content-Type': 'application/json' # POST 요청에 필요
    }

    req_params_for_signature = params # 서명 생성용 파라미터
    req_json_for_signature = json_data # 서명 생성용 JSON 데이터

    # HTTP 요청에 사용될 실제 인자
    request_kwargs = {}

    if method.upper() == 'GET':
        # GET 요청은 파라미터를 URL 쿼리 스트링으로 보냅니다.
        # json_data는 GET 요청에서 사용되지 않습니다.
        if params:
            request_kwargs['params'] = params
        else:
            request_kwargs['params'] = {} # params가 None일 경우 빈 딕셔너리 전달
        
        # GET 요청의 서명은 쿼리 파라미터로 생성됩니다.
        req_params_for_signature = params 
        req_json_for_signature = None # GET 요청 시 json_data는 서명에 사용되지 않음

    elif method.upper() == 'POST':
        # POST 요청은 JSON 데이터를 본문으로 보냅니다.
        if json_data:
            request_kwargs['json'] = json_data # requests 라이브러리에서는 'json' 키워드 사용
        else:
            request_kwargs['json'] = {} # json_data가 None일 경우 빈 딕셔너리 전달
        
        # POST 요청의 서명은 JSON 본문으로 생성됩니다.
        req_params_for_signature = None # POST 요청 시 params는 서명에 사용되지 않음
        req_json_for_signature = json_data

    else:
        raise ValueError(f"지원하지 않는 HTTP Method: {method}. 'GET' 또는 'POST'만 가능합니다.")

    # 서명 생성
    headers['X-BAPI-SIGN'] = generate_signature(
        bybit_api_secret, timestamp, bybit_api_key, method,
        params=req_params_for_signature, # GET 요청에만 사용
        json_data=req_json_for_signature # POST 요청에만 사용
    )

    try:
        if method.upper() == 'GET':
            resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, **request_kwargs)
        elif method.upper() == 'POST':
            resp = requests.post(url, headers=headers, timeout=HTTP_TIMEOUT, **request_kwargs)
        
        resp.raise_for_status() # HTTP 200 OK가 아니면 HTTPError 발생
        
        response_data = resp.json()
        return response_data

    except requests.exceptions.HTTPError as e:
        # 4xx 또는 5xx 응답 처리
        error_text = e.response.text if e.response else 'No response text'
        print(f"HTTP Error: {e.response.status_code} - {error_text} for url: {url} / request_kwargs={request_kwargs}")
        raise RuntimeError(f"HTTP Error: {e.response.status_code} - {error_text}")
    except requests.exceptions.RequestException as e:
        # 네트워크 문제 등 요청 자체의 오류
        print(f"Request Error for {url}: {e}")
        raise RuntimeError(f"Request Error: {e}")
    except json.JSONDecodeError:
        # JSON 응답이 아닐 경우
        print(f"JSON Decode Error for {url}. Response text: {resp.text}")
        raise RuntimeError(f"JSON Decode Error: Invalid response from API.")
    except Exception as e:
        # 기타 알 수 없는 오류
        print(f"An unexpected error occurred during API request to {url}: {e}")
        raise RuntimeError(f"Unexpected API request error: {e}")



# --- 주요 함수 모음 -----------------------------------------------

MAX_ORDER_AGE = 180  # 오래된 주문 기준 (초)

def cancel_old_orders(symbol: str, max_order_age: float=MAX_ORDER_AGE):
    """
    Bybit V5: 지정한 심볼의 활성 주문을 가져와서
    max_order_age 초보다 오래된 주문들을 취소합니다.
    """
    # 1) 현재 시간(ms) 및 카테고리 설정 (USDT-선물=linear)
    now_ts = int(time.time() * 1000)
    category = "linear" if symbol.upper().endswith("USDT") else "inverse"

    # 2) 활성 오더 조회: /v5/order/realtime
    endpoint = "/v5/order/realtime"
    params = {
        "category":   category,
        "symbol":     symbol.upper(),
        "page":       1,
        "limit":      50,
        "timestamp":  now_ts,
        "api_key":    bybit_api_key
    }
    params["sign"] = _sign(params)

    try:
        resp = requests.get(BASE_URL + endpoint, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[cancel_old_orders] Failed to fetch open orders: {e}")
        return

    if data.get("retCode", 1) != 0:
        print(f"[cancel_old_orders] API error {data.get('retCode')}: {data.get('retMsg')}")
        return

    orders = data.get("result", {}).get("data", []) or []
    if not orders:
        return

    # 3) 오래된 주문만 걸러서 취소
    for order in orders:
        order_id   = order.get("orderId")
        create_ts  = order.get("createTime")  # milliseconds
        age_sec    = (now_ts - create_ts) / 1000.0

        if age_sec > max_order_age:
            cancel_ep = "/v5/order/cancel"
            cancel_params = {
                "category":  category,
                "symbol":    symbol.upper(),
                "orderId":   order_id,
                "timestamp": now_ts,
                "api_key":   bybit_api_key
            }
            cancel_params["sign"] = _sign(cancel_params)
            try:
                c_resp = requests.post(BASE_URL + cancel_ep, params=cancel_params, timeout=5)
                c_resp.raise_for_status()
                print(f"Canceled old order {order_id}, age {age_sec:.1f}s")
            except Exception as ce:
                print(f"Failed to cancel {order_id}: {ce}")

def get_candles(symbol: str, interval: str, limit: int = 200) -> list:
    """
    Bybit API v5를 통해 캔들스틱 데이터를 가져옵니다.
    symbol: 예: "XRPUSDT"
    interval: "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
    limit: 가져올 캔들 수 (최대 1000)
    """
    endpoint = "/v5/market/kline"
    category = "linear" if symbol.upper().endswith("USDT") else "inverse"

    # Bybit API v5의 interval 형식에 맞게 변환
    bybit_interval = interval
    if isinstance(interval, str): # 문자열인 경우에만 변환 시도
        if interval.lower().endswith('m'):
            bybit_interval = interval.lower().replace('m', '')
        elif interval.lower().endswith('h'):
            bybit_interval = str(int(interval.lower().replace('h', '')) * 60)
        elif interval.lower() == 'd':
            bybit_interval = 'D'
        elif interval.lower() == 'w':
            bybit_interval = 'W'
        elif interval.lower() == 'mo': # Bybit에서는 'M'
            bybit_interval = 'M'
        
        # 숫자인지 확인하여 문자열로 변환 (Bybit API는 숫자를 문자열로 기대)
        if bybit_interval.isdigit():
            bybit_interval = str(int(bybit_interval))
    
    logger.debug(f"캔들 요청: {symbol}, interval: {bybit_interval}, limit: {limit}, category: {category}")

    params = {
        "category": category,
        "symbol": symbol.upper(),
        "interval": bybit_interval,
        "limit": limit,
    }

    resp = bybit_request('GET', endpoint, params=params, json_data=None)

    logger.debug(f"bybit_request로부터 받은 캔들 응답 (Raw): {resp}")

    if resp and resp.get('retCode') == 0 and resp.get('result') and resp['result'].get('list'):
        candles_raw = resp['result']['list']
        logger.debug(f"캔들 raw 데이터 (list 필드): {candles_raw}")
        
        # --- 핵심 수정: 여기서 딕셔너리로 변환하는 로직을 제거합니다. ---
        # create_tendency_chart가 기대하는 원본 리스트 형태를 그대로 반환합니다.
        # return candles_raw

        # 만약 raw 데이터를 사용하기 전에 몇 가지 변환(예: 문자열을 숫자로)이 필요하다면 아래처럼 직접 변환하세요.
        # 그러나 'KeyError: 0'을 해결하려면 리스트 인덱스 접근이 가능한 구조여야 합니다.
        # 따라서 여기서는 데이터를 원본 리스트의 리스트 형태로 반환합니다.
        
        # Bybit API의 list 데이터는 ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
        # create_tendency_chart에서 `candle[0]`으로 timestamp에 접근하므로, 이 원본 형태를 유지합니다.

        # 문자열 숫자를 float/int로 변환하는 작업은 init_functions.py의 create_tendency_chart에서 처리하는 것이 일반적입니다.
        # 예를 들어, create_tendency_chart에서 DataFrame을 만들 때 다음과 같이 변환할 수 있습니다:
        # 'Open': [float(candle[1]) for candle in candles],

        logger.debug(f"Successfully fetched and formatted {len(candles_raw)} candles for {symbol} ({bybit_interval}). First timestamp: {candles_raw[0][0]}, Last timestamp: {candles_raw[-1][0]}")
        return candles_raw
    else:
        logger.info(f"Bybit API가 {symbol}에 대한 캔들 데이터를 반환하지 않았습니다. (candles_raw is empty)")
        return []

# 2) 잔고 조회
def get_futures_asset_balance(asset: str = 'USDT') -> float:
    """
    USDT 선물 계정의 사용 가능한 잔고 조회 (Unified Account).
    Bybit V5: GET /v5/asset/transfer/query-account-coins-balance
    """
    endpoint = "/v5/asset/transfer/query-account-coins-balance"
    params = {
        "accountType": "UNIFIED",  # USDT 선물은 unified 계정 사용
        "coin":        asset
    }
    data = bybit_request("GET", endpoint, params)
    rows = data.get("result", {}).get("balance", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return 0.0

    for entry in rows:
        if entry.get("coin") == asset:
            # availableBalance 키에 남은 잔고가 문자열로 들어옵니다
            return float(entry.get("transferBalance", 0))
    return 0.0


def get_asset_balance(symbol: str, side: str = 'all'):
    pos = bybit_request('GET', '/private/linear/position/list', {'symbol': symbol})
    for p in pos:
        amt = float(p['size'])
        if amt == 0: continue
        if side=='long' and amt>0: return float(p['position_margin'])
        if side=='short' and amt<0: return float(p['position_margin'])
        if side=='all': return float(p['position_margin'])
    return 0.0




# 3) 레버리지 변경
# set_leverage 함수 내에서 json_body를 이렇게 구성:
def set_leverage(symbol: str, leverage: int, side: str = "long"):
    endpoint = "/v5/position/set-leverage"
    # Bybit이 기대하는 정확한 키 순서대로 딕셔너리 구성
    # 파이썬 3.7+ 버전부터 딕셔너리는 삽입 순서를 유지합니다.
    json_body = { # 이름은 json_body 그대로 유지
        "category": "linear", # <--- 이 순서를 지켜주세요.
        "symbol": symbol,
        "buyLeverage": str(leverage),
        "sellLeverage": str(leverage),
    }

    return bybit_request(
        method="POST",
        endpoint=endpoint,
        params=None,
        json_data=json_body
    )


def place_market_order(
    symbol: str,
    qty: float,
    leverage: int,
    side: str,
    hedge: bool = True,
    reduce_only: bool = False
):
    """
    symbol: 거래 심볼 (e.g. 'XRPUSDT')
    qty: 주문 수량
    leverage: 레버리지 (통합 모드일 땐 보통 0)
    side: 'Buy' or 'Sell'
    hedge: 헤지 모드 사용 여부
    reduce_only: 포지션 감소 전용 주문 여부
    """
    # 레버리지 설정 (청산 주문일 땐 건너뜀)
    if not reduce_only and leverage > 0:
        set_leverage(symbol, leverage, side)

    adjusted_qty = round_qty(symbol, qty)
    if adjusted_qty <= 0:
        raise ValueError(f"Adjusted quantity is zero: {adjusted_qty}")

    json_body = {
        "category":     "linear",
        "symbol":       symbol,
        "orderType":    "Market",
        "side":         side,
        "qty":          str(adjusted_qty),
        "timeInForce":  "ImmediateOrCancel",
        "isLeverage":   1,
    }

    if hedge:
        # 헤지 모드: 오픈 vs. 청산에 따라 positionIdx 분기
        if not reduce_only:
            # 오픈 주문: Buy → 롱(1), Sell → 숏(2)
            json_body["positionIdx"] = 1 if side.upper() == "BUY" else 2
        else:
            # 청산 주문: Sell → 롱(1), Buy → 숏(2)
            json_body["positionIdx"] = 1 if side.upper() == "SELL" else 2

    if reduce_only:
        json_body["reduceOnly"] = True

    print(f"DEBUG ▶ order/create body: {json_body}")
    return bybit_request(
        method="POST",
        endpoint="/v5/order/create",
        params=None,
        json_data=json_body
    )



def place_limit_order(symbol: str, price: float, qty: float, leverage: int, side: str):
    """
    지정가 주문을 전송하고 Bybit API의 전체 응답 딕셔너리를 반환합니다.
    """
    set_leverage(symbol, leverage, side)

    adjusted_qty = round_qty(symbol, qty)
    adjusted_price = round_price(symbol, price)

    if adjusted_qty <= 0:
        raise ValueError(f"Adjusted quantity for {symbol} is zero or negative: {adjusted_qty}. Original qty: {qty}")
    if adjusted_price <= 0:
        raise ValueError(f"Adjusted price for {symbol} is zero or negative: {adjusted_price}. Original price: {price}")

    endpoint = "/v5/order/create"
    json_body = {
        "category": "linear",
        "symbol": symbol,
        "orderType": "Limit",
        "price": str(adjusted_price),
        "side": "Buy" if side == "long" else "Sell",
        "qty": str(adjusted_qty),
        "timeInForce": "GoodTillCancel",
        "isLeverage": 1,
        "positionIdx": 1 if side == "long" else 2,
    }
    # bybit_request가 이제 응답 딕셔너리를 그대로 반환합니다.
    return bybit_request("POST", endpoint, json_data=json_body)


def execute_market_order(symbol: str, percentage: float, leverage: int, side: str):
    usdt_bal = get_futures_asset_balance()
    usdt_amt = usdt_bal * percentage / 100
    price    = get_current_market_price(symbol)
    size     = usdt_amt / price * leverage
    return place_market_order(symbol, round_qty(symbol, size), leverage, side)

def execute_market_order_usdt(symbol: str, usdt_amt: float, leverage: int, side: str):
    price = get_current_market_price(symbol)
    size  = usdt_amt / price * leverage
    return place_market_order(symbol, round_qty(symbol, size), leverage, side)



def execute_limit_order(symbol: str, price: float, percentage: float, leverage: int, side: str):
    usdt_bal = get_futures_asset_balance()
    usdt_amt = usdt_bal * percentage / 100
    price    = round_price(symbol, price)
    size     = usdt_amt / price * leverage
    return place_limit_order(symbol, price, round_qty(symbol, size), leverage, side)


def get_positions(symbol: str) -> list:
    """
    지정 심볼의 모든 활성 포지션 리스트를 반환합니다.
    - symbol: 'XRPUSDT' 같은 거래 심볼
    반환: Bybit v5 /v5/position/list → result.list (list of dict)
    """
    params = {
        "category": "linear",    # USDT 페어
        "symbol":   symbol.upper()
    }
    resp = bybit_request("GET", "/v5/position/list", params=params)
    # Bybit v5 응답 구조에서 result.list 경로로 포지션 정보 접근
    return resp.get("result", {}).get("list", []) or []

# 6) 청산 함수
def close(symbol: str, side: str = 'all'):
    positions = get_positions(symbol)
    if not positions:
        return {"retCode": 0, "retMsg": "No active position"}

    closed = []
    for p in positions:
        pos_side = p['side']             # 'Buy' or 'Sell'
        size = float(p['size'] or 0)
        if size <= 0:
            continue

        if (side == 'long' and pos_side == 'Buy') or \
           (side == 'short' and pos_side == 'Sell'):
            # 롱 청산 -> Sell, 숏 청산 -> Buy
            close_side = 'Sell' if pos_side=='Buy' else 'Buy'
            res = place_market_order(
                symbol,
                abs(size),
                leverage=0,
                side=close_side,
                hedge=True,
                reduce_only=True       # ← 여기!
            )
            closed.append(res)

        elif side == 'all':
            close_side = 'Sell' if pos_side=='Buy' else 'Buy'
            res = place_market_order(
                symbol,
                abs(size),
                leverage=0,
                side=close_side,
                hedge=True,
                reduce_only=True       # ← 그리고 여기!
            )
            closed.append(res)

    return {"retCode": 0,
            "retMsg": f"{len(closed)} positions closed",
            "details": closed}

def close_usdt(symbol: str, leverage: int, usdt: float, side: str = 'all'):
    """
    USDT 금액만큼 지정된 심볼의 포지션을 종료합니다.
      - symbol: 'XRPUSDT' 등
      - leverage: 사용 중인 레버리지
      - usdt: 청산에 사용할 USDT 금액
      - side: 'long', 'short' 또는 'all'
    """
    endpoint_position_list = "/v5/position/list"
    params_position_list = {
        "category": "linear",
        "symbol":   symbol.upper()
    }

    try:
        # 현재 포지션 조회
        pos_resp = bybit_request(
            method="GET",
            endpoint=endpoint_position_list,
            params=params_position_list,
            json_data=None
        )
        positions = pos_resp.get('result', {}).get('list', [])

        if not positions:
            print(f"INFO: {symbol}에 대한 활성 포지션이 없습니다.")
            return {"retCode": 0, "retMsg": "No active position"}

        closed_positions = []
        for p in positions:
            pos_side    = p.get('side')                 # 'Buy' 또는 'Sell'
            pos_size    = float(p.get('size', 0))       # 현재 계약 수
            entry_price = float(p.get('avgPrice', 0))   # 평균 진입 가격

            # 유효치 검증
            if pos_size <= 0 or entry_price <= 0:
                continue

            # 요청 방향에 맞춰 필터링
            if not ((side == 'long'  and pos_side == 'Buy')   or
                    (side == 'short' and pos_side == 'Sell') or
                    (side == 'all')):
                continue

            # 청산할 수량 계산 (USDT 단위 → 계약 수량)
            raw_qty = usdt * leverage / entry_price
            qty_to_close = min(abs(pos_size), raw_qty)
            rounded_qty = round_qty(symbol, qty_to_close)
            if rounded_qty <= 0:
                continue

            # 청산 방향 결정: 롱 포지션 → 'Sell', 숏 포지션 → 'Buy'
            close_side = 'Sell' if pos_side == 'Buy' else 'Buy'

            # 헤지 모드, reduce-only 플래그 추가
            result = place_market_order(
                symbol=symbol,
                qty=rounded_qty,
                leverage=leverage,
                side=close_side,
                hedge=True,
                reduce_only=True
            )
            closed_positions.append(result)

        if closed_positions:
            return {
                "retCode": 0,
                "retMsg": f"Total {len(closed_positions)} partial positions closed for {symbol}",
                "details": closed_positions
            }
        else:
            return {
                "retCode": 0,
                "retMsg": f"No active position or quantity to close for {symbol} in specified direction."
            }

    except RuntimeError as e:
        print(f"ERROR: {symbol} 포지션 정보를 가져오는 중 오류 발생: {e}")
        raise

# 7) 유틸: 현재 시장가, stepSize, rounding

def get_current_market_price(symbol: str):
    """
    Bybit V5 API에서 현재 시장 가격(최신 거래 가격)을 가져옵니다.
    """
    endpoint = "/v5/market/tickers"
    params = {
        "category": "linear",
        "symbol": symbol
    }
    
    
    # bybit_request는 이제 전체 응답 딕셔너리를 반환합니다.
    full_response_data = bybit_request('GET', endpoint, params=params) 
    

    # --- 핵심 수정: 'result' 키 내부의 'list'에 접근 ---
    if full_response_data and 'result' in full_response_data and full_response_data['result'].get('list'):
        ticker_list = full_response_data['result']['list']
        
        if not ticker_list:
            raise RuntimeError(f"Could not retrieve market price for {symbol}: 응답의 'list'가 비어있습니다.")
        
        # 첫 번째 항목에서 'lastPrice' 추출
        last_price = ticker_list[0].get('lastPrice')
        if last_price:
            return float(last_price)
        else:
            raise RuntimeError(f"Could not retrieve market price for {symbol}: 'lastPrice'가 응답에 없습니다. 전체 응답: {full_response_data}")
    else:
        # 오류 메시지를 좀 더 구체적으로 만듭니다.
        error_detail = ""
        if full_response_data is None:
            error_detail = "full_response_data가 None입니다."
        elif not full_response_data:
            error_detail = "full_response_data가 비어있습니다."
        elif 'result' not in full_response_data:
            error_detail = "'result' 키가 응답 데이터에 없습니다."
        elif not full_response_data['result'].get('list'):
            error_detail = "'result' 내부에 'list' 키가 없거나 비어있습니다."
        
        raise RuntimeError(f"Could not retrieve market price for {symbol}: {error_detail} 전체 응답: {full_response_data}")


symbol_info_cache = {}

def get_symbol_info(symbol: str):
    """
    Bybit API에서 심볼의 거래 규칙 (stepSize, tickSize 등)을 가져와 캐시합니다.
    """
    if symbol in symbol_info_cache:
        return symbol_info_cache[symbol]

    endpoint = "/v5/market/instruments-info"
    params = {
        "category": "linear",
        "symbol": symbol # 특정 심볼만 요청
    }

    # --- 이 부분이 중요합니다. GET 요청은 params를 사용해야 합니다! ---    
    # bybit_request 함수 호출 시 method='GET'에 params를 전달합니다.
    # json_data는 None으로 두어야 합니다.
    full_response_data = bybit_request('GET', endpoint, params=params, json_data=None) # json_data=None 명시



    if full_response_data and 'result' in full_response_data and full_response_data['result'].get('list'):
        instrument_list = full_response_data['result']['list']
        
        if not instrument_list:
            raise RuntimeError(f"Could not retrieve symbol info for {symbol}: 'list' is empty in response.")

        # 첫 번째 항목에서 필요한 정보 추출
        # 여기서는 특정 심볼을 요청했으므로, 리스트에 해당 심볼 하나만 있을 것으로 예상
        instrument_info = instrument_list[0]
        
        # 'lotSizeFilter'와 'priceFilter' 존재 여부 확인
        if 'lotSizeFilter' not in instrument_info or 'priceFilter' not in instrument_info:
            raise RuntimeError(f"Could not retrieve symbol info for {symbol}: Missing lotSizeFilter or priceFilter in response.")

        qty_step = instrument_info['lotSizeFilter']['qtyStep']
        tick_size = instrument_info['priceFilter']['tickSize']
        
        # 캐시에 저장
        symbol_info_cache[symbol] = {
            'qtyStep': float(qty_step),
            'tickSize': float(tick_size)
        }
        return symbol_info_cache[symbol]
    else:
        error_detail = ""
        if full_response_data is None:
            error_detail = "full_response_data가 None입니다."
        elif not full_response_data:
            error_detail = "full_response_data가 비어있습니다."
        elif 'result' not in full_response_data:
            error_detail = "'result' 키가 응답 데이터에 없습니다."
        elif not full_response_data['result'].get('list'):
            error_detail = "'result' 내부에 'list' 키가 없거나 비어있습니다."
        
        raise RuntimeError(f"Could not retrieve symbol info for {symbol}: {error_detail} Full response: {full_response_data}")


def step_and_tick(symbol: str):
    """
    Bybit V5 API에서 심볼의 수량 스텝(lot_size_filter.qtyStep)과 가격 틱 사이즈(price_filter.tickSize)를 가져옵니다.
    """
    s = get_symbol_info(symbol)
    if s:
        lot_size_filter = s.get('lotSizeFilter', {})
        price_filter = s.get('priceFilter', {})
        
        qty_step = float(lot_size_filter.get('qtyStep', '0.001'))
        price_tick = float(price_filter.get('tickSize', '0.01'))
        
        return qty_step, price_tick
    
    raise RuntimeError(f"Could not retrieve symbol info for {symbol} to determine step and tick.")


def round_qty(symbol: str, qty: float) -> float:
    """
    수량을 심볼의 최소 거래량 단위(qtyStep)에 맞춰 조정합니다.
    """
    info = get_symbol_info(symbol)
    qty_step = info['qtyStep']
    
    # Decimal을 사용하여 정확한 계산 및 내림 (ROUND_DOWN)
    decimal_qty = Decimal(str(qty))
    decimal_step = Decimal(str(qty_step))
    
    # 몫을 계산하고 step_size로 곱하여 내림
    adjusted_qty = (decimal_qty // decimal_step) * decimal_step
    
    # 반환할 때 float으로 변환
    return float(adjusted_qty)

def round_price(symbol: str, price: float) -> float:
    """
    가격을 심볼의 최소 가격 단위(tickSize)에 맞춰 조정합니다.
    """
    info = get_symbol_info(symbol)
    tick_size = info['tickSize']

    # Decimal을 사용하여 정확한 계산 및 내림 (ROUND_DOWN)
    decimal_price = Decimal(str(price))
    decimal_tick = Decimal(str(tick_size))
    
    # 몫을 계산하고 tick_size로 곱하여 내림
    adjusted_price = (decimal_price // decimal_tick) * decimal_tick
    
    # 반환할 때 float으로 변환
    return float(adjusted_price)

def _sign(params: dict) -> str:
    """
    Bybit REST API는 쿼리스트링을 사전순 정렬한 뒤 SHA256 HMAC 서명(signature) 필요.
    """
    qs = "&".join([f"{k}={params[k]}" for k in sorted(params)])
    return hmac.new(bybit_api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

def get_latest_order(symbol: str):
    """
    Bybit V5의 /v5/order/history 를 이용해서
    지정된 심볼의 최근 주문 1건을 반환합니다.
    - 데이터가 없으면 None 리턴
    - API 에러나 HTTP 에러는 RuntimeError를 발생시킵니다.
    """
    endpoint = "/v5/order/history"
    url = BASE_URL + endpoint

    ts = int(time.time() * 1000)
    params = {
        "category":  "linear" if symbol.upper().endswith("USDT") else "inverse",
        "symbol":    symbol.upper(),
        "limit":     10,
        "page":      1,
        "timestamp": ts,
        "api_key":   bybit_api_key,
    }
    params["sign"] = _sign(params)

    # 1) 요청 & HTTP 에러 체크
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Bybit HTTP {resp.status_code} Error: {resp.text}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Bybit request failed: {e}") from e

    # 2) JSON 파싱 체크
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"Bybit returned non-JSON response: {resp.text}")

    # 3) API 레벨 에러 체크
    # V5는 retCode, retMsg
    if data.get("retCode", 1) != 0:
        raise RuntimeError(f"Bybit API Error {data.get('retCode')}: {data.get('retMsg')}")

    # 4) 실제 주문 리스트 추출
    orders = data.get("result", {}).get("data", []) or []
    if not orders:
        return None

    # 5) 가장 마지막(최신) 주문 반환
    return orders[-1]

def check_order_status(symbol: str, order_id: str):
    """
    지정 주문(order_id)의 현재 상태 조회.
    체결(Filled) 상태이면 None, 아직 체결되지 않았다면 order dict을 그대로 반환.
    """
    endpoint = "/v2/private/order"
    ts = int(time.time() * 1000)
    params = {
        "symbol":      symbol,
        "order_id":    order_id,
        "timestamp":   ts,
        "api_key":     bybit_api_key,
    }
    params["sign"] = _sign(params)
    url = BASE_URL + endpoint
    res = requests.get(url, params=params).json()
    if res.get("ret_code") != 0 or "result" not in res:
        return None
    order = res["result"]
    # order_status: New, PartiallyFilled, Filled, Canceled, etc.
    if order.get("order_status") == "Filled":
        return None
    return order

def get_futures_position_info(symbol: str, side: str = None):
    """
    Bybit V5의 /v5/position/list 를 호출해서
    지정 심볼(symbol)의 현재 포지션 정보를 반환합니다.

    side:
      - "long"  => size>0, BUY 포지션만
      - "short" => size>0, SELL 포지션만
      - None    => 첫 번째 포지션(롱·숏 관계없이) 반환

    반환 dict:
      {
        "positionAmt":        <float>,
        "entryPrice":         <float>,
        "unRealizedProfit":   <float>,
        "liquidationPrice":   <float>,
      }
    포지션 없거나 오류 시 모두 0을 반환합니다.
    """
    endpoint = "/v5/position/list"
    url = BASE_URL + endpoint

    # 1) 파라미터 세팅 (USDT페어는 linear, 그 외 inverse)
    category = "linear" if symbol.upper().endswith("USDT") else "inverse"
    ts = int(time.time() * 1000)
    params = {
        "category":   category,
        "symbol":     symbol.upper(),
        "timestamp":  ts,
        "api_key":    bybit_api_key,
    }
    # _sign 함수가 bybit_request 함수 내부에서 호출되는 generate_signature와 다른 서명 로직일 경우
    # 기존 코드의 _sign 함수는 변경하지 않습니다.
    params["sign"] = _sign(params) # 기존 _sign 함수를 사용한다고 가정

    # 기본값: 포지션이 없을 때 반환할 dict
    default = {
        "positionAmt":        0.0,
        "entryPrice":         0.0,
        "unRealizedProfit":   0.0,
        "liquidationPrice":   0.0,
    }

    # 2) HTTP 요청 → 에러 체크
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Bybit HTTP Error {resp.status_code}: {resp.text}")
        return default
    except requests.exceptions.RequestException as e:
        print(f"Bybit request failed: {e}")
        return default

    # 3) JSON 파싱
    try:
        data = resp.json()
    except ValueError:
        print(f"Bybit returned non-JSON response: {resp.text}")
        return default

    # 4) API 레벨 오류 확인
    if data.get("retCode", 1) != 0:
        print(f"Bybit API Error {data.get('retCode')}: {data.get('retMsg')}")
        return default

    # 5) 실제 position 리스트 꺼내기
    positions = data.get("result", {}).get("list", []) or []
    if not positions:
        return default

    # 6) side 필터링 및 첫 매칭 포지션 반환
    for pos in positions:
        size = float(pos.get("size", 0))
        side_str = pos.get("side", "").lower()  # "buy" 또는 "sell"
        
        # positionAmt가 0이거나 유효하지 않은 포지션 건너뛰기 (추가된 안전 장치)
        if size <= 0:
            continue

        # long: BUY 포지션만, short: SELL 포지션만
        if side == "long"  and side_str != "buy":
            continue
        if side == "short" and side_str != "sell":
            continue

        return {
            "positionAmt":        size,
            "entryPrice":         float(pos.get("avgPrice", 0)),  # <-- **이 부분을 수정했습니다.**
            "unRealizedProfit":   float(pos.get("unrealisedPnl", 0)),
            "liquidationPrice":   float(pos.get("liqPrice", 0)),
        }

    # 7) 매칭되는 포지션 없으면 기본값 반환
    return default





def _bapi_sign(timestamp: str, body: dict) -> str:
    """
    Bybit v5 API 서명 생성 (HMAC_SHA256).
    signature = HMAC_SHA256( apiKey + timestamp + recvWindow + body_json )
    """
    recv_window = "5000"
    body_json   = json.dumps(body, separators=(",", ":"))  # compact
    to_sign     = bybit_api_key + timestamp + recv_window + body_json
    return hmac.new(
        bybit_api_secret.encode("utf-8"),
        to_sign.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

def bybit_bapi_request(method: str, path: str, body: dict):
    """
    v5 BAPI 호출 래퍼
    """
    ts = str(int(time.time() * 1000))
    sign = _bapi_sign(ts, body)

    headers = {
        "Content-Type":    "application/json",
        "X-BAPI-API-KEY":  bybit_api_key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": "5000",
        "X-BAPI-SIGN":     sign,
    }

    url = BASE_URL + path
    if method.upper() == "GET":
        return requests.get(url, headers=headers, params=body).json()
    else:
        return requests.post(url, headers=headers, json=body).json()

# ————————————————————————————————————————
# 1) 포지션 모드 조회
def get_position_mode(symbol: str = None,
                      coin: str   = None,
                      category: str = "linear"):
    """
    Bybit v5 포지션 모드 조회
    - symbol 또는 coin 둘 중 하나는 지정하셔야 합니다.
      symbol 우선, coin은 그 외 전체 심볼을 바꿀 때 사용.
    """
    payload = {"category": category}
    if symbol:
        payload["symbol"] = symbol
    elif coin:
        payload["coin"] = coin
    else:
        raise ValueError("symbol 또는 coin 중 하나는 반드시 지정해야 합니다.")

    resp = bybit_bapi_request("GET", "/v5/position/switch-mode", payload)
    return resp.get("result", {})


# 2) 포지션 모드 토글
def change_position_mode(
    hedge: bool,
    symbol: str = None,
    coin:   str = None,
    category: str = "linear"
) -> dict:
    """
    Bybit v5 포지션 모드 변경
      :param hedge: True → 헤지 모드(롱/숏 동시), False → 원웨이 모드
      :param symbol: 개별 심볼 단위 변경(ex: "XRPUSDT")
      :param coin:   심볼 미지정 시 코인 단위 변경(ex: "USDT")
      :param category: "linear" 또는 "inverse"
    """
    mode = 3 if hedge else 0
    # === 서명과 전송에 모두 사용할 동일한 JSON 바디 ===
    json_data = {
        "category": category,
        "mode":     mode
    }
    if symbol:
        json_data["symbol"] = symbol.upper()
    elif coin:
        json_data["coin"] = coin.upper()
    else:
        raise ValueError("symbol 또는 coin 중 하나는 반드시 지정해야 합니다.")

    # bybit_request 내부에서 generate_signature → requests.post(json=…) 를 사용
    return bybit_request(
        method="POST",
        endpoint="/v5/position/switch-mode",
        params=None,
        json_data=json_data
    )


def cheatkey(
    symbol: str,
    interval: str = '5m',
    threshold: float = 0.001,
    lookback_n: int = 6,
    use_time_filter: bool = True,
    side: str = "long"
) -> bool:
    """
    Bybit용 cheatkey – overflow 방지용 open_time 처리
    """
    try:
        # 1) Kline 조회 (get_candles 내부에서 interval 정규화)
        limit  = max(lookback_n + 3, 50)
        klines = get_candles(symbol, interval, limit)
        if not klines:
            print("[bybit_functions.cheatkey] no kline data")
            return False

        # 2) DataFrame 생성
        cols = ["open_time","open","high","low","close","volume"]
        df = pd.DataFrame(klines, columns=cols + list(range(len(klines[0]) - len(cols))))

        # 3) open_time: ms → s 로 나눈 다음 unit='s' 로 변환
        #    이렇게 하면 C long 범위를 초과하지 않습니다.
        ts_seconds = df["open_time"].astype('int64') // 1000
        df["open_time"] = pd.to_datetime(ts_seconds, unit="s")

        # 4) 나머지 컬럼 float 변환
        for col in ("open","high","low","close","volume"):
            df[col] = df[col].astype(float)

        # 5) 미완성 봉(drop last row) 제외
        df = df.iloc[:-1].reset_index(drop=True)
        idx = len(df) - 1
        if idx < lookback_n + 1:
            return False

        # 6) 시간 필터
        if use_time_filter:
            minute = df.at[idx, "open_time"].minute
            if minute not in (0,5, 15,20, 30,35, 45,50):
                return False

        # 7) EMA 계산
        df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()

        # 8) slope 조건
        c12, c26 = df.at[idx,   "ema12"], df.at[idx,   "ema26"]
        p12, p26 = df.at[idx-1, "ema12"], df.at[idx-1, "ema26"]
        if side == "long" and (c12 <= p12 or c26 <= p26):
            return False
        if side == "short" and (c12 >= p12 or c26 >= p26):
            return False

        # 9) 노이즈 필터
        start = idx - lookback_n + 1
        for j in range(start, idx+1):
            prev12, prev26 = df.at[j-1,"ema12"], df.at[j-1,"ema26"]
            curr12, curr26 = df.at[j,  "ema12"], df.at[j,  "ema26"]
            if side == "long" and prev12 > prev26 and curr12 < curr26:
                return False
            if side == "short" and prev12 < prev26 and curr12 > curr26:
                return False

        # 10) 캔들 방향 조건
        o, c = df.at[idx,"open"], df.at[idx,"close"]
        block = df.iloc[start:idx+1]
        if side == "long":
            if not (c12 < c26 and c > o and (block["ema12"] < block["ema26"]).all()):
                return False
        else:
            if not (c12 > c26 and c < o and (block["ema12"] > block["ema26"]).all()):
                return False

        # 11) EMA 차이 감소 & 임계값 체크
        curr_diff, prev_diff = abs(c12 - c26), abs(p12 - p26)
        return curr_diff < prev_diff and curr_diff <= threshold

    except Exception as e:
        print(f"[bybit_functions.cheatkey] error: {e}")
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
    Bybit 용 EMA 골든/데드 크로스 신호
      - get_candles() 헬퍼를 사용해 올바른 interval 포맷으로 Kline 데이터를 가져옵니다.
    """
    try:
        # 1) Kline 조회 (최소 2개 이상)
        klines = get_candles(symbol, interval, limit= ema26_period + 5)
        if len(klines) < 2:
            print("[bybit_functions.emacross] no kline data")
            return False

        # 2) DataFrame 생성 & 타입 변환
        # klines 항목: [open_time, open, high, low, close, volume, ...]
        cols = ["open_time", "open", "high", "low", "close", "volume"]
        df = pd.DataFrame(klines, columns=cols + list(range(len(klines[0]) - len(cols))))
        df["close"] = df["close"].astype(float)
        df["open"]  = df["open"].astype(float)

        # 3) EMA 계산
        df["ema12"] = df["close"].ewm(span=ema12_period, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=ema26_period, adjust=False).mean()

        # 4) 이전봉과 현재봉 EMA
        prev12, prev26 = df.iloc[-2][["ema12","ema26"]]
        curr12, curr26 = df.iloc[-1][["ema12","ema26"]]

        # 5) 골든/데드 크로스 판단
        if side == "long":
            if not (prev12 < prev26 and curr12 > curr26):
                return False
        elif side == "short":
            if not (prev12 > prev26 and curr12 < curr26):
                return False
        else:
            raise ValueError("side must be 'long' or 'short'")

        # 6) (선택) 캔들 방향 조건
        if use_candle_condition:
            o = df.iloc[-1]["open"]
            c = df.iloc[-1]["close"]
            if side == "long" and c <= o:
                return False
            if side == "short" and c >= o:
                return False

        return True

    except Exception as e:
        print(f"[bybit_functions.emacross] error: {e}")
        return False
    
def get_symbol_ticker(symbol: str) -> dict:
    """
    Bybit V5 API로부터 심볼의 최신 체결가를 {'symbol': symbol, 'price': price_str} 형태로 반환합니다.
    USDT 계약(Linear)에 대해 동작하며, HTTP 에러와 비JSON 응답을 안전하게 처리합니다.
    """
    endpoint = "/v5/market/tickers"
    url = BASE_URL + endpoint
    params = {
        "category": "linear",   # USDT 무기한 선물
        "symbol":   symbol.upper()
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # HTTP 오류 시 상세 메시지 포함
        raise RuntimeError(f"Bybit HTTP error: {e} / body={resp.text}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Bybit request failed: {e}") from e

    # JSON 파싱
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"Bybit returned non-JSON response: {resp.text}")

    # API 스펙 검증
    if data.get("retCode", data.get("ret_code", 1)) != 0:
        raise RuntimeError(f"Bybit ticker 조회 실패: {data}")
    result = data.get("result", {})
    lst    = result.get("list") or result.get("tickers") or []
    if not lst:
        raise RuntimeError(f"Bybit ticker 결과가 비어 있습니다: {data}")

    # 첫 번째 항목의 lastPrice 또는 last_price 사용
    item      = lst[0]
    price_str = item.get("lastPrice") or item.get("last_price")
    if price_str is None:
        raise RuntimeError(f"Bybit ticker에 가격 필드가 없습니다: {item}")

    return {"symbol": symbol.upper(), "price": str(price_str)}

def candle(symbol: str, side: str, interval: str = "5m") -> bool:
    """
    Bybit: 가장 최근 interval 봉을 가져와
      - side=="long"  → 종가 > 시가 일 때 True
      - side=="short" → 종가 < 시가 일 때 True
    """
    candles = get_candles(symbol, interval, 1)  # Bybit v5 kline API :contentReference[oaicite:1]{index=1}
    if not candles:
        raise RuntimeError(f"No candle data for {symbol} {interval}")
    # candles[0] = [timestamp, open, high, low, close, volume, ...]
    o = float(candles[0][1])
    c = float(candles[0][4])
    if side.lower() == "long":
        return c > o
    elif side.lower() == "short":
        return c < o
    else:
        raise ValueError("side must be 'long' or 'short'")
