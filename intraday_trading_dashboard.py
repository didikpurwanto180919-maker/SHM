"""
=========================================================================================
QUANTPULSE INTRADAY PRO — DASHBOARD ANALISIS & REKOMENDASI SCALPING / DAY TRADING SAHAM
Strategi Utama: Intraday Open-to-Close (Beli Pagi Saat Market Open, Jual Sore Sebelum Close)
=========================================================================================
Arsitektur:
1. Backend Quantitative Engine:
   - Multi-timeframe Intraday Data Ingestion (yfinance: 1m, 5m, 15m + Daily Context)
   - BEI / IDX Tick Size (Fraksi Harga) & Lot (100 lembar) Precision Calculator
   - Institutional Intraday Indicators: Session VWAP + StdDev Bands, Opening Range Breakout
     (ORB 15m/30m), EMA 9/21/50, Wilder's RSI(14), Stochastic RSI, MACD(12,26,9),
     ATR(14) Volatility, Relative Volume (RVOL) Spike & Money Flow Proxy
   - Live News & Catalyst Engine: Real-time RSS Feeds (Google News Bisnis/Saham,
     CNBC Indonesia, Yahoo Finance) + yfinance Ticker News + Bilingual Sentiment Scoring
   - Multi-Factor Quant Conviction Scoring (0-100) & Trade Plan Generator
   - Walk-Forward Intraday Backtester (Simulasi Beli Pagi -> Jual Sore / TP / SL)
2. Frontend Streamlit Interactive UI:
   - Market Scanner (Multi-Screener LQ45 / IDX Momentum / US Tech)
   - Deep-Dive Interactive Plotly Candlestick + VWAP + ORB + Volume + RSI/MACD Subplots
   - Execution Plan Card, Position Sizing & Broker Fee Calculator, Live News Feed

Cara Menjalankan:
   pip install -r requirements.txt
   streamlit run intraday_trading_dashboard.py
=========================================================================================
"""

import datetime as dt
import html
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf


# =========================================================================================
# 1. KONFIGURASI HALAMAN & STYLING FRONTEND (STREAMLIT)
# =========================================================================================
st.set_page_config(
    page_title="QuantPulse Intraday Pro | Day Trading & Scalping Saham",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 1.4rem 1.8rem;
        border-radius: 12px;
        border-left: 6px solid #10b981;
        color: #f8fafc;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.75rem;
        font-weight: 800;
        color: #f8fafc;
    }
    .main-header p {
        margin: 0.35rem 0 0 0;
        font-size: 0.95rem;
        color: #94a3b8;
    }
    .signal-card {
        padding: 1.2rem;
        border-radius: 10px;
        background-color: #1e293b;
        border: 1px solid #334155;
        color: #f1f5f9;
        margin-bottom: 1rem;
    }
    .badge-buy {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        padding: 0.3rem 0.75rem;
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #10b981;
        display: inline-block;
    }
    .badge-watch {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        padding: 0.3rem 0.75rem;
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #f59e0b;
        display: inline-block;
    }
    .badge-avoid {
        background-color: rgba(239, 68, 68, 0.2);
        color: #f87171;
        padding: 0.3rem 0.75rem;
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #ef4444;
        display: inline-block;
    }
    .news-card {
        padding: 0.85rem 1.1rem;
        border-radius: 8px;
        background-color: #0f172a;
        border-left: 4px solid #3b82f6;
        margin-bottom: 0.65rem;
    }
    .news-pos { border-left-color: #10b981 !important; }
    .news-neg { border-left-color: #ef4444 !important; }
    .news-neu { border-left-color: #64748b !important; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =========================================================================================
# 2. DAFTAR WATCHLIST & KONSTANTA PASAR (BEI / IDX & GLOBAL)
# =========================================================================================
PRESET_WATCHLISTS: Dict[str, List[str]] = {
    "IDX LQ45 & Big Caps Likuid (Beli Pagi - Jual Sore)": [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK",
        "ASII.JK", "ADRO.JK", "AMMN.JK", "BREN.JK", "GOTO.JK",
        "PGAS.JK", "PTBA.JK", "ANTM.JK", "MDKA.JK", "INCO.JK",
        "ICBP.JK", "AMRT.JK", "MEDC.JK", "AKRA.JK", "BRIS.JK",
    ],
    "IDX Komoditas, Energi & High-Beta Scalping": [
        "ADRO.JK", "MEDC.JK", "ELSA.JK", "ENRG.JK", "ANTM.JK",
        "MDKA.JK", "TINS.JK", "BRMS.JK", "MBMA.JK", "HRUM.JK",
        "ITMG.JK", "PTBA.JK", "DOID.JK", "DEWA.JK", "RAJA.JK",
    ],
    "IDX Perbankan, Tech & Consumer Momentum": [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "BRIS.JK", "BBTN.JK",
        "ARTO.JK", "GOTO.JK", "BUKA.JK", "EMTK.JK", "SCMA.JK",
        "AMRT.JK", "MAPA.JK", "MAPI.JK", "ACES.JK", "KLBF.JK",
    ],
    "US Tech & High-Liquidity Day Trading (NYSE/NASDAQ)": [
        "NVDA", "TSLA", "AAPL", "AMD", "MSFT",
        "META", "AMZN", "GOOGL", "PLTR", "COIN",
    ],
}

COMPANY_KEYWORDS: Dict[str, str] = {
    "BBCA.JK": "Bank Central Asia BBCA",
    "BBRI.JK": "Bank Rakyat Indonesia BBRI",
    "BMRI.JK": "Bank Mandiri BMRI",
    "BBNI.JK": "Bank Negara Indonesia BBNI",
    "BRIS.JK": "Bank Syariah Indonesia BRIS",
    "TLKM.JK": "Telkom Indonesia TLKM",
    "ASII.JK": "Astra International ASII",
    "ADRO.JK": "Alamtri Adaro Energy ADRO",
    "AMMN.JK": "Amman Mineral AMMN",
    "BREN.JK": "Barito Renewables BREN",
    "GOTO.JK": "GoTo Gojek Tokopedia GOTO",
    "PGAS.JK": "Perusahaan Gas Negara PGAS",
    "PTBA.JK": "Bukit Asam PTBA",
    "ANTM.JK": "Aneka Tambang ANTM",
    "MDKA.JK": "Merdeka Copper Gold MDKA",
    "INCO.JK": "Vale Indonesia INCO",
    "MEDC.JK": "Medco Energi MEDC",
    "AKRA.JK": "AKR Corporindo AKRA",
    "AMRT.JK": "Sumber Alfaria Alfamart AMRT",
    "ICBP.JK": "Indofood CBP ICBP",
}


# =========================================================================================
# 3. UTILITAS FRAKSI HARGA BEI (IDX TICK SIZE) & FORMATTER
# =========================================================================================
def get_idx_tick_size(price: float, is_idx: bool = True) -> float:
    """Mengembalikan fraksi harga (tick size) resmi Bursa Efek Indonesia (BEI)."""
    if not is_idx:
        return 0.01
    if price < 200:
        return 1.0
    elif price < 500:
        return 2.0
    elif price < 2000:
        return 5.0
    elif price < 5000:
        return 10.0
    else:
        return 25.0


def round_to_tick(price: float, is_idx: bool = True, direction: str = "nearest") -> float:
    """Membulatkan harga sesuai fraksi harga BEI (IDX) agar order tidak rejected."""
    if price <= 0 or math.isnan(price):
        return 0.0
    if not is_idx:
        return round(price, 2)
    tick = get_idx_tick_size(price, is_idx=True)
    if direction == "up":
        return float(math.ceil(price / tick) * tick)
    elif direction == "down":
        return float(math.floor(price / tick) * tick)
    return float(round(price / tick) * tick)


def format_price(price: float, is_idx: bool = True) -> str:
    """Format tampilan harga Rupiah (tanpa desimal) atau USD (2 desimal)."""
    if math.isnan(price) or price is None:
        return "-"
    if is_idx:
        return f"Rp {int(round(price)):,}".replace(",", ".")
    return f"${price:,.2f}"


# =========================================================================================
# 4. BACKEND: DATA INGESTION & INDIKATOR TEKNIKAL INTRADAY PRESISI TINGGI
# =========================================================================================
@dataclass
class TradePlan:
    ticker: str
    is_idx: bool
    last_price: float
    open_price: float
    prev_close: float
    day_high: float
    day_low: float
    vwap: float
    vwap_upper: float
    vwap_lower: float
    orb_high: float
    orb_low: float
    ema9: float
    ema21: float
    ema50: float
    rsi14: float
    stoch_k: float
    macd_line: float
    macd_signal: float
    macd_hist: float
    atr14: float
    rvol: float
    intraday_change_pct: float
    gap_pct: float
    news_sentiment_score: float
    news_catalyst_label: str
    technical_score: float
    momentum_score: float
    volume_score: float
    news_score: float
    total_conviction_score: float
    signal_action: str
    signal_badge_class: str
    entry_min: float
    entry_max: float
    tp1_price: float
    tp2_price: float
    sl_price: float
    tp1_pct: float
    tp2_pct: float
    sl_pct: float
    rr_ratio: float
    time_exit_rule: str
    reasons: List[str] = field(default_factory=list)


@st.cache_data(ttl=90, show_spinner=False)
def fetch_intraday_and_daily_data(
    ticker: str, interval: str = "5m", period: str = "5d"
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Mengambil data intraday (1m/5m/15m) dan data harian (Daily) dari Yahoo Finance.
    Menggunakan caching TTL 90 detik agar responsif untuk scalping/intraday.
    """
    try:
        stock = yf.Ticker(ticker)
        df_intra = stock.history(period=period, interval=interval, auto_adjust=False)
        df_daily = stock.history(period="3mo", interval="1d", auto_adjust=False)

        if df_intra is not None and not df_intra.empty:
            if isinstance(df_intra.columns, pd.MultiIndex):
                df_intra.columns = df_intra.columns.get_level_values(0)
            df_intra = df_intra.dropna(subset=["Open", "High", "Low", "Close"]).copy()

        if df_daily is not None and not df_daily.empty:
            if isinstance(df_daily.columns, pd.MultiIndex):
                df_daily.columns = df_daily.columns.get_level_values(0)
            df_daily = df_daily.dropna(subset=["Open", "High", "Low", "Close"]).copy()

        return df_intra, df_daily
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


def compute_intraday_indicators(df: pd.DataFrame, orb_bars: int = 3) -> pd.DataFrame:
    """
    Menghitung indikator teknikal khusus Intraday / Day Trading:
    - Session VWAP (reset setiap awal sesi perdagangan harian) & Standard Deviation Bands
    - Opening Range Breakout (ORB High & ORB Low dari N candle pertama sesi pagi)
    - EMA 9, EMA 21, EMA 50
    - Wilder's RSI (14) & Stochastic RSI
    - MACD (12, 26, 9)
    - ATR (14)
    - Relative Volume (RVOL 20-bar)
    """
    if df.empty or len(df) < 15:
        return df

    data = df.copy()
    # Pastikan index memiliki informasi tanggal sesi untuk reset VWAP & ORB harian
    data["SessionDate"] = data.index.date
    data["TypicalPrice"] = (data["High"] + data["Low"] + data["Close"]) / 3.0
    data["TP_Vol"] = data["TypicalPrice"] * data["Volume"]

    # 1. Session VWAP & Bands (Reset per hari perdagangan)
    data["Cum_Vol"] = data.groupby("SessionDate")["Volume"].cumsum()
    data["Cum_TP_Vol"] = data.groupby("SessionDate")["TP_Vol"].cumsum()
    data["VWAP"] = np.where(
        data["Cum_Vol"] > 0, data["Cum_TP_Vol"] / data["Cum_Vol"], data["Close"]
    )

    # Standar deviasi terhadap VWAP dalam sesi berjalan
    data["Sq_Diff_Vol"] = ((data["TypicalPrice"] - data["VWAP"]) ** 2) * data["Volume"]
    data["Cum_Sq_Diff_Vol"] = data.groupby("SessionDate")["Sq_Diff_Vol"].cumsum()
    data["VWAP_Std"] = np.sqrt(
        np.where(data["Cum_Vol"] > 0, data["Cum_Sq_Diff_Vol"] / data["Cum_Vol"], 0.0)
    )
    data["VWAP_Upper1"] = data["VWAP"] + 1.28 * data["VWAP_Std"]
    data["VWAP_Lower1"] = data["VWAP"] - 1.28 * data["VWAP_Std"]
    data["VWAP_Upper2"] = data["VWAP"] + 2.0 * data["VWAP_Std"]
    data["VWAP_Lower2"] = data["VWAP"] - 2.0 * data["VWAP_Std"]

    # 2. Opening Range Breakout (ORB) dari `orb_bars` pertama tiap sesi pagi
    def _calc_orb(group: pd.DataFrame) -> pd.DataFrame:
        opening_slice = group.iloc[: min(orb_bars, len(group))]
        group["ORB_High"] = opening_slice["High"].max()
        group["ORB_Low"] = opening_slice["Low"].min()
        group["Session_Open"] = group["Open"].iloc[0]
        return group

    data = data.groupby("SessionDate", group_keys=False).apply(_calc_orb)

    # 3. Exponential Moving Averages (EMA 9, 21, 50)
    data["EMA9"] = data["Close"].ewm(span=9, adjust=False).mean()
    data["EMA21"] = data["Close"].ewm(span=21, adjust=False).mean()
    data["EMA50"] = data["Close"].ewm(span=50, adjust=False).mean()

    # 4. Wilder's RSI (14)
    delta = data["Close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["RSI14"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # 5. Stochastic RSI (14, 3, 3)
    rsi_min = data["RSI14"].rolling(14, min_periods=5).min()
    rsi_max = data["RSI14"].rolling(14, min_periods=5).max()
    stoch_rsi = np.where(
        (rsi_max - rsi_min) > 0,
        (data["RSI14"] - rsi_min) / (rsi_max - rsi_min) * 100.0,
        50.0,
    )
    data["StochRSI_K"] = pd.Series(stoch_rsi, index=data.index).rolling(3, min_periods=1).mean()
    data["StochRSI_D"] = data["StochRSI_K"].rolling(3, min_periods=1).mean()

    # 6. MACD (12, 26, 9)
    ema12 = data["Close"].ewm(span=12, adjust=False).mean()
    ema26 = data["Close"].ewm(span=26, adjust=False).mean()
    data["MACD"] = ema12 - ema26
    data["MACD_Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
    data["MACD_Hist"] = data["MACD"] - data["MACD_Signal"]

    # 7. Average True Range (ATR 14)
    high_low = data["High"] - data["Low"]
    high_close = (data["High"] - data["Close"].shift(1)).abs()
    low_close = (data["Low"] - data["Close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    data["ATR14"] = tr.ewm(alpha=1 / 14, min_periods=5, adjust=False).mean()

    # 8. Relative Volume (RVOL) & Candle Anatomy (Buying Pressure)
    vol_ma20 = data["Volume"].rolling(20, min_periods=5).mean()
    data["RVOL"] = np.where(vol_ma20 > 0, data["Volume"] / vol_ma20, 1.0)
    candle_range = (data["High"] - data["Low"]).replace(0, np.nan)
    data["CloseLocationValue"] = ((data["Close"] - data["Low"]) / candle_range).fillna(0.5)

    return data


# =========================================================================================
# 5. BACKEND: REAL-TIME NEWS & BILINGUAL SENTIMENT CATALYST ENGINE
# =========================================================================================
POSITIVE_KEYWORDS_ID_EN = {
    # Bahasa Indonesia
    "laba": 1.5, "melonjak": 2.0, "naik": 1.2, "tumbuh": 1.5, "dividen": 1.8,
    "akuisisi": 1.5, "buyback": 2.0, "ekspansi": 1.5, "rekor": 1.8, "surplus": 1.5,
    "positif": 1.2, "menguat": 1.4, "breakout": 1.8, "akumulasi": 1.8, "net buy": 2.0,
    "kontrak baru": 1.8, "proyek": 1.2, "optimis": 1.3, "rekomendasi beli": 2.0,
    "target harga": 1.2, "unggul": 1.2, "cuan": 1.2, "reli": 1.5, "bullish": 1.8,
    # English
    "beat": 1.8, "surge": 2.0, "jump": 1.6, "profit": 1.5, "growth": 1.4,
    "upgrade": 2.0, "outperform": 1.8, "buy": 1.3, "record": 1.6, "dividend": 1.6,
    "partnership": 1.4, "contract": 1.4, "rally": 1.6, "soar": 2.0, "strong": 1.3,
}

NEGATIVE_KEYWORDS_ID_EN = {
    # Bahasa Indonesia
    "rugi": -2.0, "anjlok": -2.2, "turun": -1.2, "merosot": -1.8, "koreksi": -1.3,
    "suspensi": -2.5, "pkpu": -2.5, "pailit": -2.8, "gagal bayar": -2.5, "utang": -1.0,
    "negatif": -1.2, "melemah": -1.4, "net sell": -1.8, "distribusi": -1.5,
    "arb": -2.2, "tekanan": -1.3, "denda": -1.8, "gugatan": -1.8, "bearish": -1.8,
    "pangkas": -1.4, "penurunan": -1.3, "jual": -1.0, "defisit": -1.6,
    # English
    "miss": -1.8, "plunge": -2.2, "drop": -1.4, "loss": -1.8, "downgrade": -2.0,
    "underperform": -1.8, "sell": -1.2, "lawsuit": -1.8, "probe": -1.6, "slump": -1.8,
    "weak": -1.4, "cut": -1.3, "decline": -1.4, "crash": -2.2, "default": -2.5,
}


def score_headline_sentiment(text: str) -> Tuple[float, str]:
    """
    Menghitung skor sentimen berita (-1.0 s/d +1.0) menggunakan kamus leksikal
    finansial Bilingual (Indonesia & Inggris).
    """
    if not text:
        return 0.0, "Netral"
    clean_text = text.lower()
    raw_score = 0.0
    matches = 0

    for word, weight in POSITIVE_KEYWORDS_ID_EN.items():
        if word in clean_text:
            raw_score += weight
            matches += 1

    for word, weight in NEGATIVE_KEYWORDS_ID_EN.items():
        if word in clean_text:
            raw_score += weight
            matches += 1

    if matches == 0:
        return 0.0, "Netral"

    normalized = max(-1.0, min(1.0, raw_score / 4.0))
    if normalized >= 0.25:
        return round(normalized, 2), "Positif (Bullish)"
    elif normalized <= -0.25:
        return round(normalized, 2), "Negatif (Bearish)"
    return round(normalized, 2), "Netral"


@st.cache_data(ttl=180, show_spinner=False)
def fetch_live_news_for_ticker(ticker: str, max_items: int = 8) -> List[Dict]:
    """
    Mengambil berita live/terbaru untuk saham dari:
    1. Google News RSS (pencarian spesifik ticker & nama emiten dalam Bahasa Indonesia/Inggris)
    2. API Berita bawaan yfinance (`yf.Ticker(ticker).news`)
    """
    news_items: List[Dict] = []
    seen_titles = set()

    # 1. Coba ambil dari yfinance Ticker.news terlebih dahulu
    try:
        yf_news = yf.Ticker(ticker).news or []
        for item in yf_news[:max_items]:
            content = item.get("content", item)
            title = content.get("title") or item.get("title", "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            provider = (
                content.get("provider", {}).get("displayName")
                if isinstance(content.get("provider"), dict)
                else item.get("publisher", "Yahoo Finance")
            )
            link = (
                content.get("canonicalUrl", {}).get("url")
                if isinstance(content.get("canonicalUrl"), dict)
                else item.get("link", "https://finance.yahoo.com")
            )
            pub_time = content.get("pubDate") or item.get("providerPublishTime", "")
            if isinstance(pub_time, (int, float)):
                pub_str = dt.datetime.fromtimestamp(pub_time).strftime("%d %b %Y %H:%M")
            else:
                pub_str = str(pub_time)[:16] if pub_time else "Terkini"

            score, label = score_headline_sentiment(title)
            news_items.append(
                {
                    "title": title,
                    "source": provider or "Yahoo Finance",
                    "link": link or "https://finance.yahoo.com",
                    "published": pub_str,
                    "sentiment_score": score,
                    "sentiment_label": label,
                }
            )
    except Exception:
        pass

    # 2. Ambil dari Google News RSS (Sangat akurat untuk berita emiten BEI / IDX Bahasa Indonesia)
    try:
        clean_code = ticker.replace(".JK", "")
        search_terms = COMPANY_KEYWORDS.get(ticker, f"Saham {clean_code}")
        is_idx = ticker.endswith(".JK")
        if is_idx:
            query = urllib.parse.quote(f"saham {search_terms}")
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
        else:
            query = urllib.parse.quote(f"{clean_code} stock market")
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item")[:max_items]:
            raw_title = item.findtext("title", default="")
            title = html.unescape(raw_title).strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            link = item.findtext("link", default="https://news.google.com")
            pub_date = item.findtext("pubDate", default="")
            source_el = item.find("source")
            source_name = source_el.text if source_el is not None else "Google News"

            score, label = score_headline_sentiment(title)
            news_items.append(
                {
                    "title": title,
                    "source": source_name,
                    "link": link,
                    "published": pub_date[:22] if pub_date else "Hari ini",
                    "sentiment_score": score,
                    "sentiment_label": label,
                }
            )
            if len(news_items) >= max_items:
                break
    except Exception:
        pass

    return news_items[:max_items]


@st.cache_data(ttl=180, show_spinner=False)
def fetch_general_market_news() -> List[Dict]:
    """Mengambil berita pasar saham & IHSG terkini dari RSS berita ekonomi nasional."""
    rss_sources = [
        ("CNBC Indonesia Market", "https://www.cnbcindonesia.com/market/rss"),
        (
            "Google News IHSG & Bursa",
            "https://news.google.com/rss/search?q=IHSG+saham+BEI+hari+ini&hl=id&gl=ID&ceid=ID:id",
        ),
    ]
    headlines: List[Dict] = []
    seen = set()

    for src_label, url in rss_sources:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                xml_bytes = resp.read()
            root = ET.fromstring(xml_bytes)
            for item in root.findall(".//item")[:6]:
                title = html.unescape(item.findtext("title", default="")).strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                link = item.findtext("link", default="#")
                pub = item.findtext("pubDate", default="")
                score, label = score_headline_sentiment(title)
                headlines.append(
                    {
                        "title": title,
                        "source": src_label,
                        "link": link,
                        "published": pub[:22] if pub else "Live",
                        "sentiment_score": score,
                        "sentiment_label": label,
                    }
                )
        except Exception:
            continue
    return headlines[:10]


# =========================================================================================
# 6. BACKEND: ALGORITMA REKOMENDASI INTRADAY (BELI PAGI - JUAL SORE)
# =========================================================================================
def evaluate_intraday_setup(
    ticker: str,
    df_intra: pd.DataFrame,
    df_daily: pd.DataFrame,
    news_list: List[Dict],
    rr_target: float = 1.8,
) -> Optional[TradePlan]:
    """
    Menghasilkan rekomendasi perdagangan Intraday (Beli Pagi saat Market Open, Jual Sore
    sebelum Market Close) dengan menggabungkan 4 pilar kuantitatif:
    1. Struktur Harga Pagi terhadap VWAP & Opening Range Breakout (ORB) [Bobot 35 poin]
    2. Momentum & Akselerasi Osilator Intraday (EMA9/21, RSI14, MACD, StochRSI) [Bobot 25 poin]
    3. Anomali Volume & Tekanan Beli (RVOL & Close Location Value) [Bobot 25 poin]
    4. Sentimen Berita & Katalis Live [Bobot 15 poin]
    """
    if df_intra is None or df_intra.empty or len(df_intra) < 15:
        return None

    is_idx = ticker.upper().endswith(".JK")
    last_row = df_intra.iloc[-1]
    prev_row = df_intra.iloc[-2] if len(df_intra) >= 2 else last_row

    # Ambil data sesi terakhir (hari ini / sesi bursa terakhir)
    last_session_date = last_row["SessionDate"]
    session_df = df_intra[df_intra["SessionDate"] == last_session_date]

    last_price = float(last_row["Close"])
    open_price = float(session_df["Open"].iloc[0])
    day_high = float(session_df["High"].max())
    day_low = float(session_df["Low"].min())

    # Previous daily close
    if df_daily is not None and len(df_daily) >= 2:
        prev_close = float(df_daily["Close"].iloc[-2])
    else:
        prev_close = open_price

    intraday_change_pct = ((last_price - open_price) / open_price * 100.0) if open_price > 0 else 0.0
    gap_pct = ((open_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0

    vwap = float(last_row["VWAP"])
    vwap_upper = float(last_row["VWAP_Upper1"])
    vwap_lower = float(last_row["VWAP_Lower1"])
    orb_high = float(last_row["ORB_High"])
    orb_low = float(last_row["ORB_Low"])
    ema9 = float(last_row["EMA9"])
    ema21 = float(last_row["EMA21"])
    ema50 = float(last_row["EMA50"])
    rsi14 = float(last_row["RSI14"])
    stoch_k = float(last_row["StochRSI_K"])
    macd_line = float(last_row["MACD"])
    macd_signal = float(last_row["MACD_Signal"])
    macd_hist = float(last_row["MACD_Hist"])
    prev_macd_hist = float(prev_row["MACD_Hist"])
    atr14 = float(last_row["ATR14"])
    rvol = float(last_row["RVOL"])
    clv = float(last_row["CloseLocationValue"])

    # Rata-rata RVOL 3 bar terakhir agar tidak tertipu 1 bar semu
    recent_rvol = float(df_intra["RVOL"].iloc[-3:].mean())
    effective_rvol = max(rvol, recent_rvol)

    reasons: List[str] = []

    # -------------------------------------------------------------------------
    # PILAR 1: Struktur Harga Pagi, VWAP & Opening Range Breakout (Maks 35 poin)
    # -------------------------------------------------------------------------
    tech_score = 0.0
    if last_price >= vwap:
        tech_score += 14.0
        reasons.append(f"Harga bertahan di atas Institutional VWAP ({format_price(vwap, is_idx)}).")
    else:
        reasons.append(f"Harga masih di bawah VWAP ({format_price(vwap, is_idx)}), waspadai tekanan jual sesi pagi.")

    if last_price >= orb_high:
        tech_score += 11.0
        reasons.append(f"Konfirmasi Opening Range Breakout (ORB High {format_price(orb_high, is_idx)} tertembus).")
    elif last_price >= (orb_high + orb_low) / 2.0:
        tech_score += 6.0
        reasons.append("Harga bergerak di paruh atas Opening Range pagi.")

    if ema9 > ema21 and last_price >= ema9:
        tech_score += 6.0
        reasons.append("EMA-9 berada di atas EMA-21 (struktur tren mikro intraday bullish).")
    elif ema9 > ema21:
        tech_score += 3.5

    # Open-Drive / Morning Bullish Bias (Open tidak jauh dari Low pagi & harga > Open)
    if last_price > open_price and -1.0 <= gap_pct <= 4.0:
        tech_score += 4.0
        reasons.append(f"Akumulasi pagi positif (+{intraday_change_pct:.2f}% dari harga Open tanpa gap berlebih).")
    elif gap_pct > 5.0:
        tech_score -= 3.0
        reasons.append(f"Gap Open cukup tinggi (+{gap_pct:.2f}%), rawan profit-taking sesaat.")

    tech_score = max(0.0, min(35.0, tech_score))

    # -------------------------------------------------------------------------
    # PILAR 2: Momentum & Osilator Intraday (Maks 25 poin)
    # -------------------------------------------------------------------------
    mom_score = 0.0
    if 52.0 <= rsi14 <= 72.0:
        mom_score += 10.0
        reasons.append(f"RSI(14) di zona sweet-spot momentum ({rsi14:.1f}) — kuat namun belum jenuh beli ekstrem.")
    elif 45.0 <= rsi14 < 52.0:
        mom_score += 6.0
    elif rsi14 > 72.0:
        mom_score += 4.0
        reasons.append(f"RSI(14) memasuki area overbought ({rsi14:.1f}), utamakan entry saat pullback ke VWAP/EMA9.")

    if macd_line > macd_signal and macd_hist > 0:
        mom_score += 9.0
        if macd_hist > prev_macd_hist:
            mom_score += 3.0
            reasons.append("Histogram MACD positif dan mengalami akselerasi kenaikan.")
    elif macd_hist > prev_macd_hist:
        mom_score += 4.0

    if 20.0 <= stoch_k <= 85.0 and stoch_k >= float(last_row["StochRSI_D"]):
        mom_score += 3.0

    mom_score = max(0.0, min(25.0, mom_score))

    # -------------------------------------------------------------------------
    # PILAR 3: Volume Spike (RVOL) & Orderflow Proxy (Maks 25 poin)
    # -------------------------------------------------------------------------
    vol_score = 0.0
    if effective_rvol >= 2.0:
        vol_score += 18.0
        reasons.append(f"Lonjakan Volume Institusional: RVOL {effective_rvol:.2f}x di atas rata-rata 20 candle.")
    elif effective_rvol >= 1.3:
        vol_score += 13.0
        reasons.append(f"Volume di atas rata-rata (RVOL {effective_rvol:.2f}x) mendukung likuiditas intraday.")
    elif effective_rvol >= 0.9:
        vol_score += 7.0
    else:
        vol_score += 2.0

    if clv >= 0.65:
        vol_score += 7.0
        reasons.append("Penutupan candle berada dekat titik tertinggi bar (dominasi buyer agresif / HAKA).")
    elif clv >= 0.45:
        vol_score += 3.5

    vol_score = max(0.0, min(25.0, vol_score))

    # -------------------------------------------------------------------------
    # PILAR 4: Sentimen Berita & Katalis Live (Maks 15 poin, basis netral = 7.5)
    # -------------------------------------------------------------------------
    if news_list:
        avg_sent = float(np.mean([n["sentiment_score"] for n in news_list]))
    else:
        avg_sent = 0.0

    news_score = max(0.0, min(15.0, 7.5 + (avg_sent * 7.5)))
    if avg_sent >= 0.20:
        news_catalyst_label = f"Katalis Positif ({avg_sent:+.2f})"
        reasons.append(f"Sentimen pemberitaan terkini cenderung Bullish (skor {avg_sent:+.2f}).")
    elif avg_sent <= -0.20:
        news_catalyst_label = f"Katalis Negatif ({avg_sent:+.2f})"
        reasons.append(f"Waspadai sentimen berita negatif (skor {avg_sent:+.2f}).")
    else:
        news_catalyst_label = f"Netral ({avg_sent:+.2f})"

    total_score = round(tech_score + mom_score + vol_score + news_score, 1)

    # -------------------------------------------------------------------------
    # KLASIFIKASI SINYAL & KALKULASI ENTRY / TP / SL PRESISI (BELI PAGI - JUAL SORE)
    # -------------------------------------------------------------------------
    # Proteksi ATR minimum (minimal 0.6% dari harga agar tidak terlalu sempit terhadap spread)
    effective_atr = max(atr14, last_price * 0.006)

    # Zona Beli Pagi ideal: di sekitar VWAP / EMA9 atau sedikit di atas ORB High
    raw_entry_min = max(min(last_price, vwap), last_price - 0.35 * effective_atr)
    raw_entry_max = last_price + 0.15 * effective_atr

    entry_min = round_to_tick(raw_entry_min, is_idx=is_idx, direction="down")
    entry_max = round_to_tick(raw_entry_max, is_idx=is_idx, direction="up")
    if entry_max <= entry_min:
        entry_max = round_to_tick(entry_min + get_idx_tick_size(entry_min, is_idx), is_idx, "up")

    ref_entry = last_price

    # Stop Loss: di bawah VWAP Lower / ORB Low atau 1.3x ATR Intraday
    structural_support = min(vwap, orb_low if orb_low > 0 else vwap)
    raw_sl = min(ref_entry - 1.3 * effective_atr, structural_support - 0.3 * effective_atr)
    # Batasi risiko maksimum intraday ~2.8% untuk disiplin day trading
    raw_sl = max(raw_sl, ref_entry * 0.972)
    sl_price = round_to_tick(raw_sl, is_idx=is_idx, direction="down")
    if sl_price >= ref_entry:
        sl_price = round_to_tick(ref_entry - 2 * get_idx_tick_size(ref_entry, is_idx), is_idx, "down")

    risk_per_share = max(ref_entry - sl_price, get_idx_tick_size(ref_entry, is_idx))

    # Target Profit Sore (TP1 konservatif sesi siang/sore, TP2 optimal sebelum pre-closing)
    raw_tp1 = max(ref_entry + (risk_per_share * 1.3), vwap_upper)
    raw_tp2 = ref_entry + (risk_per_share * max(rr_target, 1.8))

    tp1_price = round_to_tick(raw_tp1, is_idx=is_idx, direction="up")
    tp2_price = round_to_tick(raw_tp2, is_idx=is_idx, direction="up")
    if tp2_price <= tp1_price:
        tp2_price = round_to_tick(tp1_price + 2 * get_idx_tick_size(tp1_price, is_idx), is_idx, "up")

    tp1_pct = (tp1_price - ref_entry) / ref_entry * 100.0
    tp2_pct = (tp2_price - ref_entry) / ref_entry * 100.0
    sl_pct = (sl_price - ref_entry) / ref_entry * 100.0
    rr_ratio = round((tp2_price - ref_entry) / risk_per_share, 2) if risk_per_share > 0 else 1.5

    if total_score >= 74.0 and last_price >= vwap:
        signal_action = "STRONG BUY (MORNING OPEN / ORB BREAKOUT)"
        badge_class = "badge-buy"
    elif total_score >= 60.0 and last_price >= (vwap * 0.995):
        signal_action = "BUY ON PULLBACK (DEKAT VWAP / EMA-9)"
        badge_class = "badge-buy"
    elif total_score >= 46.0:
        signal_action = "WAIT & WATCH (TUNGGU BREAKOUT VWAP / ORB)"
        badge_class = "badge-watch"
    else:
        signal_action = "AVOID / NO TRADE (MOMENTUM LEMAH)"
        badge_class = "badge-avoid"

    time_exit = (
        "Beli Sesi I Pagi (09:05–10:00 WIB) • Wajib Jual Sesi II Sore (15:30–15:48 WIB sebelum Pre-Closing)"
        if is_idx
        else "Buy Morning Open (09:35–10:30 EST) • Mandatory Exit Pre-Close (15:45–15:58 EST)"
    )

    return TradePlan(
        ticker=ticker,
        is_idx=is_idx,
        last_price=last_price,
        open_price=open_price,
        prev_close=prev_close,
        day_high=day_high,
        day_low=day_low,
        vwap=vwap,
        vwap_upper=vwap_upper,
        vwap_lower=vwap_lower,
        orb_high=orb_high,
        orb_low=orb_low,
        ema9=ema9,
        ema21=ema21,
        ema50=ema50,
        rsi14=rsi14,
        stoch_k=stoch_k,
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        atr14=atr14,
        rvol=effective_rvol,
        intraday_change_pct=intraday_change_pct,
        gap_pct=gap_pct,
        news_sentiment_score=avg_sent,
        news_catalyst_label=news_catalyst_label,
        technical_score=round(tech_score, 1),
        momentum_score=round(mom_score, 1),
        volume_score=round(vol_score, 1),
        news_score=round(news_score, 1),
        total_conviction_score=total_score,
        signal_action=signal_action,
        signal_badge_class=badge_class,
        entry_min=entry_min,
        entry_max=entry_max,
        tp1_price=tp1_price,
        tp2_price=tp2_price,
        sl_price=sl_price,
        tp1_pct=round(tp1_pct, 2),
        tp2_pct=round(tp2_pct, 2),
        sl_pct=round(sl_pct, 2),
        rr_ratio=rr_ratio,
        time_exit_rule=time_exit,
        reasons=reasons,
    )


# =========================================================================================
# 7. BACKEND: WALK-FORWARD INTRADAY BACKTESTER (SIMULASI BELI PAGI -> JUAL SORE)
# =========================================================================================
def backtest_open_to_close_strategy(
    df_intra: pd.DataFrame,
    df_daily: pd.DataFrame,
    tp_pct_target: float = 2.2,
    sl_pct_limit: float = 1.2,
    fee_roundtrip_pct: float = 0.40,
    only_morning_vwap_filter: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Menguji akurasi strategi 'Beli Pagi (setelah 15 menit pembukaan / konfirmasi VWAP)
    dan Jual Sore (sebelum Market Close, atau ketika menyentuh TP / SL intraday)'
    pada data historis yang tersedia.
    """
    trades = []

    # 1. Evaluasi per sesi dari data intraday yang termuat
    if df_intra is not None and not df_intra.empty:
        for session_date, group in df_intra.groupby("SessionDate"):
            if len(group) < 4:
                continue
            # Masuk pada penutupan bar ke-2 sesi pagi (setelah arah pembukaan terlihat)
            entry_idx = min(1, len(group) - 2)
            entry_bar = group.iloc[entry_idx]
            entry_price = float(entry_bar["Close"])
            entry_vwap = float(entry_bar["VWAP"])

            if only_morning_vwap_filter and entry_price < entry_vwap * 0.997:
                # Filter disiplin: Hanya ambil posisi jika pagi hari harga tidak jatuh jauh di bawah VWAP
                continue

            tp_level = entry_price * (1.0 + tp_pct_target / 100.0)
            sl_level = entry_price * (1.0 - sl_pct_limit / 100.0)

            remaining_bars = group.iloc[entry_idx + 1 :]
            exit_price = float(group.iloc[-1]["Close"])
            exit_reason = "Time Exit (Jual Sore Pre-Close)"
            exit_time = group.index[-1]

            for ts, bar in remaining_bars.iterrows():
                if float(bar["Low"]) <= sl_level:
                    exit_price = sl_level
                    exit_reason = "Stop Loss Intraday"
                    exit_time = ts
                    break
                if float(bar["High"]) >= tp_level:
                    exit_price = tp_level
                    exit_reason = "Target Profit Tercapai"
                    exit_time = ts
                    break

            gross_ret = (exit_price - entry_price) / entry_price * 100.0
            net_ret = gross_ret - fee_roundtrip_pct
            trades.append(
                {
                    "Tanggal Sesi": str(session_date),
                    "Harga Beli (Pagi)": round(entry_price, 2),
                    "Harga Jual (Sore/Exit)": round(exit_price, 2),
                    "Alasan Exit": exit_reason,
                    "Gross Return (%)": round(gross_ret, 2),
                    "Net Return Setelah Fee (%)": round(net_ret, 2),
                }
            )

    # 2. Jika sampel sesi intraday < 5 hari, perkaya dengan simulasi Open-to-Close dari Daily OHLCV (60 hari)
    if len(trades) < 5 and df_daily is not None and len(df_daily) >= 10:
        trades = []
        daily_slice = df_daily.tail(45).copy()
        daily_slice["EMA9_D"] = daily_slice["Close"].ewm(span=9, adjust=False).mean()
        for idx_ts, row in daily_slice.iterrows():
            o_price = float(row["Open"])
            h_price = float(row["High"])
            l_price = float(row["Low"])
            c_price = float(row["Close"])
            if o_price <= 0:
                continue

            # Filter momentum pagi: Open tidak boleh breakdown parah dari Low (Open-Drive filter)
            if only_morning_vwap_filter and c_price < float(row["EMA9_D"]) * 0.985 and h_price <= o_price:
                continue

            tp_level = o_price * (1.0 + tp_pct_target / 100.0)
            sl_level = o_price * (1.0 - sl_pct_limit / 100.0)

            # Estimasi konservatif urutan sentuh pada bar harian
            if l_price <= sl_level and c_price < o_price:
                exit_p = sl_level
                reason = "Stop Loss Intraday"
            elif h_price >= tp_level:
                exit_p = tp_level
                reason = "Target Profit Tercapai"
            elif l_price <= sl_level:
                exit_p = sl_level
                reason = "Stop Loss Intraday"
            else:
                exit_p = c_price
                reason = "Time Exit (Jual Sore Close)"

            gross_ret = (exit_p - o_price) / o_price * 100.0
            net_ret = gross_ret - fee_roundtrip_pct
            trades.append(
                {
                    "Tanggal Sesi": str(idx_ts.date()),
                    "Harga Beli (Pagi)": round(o_price, 2),
                    "Harga Jual (Sore/Exit)": round(exit_p, 2),
                    "Alasan Exit": reason,
                    "Gross Return (%)": round(gross_ret, 2),
                    "Net Return Setelah Fee (%)": round(net_ret, 2),
                }
            )

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        return df_trades, {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_net_return": 0.0,
            "cum_return": 0.0,
            "profit_factor": 0.0,
        }

    wins = df_trades[df_trades["Net Return Setelah Fee (%)"] > 0]
    losses = df_trades[df_trades["Net Return Setelah Fee (%)"] <= 0]
    win_rate = len(wins) / len(df_trades) * 100.0
    avg_net = float(df_trades["Net Return Setelah Fee (%)"].mean())

    df_trades["Equity_Curve"] = (1.0 + df_trades["Net Return Setelah Fee (%)"] / 100.0).cumprod() * 100.0
    cum_ret = float(df_trades["Equity_Curve"].iloc[-1] - 100.0)

    gross_profit = float(wins["Net Return Setelah Fee (%)"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["Net Return Setelah Fee (%)"].sum())) if not losses.empty else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (9.99 if gross_profit > 0 else 0.0)

    metrics = {
        "total_trades": int(len(df_trades)),
        "win_rate": round(win_rate, 1),
        "avg_net_return": round(avg_net, 2),
        "cum_return": round(cum_ret, 2),
        "profit_factor": profit_factor,
    }
    return df_trades, metrics


# =========================================================================================
# 8. VISUALISASI CHART PLOTLY INTERAKTIF (CANDLESTICK + VWAP + ORB + VOLUME + RSI/MACD)
# =========================================================================================
def build_intraday_plotly_chart(df: pd.DataFrame, plan: TradePlan) -> go.Figure:
    """Membangun chart teknikal multi-panel kelas institusional."""
    plot_df = df.tail(95).copy()
    x_labels = [ts.strftime("%d %b %H:%M") for ts in plot_df.index]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.58, 0.20, 0.22],
        subplot_titles=(
            f"{plan.ticker} — Candlestick Intraday, Institutional VWAP, EMA 9/21 & Opening Range (ORB)",
            "Volume & Relative Volume (RVOL) Spike",
            "Momentum Intraday: Wilder's RSI(14) & MACD Histogram",
        ),
    )

    # Panel 1: Candlestick + VWAP + Bands + EMA + ORB
    fig.add_trace(
        go.Candlestick(
            x=x_labels,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="OHLC",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=plot_df["VWAP"],
            mode="lines",
            name="Session VWAP",
            line=dict(color="#f59e0b", width=2.4),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=plot_df["EMA9"],
            mode="lines",
            name="EMA 9 (Fast)",
            line=dict(color="#38bdf8", width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=plot_df["EMA21"],
            mode="lines",
            name="EMA 21 (Slow)",
            line=dict(color="#a855f7", width=1.5, dash="dot"),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=plot_df["ORB_High"],
            mode="lines",
            name="ORB High (Breakout Pagi)",
            line=dict(color="#22c55e", width=1.2, dash="dash"),
        ),
        row=1,
        col=1,
    )

    # Garis Horizontal Target Profit & Stop Loss
    fig.add_hline(
        y=plan.tp2_price,
        line_dash="dash",
        line_color="#10b981",
        annotation_text=f"TP2 Sore: {format_price(plan.tp2_price, plan.is_idx)}",
        annotation_position="top left",
        row=1,
        col=1,
    )
    fig.add_hline(
        y=plan.sl_price,
        line_dash="dash",
        line_color="#ef4444",
        annotation_text=f"SL: {format_price(plan.sl_price, plan.is_idx)}",
        annotation_position="bottom left",
        row=1,
        col=1,
    )

    # Panel 2: Volume Bar
    vol_colors = [
        "#10b981" if c >= o else "#ef4444"
        for c, o in zip(plot_df["Close"], plot_df["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=x_labels,
            y=plot_df["Volume"],
            name="Volume",
            marker_color=vol_colors,
            opacity=0.85,
        ),
        row=2,
        col=1,
    )

    # Panel 3: RSI(14)
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=plot_df["RSI14"],
            mode="lines",
            name="RSI (14)",
            line=dict(color="#e2e8f0", width=1.8),
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#64748b", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#10b981", row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=740,
        margin=dict(l=20, r=20, t=45, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
    )
    fig.update_xaxes(type="category", nticks=12, showgrid=True, gridcolor="#1e293b")
    fig.update_yaxes(showgrid=True, gridcolor="#1e293b")
    return fig


# =========================================================================================
# 9. MAIN STREAMLIT DASHBOARD UI & WORKFLOW
# =========================================================================================
def main() -> None:
    # Header Banner
    st.markdown(
        """
        <div class="main-header">
            <h1>📈 QuantPulse Intraday Pro — Dashboard Scalping & Day Trading Saham</h1>
            <p>Strategi Kuantitatif Presisi Tinggi: <b>Beli Pagi Saat Market Open (ORB & VWAP Confirmation) • Jual Sore Sebelum Market Close (Zero Overnight Risk)</b></p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------------------
    # SIDEBAR: PARAMETER TRADING, MODAL & FILTER SCREENER
    # -------------------------------------------------------------------------------------
    with st.sidebar:
        st.header("⚙️ Parameter Strategi & Modal")

        selected_preset = st.selectbox(
            "Pilih Universe / Watchlist Saham:",
            options=list(PRESET_WATCHLISTS.keys()),
            index=0,
        )

        default_tickers = PRESET_WATCHLISTS[selected_preset]
        selected_tickers = st.multiselect(
            "Daftar Saham yang Dipindai (Screener):",
            options=default_tickers,
            default=default_tickers[:8],
            help="Pilih saham yang ingin dianalisis secara serentak.",
        )

        custom_ticker_input = st.text_input(
            "Tambah Kode Saham Manual (pisahkan koma):",
            placeholder="Contoh: BRPT.JK, TPIA.JK, NVDA",
            help="Gunakan akhiran .JK untuk saham Bursa Efek Indonesia (BEI).",
        )
        if custom_ticker_input.strip():
            extra = [t.strip().upper() for t in custom_ticker_input.split(",") if t.strip()]
            for t_code in extra:
                if t_code not in selected_tickers:
                    selected_tickers.append(t_code)

        st.divider()
        st.subheader("⏱️ Timeframe & Aturan Intraday")
        interval_choice = st.selectbox(
            "Timeframe Chart Intraday:",
            options=["5m", "15m", "1m"],
            index=0,
            help="5m dan 15m adalah standar institusional untuk strategi Beli Pagi - Jual Sore.",
        )
        period_map = {"1m": "5d", "5m": "5d", "15m": "1mo"}
        orb_bars = st.slider(
            "Periode Opening Range Pagi (Jumlah Candle):",
            min_value=2,
            max_value=6,
            value=3,
            help="Menentukan batas ORB High & Low dari N candle pertama saat pasar buka pagi.",
        )
        rr_target = st.slider(
            "Target Risk-to-Reward Ratio (Sore):",
            min_value=1.2,
            max_value=3.5,
            value=1.8,
            step=0.1,
        )

        st.divider()
        st.subheader("💰 Kalkulator Modal & Risiko (Position Sizing)")
        total_capital = st.number_input(
            "Total Modal Trading (Rp / USD):",
            min_value=100_000.0,
            value=25_000_000.0,
            step=1_000_000.0,
        )
        max_risk_pct = st.slider(
            "Risiko Maksimal per Transaksi (% dari Modal):",
            min_value=0.25,
            max_value=3.0,
            value=1.0,
            step=0.25,
        )
        max_alloc_pct = st.slider(
            "Alokasi Modal Maksimal per Saham (%):",
            min_value=10,
            max_value=100,
            value=30,
            step=5,
        )
        broker_buy_fee = st.number_input("Fee Beli Sekuritas (%):", value=0.15, step=0.01)
        broker_sell_fee = st.number_input("Fee Jual Sekuritas (%):", value=0.25, step=0.01)

        if st.button("🔄 Refresh Data & Berita Live Sekarang", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not selected_tickers:
        st.warning("Silakan pilih minimal 1 saham di panel samping untuk memulai pemindaian.")
        return

    # -------------------------------------------------------------------------------------
    # PROSES PEMINDAIAN KUANTITATIF (SCREENER ENGINE)
    # -------------------------------------------------------------------------------------
    plans: List[TradePlan] = []
    intraday_cache: Dict[str, pd.DataFrame] = {}
    daily_cache: Dict[str, pd.DataFrame] = {}
    news_cache: Dict[str, List[Dict]] = {}

    progress_bar = st.progress(0, text="Memindai data pasar real-time, VWAP, ORB & sentimen berita...")
    for idx, ticker in enumerate(selected_tickers):
        df_intra, df_daily = fetch_intraday_and_daily_data(
            ticker, interval=interval_choice, period=period_map[interval_choice]
        )
        if not df_intra.empty:
            df_intra = compute_intraday_indicators(df_intra, orb_bars=orb_bars)
            intraday_cache[ticker] = df_intra
            daily_cache[ticker] = df_daily
            ticker_news = fetch_live_news_for_ticker(ticker, max_items=6)
            news_cache[ticker] = ticker_news

            plan = evaluate_intraday_setup(
                ticker=ticker,
                df_intra=df_intra,
                df_daily=df_daily,
                news_list=ticker_news,
                rr_target=rr_target,
            )
            if plan is not None:
                plans.append(plan)

        progress_bar.progress(
            (idx + 1) / len(selected_tickers),
            text=f"Memproses analisis kuantitatif & berita live: {ticker} ({idx + 1}/{len(selected_tickers)})",
        )
    progress_bar.empty()

    if not plans:
        st.error("Tidak dapat mengambil data pasar saat ini. Periksa koneksi internet atau kode saham.")
        return

    # Urutkan berdasarkan Total Conviction Score tertinggi
    plans.sort(key=lambda x: x.total_conviction_score, reverse=True)
    top_pick = plans[0]

    # -------------------------------------------------------------------------------------
    # RINGKASAN METRIK UTAMA PASAR & TOP PICK HARI INI
    # -------------------------------------------------------------------------------------
    strong_buys = [p for p in plans if "BUY" in p.signal_action]
    avg_conviction = np.mean([p.total_conviction_score for p in plans])
    avg_rvol = np.mean([p.rvol for p in plans])

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric(
        "🏆 Top Pick Intraday Hari Ini",
        f"{top_pick.ticker}",
        f"Skor: {top_pick.total_conviction_score:.1f}/100",
    )
    col_m2.metric(
        "✅ Saham Layak Beli Pagi",
        f"{len(strong_buys)} dari {len(plans)} Emiten",
        f"Avg Skor: {avg_conviction:.1f}",
    )
    col_m3.metric(
        "📊 Rata-Rata Lonjakan Volume (RVOL)",
        f"{avg_rvol:.2f}x",
        "Likuiditas Sesi Berjalan",
    )
    col_m4.metric(
        "⏰ Disiplin Jam Eksekusi",
        "09:05 -> 15:45 WIB",
        "Zero Overnight Risk",
    )

    # -------------------------------------------------------------------------------------
    # TABS UTAMA DASHBOARD
    # -------------------------------------------------------------------------------------
    tab_screener, tab_deepdive, tab_news, tab_backtest, tab_sop = st.tabs(
        [
            "🎯 1. Screener & Rekomendasi Beli Pagi - Jual Sore",
            "🔬 2. Analisis Teknikal Mendalam & Kalkulator Lot",
            "📰 3. Live News & Sentimen Katalis Real-Time",
            "🧪 4. Backtest Akurasi Strategi (Open-to-Close)",
            "📘 5. SOP & Algoritma Intraday Presisi Tinggi",
        ]
    )

    # =====================================================================================
    # TAB 1: SCREENER MULTI-SAHAM & RANKING KUANTITATIF
    # =====================================================================================
    with tab_screener:
        st.subheader("🔥 Peringkat Rekomendasi Saham Intraday (Diurutkan Berdasarkan Skor Konviksi Kuantitatif)")
        st.caption(
            "Prioritaskan saham dengan sinyal **STRONG BUY** atau **BUY ON PULLBACK**, "
            "berada di atas **VWAP**, memiliki **RVOL > 1.3x**, dan katalis berita positif/netral."
        )

        screener_rows = []
        for p in plans:
            screener_rows.append(
                {
                    "Ticker": p.ticker,
                    "Sinyal Rekomendasi": p.signal_action,
                    "Skor Konviksi (0-100)": p.total_conviction_score,
                    "Harga Terakhir": format_price(p.last_price, p.is_idx),
                    "Chg dari Open (%)": f"{p.intraday_change_pct:+.2f}%",
                    "VWAP Sesi": format_price(p.vwap, p.is_idx),
                    "Zona Beli Pagi": f"{format_price(p.entry_min, p.is_idx)} - {format_price(p.entry_max, p.is_idx)}",
                    "TP1 (Siang/Sore)": f"{format_price(p.tp1_price, p.is_idx)} (+{p.tp1_pct:.2f}%)",
                    "TP2 (Pre-Close)": f"{format_price(p.tp2_price, p.is_idx)} (+{p.tp2_pct:.2f}%)",
                    "Stop Loss (SL)": f"{format_price(p.sl_price, p.is_idx)} ({p.sl_pct:.2f}%)",
                    "R:R": f"1 : {p.rr_ratio}",
                    "RSI(14)": round(p.rsi14, 1),
                    "RVOL": f"{p.rvol:.2f}x",
                    "Sentimen Berita": p.news_catalyst_label,
                }
            )

        df_screener = pd.DataFrame(screener_rows)
        st.dataframe(df_screener, use_container_width=True, hide_index=True)

        # Highlight Top 3 Actionable Cards
        st.markdown("### ⚡ Top 3 Setup Terbaik untuk Eksekusi Pagi Ini")
        top_cols = st.columns(min(3, len(plans)))
        for idx_c, col_obj in enumerate(top_cols):
            cand = plans[idx_c]
            with col_obj:
                st.markdown(
                    f"""
                    <div class="signal-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h3 style="margin:0;">{cand.ticker}</h3>
                            <span class="{cand.signal_badge_class}">{cand.total_conviction_score:.1f} / 100</span>
                        </div>
                        <p style="margin:0.4rem 0; font-weight:700; color:#38bdf8;">{cand.signal_action}</p>
                        <hr style="border-color:#334155; margin:0.5rem 0;">
                        <p style="margin:0.2rem 0;"><b>Harga Saat Ini:</b> {format_price(cand.last_price, cand.is_idx)} ({cand.intraday_change_pct:+.2f}% dari Open)</p>
                        <p style="margin:0.2rem 0;"><b>Area Beli Pagi:</b> {format_price(cand.entry_min, cand.is_idx)} – {format_price(cand.entry_max, cand.is_idx)}</p>
                        <p style="margin:0.2rem 0; color:#34d399;"><b>Target Jual Sore (TP1 / TP2):</b> {format_price(cand.tp1_price, cand.is_idx)} / {format_price(cand.tp2_price, cand.is_idx)}</p>
                        <p style="margin:0.2rem 0; color:#f87171;"><b>Batas Cut Loss (SL):</b> {format_price(cand.sl_price, cand.is_idx)} ({cand.sl_pct:.2f}%)</p>
                        <p style="margin:0.2rem 0; font-size:0.85rem; color:#94a3b8;">VWAP: {format_price(cand.vwap, cand.is_idx)} | RVOL: {cand.rvol:.2f}x | RSI: {cand.rsi14:.1f}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # =====================================================================================
    # TAB 2: ANALISIS TEKNIKAL MENDALAM, CHART PLOTLY & KALKULATOR LOT PRESISI
    # =====================================================================================
    with tab_deepdive:
        selected_detail_ticker = st.selectbox(
            "Pilih Saham untuk Bedah Chart Intraday & Rencana Eksekusi Lengkap:",
            options=[p.ticker for p in plans],
            index=0,
        )
        active_plan = next(p for p in plans if p.ticker == selected_detail_ticker)
        active_df = intraday_cache[selected_detail_ticker]

        left_col, right_col = st.columns([2.1, 1.0])

        with left_col:
            fig_chart = build_intraday_plotly_chart(active_df, active_plan)
            st.plotly_chart(fig_chart, use_container_width=True)

        with right_col:
            st.markdown(
                f"""
                <div class="signal-card">
                    <h3 style="margin-top:0;">🎯 Trading Plan: {active_plan.ticker}</h3>
                    <span class="{active_plan.signal_badge_class}">{active_plan.signal_action}</span>
                    <p style="margin-top:0.7rem; margin-bottom:0.3rem;"><b>Skor Total Kuantitatif:</b> {active_plan.total_conviction_score:.1f} / 100</p>
                    <ul style="font-size:0.88rem; color:#cbd5e1; padding-left:1.2rem; margin-top:0.2rem;">
                        <li>Struktur VWAP & ORB: <b>{active_plan.technical_score}/35</b></li>
                        <li>Momentum (RSI/MACD): <b>{active_plan.momentum_score}/25</b></li>
                        <li>Volume Spike (RVOL): <b>{active_plan.volume_score}/25</b></li>
                        <li>Katalis Berita Live: <b>{active_plan.news_score}/15</b></li>
                    </ul>
                    <hr style="border-color:#334155;">
                    <p style="margin:0.25rem 0;"><b>Harga Open Pagi:</b> {format_price(active_plan.open_price, active_plan.is_idx)} (Gap: {active_plan.gap_pct:+.2f}%)</p>
                    <p style="margin:0.25rem 0;"><b>Harga Terakhir:</b> {format_price(active_plan.last_price, active_plan.is_idx)}</p>
                    <p style="margin:0.25rem 0;"><b>VWAP Intraday:</b> {format_price(active_plan.vwap, active_plan.is_idx)}</p>
                    <p style="margin:0.25rem 0;"><b>ORB High / Low Pagi:</b> {format_price(active_plan.orb_high, active_plan.is_idx)} / {format_price(active_plan.orb_low, active_plan.is_idx)}</p>
                    <hr style="border-color:#334155;">
                    <p style="margin:0.25rem 0; color:#38bdf8;"><b>🟢 Zona Beli Pagi:</b> {format_price(active_plan.entry_min, active_plan.is_idx)} – {format_price(active_plan.entry_max, active_plan.is_idx)}</p>
                    <p style="margin:0.25rem 0; color:#34d399;"><b>🎯 Target Jual 1 (TP1):</b> {format_price(active_plan.tp1_price, active_plan.is_idx)} (+{active_plan.tp1_pct:.2f}%)</p>
                    <p style="margin:0.25rem 0; color:#10b981;"><b>🚀 Target Jual Sore (TP2):</b> {format_price(active_plan.tp2_price, active_plan.is_idx)} (+{active_plan.tp2_pct:.2f}%)</p>
                    <p style="margin:0.25rem 0; color:#f87171;"><b>🛑 Stop Loss Ketat (SL):</b> {format_price(active_plan.sl_price, active_plan.is_idx)} ({active_plan.sl_pct:.2f}%)</p>
                    <p style="margin:0.4rem 0 0 0; font-size:0.82rem; color:#fbbf24;">⏰ <b>Aturan Waktu:</b> {active_plan.time_exit_rule}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Position Sizing & Broker Fee Calculator
            st.markdown("#### 🧮 Kalkulator Lot & Estimasi Profit Bersih")
            lot_multiplier = 100 if active_plan.is_idx else 1
            unit_label = "Lot (100 Lembar)" if active_plan.is_idx else "Shares"

            max_risk_money = total_capital * (max_risk_pct / 100.0)
            max_alloc_money = total_capital * (max_alloc_pct / 100.0)

            risk_per_share = max(
                active_plan.last_price - active_plan.sl_price,
                get_idx_tick_size(active_plan.last_price, active_plan.is_idx),
            )
            shares_by_risk = max_risk_money / risk_per_share if risk_per_share > 0 else 0
            shares_by_alloc = max_alloc_money / active_plan.last_price if active_plan.last_price > 0 else 0

            recommended_shares = min(shares_by_risk, shares_by_alloc)
            recommended_lots = max(1, int(math.floor(recommended_shares / lot_multiplier)))
            actual_shares = recommended_lots * lot_multiplier

            gross_buy_val = actual_shares * active_plan.last_price
            buy_fee_val = gross_buy_val * (broker_buy_fee / 100.0)
            total_modal_used = gross_buy_val + buy_fee_val

            # Estimasi Net Profit di TP2 & Net Loss di SL (sudah dipotong fee beli + jual)
            gross_tp2_val = actual_shares * active_plan.tp2_price
            sell_fee_tp2 = gross_tp2_val * (broker_sell_fee / 100.0)
            net_profit_tp2 = (gross_tp2_val - sell_fee_tp2) - total_modal_used

            gross_sl_val = actual_shares * active_plan.sl_price
            sell_fee_sl = gross_sl_val * (broker_sell_fee / 100.0)
            net_loss_sl = (gross_sl_val - sell_fee_sl) - total_modal_used

            st.info(
                f"**Rekomendasi Ukuran Posisi:** `{recommended_lots:,} {unit_label}` "
                f"({actual_shares:,} lembar)\n\n"
                f"- **Modal Terpakai (+Fee Beli):** {format_price(total_modal_used, active_plan.is_idx)}\n"
                f"- **Est. Profit Bersih di TP2 Sore:** +{format_price(net_profit_tp2, active_plan.is_idx)}\n"
                f"- **Est. Risiko Maksimal di SL:** {format_price(net_loss_sl, active_plan.is_idx)}"
            )

        st.markdown("#### 🔍 Rasional Analisis Kuantitatif & Konfirmasi Indikator")
        for r_item in active_plan.reasons:
            st.markdown(f"- {r_item}")

    # =====================================================================================
    # TAB 3: LIVE NEWS & SENTIMEN KATALIS REAL-TIME
    # =====================================================================================
    with tab_news:
        col_n1, col_n2 = st.columns([1.2, 1.0])

        with col_n1:
            st.subheader(f"📰 Berita & Katalis Terkini Emiten: {selected_detail_ticker}")
            ticker_news_items = news_cache.get(selected_detail_ticker, [])
            if not ticker_news_items:
                st.info("Belum ada berita spesifik terbaru untuk emiten ini dalam beberapa jam terakhir.")
            else:
                for n in ticker_news_items:
                    css_cls = (
                        "news-pos"
                        if n["sentiment_score"] >= 0.25
                        else ("news-neg" if n["sentiment_score"] <= -0.25 else "news-neu")
                    )
                    st.markdown(
                        f"""
                        <div class="news-card {css_cls}">
                            <div style="font-size:0.8rem; color:#94a3b8; display:flex; justify-content:space-between;">
                                <span><b>{html.escape(str(n['source']))}</b> • {html.escape(str(n['published']))}</span>
                                <span>Sentimen: <b>{n['sentiment_label']} ({n['sentiment_score']:+.2f})</b></span>
                            </div>
                            <div style="margin-top:0.3rem; font-size:0.95rem;">
                                <a href="{html.escape(str(n['link']))}" target="_blank" style="color:#f8fafc; text-decoration:none; font-weight:600;">
                                    {html.escape(str(n['title']))} 🔗
                                </a>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with col_n2:
            st.subheader("🌐 Radar Berita Pasar & Makro (IHSG / Global Live RSS)")
            market_news = fetch_general_market_news()
            if not market_news:
                st.info("Sedang memuat feed berita pasar...")
            else:
                for mn in market_news:
                    css_cls = (
                        "news-pos"
                        if mn["sentiment_score"] >= 0.25
                        else ("news-neg" if mn["sentiment_score"] <= -0.25 else "news-neu")
                    )
                    st.markdown(
                        f"""
                        <div class="news-card {css_cls}">
                            <div style="font-size:0.78rem; color:#94a3b8; display:flex; justify-content:space-between;">
                                <span><b>{html.escape(str(mn['source']))}</b></span>
                                <span><b>{mn['sentiment_label']}</b></span>
                            </div>
                            <div style="margin-top:0.25rem; font-size:0.9rem;">
                                <a href="{html.escape(str(mn['link']))}" target="_blank" style="color:#e2e8f0; text-decoration:none;">
                                    {html.escape(str(mn['title']))} 🔗
                                </a>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    # =====================================================================================
    # TAB 4: WALK-FORWARD INTRADAY BACKTESTER (UJI AKURASI HISTORIS)
    # =====================================================================================
    with tab_backtest:
        st.subheader(f"🧪 Backtest Strategi 'Beli Pagi Saat Open – Jual Sore Sebelum Close' ({selected_detail_ticker})")
        st.caption(
            "Simulasi menguji aturan disiplin: Entry di sesi pagi ketika harga terkonfirmasi di sekitar/atas VWAP, "
            "keluar saat menyentuh Target Profit (TP), Stop Loss (SL), atau wajib likuidasi di sore hari sebelum penutupan pasar (sudah memperhitungkan fee sekuritas)."
        )

        bt_col1, bt_col2, bt_col3 = st.columns(3)
        bt_tp = bt_col1.slider("Target Profit Intraday Simulasi (%):", 0.8, 6.0, 2.2, 0.2)
        bt_sl = bt_col2.slider("Stop Loss Intraday Simulasi (%):", 0.5, 4.0, 1.2, 0.1)
        bt_vwap_filter = bt_col3.checkbox(
            "Aktifkan Filter Konfirmasi VWAP/Momentum Pagi", value=True
        )

        roundtrip_fee = broker_buy_fee + broker_sell_fee
        df_bt, bt_metrics = backtest_open_to_close_strategy(
            df_intra=intraday_cache[selected_detail_ticker],
            df_daily=daily_cache[selected_detail_ticker],
            tp_pct_target=bt_tp,
            sl_pct_limit=bt_sl,
            fee_roundtrip_pct=roundtrip_fee,
            only_morning_vwap_filter=bt_vwap_filter,
        )

        m_c1, m_c2, m_c3, m_c4, m_c5 = st.columns(5)
        m_c1.metric("Total Sesi Diuji", f"{bt_metrics['total_trades']} Transaksi")
        m_c2.metric("Win Rate Akurasi", f"{bt_metrics['win_rate']:.1f}%")
        m_c3.metric("Profit Factor", f"{bt_metrics['profit_factor']:.2f}")
        m_c4.metric("Rata-Rata Net/Trade", f"{bt_metrics['avg_net_return']:+.2f}%")
        m_c5.metric("Kumulatif Net Return", f"{bt_metrics['cum_return']:+.2f}%")

        if not df_bt.empty:
            fig_eq = go.Figure()
            fig_eq.add_trace(
                go.Scatter(
                    x=df_bt["Tanggal Sesi"],
                    y=df_bt["Equity_Curve"],
                    mode="lines+markers",
                    name="Kurva Ekuitas (Basis 100)",
                    line=dict(color="#10b981", width=2.5),
                    fill="tozeroy",
                    fillcolor="rgba(16, 185, 129, 0.12)",
                )
            )
            fig_eq.update_layout(
                title=f"Pertumbuhan Ekuitas Strategi Intraday (Beli Pagi - Jual Sore) — {selected_detail_ticker}",
                template="plotly_dark",
                height=340,
                margin=dict(l=20, r=20, t=40, b=20),
                paper_bgcolor="#0f172a",
                plot_bgcolor="#0f172a",
            )
            st.plotly_chart(fig_eq, use_container_width=True)
            st.dataframe(df_bt, use_container_width=True, hide_index=True)

    # =====================================================================================
    # TAB 5: SOP EKSEKUSI & PANDUAN ARSITEKTUR KUANTITATIF
    # =====================================================================================
    with tab_sop:
        st.markdown(
            """
            ### 📘 Standar Operasional Prosedur (SOP) Intraday Trading: Beli Pagi, Jual Sore

            Agar tingkat akurasi dan presisi mencapai probabilitas institusional tertinggi, ikuti protokol eksekusi 4 tahap berikut setiap hari bursa:

            1. **Tahap 1 — Seleksi Pre-Market & Pembukaan Pagi (08:45 – 09:15 WIB):**
               - Hindari langsung melakukan *market order* buta pada detik `09:00:01` karena volatilitas semu (*opening noise*).
               - Biarkan **2 hingga 3 candle pertama (5m/15m)** terbentuk untuk memetakan **Opening Range High (ORB High)**, **ORB Low**, dan garis **Institutional VWAP**.
               - Periksa **Tab 3 (Live News)**: pastikan tidak ada katalis negatif mendadak (seperti suspensi, PKPU, atau *net sell* masif).

            2. **Tahap 2 — Kriteria Entry Presisi Pagi Hari (09:15 – 10:15 WIB):**
               - **Skenario A (ORB Breakout):** Masuk *Buy* ketika candle menutup di atas **ORB High** dan berada di atas **VWAP**, didukung oleh **RVOL ≥ 1.5x** serta **Histogram MACD positif**.
               - **Skenario B (VWAP Pullback — Risiko Paling Rendah):** Jika saham mengalami kenaikan kuat saat pembukaan lalu terkoreksi sehat menyentuh garis **VWAP** atau **EMA-9** dengan volume jual yang mengecil, lakukan *Buy on Weakness* di **Zona Beli Pagi** dengan Stop Loss ketat 1–2 fraksi di bawah VWAP/ORB Low.

            3. **Tahap 3 — Manajemen Posisi Sesi Siang (11:00 – 14:30 WIB):**
               - Ketika harga menyentuh **TP1 (Target Konservatif)**, jual **50% porsi lot** untuk mengunci keuntungan (*scale-out*) dan geser Stop Loss sisanya ke harga beli (*Break-Even Stop*).

            4. **Tahap 4 — Aturan Wajib Exit Sore Hari (15:30 – 15:48 WIB sebelum Pre-Closing):**
               - Apabila hingga pukul **15:30 – 15:45 WIB** (untuk BEI/IDX) posisi masih terbuka dan belum menyentuh TP2 maupun SL, **wajib lakukan penjualan (Time-Based Exit)** sebelum sesi *Pre-Closing* (15:50 WIB).
               - Prinsip utama *Day Trading* murni adalah **100% Cash saat pasar tutup**, sehingga modal Anda bebas dari risiko *gap down* semalam akibat gejolak bursa global.
            """
        )


if __name__ == "__main__":
    main()