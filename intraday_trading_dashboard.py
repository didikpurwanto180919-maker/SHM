import os
import re
import sys
import html
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 0. AUTO-INSTALLER PUSTAKA (ANTI-MODULENOTFOUND)
# ==========================================
def verify_and_install(package_name: str, import_name: str = None):
    """Memastikan pustaka utama terinstal di server Streamlit Cloud."""
    mod_name = import_name or package_name
    try:
        __import__(mod_name)
    except ModuleNotFoundError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

verify_and_install("yfinance")
verify_and_install("plotly")

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. KONFIGURASI HALAMAN & KONSTANTA PASAR
# ==========================================
st.set_page_config(
    page_title="IDX, MSCI & Real-Time News Intelligence Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSV_FILENAME = "daftar_lengkap_saham_indonesia_bei.csv"

MSCI_CONSTITUENTS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "BBNI", "AMMN",
    "GOTO", "ADRO", "ICBP", "UNTR", "KLBF", "INDF", "CPIN"
]

# Daftar RSS Feed Real-Time Terkategori (Sesuai Referensi Pasar Modal Indonesia)
REALTIME_RSS_FEEDS = {
    "Rekomendasi Saham & Target Harga Sekuritas": [
        ("Rekomendasi Saham Hari Ini (Semua Sekuritas)", "https://news.google.com/rss/search?q=%22rekomendasi+saham+hari+ini%22+OR+%22saham+pilihan%22+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Rekomendasi CNBC & Kontan", "https://news.google.com/rss/search?q=(site:cnbcindonesia.com+OR+site:kontan.co.id)+(%22rekomendasi+saham%22+OR+%22saham+pilihan%22+OR+%22target+harga%22)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Rekomendasi Bisnis.com", "https://news.google.com/rss/search?q=site:market.bisnis.com+(%22rekomendasi+saham%22+OR+%22saham+pilihan%22+OR+%22target+harga%22)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Rekomendasi Bloomberg Technoz", "https://news.google.com/rss/search?q=site:bloombergtechnoz.com+(%22rekomendasi+saham%22+OR+%22saham+pilihan%22+OR+%22target+harga%22)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Riset Stockbit Sekuritas", "https://news.google.com/rss/search?q=%22Stockbit+Sekuritas%22+OR+%22analis+Stockbit%22+saham+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Riset Ajaib Sekuritas", "https://news.google.com/rss/search?q=%22Ajaib+Sekuritas%22+OR+site:ajaib.co.id+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("CNBC My Money Ideas", "https://www.cnbcindonesia.com/mymoney/rss"),
    ],
    "Katalis Emiten, Borong Saham & Aksi Korporasi": [
        ("Sinyal Borong / Dividen / Akuisisi (EmitenNews)", "https://news.google.com/rss/search?q=site:emitennews.com+(borong+OR+akuisisi+OR+dividen+OR+%22rekomendasi+saham%22+OR+unsuspensi)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("EmitenNews Real-Time 24 Jam", "https://news.google.com/rss/search?q=site:emitennews.com+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("IDN Financials & Investor.id Korporasi", "https://news.google.com/rss/search?q=site:idnfinancials.com+OR+site:investor.id/market+OR+site:investor.id/corporate-action+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Kontan Investasi", "https://rss.kontan.co.id/news/investasi"),
        ("Bisnis.com Market Real-Time", "https://news.google.com/rss/search?q=site:market.bisnis.com+when:1d&hl=id&gl=ID&ceid=ID:id"),
    ],
    "Regulator BEI, IDX Channel & Detektor UMA/Suspensi": [
        ("Detektor UMA & Suspensi BEI", "https://news.google.com/rss/search?q=%22Unusual+Market+Activity%22+OR+%22Suspensi+Saham%22+BEI+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Situs Resmi BEI & IDX Channel", "https://news.google.com/rss/search?q=site:idxchannel.com+OR+site:idx.co.id+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("IDX Channel Direct RSS", "https://www.idxchannel.com/rss"),
    ],
    "Bandarmology, Foreign Flow & Komunitas Trader": [
        ("Bandarmology & Net Buy Asing", "https://news.google.com/rss/search?q=%22Bandarmology%22+OR+%22Creative+Trader%22+OR+%22akumulasi+asing%22+OR+%22net+buy+asing%22+saham+when:2d&hl=id&gl=ID&ceid=ID:id"),
        ("Stockbit Snips & Blog", "https://news.google.com/rss/search?q=site:snips.stockbit.com+OR+site:blog.stockbit.com+when:7d&hl=id&gl=ID&ceid=ID:id"),
        ("Big Alpha & Emtrade Insight", "https://news.google.com/rss/search?q=site:bigalpha.id+OR+site:emtrade.id+when:3d&hl=id&gl=ID&ceid=ID:id"),
        ("Stockwise, Dreamstock & Komunitas", "https://news.google.com/rss/search?q=site:stockwise.id+OR+site:dreamstock.id+OR+%22Creative+Trader%22+OR+%22Ruang+Saham%22+saham+when:7d&hl=id&gl=ID&ceid=ID:id"),
        ("SahamGO & PintarSaham", "https://news.google.com/rss/search?q=site:sahamgo.com+OR+site:pintarsaham.id+when:7d&hl=id&gl=ID&ceid=ID:id"),
    ],
    "Komoditas, Energi, Makro & Global": [
        ("Bloomberg Technoz Komoditas (Emas, Nikel, Batu Bara)", "https://news.google.com/rss/search?q=site:bloombergtechnoz.com+(emas+OR+nikel+OR+%22batu+bara%22+OR+minyak)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Bloomberg Technoz Market & Bisnis", "https://news.google.com/rss/search?q=site:bloombergtechnoz.com+(saham+OR+IHSG+OR+emiten+OR+market)+when:1d&hl=id&gl=ID&ceid=ID:id"),
        ("Kontan Industri (Tambang & Energi)", "https://rss.kontan.co.id/news/industri"),
        ("Kontan Keuangan (Perbankan)", "https://rss.kontan.co.id/news/keuangan"),
        ("CNBC Indonesia Market", "https://www.cnbcindonesia.com/market/rss"),
        ("CNBC Research", "https://www.cnbcindonesia.com/research/rss"),
        ("Investing.com Saham Indonesia", "https://id.investing.com/rss/news_25.rss"),
        ("Investing.com Komoditas", "https://id.investing.com/rss/news_11.rss"),
        ("Antara Ekonomi", "https://www.antaranews.com/rss/ekonomi.xml"),
        ("Detik Finance", "https://rss.detik.com/index.php/finance"),
        ("Sindonews Ekbis", "https://ekbis.sindonews.com/rss"),
    ]
}

# Direktori Tautan Langsung Portal Pasar Modal (Terstruktur per Kategori)
PORTAL_LINKS_DIRECTORY = {
    "1. Regulator Resmi (BEI, KSEI, OJK & e-IPO)": [
        ("Keterbukaan Informasi BEI (Real-Time PDF)", "https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/"),
        ("Pengumuman Bursa (Suspensi, Unsuspensi, Delisting)", "https://www.idx.co.id/id/berita/pengumuman/"),
        ("Radar Saham UMA (Unusual Market Activity)", "https://www.idx.co.id/id/berita/unusual-market-activity-uma/"),
        ("Daftar Efek Pemantauan Khusus (FCA)", "https://www.idx.co.id/id/data-pasar/data-saham/daftar-efek-pemantauan-khusus/"),
        ("Kalender Aksi Korporasi BEI (Dividen, RUPS, Right Issue)", "https://www.idx.co.id/id/perusahaan-tercatat/kalender-perusahaan-tercatat/"),
        ("Ringkasan Perdagangan Saham & Foreign Flow BEI", "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/"),
        ("Ringkasan Broker Harian BEI", "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"),
        ("Ringkasan Indeks Sektoral (IDX-IC)", "https://www.idx.co.id/id/data-pasar/data-indeks/ringkasan-indeks/"),
        ("Daftar Efek Marjin & Short Selling", "https://www.idx.co.id/id/data-pasar/data-saham/daftar-efek-marjin-dan-short-selling/"),
        ("Laporan Keuangan Tahunan & Kuartalan BEI", "https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/"),
        ("Data Kepemilikan Saham KSEI (>5%)", "https://www.ksei.co.id/publications/shareholder-information"),
        ("Jadwal Aksi Korporasi KSEI", "https://www.ksei.co.id/publications/corporate-action-schedules"),
        ("Statistik Bulanan KSEI", "https://www.ksei.co.id/publications/monthly-statistic"),
        ("e-IPO (Jadwal & Prospektus Saham IPO)", "https://e-ipo.co.id/id/ipo/index"),
        ("Pengumuman Pasar Modal OJK", "https://ojk.go.id/id/berita-dan-kegiatan/pengumuman/Default.aspx"),
    ],
    "2. Media Finansial Tier-1 (CNBC, Kontan, Bisnis, Bloomberg, EmitenNews)": [
        ("CNBC Indonesia Market", "https://www.cnbcindonesia.com/market"),
        ("CNBC My Money (Rekomendasi & Trading Ideas)", "https://www.cnbcindonesia.com/mymoney"),
        ("CNBC Indeks Berita Kronologis", "https://www.cnbcindonesia.com/market/indeks"),
        ("Kontan Investasi", "https://investasi.kontan.co.id/"),
        ("Kontan Industri (Tambang, Energi, Manufaktur)", "https://industri.kontan.co.id/"),
        ("Kontan Insight (Riset Eksklusif)", "https://insight.kontan.co.id/"),
        ("Bisnis.com Market & Bursa", "https://market.bisnis.com/bursa-dan-saham"),
        ("Bisnis.com Rekomendasi Saham", "https://market.bisnis.com/rekomendasi"),
        ("Bisnis.com Korporasi", "https://market.bisnis.com/korporasi"),
        ("Bloomberg Technoz Market", "https://www.bloombergtechnoz.com/kanal/market"),
        ("Bloomberg Technoz Energi & Komoditas", "https://www.bloombergtechnoz.com/kanal/energi"),
        ("EmitenNews Kanal Emiten & Aksi Korporasi", "https://emitennews.com/category/emiten"),
        ("EmitenNews Borong Saham", "https://emitennews.com/search?q=borong+saham"),
        ("IDX Channel Market News", "https://www.idxchannel.com/market-news"),
        ("Investor.id Corporate Action", "https://investor.id/corporate-action"),
        ("IDN Financials (Berita Emiten & Kepemilikan)", "https://www.idnfinancials.com/id/news"),
        ("IQPlus Berita Cepat Pasar Modal", "http://www.iqplus.info/"),
        ("Katadata Finansial Bursa", "https://katadata.co.id/finansial/bursa"),
        ("Pasardana News", "https://pasardana.id/news"),
    ],
    "3. Riset Sekuritas, Bandarmology & Screener Komunitas": [
        ("Stockbit Snips (Riset Harian & Bedah Emiten)", "https://snips.stockbit.com/"),
        ("Stockbit Stream (Trending & Rumor Real-Time)", "https://stockbit.com/stream"),
        ("Stockbit Screener (Volume Spike & Bandarmology)", "https://stockbit.com/screener"),
        ("Stockbit Ideas (Trading Plan Komunitas)", "https://stockbit.com/ideas"),
        ("Ajaib Berita Saham & Web Trading", "https://ajaib.co.id/belajar/berita-saham/"),
        ("IPOTNews (Indo Premier Sekuritas)", "https://www.ipotnews.com/"),
        ("Mirae Asset Sekuritas Research", "https://sekuritas.miraeasset.co.id/id/research"),
        ("Mandiri Sekuritas (MOST Daily Research)", "https://www.most.co.id/riset/harian"),
        ("BRI Danareksa Sekuritas Research", "https://brights.id/id/research"),
        ("Phillip Sekuritas (POEMS Research)", "https://www.poems.co.id/id/research/"),
        ("Creative Trader (Bandarmology & Foreign Flow)", "https://www.creativetrader.id/"),
        ("Bandarmology.com Official", "https://www.bandarmology.com/"),
        ("Invezgo (Broker Summary & Sankey Flow)", "https://app.invezgo.com/"),
        ("Sahamology (Teknikal & Bandarmology)", "https://sahamology.id/"),
        ("Stockwise.id", "https://www.stockwise.id/"),
        ("Emtrade.id Artikel & Sinyal", "https://emtrade.id/artikel"),
        ("Big Alpha News", "https://bigalpha.id/news"),
        ("Dreamstock.id", "https://dreamstock.id/"),
        ("PintarSaham.id", "https://pintarsaham.id/"),
        ("SahamGO", "https://sahamgo.com/"),
        ("Invesnesia", "https://www.invesnesia.com/"),
        ("Ruang Saham", "https://ruangsaham.com/"),
        ("Astronacci International", "https://astronacci.com/"),
    ],
    "4. Market Movers, Unusual Volume & Komoditas Global": [
        ("TradingView Unusual Volume / Volume Spike IDX", "https://id.tradingview.com/markets/stocks-indonesia/market-movers-unusual-volume/"),
        ("TradingView Top Gainers IDX", "https://id.tradingview.com/markets/stocks-indonesia/market-movers-gainers/"),
        ("TradingView Most Active IDX", "https://id.tradingview.com/markets/stocks-indonesia/market-movers-active/"),
        ("TradingView Most Volatile IDX", "https://id.tradingview.com/markets/stocks-indonesia/market-movers-most-volatile/"),
        ("TradingView News Flow Indonesia", "https://id.tradingview.com/markets/stocks-indonesia/news/"),
        ("Investing.com Harga Komoditas Real-Time", "https://id.investing.com/commodities/real-time-futures"),
        ("Investing.com Kalender Ekonomi Global & RI", "https://id.investing.com/economic-calendar/"),
        ("Investing.com Indeks Futures Dunia", "https://id.investing.com/indices/indices-futures"),
        ("TradingEconomics Commodities", "https://tradingeconomics.com/commodities"),
        ("Barchart Commodities Futures", "https://www.barchart.com/futures"),
        ("RTI Business Web", "https://www.rti.co.id/"),
    ]
}

# Kamus Kata Kunci NLP Sentimen & Katalis Pasar Modal Indonesia
BULLISH_KEYWORDS = {
    "borong": 3, "akumulasi": 3, "net buy": 3, "beli bersih": 3, "dividen": 2,
    "buyback": 3, "akuisisi": 2, "kontrak baru": 3, "laba melonjak": 3, "laba bersih naik": 3,
    "tumbuh": 2, "rekomendasi saham": 1, "saham pilihan": 1, "target harga": 2, "buy": 2,
    "menguat": 1, "breakout": 2, "unsuspensi": 3, "buka gembok": 3, "ekspansi": 2,
    "proyek": 1, "rekor": 2, "surplus": 2, "undervalued": 2, "msci": 2, "lq45": 1,
    "all time high": 2, "cuan": 1, "bullish": 2, "potensi naik": 2, "melambung": 2
}

BEARISH_OR_RISK_KEYWORDS = {
    "suspensi": -5, "disuspensi": -5, "gembok": -4, "unusual market activity": -4,
    "uma": -4, "pemantauan khusus": -4, "fca": -4, "delisting": -5, "pailit": -5,
    "pkpu": -5, "rugi": -3, "anjlok": -2, "net sell": -2, "jual bersih": -2,
    "koreksi": -1, "turun": -1, "denda": -3, "sanksi": -3, "gagal bayar": -5,
    "downgrade": -3, "bearish": -2, "longsor": -2, "tertekan": -1
}

# ==========================================
# 2. LOADER DATABASE 1.011 SAHAM BEI & DATA PASAR
# ==========================================
@st.cache_data(show_spinner=False)
def load_bei_catalog(csv_path: str) -> pd.DataFrame:
    """Memuat seluruh daftar 1.011 saham BEI dari file CSV lokal."""
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        df["Kode_Saham"] = df["Kode_Saham"].astype(str).str.strip().str.upper()
        return df
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_market_ohlcv(ticker_symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Mengambil data historis/intraday OHLCV dari Yahoo Finance."""
    try:
        asset = yf.Ticker(ticker_symbol)
        hist = asset.history(period=period, interval=interval, auto_adjust=False)
        if hist is None or hist.empty:
            return pd.DataFrame()
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        hist.index = pd.to_datetime(hist.index)
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
        return hist.dropna(subset=["Open", "High", "Low", "Close"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_fundamental_metrics(ticker_symbol: str) -> dict:
    """Mengambil rasio keuangan dan valuasi fundamental dari Yahoo Finance."""
    try:
        raw_info = yf.Ticker(ticker_symbol).info
        return {
            "name": raw_info.get("shortName", ticker_symbol),
            "sector": raw_info.get("sector", "N/A"),
            "industry": raw_info.get("industry", "N/A"),
            "mcap": raw_info.get("marketCap"),
            "pe": raw_info.get("trailingPE"),
            "pbv": raw_info.get("priceToBook"),
            "roe": raw_info.get("returnOnEquity"),
            "der": raw_info.get("debtToEquity"),
            "eps": raw_info.get("trailingEps"),
            "div_yield": raw_info.get("dividendYield"),
            "high_52w": raw_info.get("fiftyTwoWeekHigh"),
            "low_52w": raw_info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def load_batch_ohlcv(tickers: list, period: str = "6mo") -> dict:
    """Mengambil data OHLCV banyak saham sekaligus untuk Screener Awal Fase Bullish."""
    result = {}
    try:
        raw = yf.download(tickers, period=period, interval="1d", group_by="ticker", progress=False, threads=True)
        if raw is None or raw.empty:
            return result
        for t in tickers:
            try:
                sub = raw[t] if len(tickers) > 1 else raw
                sub = sub.dropna(subset=["Open", "High", "Low", "Close"])
                if not sub.empty and len(sub) >= 25:
                    result[t] = sub
            except Exception:
                continue
    except Exception:
        pass
    return result

# ==========================================
# 3. ENGINE REAL-TIME NEWS, RSS & NLP SENTIMENT
# ==========================================
def clean_html_text(raw_html: str) -> str:
    """Membersihkan tag HTML dan entitas dari teks RSS."""
    if not raw_html:
        return ""
    text = html.unescape(str(raw_html))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def score_headline_sentiment(title: str, summary: str = "") -> tuple:
    """Menghitung skor sentimen berita, mendeteksi peringatan UMA/Suspensi, dan label katalis."""
    combined = f"{title} {summary}".lower()
    score = 0
    matched_tags = []
    is_regulatory_warning = False

    for kw, weight in BULLISH_KEYWORDS.items():
        if kw in combined:
            score += weight
            matched_tags.append(f"+{kw.upper()}")

    for kw, weight in BEARISH_OR_RISK_KEYWORDS.items():
        if kw in combined:
            score += weight
            matched_tags.append(f"{kw.upper()}")
            if kw in ["suspensi", "disuspensi", "gembok", "unusual market activity", "uma", "pemantauan khusus", "fca", "delisting", "pkpu"]:
                is_regulatory_warning = True

    if is_regulatory_warning:
        sentiment_label = "⚠️ PERINGATAN UMA/SUSPENSI"
    elif score >= 2:
        sentiment_label = "🟢 Katalis Bullish"
    elif score <= -2:
        sentiment_label = "🔴 Sentimen Negatif"
    else:
        sentiment_label = "⚪ Netral / Info Pasar"

    return score, sentiment_label, is_regulatory_warning, matched_tags[:4]


def fetch_single_rss(source_name: str, url: str, max_items: int = 12) -> list:
    """Mengambil dan mem-parsing satu URL XML RSS/Atom menggunakan pustaka standar Python."""
    items = []
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*"
            }
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            xml_bytes = resp.read()

        root = ET.fromstring(xml_bytes)
        # Cek format RSS 2.0 (<item>) atau Atom (<entry>)
        nodes = root.findall(".//item")
        if not nodes:
            nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for node in nodes[:max_items]:
            title_el = node.find("title")
            if title_el is None:
                title_el = node.find("{http://www.w3.org/2005/Atom}title")
            link_el = node.find("link")
            if link_el is None:
                link_el = node.find("{http://www.w3.org/2005/Atom}link")
            pub_el = node.find("pubDate")
            if pub_el is None:
                pub_el = node.find("{http://www.w3.org/2005/Atom}updated")
            desc_el = node.find("description")

            title_txt = clean_html_text(title_el.text if title_el is not None else "")
            if not title_txt:
                continue

            link_txt = ""
            if link_el is not None:
                link_txt = link_el.text if link_el.text else link_el.attrib.get("href", "")
            pub_txt = clean_html_text(pub_el.text if pub_el is not None else "")
            desc_txt = clean_html_text(desc_el.text if desc_el is not None else "")

            s_score, s_label, is_warn, tags = score_headline_sentiment(title_txt, desc_txt)
            items.append({
                "Sumber": source_name,
                "Judul": title_txt,
                "Waktu": pub_txt[:25] if pub_txt else "Hari Ini",
                "Sentimen": s_label,
                "Skor_Sentimen": s_score,
                "Peringatan_Bursa": is_warn,
                "Kata_Kunci": ", ".join(tags) if tags else "-",
                "Link": link_txt.strip()
            })
    except Exception:
        pass
    return items


@st.cache_data(ttl=180, show_spinner=False)
def fetch_ticker_specific_news(stock_code: str, company_name: str = "") -> list:
    """Mengambil berita real-time spesifik untuk kode saham yang sedang dianalisis."""
    if not stock_code or stock_code.startswith("^"):
        return []
    clean_code = stock_code.replace(".JK", "").strip().upper()
    short_comp = " ".join(company_name.replace("Tbk.", "").replace("Tbk", "").split()[:2]).strip()
    q_comp = f'+OR+"{urllib.parse.quote(short_comp)}"' if len(short_comp) > 3 else ""

    specific_urls = [
        (f"Google News ({clean_code})", f"https://news.google.com/rss/search?q=saham+{clean_code}+OR+%22{clean_code}%22{q_comp}+when:7d&hl=id&gl=ID&ceid=ID:id"),
        (f"Media Tier-1 ({clean_code})", f"https://news.google.com/rss/search?q=(site:cnbcindonesia.com+OR+site:kontan.co.id+OR+site:market.bisnis.com+OR+site:emitennews.com+OR+site:bloombergtechnoz.com+OR+site:idxchannel.com)+{clean_code}+when:14d&hl=id&gl=ID&ceid=ID:id"),
        (f"Yahoo Finance ({clean_code}.JK)", f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean_code}.JK&region=US&lang=en-US"),
    ]

    aggregated = []
    seen_titles = set()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_single_rss, src, u, 10) for src, u in specific_urls]
        for fut in as_completed(futures):
            for item in fut.result():
                norm_t = item["Judul"].lower()[:60]
                if norm_t not in seen_titles:
                    seen_titles.add(norm_t)
                    aggregated.append(item)
    return aggregated


@st.cache_data(ttl=180, show_spinner=False)
def fetch_category_news_feeds(category_name: str, valid_codes_tuple: tuple) -> pd.DataFrame:
    """Mengambil seluruh berita dari kategori RSS secara paralel & mengekstrak kode saham BEI."""
    feed_list = REALTIME_RSS_FEEDS.get(category_name, [])
    all_rows = []
    seen = set()
    valid_set = set(valid_codes_tuple)
    # Abaikan kata umum bahasa Indonesia yang kebetulan sama dengan ticker 4 huruf
    common_words_blacklist = {
        "DARI", "PADA", "YANG", "AKAN", "BISA", "JUGA", "KINI", "SAAT", "BILA",
        "HARI", "ATAU", "PARA", "SATU", "TIGA", "LIMA", "UANG", "BANK", "EMAS",
        "BATU", "BARA", "DATA", "INFO", "BACA", "LAGI", "NAIK", "ASET", "RUGI",
        "LABA", "POIN", "FASE", "AWAL", "SORE", "PAGI", "DANA", "KOTA", "BUMI"
    }

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(fetch_single_rss, name, url, 10): name for name, url in feed_list}
        for fut in as_completed(future_map):
            for row in fut.result():
                key = row["Judul"].lower()[:65]
                if key not in seen:
                    seen.add(key)
                    # Ekstraksi kode saham 4 huruf kapital dari judul berita
                    tokens = re.findall(r"\b[A-Z]{4}\b", row["Judul"])
                    detected = []
                    for tok in tokens:
                        if tok in valid_set and (tok not in common_words_blacklist or f"({tok})" in row["Judul"]):
                            if tok not in detected:
                                detected.append(tok)
                    row["Emiten_Terkait"] = ", ".join(detected) if detected else "-"
                    all_rows.append(row)

    return pd.DataFrame(all_rows)

# ==========================================
# 4. ENGINE DETEKTOR "AWAL FASE BULLISH" & TRADING PLAN
# ==========================================
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung EMA 9, SMA 20/50/200, Bollinger Bands, RSI 14, MACD, ATR 14, OBV, dan CMF."""
    if df.empty:
        return df

    out = df.copy()
    out["EMA_9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["SMA_20"] = out["Close"].rolling(20, min_periods=1).mean()
    out["SMA_50"] = out["Close"].rolling(50, min_periods=1).mean()
    out["SMA_200"] = out["Close"].rolling(200, min_periods=20).mean()

    rolling_std = out["Close"].rolling(20, min_periods=2).std().fillna(0)
    out["BB_Upper"] = out["SMA_20"] + (2.0 * rolling_std)
    out["BB_Lower"] = out["SMA_20"] - (2.0 * rolling_std)
    out["BB_Width"] = ((out["BB_Upper"] - out["BB_Lower"]) / out["SMA_20"].replace(0, np.nan)) * 100

    diff = out["Close"].diff()
    up = diff.clip(lower=0)
    down = -1 * diff.clip(upper=0)
    ema_up = up.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
    ema_down = down.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
    rs_val = ema_up / ema_down.replace(0, np.nan)
    out["RSI_14"] = (100 - (100 / (1 + rs_val))).fillna(50)

    fast_ema = out["Close"].ewm(span=12, adjust=False).mean()
    slow_ema = out["Close"].ewm(span=26, adjust=False).mean()
    out["MACD"] = fast_ema - slow_ema
    out["MACD_Signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_Hist"] = out["MACD"] - out["MACD_Signal"]

    tr1 = out["High"] - out["Low"]
    tr2 = (out["High"] - out["Close"].shift()).abs()
    tr3 = (out["Low"] - out["Close"].shift()).abs()
    out["ATR_14"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14, min_periods=1).mean()
    out["Vol_MA20"] = out["Volume"].rolling(20, min_periods=1).mean()

    # Chaikin Money Flow (CMF 20) untuk deteksi Akumulasi Bandar / Smart Money
    hl_range = (out["High"] - out["Low"]).replace(0, np.nan)
    mf_multiplier = ((out["Close"] - out["Low"]) - (out["High"] - out["Close"])) / hl_range
    mf_volume = mf_multiplier.fillna(0) * out["Volume"]
    out["CMF_20"] = mf_volume.rolling(20, min_periods=1).sum() / out["Volume"].rolling(20, min_periods=1).sum().replace(0, np.nan)
    out["CMF_20"] = out["CMF_20"].fillna(0)

    return out


def analyze_early_bullish_and_plan(
    df: pd.DataFrame,
    fund: dict,
    news_items: list,
    capital_idr: float = 50_000_000,
    risk_per_trade_pct: float = 1.5,
    board_status: str = "Utama"
) -> dict:
    """
    Mendeteksi apakah saham berada di AWAL FASE BULLISH (Stage 2 Transition),
    menggabungkan sentimen berita real-time, dan menyusun Trading Plan presisi.
    """
    curr = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else curr
    prev5 = df.iloc[-5] if len(df) >= 5 else prev

    price = float(curr["Close"])
    open_px = float(curr["Open"])
    ema9 = float(curr["EMA_9"])
    sma20 = float(curr["SMA_20"])
    sma50 = float(curr["SMA_50"])
    rsi = float(curr["RSI_14"])
    macd = float(curr["MACD"])
    macd_sig = float(curr["MACD_Signal"])
    macd_hist = float(curr["MACD_Hist"])
    prev_hist = float(prev["MACD_Hist"])
    vol = float(curr["Volume"])
    vol_ma20 = float(curr["Vol_MA20"]) if curr["Vol_MA20"] > 0 else 1.0
    cmf = float(curr.get("CMF_20", 0.0))
    atr = float(curr.get("ATR_14", price * 0.02))
    if pd.isna(atr) or atr <= 0:
        atr = price * 0.02

    # 1. SKOR DETEKSI AWAL FASE BULLISH (0 - 60 Poin)
    early_bull_score = 0
    checklist = []

    dist_to_sma20_pct = ((price - sma20) / sma20) * 100 if sma20 > 0 else 0.0
    vol_ratio = vol / vol_ma20

    # Kriteria A: Posisi Harga terhadap EMA 9 & SMA 20 (Early Breakout / Dekat Base)
    if price >= ema9 >= sma20 and 0.0 <= dist_to_sma20_pct <= 6.5:
        early_bull_score += 18
        checklist.append(f"✅ **Early Stage 2 Inflection:** Harga (`Rp {price:,.0f}`) baru menembus di atas EMA 9 & SMA 20 (+{dist_to_sma20_pct:.1f}% dari SMA 20, belum *overextended*).")
    elif price > sma20 and dist_to_sma20_pct > 6.5:
        early_bull_score += 8
        checklist.append(f"ℹ️ **Fase Bullish Lanjutan:** Harga sudah +{dist_to_sma20_pct:.1f}% di atas SMA 20 (tunggu *pullback* sehat ke EMA 9).")
    elif price < sma20:
        early_bull_score -= 10
        checklist.append("❌ **Di Bawah SMA 20:** Struktur harga jangka pendek belum mengonfirmasi fase *markup*.")

    # Kriteria B: Kemiringan (Slope) SMA 20 & Struktur SMA 50
    sma20_rising = sma20 > float(prev5["SMA_20"])
    if sma20 >= sma50 and sma20_rising:
        early_bull_score += 12
        checklist.append("✅ **Alignment Tren Menengah:** SMA 20 menanjak dan berada di atas SMA 50.")
    elif sma20_rising and price > sma50:
        early_bull_score += 9
        checklist.append("✅ **Transisi Reversal Menengah:** Harga telah menembus SMA 50 dan SMA 20 mulai melengkung naik.")

    # Kriteria C: Infleksi Momentum MACD
    if macd > macd_sig and prev["MACD"] <= prev["MACD_Signal"]:
        early_bull_score += 14
        checklist.append("✅ **Fresh MACD Golden Cross:** Garis MACD baru saja memotong ke atas Signal Line hari ini.")
    elif macd > macd_sig and macd_hist > prev_hist:
        early_bull_score += 10
        checklist.append("✅ **Akselerasi Histogram MACD:** Momentum beli menguat secara bertahap.")
    else:
        early_bull_score -= 5

    # Kriteria D: RSI Sweet Spot (48 - 66)
    if 48 <= rsi <= 66 and rsi >= float(prev["RSI_14"]):
        early_bull_score += 10
        checklist.append(f"✅ **RSI Sweet Spot ({rsi:.1f}):** Momentum akumulasi kuat dan ruang kenaikan menuju zona *Overbought* (70) masih lebar.")
    elif 35 <= rsi < 48 and rsi > float(prev["RSI_14"]):
        early_bull_score += 5
        checklist.append(f"ℹ️ **RSI Early Rebound ({rsi:.1f}):** Mulai bangkit dari area bawah.")
    elif rsi > 72:
        early_bull_score -= 4
        checklist.append(f"⚠️ **RSI Overbought ({rsi:.1f}):** Rawan aksi *profit taking* jangka pendek.")

    # Kriteria E: Volume Spike & Akumulasi Smart Money (CMF)
    if vol_ratio >= 1.2 and price >= open_px:
        early_bull_score += 10
        checklist.append(f"✅ **Lonjakan Volume Akumulasi ({vol_ratio:.2f}x MA20):** Kenaikan harga didukung volume transaksi di atas rata-rata.")
    if cmf > 0.05:
        early_bull_score += 6
        checklist.append(f"✅ **Arus Uang Positif (CMF: +{cmf:.2f}):** Indikasi akumulasi *Smart Money / Bandar* dalam 20 hari terakhir.")

    # 2. SKOR SENTIMEN BERITA REAL-TIME & FILTER RISIKO BURSA (-40 s/d +25 Poin)
    news_score = 0
    has_uma_or_suspend = False
    bullish_headlines = []
    risk_headlines = []

    for item in news_items[:8]:
        s_val = item.get("Skor_Sentimen", 0)
        news_score += s_val
        if item.get("Peringatan_Bursa", False):
            has_uma_or_suspend = True
            risk_headlines.append(item["Judul"])
        elif s_val >= 2:
            bullish_headlines.append(item["Judul"])

    news_score = max(min(news_score, 25), -35)

    if board_status == "Pemantauan Khusus":
        has_uma_or_suspend = True
        news_score -= 15
        checklist.append("⚠️ **Peringatan Papan FCA:** Emiten tercatat di Papan Pemantauan Khusus (*Full Call Auction*).")

    if has_uma_or_suspend:
        checklist.append("🚨 **PERINGATAN BURSA (UMA/SUSPENSI/FCA):** Terdeteksi rilis berita terkait pengawasan bursa atau potensi suspensi.")
    elif bullish_headlines:
        checklist.append(f"📰 **Katalis Berita Positif Aktif:** Ditemukan {len(bullish_headlines)} berita katalis mendukung pergerakan emiten.")

    # 3. SKOR FUNDAMENTAL SINGKAT (0 - 15 Poin)
    fund_score = 0
    pe = fund.get("pe")
    roe = fund.get("roe")
    if pe is not None and 0 < pe < 18:
        fund_score += 7
    if roe is not None and roe > 0.12:
        fund_score += 8

    total_composite = early_bull_score + news_score + fund_score

    # Klasifikasi Fase Pasar & Rekomendasi Akhir
    is_early_bullish = (
        price >= ema9 and price >= sma20 and
        0.0 <= dist_to_sma20_pct <= 7.0 and
        macd >= macd_sig and
        46 <= rsi <= 67 and
        not has_uma_or_suspend
    )

    if has_uma_or_suspend and total_composite < 30:
        phase_status = "⚠️ HIGH RISK (UMA / FCA / SUSPENSI)"
        action = "AVOID / SELL"
        badge_color = "#dc2626"
    elif is_early_bullish and total_composite >= 35:
        phase_status = "🚀 AWAL FASE BULLISH (OPTIMAL ENTRY)"
        action = "STRONG BUY (EARLY PHASE)"
        badge_color = "#15803d"
    elif total_composite >= 28:
        phase_status = "📈 FASE BULLISH AKTIF (UPTREND)"
        action = "BUY ON PULLBACK"
        badge_color = "#16a34a"
    elif total_composite <= 0:
        phase_status = "📉 FASE BEARISH / DISTRIBUSI"
        action = "SELL / WAIT"
        badge_color = "#dc2626"
    else:
        phase_status = "⏸️ FASE KONSOLIDASI / SIDEWAYS"
        action = "HOLD / WATCHLIST"
        badge_color = "#d97706"

    # 4. KALKULASI TRADING PLAN PROFITABLE & POSITION SIZING
    recent_20 = df.tail(20)
    swing_low = float(recent_20["Low"].min())
    swing_high = float(recent_20["High"].max())

    # Area Beli Ideal (Pullback ke EMA9 - SMA20) & Breakout Trigger
    buy_zone_low = round(max(sma20, price - (0.8 * atr)), 0)
    buy_zone_high = round(price, 0)
    breakout_trigger = round(float(curr["High"]) * 1.005, 0)

    # Stop Loss Presisi (Di bawah SMA20 / Swing Low / 1.8x ATR)
    raw_sl = max(swing_low * 0.99, min(sma20 * 0.98, price - (1.8 * atr)))
    stop_loss = round(min(raw_sl, price * 0.96), 0)
    risk_per_share = max(price - stop_loss, price * 0.015)

    # Target Profit Bertahap (TP1 RRR 1:2, TP2 RRR 1:3.5)
    tp1 = round(price + (risk_per_share * 2.0), 0)
    tp2 = round(max(swing_high * 1.02, price + (risk_per_share * 3.5)), 0)
    rrr = (tp1 - price) / risk_per_share if risk_per_share > 0 else 0.0

    # Kalkulasi Lot Optimal Berdasarkan Risiko Modal
    max_loss_idr = capital_idr * (risk_per_trade_pct / 100.0)
    loss_per_lot = risk_per_share * 100.0
    recommended_lots = int(max_loss_idr // loss_per_lot) if loss_per_lot > 0 else 0
    max_affordable_lots = int(capital_idr // (price * 100.0)) if price > 0 else 0
    final_lots = max(min(recommended_lots, max_affordable_lots), 0)
    position_value_idr = final_lots * 100.0 * price

    return {
        "action": action,
        "phase": phase_status,
        "is_early_bullish": is_early_bullish,
        "composite_score": total_composite,
        "tech_score": early_bull_score,
        "news_score": news_score,
        "fund_score": fund_score,
        "color": badge_color,
        "checklist": checklist,
        "entry": round(price, 0),
        "buy_zone_low": buy_zone_low,
        "buy_zone_high": buy_zone_high,
        "breakout_trigger": breakout_trigger,
        "support": round(swing_low, 0),
        "resistance": round(swing_high, 0),
        "sl": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "risk_pct": (risk_per_share / price) * 100,
        "reward_tp1_pct": ((tp1 - price) / price) * 100,
        "reward_tp2_pct": ((tp2 - price) / price) * 100,
        "rrr": rrr,
        "vol_ratio": vol_ratio,
        "dist_sma20_pct": dist_to_sma20_pct,
        "cmf": cmf,
        "lots": final_lots,
        "pos_value": position_value_idr,
        "max_risk_idr": final_lots * loss_per_lot
    }

# ==========================================
# 5. VISUALISASI PLOTLY MULTI-PANEL
# ==========================================
def render_master_chart(df: pd.DataFrame, symbol: str, plan: dict) -> go.Figure:
    """Membuat grafik teknikal 4 panel lengkap dengan zona Entry, TP1, TP2, dan Stop Loss."""
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.52, 0.14, 0.17, 0.17],
        subplot_titles=(
            f"{symbol} - Early Bullish Detector (EMA 9, SMA 20/50/200 & Bollinger Bands)",
            "Volume Transaksi & MA20",
            "MACD (12, 26, 9) Inflection",
            "RSI (14) & Chaikin Money Flow"
        )
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="OHLC"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["EMA_9"], line=dict(color="#22c55e", width=1.3), name="EMA 9"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_20"], line=dict(color="#38bdf8", width=1.6), name="SMA 20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_50"], line=dict(color="#f59e0b", width=1.5), name="SMA 50"), row=1, col=1)
    if df["SMA_200"].notna().sum() > 0:
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA_200"], line=dict(color="#a855f7", width=1.8), name="SMA 200"), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Upper"], line=dict(color="rgba(148,163,184,0.35)", width=1, dash="dot"), name="BB Upper"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], line=dict(color="rgba(148,163,184,0.35)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(148,163,184,0.06)", name="BB Lower"
    ), row=1, col=1)

    fig.add_hline(y=plan["tp2"], line_dash="dot", line_color="#10b981", annotation_text=f"TP2: {plan['tp2']:,.0f}", row=1, col=1)
    fig.add_hline(y=plan["tp1"], line_dash="dash", line_color="#16a34a", annotation_text=f"TP1: {plan['tp1']:,.0f}", row=1, col=1)
    fig.add_hline(y=plan["sl"], line_dash="dash", line_color="#dc2626", annotation_text=f"SL: {plan['sl']:,.0f}", row=1, col=1)

    v_colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=v_colors, name="Volume"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Vol_MA20"], line=dict(color="#facc15", width=1.2), name="Vol MA20"), row=2, col=1)

    m_colors = ["#16a34a" if h >= 0 else "#dc2626" for h in df["MACD_Hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], marker_color=m_colors, name="MACD Hist"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], line=dict(color="#38bdf8", width=1.5), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], line=dict(color="#f97316", width=1.5), name="Signal"), row=3, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI_14"], line=dict(color="#c084fc", width=1.8), name="RSI 14"), row=4, col=1)
    fig.add_hline(y=65, line_dash="dot", line_color="#f59e0b", annotation_text="Batas Atas Early Bullish (65)", row=4, col=1)
    fig.add_hline(y=48, line_dash="dot", line_color="#22c55e", annotation_text="Batas Bawah Momentum (48)", row=4, col=1)

    fig.update_layout(
        height=880, template="plotly_dark", xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1)
    )
    return fig

# ==========================================
# 6. SIDEBAR FILTER, MODAL TRADING & PEMILIHAN EMITEN
# ==========================================
bei_df = load_bei_catalog(CSV_FILENAME)
all_valid_codes = tuple(bei_df["Kode_Saham"].dropna().unique().tolist()) if not bei_df.empty else tuple(MSCI_CONSTITUENTS)

with st.sidebar:
    st.title("🏛️ IDX & News Terminal")
    st.caption("1.011 Saham BEI • Real-Time RSS • Early Bullish Engine")

    if bei_df.empty:
        uploaded_csv = st.file_uploader("Unggah CSV 1.011 Saham BEI:", type=["csv"])
        if uploaded_csv is not None:
            bei_df = pd.read_csv(uploaded_csv)
            bei_df["Kode_Saham"] = bei_df["Kode_Saham"].astype(str).str.strip().str.upper()
            all_valid_codes = tuple(bei_df["Kode_Saham"].dropna().unique().tolist())

    if not bei_df.empty:
        universe_mode = st.selectbox(
            "Filter Kategori / Indeks:",
            [
                "Semua Emiten Aktif BEI",
                "Konstituen MSCI Indonesia",
                "Indeks LQ45",
                "Indeks KOMPAS100",
                "Indeks PEFINDO25",
                "Seluruh Database BEI (1.011 Saham)",
                "Indeks Acuan IHSG (^JKSE)"
            ]
        )

        filtered_df = bei_df.copy()
        if universe_mode == "Semua Emiten Aktif BEI":
            filtered_df = filtered_df[filtered_df["Status_Pencatatan"] != "Delisting"]
        elif universe_mode == "Konstituen MSCI Indonesia":
            filtered_df = filtered_df[filtered_df["Kode_Saham"].isin(MSCI_CONSTITUENTS)]
        elif universe_mode == "Indeks LQ45":
            filtered_df = filtered_df[filtered_df["Indeks_Utama"].str.contains("LQ45", na=False)]
        elif universe_mode == "Indeks KOMPAS100":
            filtered_df = filtered_df[filtered_df["Indeks_Utama"].str.contains("KOMPAS100", na=False)]
        elif universe_mode == "Indeks PEFINDO25":
            filtered_df = filtered_df[filtered_df["Indeks_Utama"].str.contains("PEFINDO25", na=False)]

        if universe_mode != "Indeks Acuan IHSG (^JKSE)":
            sector_list = ["Semua Sektor"] + sorted(filtered_df["Sektor_Indonesia"].dropna().unique().tolist())
            chosen_sector = st.selectbox("Filter Sektor BEI:", sector_list)
            if chosen_sector != "Semua Sektor":
                filtered_df = filtered_df[filtered_df["Sektor_Indonesia"] == chosen_sector]

            board_list = ["Semua Papan"] + sorted(filtered_df["Papan_Pencatatan"].dropna().unique().tolist())
            chosen_board = st.selectbox("Filter Papan Pencatatan:", board_list)
            if chosen_board != "Semua Papan":
                filtered_df = filtered_df[filtered_df["Papan_Pencatatan"] == chosen_board]

            if not filtered_df.empty:
                options_map = {
                    row["Ticker_Yahoo_Finance"]: f"{row['Kode_Saham']} - {row['Nama_Perusahaan']} ({row['Papan_Pencatatan']})"
                    for _, row in filtered_df.iterrows()
                }
                default_idx = list(options_map.keys()).index("BBCA.JK") if "BBCA.JK" in options_map else 0
                selected_symbol = st.selectbox(
                    f"Pilih Emiten ({len(filtered_df)} Saham):",
                    options=list(options_map.keys()),
                    index=default_idx,
                    format_func=lambda x: options_map.get(x, x)
                )
            else:
                st.warning("Tidak ada emiten yang cocok dengan kombinasi filter.")
                st.stop()
        else:
            selected_symbol = "^JKSE"
    else:
        fallback_code = st.text_input("Masukkan Kode Saham BEI:", value="BRMS").upper().strip()
        selected_symbol = fallback_code if fallback_code.endswith(".JK") or fallback_code.startswith("^") else f"{fallback_code}.JK"

    st.divider()
    st.subheader("💰 Parameter Modal & Risiko")
    capital_input = st.number_input("Total Modal Trading (Rp):", min_value=1_000_000, value=50_000_000, step=5_000_000)
    risk_pct_input = st.slider("Batas Risiko per Transaksi (% Modal):", min_value=0.5, max_value=5.0, value=1.5, step=0.25)

    period_choice = st.selectbox("Rentang Historis Chart:", ["6mo", "1y", "2y", "5y"], index=1)
    interval_choice = st.selectbox("Interval Candle:", ["1d", "1wk", "1h"], index=0)

    if st.button("🔄 Refresh Harga & Berita Real-Time", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 7. EKSEKUSI DATA UTAMA & SENTIMEN EMITEN
# ==========================================
ihsg_data = load_market_ohlcv("^JKSE", period="5d", interval="1d")
price_df = load_market_ohlcv(selected_symbol, period=period_choice, interval=interval_choice)

if price_df.empty:
    st.error(f"Data pasar Yahoo Finance untuk **{selected_symbol}** tidak tersedia atau saham sedang disuspensi/delisting.")
    st.stop()

csv_profile = {}
if not bei_df.empty and selected_symbol != "^JKSE":
    match_row = bei_df[bei_df["Ticker_Yahoo_Finance"] == selected_symbol]
    if not match_row.empty:
        csv_profile = match_row.iloc[0].to_dict()

clean_code = selected_symbol.replace(".JK", "")
comp_name = csv_profile.get("Nama_Perusahaan", clean_code)
board_name = csv_profile.get("Papan_Pencatatan", "Utama")

tech_df = compute_indicators(price_df)
fund_info = load_fundamental_metrics(selected_symbol) if selected_symbol != "^JKSE" else {}
ticker_news = fetch_ticker_specific_news(selected_symbol, comp_name) if selected_symbol != "^JKSE" else []

plan = analyze_early_bullish_and_plan(
    tech_df, fund_info, ticker_news,
    capital_idr=float(capital_input),
    risk_per_trade_pct=float(risk_pct_input),
    board_status=board_name
)

# Baris Metrik Utama
last_px = float(tech_df["Close"].iloc[-1])
prev_px = float(tech_df["Close"].iloc[-2]) if len(tech_df) > 1 else last_px
chg_pct = ((last_px - prev_px) / prev_px) * 100 if prev_px != 0 else 0.0

m1, m2, m3, m4, m5 = st.columns(5)
if not ihsg_data.empty and len(ihsg_data) >= 2:
    jkse_now = float(ihsg_data["Close"].iloc[-1])
    jkse_prev = float(ihsg_data["Close"].iloc[-2])
    jkse_pct = ((jkse_now - jkse_prev) / jkse_prev) * 100
    m1.metric("IHSG (^JKSE)", f"{jkse_now:,.2f}", f"{jkse_pct:+.2f}%")
else:
    m1.metric("IHSG (^JKSE)", "N/A", "0.00%")

m2.metric(f"Harga {clean_code}", f"Rp {last_px:,.0f}", f"{chg_pct:+.2f}% | Vol {plan['vol_ratio']:.1f}x")
m3.metric("Status Fase Pasar", plan["action"], plan["phase"][:28])
m4.metric("Skor Profit Gabungan", f"{plan['composite_score']} Poin", f"Tek: {plan['tech_score']} | News: {plan['news_score']:+d}")
m5.metric("Risk / Reward Ratio", f"1 : {plan['rrr']:.2f}", f"SL -{plan['risk_pct']:.1f}% | TP1 +{plan['reward_tp1_pct']:.1f}%")

st.divider()

# ==========================================
# 8. LIMA TAB UTAMA TERMINAL
# ==========================================
tab_plan, tab_screener, tab_news, tab_fund, tab_portals = st.tabs([
    "📊 Trading Plan & Detektor Awal Bullish",
    "🚀 Screener Awal Fase Bullish (Multi-Saham)",
    "📰 Radar Berita & Sentimen Real-Time (RSS)",
    "📑 Fundamental & Direktori 1.011 Saham",
    "🌐 Hub Portal Bursa, Bandarmology & Komunitas"
])

# ------------------------------------------
# TAB 1: TRADING PLAN & CHARTING
# ------------------------------------------
with tab_plan:
    c_chart, c_plan = st.columns([2.45, 1.05])
    with c_chart:
        st.plotly_chart(render_master_chart(tech_df, selected_symbol, plan), use_container_width=True)

        # Berita Spesifik Emiten di Bawah Grafik
        st.subheader(f"📰 Berita & Katalis Real-Time Emiten: {clean_code} ({comp_name})")
        if ticker_news:
            st.dataframe(
                pd.DataFrame(ticker_news)[["Waktu", "Sumber", "Sentimen", "Judul", "Kata_Kunci", "Link"]],
                column_config={"Link": st.column_config.LinkColumn("Buka Berita")},
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"Belum ditemukan rilis berita spesifik untuk {clean_code} dalam beberapa hari terakhir.")

    with c_plan:
        st.markdown(
            f"<div style='background-color:{plan['color']};padding:12px;border-radius:8px;text-align:center;color:white;font-weight:bold;font-size:18px;'>"
            f"{plan['action']}<br><span style='font-size:13px;font-weight:normal;'>{plan['phase']}</span></div>",
            unsafe_allow_html=True
        )
        st.write("")
        st.subheader("🎯 Trading Plan Profitable")
        st.markdown(f"""
        * **Harga Terakhir:** `Rp {plan['entry']:,.0f}`
        * **Zona Beli Ideal (Pullback EMA9–SMA20):** `Rp {plan['buy_zone_low']:,.0f} – Rp {plan['buy_zone_high']:,.0f}`
        * **Trigger Breakout Entry:** `> Rp {plan['breakout_trigger']:,.0f}`
        * **Stop Loss Ketat (Batas Risiko):** `Rp {plan['sl']:,.0f}` (**-{plan['risk_pct']:.2f}%**)
        * **Target Profit 1 (TP1 - Jual 50%):** `Rp {plan['tp1']:,.0f}` (**+{plan['reward_tp1_pct']:.2f}%**)
        * **Target Profit 2 (TP2 - Swing/Trailing):** `Rp {plan['tp2']:,.0f}` (**+{plan['reward_tp2_pct']:.2f}%**)
        * **Support / Resistance (20D):** `Rp {plan['support']:,.0f}` / `Rp {plan['resistance']:,.0f}`
        """)

        st.divider()
        st.subheader("🧮 Position Sizing (Manajemen Modal)")
        st.markdown(f"""
        * **Rekomendasi Ukuran Posisi:** **`{plan['lots']:,} Lot`** ({plan['lots']*100:,} lembar)
        * **Nilai Alokasi Pembelian:** `Rp {plan['pos_value']:,.0f}`
        * **Risiko Maksimal Jika Kena SL:** `Rp {plan['max_risk_idr']:,.0f}` ({risk_pct_input}% dari modal)
        """)

        st.divider()
        st.subheader("🔍 Checklist Kuantitatif & Berita")
        for chk in plan["checklist"]:
            st.markdown(f"- {chk}")

        if selected_symbol != "^JKSE":
            st.divider()
            st.subheader(f"⚡ Pintasan Analisis {clean_code}")
            q_col1, q_col2 = st.columns(2)
            q_col1.link_button(f"Stockbit {clean_code}", f"https://stockbit.com/symbol/{clean_code}", use_container_width=True)
            q_col2.link_button(f"Insider {clean_code}", f"https://stockbit.com/symbol/{clean_code}/insider", use_container_width=True)
            q_col3, q_col4 = st.columns(2)
            q_col3.link_button(f"Yahoo {clean_code}", f"https://finance.yahoo.com/quote/{clean_code}.JK/news/", use_container_width=True)
            q_col4.link_button(f"Google News {clean_code}", f"https://news.google.com/search?q=saham+{clean_code}+when:7d&hl=id&gl=ID&ceid=ID:id", use_container_width=True)

# ------------------------------------------
# TAB 2: SCREENER AWAL FASE BULLISH
# ------------------------------------------
with tab_screener:
    st.subheader("🚀 Screener Otomatis: Mencari Saham di Awal Fase Bullish (Stage 2 Inflection)")
    st.caption(
        "Menyaring saham yang baru menembus ke atas EMA 9 & SMA 20 (jarak 0% s/d +7%), "
        "MACD positif/Golden Cross, RSI di zona 48–66, dan didukung aliran volume/uang masuk."
    )

    sc_col1, sc_col2 = st.columns([2, 1])
    with sc_col1:
        basket_choice = st.selectbox(
            "Pilih Kelompok Saham untuk Di-Scan:",
            [
                "Indeks LQ45 (45 Saham Likuid Utama)",
                "Konstituen MSCI Indonesia",
                "Sektor Energi & Pertambangan (Batu Bara, Migas, Mineral)",
                "Sektor Barang Baku (Emas, Nikel, Logam, Kimia)",
                "Sektor Keuangan & Perbankan",
                "Indeks PEFINDO25 (Growth & Mid-Cap)"
            ]
        )
    with sc_col2:
        run_scan = st.button("🔍 Jalankan Pemindaian Awal Bullish", type="primary", use_container_width=True)

    if run_scan:
        if not bei_df.empty:
            active_only = bei_df[bei_df["Status_Pencatatan"] != "Delisting"]
            if basket_choice.startswith("Indeks LQ45"):
                scan_df = active_only[active_only["Indeks_Utama"].str.contains("LQ45", na=False)]
            elif basket_choice.startswith("Konstituen MSCI"):
                scan_df = active_only[active_only["Kode_Saham"].isin(MSCI_CONSTITUENTS)]
            elif basket_choice.startswith("Sektor Energi"):
                scan_df = active_only[active_only["Sektor_Indonesia"] == "Energi"].head(45)
            elif basket_choice.startswith("Sektor Barang Baku"):
                scan_df = active_only[active_only["Sektor_Indonesia"] == "Barang Baku"].head(45)
            elif basket_choice.startswith("Sektor Keuangan"):
                scan_df = active_only[active_only["Sektor_Indonesia"] == "Keuangan"].head(45)
            else:
                scan_df = active_only[active_only["Indeks_Utama"].str.contains("PEFINDO25", na=False)]
            tickers_to_scan = scan_df["Ticker_Yahoo_Finance"].tolist()
            name_lookup = dict(zip(scan_df["Ticker_Yahoo_Finance"], scan_df["Nama_Perusahaan"]))
        else:
            tickers_to_scan = [f"{c}.JK" for c in MSCI_CONSTITUENTS]
            name_lookup = {f"{c}.JK": c for c in MSCI_CONSTITUENTS}

        with st.spinner(f"Memindai struktur teknikal & volume pada {len(tickers_to_scan)} saham..."):
            batch_data = load_batch_ohlcv(tickers_to_scan, period="6mo")
            screener_rows = []
            for sym, ohlc in batch_data.items():
                ind = compute_indicators(ohlc)
                res = analyze_early_bullish_and_plan(ind, {}, [], capital_idr=float(capital_input), risk_per_trade_pct=float(risk_pct_input))
                screener_rows.append({
                    "Kode": sym.replace(".JK", ""),
                    "Nama Perusahaan": name_lookup.get(sym, sym),
                    "Harga": res["entry"],
                    "Status Fase": res["phase"],
                    "Skor Teknikal": res["tech_score"],
                    "Jarak ke SMA20 (%)": round(res["dist_sma20_pct"], 2),
                    "RSI (14)": round(float(ind["RSI_14"].iloc[-1]), 1),
                    "Rasio Volume (xMA20)": round(res["vol_ratio"], 2),
                    "CMF (20)": round(res["cmf"], 2),
                    "Zona Beli": f"{res['buy_zone_low']:,.0f} - {res['buy_zone_high']:,.0f}",
                    "Stop Loss": res["sl"],
                    "TP 1": res["tp1"],
                    "TP 2": res["tp2"],
                    "R/R Ratio": f"1 : {res['rrr']:.1f}"
                })

            if screener_rows:
                res_df = pd.DataFrame(screener_rows).sort_values(by="Skor Teknikal", ascending=False)
                st.dataframe(res_df, use_container_width=True, hide_index=True, height=500)
            else:
                st.warning("Tidak ada data yang berhasil dipindai saat ini.")

# ------------------------------------------
# TAB 3: RADAR BERITA & SENTIMEN REAL-TIME
# ------------------------------------------
with tab_news:
    st.subheader("📡 Agregasi Berita Pasar Modal, Riset Sekuritas & Detektor UMA Real-Time")
    cat_selected = st.selectbox("Pilih Kanal Berita Real-Time:", list(REALTIME_RSS_FEEDS.keys()))

    with st.spinner(f"Mengambil berita real-time dari kanal {cat_selected}..."):
        news_df = fetch_category_news_feeds(cat_selected, all_valid_codes)

    if not news_df.empty:
        # Ringkasan Saham yang Paling Banyak Disebut di Berita
        mentioned_series = news_df[news_df["Emiten_Terkait"] != "-"]["Emiten_Terkait"].str.split(", ").explode()
        if not mentioned_series.empty:
            top_mentioned = mentioned_series.value_counts().head(10)
            st.markdown(
                "**🔥 Saham Paling Banyak Disebut pada Kanal Ini:** " +
                " • ".join([f"`{k}` ({v} berita)" for k, v in top_mentioned.items()])
            )

        filter_kw = st.text_input("🔍 Cari Kata Kunci / Kode Emiten di Berita (contoh: dividen, BRMS, borong, UMA):", "")
        disp_news = news_df.copy()
        if filter_kw:
            mask_n = (
                disp_news["Judul"].str.contains(filter_kw, case=False, na=False) |
                disp_news["Emiten_Terkait"].str.contains(filter_kw, case=False, na=False) |
                disp_news["Sentimen"].str.contains(filter_kw, case=False, na=False)
            )
            disp_news = disp_news[mask_n]

        st.dataframe(
            disp_news[["Waktu", "Sumber", "Emiten_Terkait", "Sentimen", "Judul", "Kata_Kunci", "Link"]],
            column_config={"Link": st.column_config.LinkColumn("Buka Artikel")},
            use_container_width=True,
            hide_index=True,
            height=520
        )
    else:
        st.warning("Tidak dapat memuat feed berita saat ini. Klik tombol Refresh untuk mencoba kembali.")

# ------------------------------------------
# TAB 4: FUNDAMENTAL & DIREKTORI 1.011 SAHAM
# ------------------------------------------
with tab_fund:
    if selected_symbol != "^JKSE":
        st.subheader(f"🏛️ Profil Pencatatan BEI & Valuasi Fundamental: {clean_code}")
        if csv_profile:
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Sektor BEI (IDX-IC)", csv_profile.get("Sektor_Indonesia", "-"))
            p2.metric("Papan Pencatatan", csv_profile.get("Papan_Pencatatan", "-"))
            p3.metric("Tanggal IPO", csv_profile.get("Tanggal_IPO_Teks", "-"))
            p4.metric("Jumlah Saham Tercatat", f"{int(csv_profile.get('Jumlah_Saham_Tercatat', 0)):,}")

        k1, k2, k3, k4 = st.columns(4)
        mcap = fund_info.get("mcap")
        pe = fund_info.get("pe")
        pbv = fund_info.get("pbv")
        roe = fund_info.get("roe")
        der = fund_info.get("der")
        eps = fund_info.get("eps")
        div_y = fund_info.get("div_yield")
        h52 = fund_info.get("high_52w")

        k1.metric("Market Cap", f"Rp {mcap/1e12:,.2f} T" if mcap else "N/A")
        k2.metric("PER (Trailing)", f"{pe:.2f}x" if pe else "N/A")
        k3.metric("PBV (Price to Book)", f"{pbv:.2f}x" if pbv else "N/A")
        k4.metric("ROE (Return on Equity)", f"{roe*100:.2f}%" if roe else "N/A")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("EPS (Trailing)", f"Rp {eps:,.0f}" if eps else "N/A")
        k6.metric("Debt to Equity (DER)", f"{der:.2f}%" if der else "N/A")
        k7.metric("Dividend Yield", f"{div_y*100:.2f}%" if div_y else "N/A")
        k8.metric("52-Week High", f"Rp {h52:,.0f}" if h52 else "N/A")
        st.divider()

    st.subheader("🗂️ Direktori Lengkap 1.011 Saham Bursa Efek Indonesia")
    if not bei_df.empty:
        q_dir = st.text_input("🔍 Cari Kode Saham / Nama Perusahaan / Sektor:", "")
        dir_view = bei_df.copy()
        if q_dir:
            m_dir = (
                dir_view["Kode_Saham"].str.contains(q_dir, case=False, na=False) |
                dir_view["Nama_Perusahaan"].str.contains(q_dir, case=False, na=False) |
                dir_view["Sektor_Indonesia"].str.contains(q_dir, case=False, na=False)
            )
            dir_view = dir_view[m_dir]
        st.dataframe(dir_view, use_container_width=True, height=450)

# ------------------------------------------
# TAB 5: HUB PORTAL BURSA, BANDARMOLOGY & KOMUNITAS
# ------------------------------------------
with tab_portals:
    st.subheader("🌐 Pusat Intelijen Pasar Modal: Tautan Resmi BEI, KSEI, Media, Sekuritas & Bandarmology")
    for group_title, links in PORTAL_LINKS_DIRECTORY.items():
        with st.expander(group_title, expanded=True):
            cols = st.columns(3)
            for idx, (label, url) in enumerate(links):
                cols[idx % 3].markdown(f"- [{label}]({url})")
