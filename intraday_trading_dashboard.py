import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# ==========================================
# 1. KONFIGURASI HALAMAN & KONSTANTA PASAR
# ==========================================
st.set_page_config(
    page_title="IDX & MSCI Financial Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Daftar Konstituen Utama MSCI Indonesia & Saham Likuid IDX
MSCI_INDONESIA_TICKERS = {
    "BBCA.JK": "Bank Central Asia Tbk",
    "BBRI.JK": "Bank Rakyat Indonesia Tbk",
    "BMRI.JK": "Bank Mandiri Tbk",
    "TLKM.JK": "Telkom Indonesia Tbk",
    "ASII.JK": "Astra International Tbk",
    "BBNI.JK": "Bank Negara Indonesia Tbk",
    "AMMN.JK": "Amman Mineral Internasional Tbk",
    "GOTO.JK": "GoTo Gojek Tokopedia Tbk",
    "ADRO.JK": "Alamtri Resources Indonesia Tbk",
    "ICBP.JK": "Indofood CBP Sukses Makmur Tbk",
    "UNTR.JK": "United Tractors Tbk",
    "KLBF.JK": "Kalbe Farma Tbk",
    "INDF.JK": "Indofood Sukses Makmur Tbk",
    "CPIN.JK": "Charoen Pokphand Indonesia Tbk"
}

# ==========================================
# 2. DATA ENGINE & CACHING LAYER
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlcv_data(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Mengambil data historis/intraday OHLCV dengan penanganan error dan normalisasi kolom."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        
        # Normalisasi jika terdapat MultiIndex pada kolom
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
            
        return df.dropna(subset=["Open", "High", "Low", "Close"])
    except Exception as e:
        st.error(f"Gagal memuat data pasar untuk {ticker}: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamental_data(ticker: str) -> dict:
    """Mengambil metrik fundamental utama emiten dari Yahoo Finance API."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "shortName": info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "marketCap": info.get("marketCap", None),
            "trailingPE": info.get("trailingPE", None),
            "forwardPE": info.get("forwardPE", None),
            "priceToBook": info.get("priceToBook", None),
            "returnOnEquity": info.get("returnOnEquity", None),
            "debtToEquity": info.get("debtToEquity", None),
            "trailingEps": info.get("trailingEps", None),
            "dividendYield": info.get("dividendYield", None),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh", None),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow", None),
        }
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_multi_tickers_close(tickers: list, period: str = "6mo") -> pd.DataFrame:
    """Mengambil harga penutupan sejumlah ticker sekaligus untuk komparasi performa relatif."""
    try:
        data = yf.download(tickers, period=period, interval="1d", progress=False)["Close"]
        if isinstance(data, pd.Series):
            data = data.to_frame()
        return data.dropna(how="all")
    except Exception:
        return pd.DataFrame()

# ==========================================
# 3. QUANTITATIVE TECHNICAL & SIGNAL ENGINE
# ==========================================
def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung indikator teknikal lengkap: MA, Bollinger Bands, RSI, MACD, ATR, Support/Resistance."""
    if df.empty or len(df) < 30:
        return df
    
    data = df.copy()
    
    # Moving Averages
    data["SMA_20"] = data["Close"].rolling(window=20).mean()
    data["SMA_50"] = data["Close"].rolling(window=50).mean()
    data["SMA_200"] = data["Close"].rolling(window=200).mean()
    data["EMA_20"] = data["Close"].ewm(span=20, adjust=False).mean()
    
    # Bollinger Bands (20, 2)
    std_20 = data["Close"].rolling(window=20).std()
    data["BB_Upper"] = data["SMA_20"] + (std_20 * 2)
    data["BB_Lower"] = data["SMA_20"] - (std_20 * 2)
    
    # RSI (14) - Wilder's Smoothing
    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["RSI_14"] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    ema_12 = data["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = data["Close"].ewm(span=26, adjust=False).mean()
    data["MACD"] = ema_12 - ema_26
    data["MACD_Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
    data["MACD_Hist"] = data["MACD"] - data["MACD_Signal"]
    
    # Average True Range (ATR 14) untuk Volatilitas & Stop Loss Dinamis
    high_low = data["High"] - data["Low"]
    high_close = (data["High"] - data["Close"].shift()).abs()
    low_close = (data["Low"] - data["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    data["ATR_14"] = true_range.rolling(window=14).mean()
    
    # Volume Moving Average (20)
    data["Vol_SMA_20"] = data["Volume"].rolling(window=20).mean()
    
    return data


def generate_trading_decision(df: pd.DataFrame, fund: dict) -> dict:
    """Menghasilkan skoring objektif, rekomendasi (BUY/HOLD/SELL), dan rasio Risk/Reward."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    close = latest["Close"]
    atr = latest.get("ATR_14", close * 0.02)
    if pd.isna(atr) or atr == 0:
        atr = close * 0.02

    score = 0
    reasons = []

    # 1. Evaluasi Tren (Moving Averages)
    if pd.notna(latest["SMA_20"]) and pd.notna(latest["SMA_50"]):
        if close > latest["SMA_20"] > latest["SMA_50"]:
            score += 2
            reasons.append("Tren Bullish: Harga berada di atas SMA 20 dan SMA 50.")
        elif close < latest["SMA_20"] < latest["SMA_50"]:
            score -= 2
            reasons.append("Tren Bearish: Harga tertekan di bawah SMA 20 dan SMA 50.")

    if pd.notna(latest["SMA_200"]):
        if close > latest["SMA_200"]:
            score += 1
            reasons.append("Tren Jangka Panjang Positif (Harga di atas SMA 200).")
        else:
            score -= 1
            reasons.append("Harga berada di bawah rata-rata jangka panjang (SMA 200).")

    # 2. Evaluasi Momentum (RSI & MACD)
    rsi = latest.get("RSI_14", 50)
    if pd.notna(rsi):
        if 30 <= rsi <= 45:
            score += 1
            reasons.append(f"RSI ({rsi:.1f}) mendekati area jenuh jual (potensial rebound).")
        elif 50 < rsi < 68:
            score += 1
            reasons.append(f"RSI ({rsi:.1f}) menunjukkan momentum akumulasi yang sehat.")
        elif rsi >= 72:
            score -= 1
            reasons.append(f"RSI ({rsi:.1f}) berada di zona Overbought (rawan profit taking).")
        elif rsi < 30:
            score += 1
            reasons.append(f"RSI ({rsi:.1f}) berada di zona Oversold ekstrem.")

    if pd.notna(latest["MACD"]) and pd.notna(latest["MACD_Signal"]):
        if latest["MACD"] > latest["MACD_Signal"] and prev["MACD"] <= prev["MACD_Signal"]:
            score += 2
            reasons.append("Sinyal Golden Cross baru terbentuk pada indikator MACD.")
        elif latest["MACD"] > latest["MACD_Signal"]:
            score += 1
            reasons.append("Histogram MACD positif (momentum beli mendominasi).")
        else:
            score -= 1
            reasons.append("MACD berada di bawah garis sinyal (tekanan jual aktif).")

    # 3. Evaluasi Fundamental Singkat
    pe = fund.get("trailingPE")
    roe = fund.get("returnOnEquity")
    if pe is not None and 0 < pe < 15:
        score += 1
        reasons.append(f"Valuasi PER menarik ({pe:.2f}x).")
    if roe is not None and roe > 0.15:
        score += 1
        reasons.append(f"Profitabilitas ROE solid ({roe*100:.1f}%).")

    # Penentuan Rekomendasi
    if score >= 3:
        action = "BUY"
        badge_color = "#16a34a"
    elif score <= -2:
        action = "SELL"
        badge_color = "#dc2626"
    else:
        action = "HOLD"
        badge_color = "#d97706"

    # Level Support & Resistance (20-Day Swing + ATR Buffer)
    recent_20 = df.tail(20)
    support_level = min(recent_20["Low"].min(), close - (1.8 * atr))
    resistance_level = max(recent_20["High"].max(), close + (3.6 * atr))

    # Perhitungan Stop Loss & Take Profit Presisi
    stop_loss = round(max(support_level * 0.99, close - (2.0 * atr)), 0)
    risk = max(close - stop_loss, close * 0.01)
    take_profit_1 = round(close + (risk * 2.0), 0)
    take_profit_2 = round(max(resistance_level, close + (risk * 3.0)), 0)
    rr_ratio = (take_profit_1 - close) / risk if risk > 0 else 0

    return {
        "action": action,
        "score": score,
        "color": badge_color,
        "reasons": reasons,
        "entry": round(close, 0),
        "support": round(support_level, 0),
        "resistance": round(resistance_level, 0),
        "stop_loss": stop_loss,
        "tp1": take_profit_1,
        "tp2": take_profit_2,
        "risk_pct": (risk / close) * 100,
        "reward_pct": ((take_profit_1 - close) / close) * 100,
        "rr_ratio": rr_ratio
    }

# ==========================================
# 4. VISUALISASI PLOTLY INTERAKTIF
# ==========================================
def build_master_chart(df: pd.DataFrame, ticker: str, setup: dict) -> go.Figure:
    """Membuat grafik interaktif 3 panel: Candlestick + BB + MA, Volume, dan RSI/MACD."""
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.52, 0.14, 0.17, 0.17],
        subplot_titles=(
            f"{ticker} - Price Action, Moving Averages & Bollinger Bands",
            "Volume Transaksi & Rata-rata 20 Hari",
            "MACD (12, 26, 9)",
            "Relative Strength Index (RSI 14)"
        )
    )

    # Panel 1: Candlestick + Bollinger Bands + MA
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="OHLC"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Upper"], line=dict(color="rgba(148, 163, 184, 0.4)", width=1, dash="dot"),
        name="BB Upper"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], line=dict(color="rgba(148, 163, 184, 0.4)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(148, 163, 184, 0.07)", name="BB Lower"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA_20"], line=dict(color="#38bdf8", width=1.5), name="SMA 20"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA_50"], line=dict(color="#f59e0b", width=1.5), name="SMA 50"
    ), row=1, col=1)

    if df["SMA_200"].notna().sum() > 0:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["SMA_200"], line=dict(color="#a855f7", width=1.8), name="SMA 200"
        ), row=1, col=1)

    # Garis Horizontal Target Profit & Stop Loss
    fig.add_hline(y=setup["tp1"], line_dash="dash", line_color="#16a34a",
                  annotation_text=f"TP1: {setup['tp1']:,.0f}", row=1, col=1)
    fig.add_hline(y=setup["stop_loss"], line_dash="dash", line_color="#dc2626",
                  annotation_text=f"SL: {setup['stop_loss']:,.0f}", row=1, col=1)

    # Panel 2: Volume
    vol_colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"], marker_color=vol_colors, name="Volume"
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Vol_SMA_20"], line=dict(color="#facc15", width=1.2), name="Vol MA20"
    ), row=2, col=1)

    # Panel 3: MACD
    hist_colors = ["#16a34a" if v >= 0 else "#dc2626" for v in df["MACD_Hist"]]
    fig.add_trace(go.Bar(
        x=df.index, y=df["MACD_Hist"], marker_color=hist_colors, name="MACD Hist"
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD"], line=dict(color="#38bdf8", width=1.5), name="MACD"
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD_Signal"], line=dict(color="#f97316", width=1.5), name="Signal"
    ), row=3, col=1)

    # Panel 4: RSI
    fig.add_trace(go.Scatter(
        x=df.index, y=df["RSI_14"], line=dict(color="#c084fc", width=1.8), name="RSI (14)"
    ), row=4, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=4, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=4, col=1)

    fig.update_layout(
        height=880,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1)
    )
    return fig

# ==========================================
# 5. LAYOUT UTAMA & SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.title("🏛️ IDX & MSCI Terminal")
    st.caption("Real-Time Fundamental, Technical & Risk Engine")
    st.divider()

    category = st.radio(
        "Pilih Kategori Aset:",
        ["Konstituen MSCI Indonesia", "Indeks Utama (IHSG)", "Input Ticker Kustom (IDX)"]
    )

    if category == "Konstituen MSCI Indonesia":
        selected_ticker = st.selectbox(
            "Pilih Saham MSCI:",
            options=list(MSCI_INDONESIA_TICKERS.keys()),
            format_func=lambda x: f"{x.replace('.JK', '')} - {MSCI_INDONESIA_TICKERS[x]}"
        )
    elif category == "Indeks Utama (IHSG)":
        selected_ticker = "^JKSE"
    else:
        raw_input = st.text_input("Masukkan Kode Saham IDX (contoh: BREN, PTBA, MDKA):", value="BMRI").upper().strip()
        selected_ticker = raw_input if raw_input.endswith(".JK") or raw_input.startswith("^") else f"{raw_input}.JK"

    period_opt = st.selectbox("Rentang Waktu Historis:", ["6mo", "1y", "2y", "5y"], index=1)
    interval_opt = st.selectbox("Interval Data:", ["1d", "1wk", "1h"], index=0)

    if st.button("🔄 Refresh Data Real-Time", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Header Indeks Acuan IHSG & Saham Terpilih
ihsg_df = fetch_ohlcv_data("^JKSE", period="5d", interval="1d")
raw_df = fetch_ohlcv_data(selected_ticker, period=period_opt, interval=interval_opt)

if raw_df.empty:
    st.warning(f"Data tidak ditemukan untuk ticker **{selected_ticker}**. Pastikan kode emiten terdaftar di Yahoo Finance (akhiran `.JK`).")
    st.stop()

df_tech = calculate_technical_indicators(raw_df)
fund_data = fetch_fundamental_data(selected_ticker) if selected_ticker != "^JKSE" else {}
trade_setup = generate_trading_decision(df_tech, fund_data)

# Baris Metrik Utama
last_close = df_tech["Close"].iloc[-1]
prev_close = df_tech["Close"].iloc[-2] if len(df_tech) > 1 else last_close
pct_change = ((last_close - prev_close) / prev_close) * 100

col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)

if not ihsg_df.empty and len(ihsg_df) >= 2:
    ihsg_last = ihsg_df["Close"].iloc[-1]
    ihsg_prev = ihsg_df["Close"].iloc[-2]
    ihsg_chg = ((ihsg_last - ihsg_prev) / ihsg_prev) * 100
    col_m1.metric("IHSG (^JKSE)", f"{ihsg_last:,.2f}", f"{ihsg_chg:+.2f}%")
else:
    col_m1.metric("IHSG (^JKSE)", "N/A", "0.00%")

col_m2.metric(f"Harga {selected_ticker.replace('.JK', '')}", f"Rp {last_close:,.0f}", f"{pct_change:+.2f}%")
col_m3.metric("Rekomendasi Sistem", trade_setup["action"], f"Skor Kuantitatif: {trade_setup['score']}")
col_m4.metric("RSI (14) Momentum", f"{df_tech['RSI_14'].iloc[-1]:.1f}", "Netral (30-70)")
col_m5.metric("Risk / Reward Ratio", f"1 : {trade_setup['rr_ratio']:.2f}", f"SL -{trade_setup['risk_pct']:.1f}% | TP1 +{trade_setup['reward_pct']:.1f}%")

st.divider()

# ==========================================
# 6. TABS ANALISIS MENDALAM
# ==========================================
tab_chart, tab_fund, tab_msci = st.tabs([
    "📊 Analisis Teknikal & Trade Setup",
    "📑 Valuasi Fundamental & Rasio Keuangan",
    "🌐 Komparasi Kinerja Konstituen MSCI vs IHSG"
])

with tab_chart:
    c_left, c_right = st.columns([2.6, 1])
    with c_left:
        st.plotly_chart(build_master_chart(df_tech, selected_ticker, trade_setup), use_container_width=True)
    with c_right:
        st.subheader("🎯 Eksekusi & Manajemen Risiko")
        st.markdown(
            f"<div style='background-color:{trade_setup['color']};padding:12px;border-radius:8px;text-align:center;color:white;font-weight:bold;font-size:20px;'>"
            f"REKOMENDASI: {trade_setup['action']}</div>",
            unsafe_allow_html=True
        )
        st.write("")
        st.markdown(f"""
        * **Harga Acuan / Entry:** `Rp {trade_setup['entry']:,.0f}`
        * **Target Profit 1 (Konservatif):** `Rp {trade_setup['tp1']:,.0f}` (+{trade_setup['reward_pct']:.2f}%)
        * **Target Profit 2 (Agresif):** `Rp {trade_setup['tp2']:,.0f}`
        * **Stop Loss (Batas Risiko):** `Rp {trade_setup['stop_loss']:,.0f}` (-{trade_setup['risk_pct']:.2f}%)
        * **Support Terdekat (20D):** `Rp {trade_setup['support']:,.0f}`
        * **Resistance Terdekat (20D):** `Rp {trade_setup['resistance']:,.0f}`
        """)
        st.divider()
        st.subheader("🔍 Dasar Pertimbangan Algoritma")
        for r in trade_setup["reasons"]:
            st.markdown(f"- {r}")

with tab_fund:
    if selected_ticker == "^JKSE":
        st.info("Data rasio laporan keuangan emiten tidak berlaku untuk indeks agregat IHSG (`^JKSE`). Pilih saham konstituen IDX/MSCI pada sidebar.")
    else:
        st.subheader(f"Ringkasan Fundamental: {fund_data.get('shortName', selected_ticker)}")
        st.caption(f"Sektor: **{fund_data.get('sector', 'N/A')}** | Industri: **{fund_data.get('industry', 'N/A')}**")
        
        f1, f2, f3, f4 = st.columns(4)
        mcap = fund_data.get("marketCap")
        pe = fund_data.get("trailingPE")
        pbv = fund_data.get("priceToBook")
        roe = fund_data.get("returnOnEquity")
        der = fund_data.get("debtToEquity")
        eps = fund_data.get("trailingEps")
        div = fund_data.get("dividendYield")
        high52 = fund_data.get("fiftyTwoWeekHigh")

        f1.metric("Market Cap", f"Rp {mcap/1e12:,.2f} T" if mcap else "N/A")
        f2.metric("PER (Trailing)", f"{pe:.2f}x" if pe else "N/A")
        f3.metric("PBV (Price to Book)", f"{pbv:.2f}x" if pbv else "N/A")
        f4.metric("ROE (Return on Equity)", f"{roe*100:.2f}%" if roe else "N/A")

        f5, f6, f7, f8 = st.columns(4)
        f5.metric("EPS (Trailing)", f"Rp {eps:,.0f}" if eps else "N/A")
        f6.metric("Debt to Equity (DER)", f"{der:.2f}%" if der else "N/A")
        f7.metric("Dividend Yield", f"{div*100:.2f}%" if div else "N/A")
        f8.metric("52-Week High", f"Rp {high52:,.0f}" if high52 else "N/A")

with tab_msci:
    st.subheader("Perbandingan Performa Relatif: IHSG vs Big Caps MSCI Indonesia (Normalized %)")
    compare_list = ["^JKSE", "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "AMMN.JK"]
    multi_close = fetch_multi_tickers_close(compare_list, period="6mo")

    if not multi_close.empty:
        normalized_df = (multi_close / multi_close.ffill().bfill().iloc[0] - 1) * 100
        fig_comp = go.Figure()
        for col in normalized_df.columns:
            line_width = 3 if col == "^JKSE" else 1.6
            fig_comp.add_trace(go.Scatter(
                x=normalized_df.index,
                y=normalized_df[col],
                mode="lines",
                name=col.replace(".JK", ""),
                line=dict(width=line_width)
            ))
        fig_comp.update_layout(
            height=500,
            template="plotly_dark",
            yaxis_title="Return Relatif (%)",
            xaxis_title="Tanggal",
            hovermode="x unified"
        )
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.warning("Gagal memuat data komparasi multi-indeks.")
