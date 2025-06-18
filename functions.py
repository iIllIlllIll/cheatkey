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

from init_functions import *

# 거래소별 구현 모듈 import
import binance_functions
import bybit_functions

EXCHANGE = 'binance'   # 기본값: 'binance'. 'bybit' 로 변경 가능.

def set_exchange(name: str):
    """
    런타임 중 EXCHANGE 값을 바꿉니다.
      set_exchange('binance')  → Binance 사용
      set_exchange('bybit')    → Bybit 사용
    """
    global EXCHANGE
    n = name.lower()
    if n not in ('binance', 'bybit'):
        raise ValueError(f"지원하지 않는 거래소: {name}")
    EXCHANGE = n

def get_exchange() -> str:
    """현재 사용 중인 거래소 이름('binance' 또는 'bybit')을 반환합니다."""
    return EXCHANGE

colorama.init(autoreset=True)


def get_position_mode(**kwargs):
    """
    포지션 모드 조회
      Binance: get_position_mode()
      Bybit:   get_position_mode(symbol=...), get_position_mode(coin=...)
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_position_mode()
    else:
        # Bybit 쪽은 반드시 symbol 또는 coin 인자를 kwargs 에 담아 호출하세요.
        return bybit_functions.get_position_mode(**kwargs)

def change_position_mode(dualSidePosition: bool, **kwargs):
    """
    포지션 모드 토글
      Binance: change_position_mode(dualSidePosition)
      Bybit:   change_position_mode(hedge, symbol=..., coin=...)
    """
    if EXCHANGE == 'binance':
        return binance_functions.change_position_mode(dualSidePosition)
    else:
        return bybit_functions.change_position_mode(dualSidePosition, **kwargs)

def get_candles(symbol: str, interval: str, candle_count: int):
    """
    캔들 조회
      Binance: get_candles(symbol, interval, limit)
      Bybit:   get_candles(symbol, interval, limit)
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_candles(symbol, interval, candle_count)
    else:
        return bybit_functions.get_candles(symbol, interval, candle_count)

def place_market_order(symbol: str, quantity: float, leverage: int, side: str):
    """
    시장가 주문을 전송
      side: 'BUY' 또는 'SELL' (사용자가 입력한 값)
    """
    if EXCHANGE == 'bybit':
        # Bybit API는 'Buy' 또는 'Sell'을 기대
        bybit_side = 'Buy' if side.upper() == 'BUY' else 'Sell'
        return bybit_functions.place_market_order(symbol, quantity, leverage, bybit_side)
    elif EXCHANGE == 'binance':
        # Binance API도 보통 'BUY' 또는 'SELL' 대문자 그대로 사용
        return binance_functions.place_market_order(symbol, quantity, leverage, side.upper())
    else:
        raise ValueError(f"지원하지 않는 거래소입니다: {EXCHANGE}")

def place_limit_order(symbol: str, price: float, quantity: float, leverage: int, side: str):
    """
    지정가 주문
      side: 'BUY' 또는 'SELL'
    """
    if EXCHANGE == 'binance':
        return binance_functions.place_limit_order(symbol, price, quantity, leverage, side)
    elif EXCHANGE == 'bybit':
        bybit_side = 'Buy' if side.upper() == 'BUY' else 'Sell'
        return bybit_functions.place_limit_order(symbol, price, quantity, leverage, bybit_side)

def execute_market_order(symbol: str,
                         quantity: float,
                         leverage: int,
                         side: str,
                         **kwargs):
    """
    시장가 주문 실행
      symbol   : 거래 심볼 (e.g. "XRPUSDT")
      quantity : 주문 수량
      leverage : 레버리지
      side     : "BUY" 또는 "SELL"
    """
    if EXCHANGE == 'binance':
        return binance_functions.execute_market_order(symbol, quantity, leverage, side)
    else:
        return bybit_functions.execute_market_order(symbol, quantity, leverage, side, **kwargs)

def execute_market_order_usdt(symbol: str,
                              usdt_amount: float,
                              leverage: int,
                              side: str,
                              **kwargs):
    """
    USDT 기준 시장가 진입
    usdt_amount: 투입할 USDT 금액
    leverage: 레버리지
    side: 'BUY' 또는 'SELL'
    """
    if EXCHANGE == 'binance':
        return binance_functions.execute_market_order_usdt(
            symbol, usdt_amount, leverage, side
        )
    else:
        return bybit_functions.execute_market_order_usdt(
            symbol, usdt_amount, leverage, side, **kwargs
        )
    
def execute_limit_order(symbol: str,
                        price: float,
                        quantity: float,
                        leverage: int,
                        side: str,
                        **kwargs):
    """
    지정가 주문 실행
      symbol   : 거래 심볼
      price    : 지정가
      quantity : 주문 수량
      leverage : 레버리지
      side     : "BUY" 또는 "SELL"
    """
    if EXCHANGE == 'binance':
        return binance_functions.execute_limit_order(symbol, price, quantity, leverage, side)
    else:
        return bybit_functions.execute_limit_order(symbol, price, quantity, leverage, side, **kwargs)

def close(symbol: str, side: str='all', **kwargs):
    """
    전량 청산 (Market)
      side: 'BUY' 또는 'SELL' (포지션 반대 방향)
    """
    if EXCHANGE == 'binance':
        return binance_functions.close(symbol, side=side)
    else:
        return bybit_functions.close(symbol, side=side, **kwargs)

def close_usdt(symbol: str, leverage: int, usdt: float, side: str='all', **kwargs):
    """
    USDT 금액 기준 청산
      usdt: 청산할 USDT 금액
    """
    if EXCHANGE == 'binance':
        return binance_functions.close_usdt(symbol, leverage, usdt, side=side)
    else:
        return bybit_functions.close_usdt(symbol, leverage, usdt, side=side, **kwargs)

def close_pct(symbol: str, pct: float, side: str='all', **kwargs):
    """
    PCT 기준 청산
    현재 남아있는 포지션 중 퍼센트로 청산시킴
    """
    if EXCHANGE == 'binance':
        return binance_functions.close_pct(symbol,pct,side)
    else:
        return message("기능 구현 안됨 : binance 거래소를 이용하세요")


def cheatkey(symbol: str,
             interval: str = '5m',
             threshold: float = 0.001,
             lookback_n: int = 6,
             use_time_filter: bool = True,
             side: str = "long") -> bool:
    """
    진입 신호 함수: Binance/Bybit 공통 인터페이스
    """
    if EXCHANGE == 'binance':
        return binance_functions.cheatkey(symbol,
                                          interval=interval,
                                          threshold=threshold,
                                          lookback_n=lookback_n,
                                          use_time_filter=use_time_filter,
                                          side=side)
    else:
        return bybit_functions.cheatkey(symbol,
                                        interval=interval,
                                        threshold=threshold,
                                        lookback_n=lookback_n,
                                        use_time_filter=use_time_filter,
                                        side=side)

def emacross(symbol: str,
             ema12_period: int = 12,
             ema26_period: int = 26,
             interval: str = '5m',
             side: str = "long",
             use_candle_condition: bool = False) -> bool:
    """
    골든/데드 크로스 신호 함수: Binance/Bybit 공통 인터페이스
    """
    if EXCHANGE == 'binance':
        return binance_functions.emacross(symbol,
                                          ema12_period=ema12_period,
                                          ema26_period=ema26_period,
                                          interval=interval,
                                          side=side,
                                          use_candle_condition=use_candle_condition)
    else:
        return bybit_functions.emacross(symbol,
                                        ema12_period=ema12_period,
                                        ema26_period=ema26_period,
                                        interval=interval,
                                        side=side,
                                        use_candle_condition=use_candle_condition)
    

def get_latest_order(symbol: str, **kwargs):
    """
    가장 최근 주문 정보 반환 (없으면 None)
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_latest_order(symbol)
    else:
        # Bybit 쪽은 필요 시 symbol 외 추가 인자(kwargs) 전달
        return bybit_functions.get_latest_order(symbol, **kwargs)

def check_order_status(symbol: str, order_id: str, **kwargs):
    """
    특정 주문의 체결 상태 조회:
    - Filled 이면 None, 아니면 주문 dict 반환
    """
    if EXCHANGE == 'binance':
        return binance_functions.check_order_status(symbol, order_id)
    else:
        return bybit_functions.check_order_status(symbol, order_id, **kwargs)

def get_futures_position_info(symbol: str, side: str = None, **kwargs):
    """
    현재 선물 포지션 정보 조회
    side: 'long' 또는 'short' 또는 None
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_futures_position_info(symbol, side=side)
    else:
        return bybit_functions.get_futures_position_info(symbol, side=side, **kwargs)
    
def get_futures_asset_balance(asset: str = 'USDT', **kwargs):
    """
    선물 계정 내 특정 자산(USDT 등) 잔액 조회
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_futures_asset_balance(asset)
    else:
        return bybit_functions.get_futures_asset_balance(asset, **kwargs)

def cancel_old_orders(symbol: str, older_than: int = 300, **kwargs):
    """
    지정 시간(초) 이전에 생성된 오픈오더 일괄 취소
    older_than: 취소 기준 경과 시간(초)
    """
    if EXCHANGE == 'binance':
        return binance_functions.cancel_old_orders(symbol)
    else:
        return bybit_functions.cancel_old_orders(symbol, **kwargs)

def get_symbol_ticker(symbol: str):
    "symbol 조회"
    if EXCHANGE == 'binance':
        return client.get_symbol_ticker(symbol=f"{symbol}")
    else:
        return bybit_functions.get_symbol_ticker(symbol=f"{symbol}")



def get_current_market_price(symbol: str, **kwargs) -> float:
    """
    현재 시장가(최우선 호가) 조회
      symbol: 거래 심볼
    """
    if EXCHANGE == 'binance':
        return binance_functions.get_current_market_price(symbol)
    else:
        return bybit_functions.get_current_market_price(symbol, **kwargs)


def round_price(symbol: str, price: float) -> float:
    """
    가격을 거래소의 tick size에 맞춰 내림하여 반올림합니다.
    """
    if EXCHANGE == 'bybit':
        return bybit_functions.round_price(symbol, price)
    elif EXCHANGE == 'binance':
        # Binance의 가격 라운딩 함수 이름을 확인하고 호출
        # 예: binance_functions.round_price_to_tick_size
        return binance_functions.round_price_to_tick_size(symbol, price)
    else:
        raise ValueError(f"Unsupported exchange: {EXCHANGE}")
    
def round_qty(symbol: str, qty: float) -> float:
    """
    수량을 거래소의 step size에 맞춰 내림하여 반올림합니다.
    """
    if EXCHANGE == 'bybit':
        # bybit_functions.py에 정의된 round_qty 함수를 호출
        return bybit_functions.round_qty(symbol, qty)
    elif EXCHANGE == 'binance':
        # binance_functions.py에 정의된 수량 라운딩 함수를 호출 (함수명 확인)
        return binance_functions.round_quantity_to_step_size(symbol, qty) # 예시
    else:
        raise ValueError(f"지원하지 않는 거래소입니다: {EXCHANGE}")


def set_leverage(symbol: str, leverage: int, side: str = None):
    """
    레버리지를 설정합니다.
    """
    if EXCHANGE == 'bybit':
        bybit_functions.set_leverage(symbol, leverage, side)
    elif EXCHANGE == 'binance':
        binance_functions.set_leverage(symbol, leverage) # Binance는 side 파라미터가 없을 수 있음
    else:
        raise ValueError(f"Unsupported exchange: {EXCHANGE}")
    
def candle(symbol: str, side: str, interval: str = '5m') -> bool:
    """
    현재 설정된 EXCHANGE 에 따라 candle() 호출
      - Binance: 지정된 interval
      - Bybit  : 지정된 interval
    """
    exch = EXCHANGE.lower()
    if exch == 'binance':
        return binance_functions.candle(symbol, side, interval)
    elif exch == 'bybit':
        return bybit_functions.candle(symbol, side, interval)
    else:
        raise ValueError(f"Unsupported EXCHANGE: {EXCHANGE!r}")
    
def get_symbol_info(symbol):
    return bybit_functions.get_symbol_info(symbol)
    

