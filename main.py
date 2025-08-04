import discord
from discord.ext import commands
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from binance.client import Client
from binance.enums import *
import matplotlib
matplotlib.use('Agg')  # 서버 환경에서 GUI 없이 사용
import mplfinance as mpf
import pandas as pd

from functions import *
from discord_functions import *



init_db()
bot.run(TOKEN)  