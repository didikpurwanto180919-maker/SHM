import os
import sys
import subprocess

# ==========================================
# 0. AUTO-INSTALLER PUSTAKA (ANTI-MODULENOTFOUND)
# ==========================================
def verify_and_install(package_name: str, import_name: str = None):
    """Memastikan pustaka eksternal terinstal di environment Streamlit Cloud."""
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
# 1. KONFIGURASI HALAMAN & INDEKS UTAMA
# ==========================================
st.set_page_config(
    page_title="Terminal Saham BEI (1.011 Emiten) & MSCI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSV_FILENAME = "daftar_lengkap_saham_indonesia_bei.csv"

MSCI_CONSTITUENTS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "BBNI", "AMMN",
    "GOTO", "ADRO", "ICBP", "UNTR", "KLBF", "INDF", "CPIN"
]

# ==========================================
# 2. LOADER DATABASE 1.011 SAHAM BEI & DATA PASAR
# ==========================================
@st.cache_data(show_spinner=False)
def load_bei_catalog(csv_path: str) -> pd.DataFrame:
    """Memuat seluruh daftar saham BEI dari file CSV lokal di repositori."""
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        df["Kode_Saham"] = df["Kode_Saham"].astype(str).str.strip().str.upper()
        return df
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_market_ohlcv(ticker_symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Mengambil data harga historis/intraday dari Yahoo Finance."""
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
    except Exception as err:
        st.error(f"Koneksi data pasar terkendala untuk {ticker_symbol}: {err}")
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
def load_benchmark_comparison(symbols: list, period: str = "6mo") -> pd.DataFrame:
    """Mengunduh data penutupan multi-saham untuk perbandingan kinerja relatif."""
    try:
        downloaded = yf.download(symbols, period=period, interval="1d", progress=False)
        if downloaded is None or downloaded.empty:
            return pd.DataFrame()
        closes = downloaded["Close"] if "Close" in downloaded else downloaded
        if isinstance(closes, pd.Series):
            closes = closes.to_frame()
        return closes.dropna(how="all")
    except Exception:
        return pd.DataFrame()

# ==========================================
# 3. ENGINE INDIKATOR TEKNIKAL & MANAJEMEN RISIKO
# ==========================================
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung SMA, EMA, Bollinger Bands, RSI (14), MACD, dan ATR (14)."""
    if df.empty:
        return df

    out = df.copy()
    out["SMA_20"] = out["Close"].rolling(20, min_periods=1).mean()
    out["SMA_50"] = out["Close"].rolling(50, min_periods=1).mean()
    out["SMA_200"] = out["Close"].rolling(200, min_periods=20).mean()

    rolling_std = out["Close"].rolling(20, min_periods=2).std().fillna(0)
    out["BB_Upper"] = out["SMA_20"] + (2.0 * rolling_std)
    out["BB_Lower"] = out["SMA_20"] - (2.0 * rolling_std)

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
    return out


def evaluate_trade_setup(df: pd.DataFrame, fund: dict) -> dict:
    """Menentukan sinyal BUY/HOLD/SELL beserta target harga dan batas Stop Loss."""
    curr = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else curr
    price = float(curr["Close"])
    atr_val = float(curr.get("ATR_14", price * 0.02))
    if pd.isna(atr_val) or atr_val <= 0:
        atr_val = price * 0.02

    pts = 0
    notes = []

    if price > curr["SMA_20"] > curr["SMA_50"]:
        pts += 2
        notes.append("Struktur Bullish: Harga bergerak di atas SMA 20 dan SMA 50.")
    elif price < curr["SMA_20"] < curr["SMA_50"]:
        pts -= 2
        notes.append("Struktur Bearish: Harga berada di bawah SMA 20 dan SMA 50.")

    if pd.notna(curr.get("SMA_200")):
        if price > curr["SMA_200"]:
            pts += 1
            notes.append("Tren Mayor Positif: Harga di atas SMA 200.")
        else:
            pts -= 1
            notes.append("Tren Mayor Tertekan: Harga di bawah SMA 200.")

    rsi_val = float(curr.get("RSI_14", 50))
    if 30 <= rsi_val <= 45:
        pts += 1
        notes.append(f"Momentum RSI ({rsi_val:.1f}) berada di area akumulasi bawah.")
    elif 50 < rsi_val < 68:
        pts += 1
        notes.append(f"Momentum RSI ({rsi_val:.1f}) mengonfirmasi dorongan beli.")
    elif rsi_val >= 72:
        pts -= 1
        notes.append(f"RSI ({rsi_val:.1f}) memasuki area jenuh beli (Overbought).")

    if curr["MACD"] > curr["MACD_Signal"] and prev["MACD"] <= prev["MACD_Signal"]:
        pts += 2
        notes.append("Terbentuk perpotongan Golden Cross pada MACD.")
    elif curr["MACD"] > curr["MACD_Signal"]:
        pts += 1
        notes.append("MACD bertahan di atas garis sinyal (momentum positif).")
    else:
        pts -= 1
        notes.append("MACD masih berada di bawah garis sinyal.")

    pe_ratio = fund.get("pe")
    roe_ratio = fund.get("roe")
    if pe_ratio is not None and 0 < pe_ratio < 15:
        pts += 1
        notes.append(f"Valuasi PER relatif diskon ({pe_ratio:.2f}x).")
    if roe_ratio is not None and roe_ratio > 0.15:
        pts += 1
        notes.append(f"Tingkat pengembalian ekuitas (ROE) tinggi ({roe_ratio*100:.1f}%).")

    if pts >= 3:
        signal, color = "BUY", "#16a34a"
    elif pts <= -2:
        signal, color = "SELL", "#dc2626"
    else:
        signal, color = "HOLD", "#d97706"

    window_20 = df.tail(20)
    sup = min(float(window_20["Low"].min()), price - (1.8 * atr_val))
    res = max(float(window_20["High"].max()), price + (3.6 * atr_val))

    sl = round(max(sup * 0.99, price - (2.0 * atr_val)), 0)
    unit_risk = max(price - sl, price * 0.01)
    tp1 = round(price + (2.0 * unit_risk), 0)
    tp2 = round(max(res, price + (3.0 * unit_risk)), 0)
    rrr = (tp1 - price) / unit_risk if unit_risk > 0 else 0.0

    return {
        "signal": signal,
        "score": pts,
        "color": color,
        "notes": notes,
        "entry": round(price, 0),
        "support": round(sup, 0),
        "resistance": round(res, 0),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk_pct": (unit_risk / price) * 100,
        "reward_pct": ((tp1 - price) / price) * 100,
        "rrr": rrr
    }

# ==========================================
# 4. GRAFIK PLOTLY MULTI-PANEL
# ==========================================
def render_technical_chart(df: pd.DataFrame, symbol: str, plan: dict) -> go.Figure:
    """Membangun grafik interaktif Candlestick, Bollinger Bands, Volume, MACD, dan RSI."""
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.52, 0.14, 0.17, 0.17],
        subplot_titles=(
            f"{symbol} - Candlestick, Moving Averages & Bollinger Bands",
            "Volume & MA20", "MACD (12, 26, 9)", "RSI (14)"
        )
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="OHLC"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Upper"], line=dict(color="rgba(148,163,184,0.4)", width=1, dash="dot"),
        name="BB Upper"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], line=dict(color="rgba(148,163,184,0.4)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(148,163,184,0.07)", name="BB Lower"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_20"], line=dict(color="#38bdf8", width=1.5), name="SMA 20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_50"], line=dict(color="#f59e0b", width=1.5), name="SMA 50"), row=1, col=1)
    if df["SMA_200"].notna().sum() > 0:
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA_200"], line=dict(color="#a855f7", width=1.8), name="SMA 200"), row=1, col=1)

    fig.add_hline(y=plan["tp1"], line_dash="dash", line_color="#16a34a", annotation_text=f"TP1: {plan['tp1']:,.0f}", row=1, col=1)
    fig.add_hline(y=plan["sl"], line_dash="dash", line_color="#dc2626", annotation_text=f"SL: {plan['sl']:,.0f}", row=1, col=1)

    v_colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=v_colors, name="Volume"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Vol_MA20"], line=dict(color="#facc15", width=1.2), name="Vol MA20"), row=2, col=1)

    m_colors = ["#16a34a" if h >= 0 else "#dc2626" for h in df["MACD_Hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], marker_color=m_colors, name="Hist"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], line=dict(color="#38bdf8", width=1.5), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], line=dict(color="#f97316", width=1.5), name="Signal"), row=3, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI_14"], line=dict(color="#c084fc", width=1.8), name="RSI 14"), row=4, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=4, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=4, col=1)

    fig.update_layout(
        height=860, template="plotly_dark", xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1)
    )
    return fig

# ==========================================
# 5. SIDEBAR FILTER & PEMILIHAN DARI 1.011 SAHAM BEI
# ==========================================
bei_df = load_bei_catalog(CSV_FILENAME)

with st.sidebar:
    st.title("🏛️ Terminal Saham BEI")
    st.caption("Terintegrasi Database 1.011 Emiten IDX & MSCI")

    if bei_df.empty:
        st.warning(f"File `{CSV_FILENAME}` belum ditemukan di folder GitHub.")
        uploaded_csv = st.file_uploader("Unggah file CSV Saham BEI:", type=["csv"])
        if uploaded_csv is not None:
            bei_df = pd.read_csv(uploaded_csv)
            bei_df["Kode_Saham"] = bei_df["Kode_Saham"].astype(str).str.strip().str.upper()

    st.divider()

    if not bei_df.empty:
        universe_mode = st.selectbox(
            "Filter Kategori / Indeks:",
            [
                "Semua Emiten Aktif BEI",
                "Seluruh Database BEI (1.011 Saham)",
                "Konstituen MSCI Indonesia",
                "Indeks LQ45",
                "Indeks KOMPAS100",
                "Indeks PEFINDO25",
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

            st.caption(f"Menampilkan **{len(filtered_df)}** emiten sesuai filter.")

            if not filtered_df.empty:
                options_map = {
                    row["Ticker_Yahoo_Finance"]: f"{row['Kode_Saham']} - {row['Nama_Perusahaan']} ({row['Papan_Pencatatan']})"
                    for _, row in filtered_df.iterrows()
                }
                selected_symbol = st.selectbox(
                    "Pilih Emiten BEI:",
                    options=list(options_map.keys()),
                    format_func=lambda x: options_map.get(x, x)
                )
            else:
                st.warning("Tidak ada emiten yang cocok dengan kombinasi filter.")
                st.stop()
        else:
            selected_symbol = "^JKSE"
    else:
        fallback_code = st.text_input("Masukkan Kode Saham BEI (contoh: BBCA, BMRI, AADI):", value="BBCA").upper().strip()
        selected_symbol = fallback_code if fallback_code.endswith(".JK") or fallback_code.startswith("^") else f"{fallback_code}.JK"

    period_choice = st.selectbox("Rentang Historis:", ["6mo", "1y", "2y", "5y"], index=1)
    interval_choice = st.selectbox("Interval Candle:", ["1d", "1wk", "1h"], index=0)

    if st.button("🔄 Muat Ulang Data Real-Time", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 6. EKSEKUSI DATA & METRIK HEADER
# ==========================================
ihsg_data = load_market_ohlcv("^JKSE", period="5d", interval="1d")
price_df = load_market_ohlcv(selected_symbol, period=period_choice, interval=interval_choice)

if price_df.empty:
    st.error(
        f"Data transaksi Yahoo Finance untuk **{selected_symbol}** tidak tersedia "
        "(emiten mungkin berstatus Delisting, Suspensi, atau belum memiliki riwayat perdagangan)."
    )
    st.stop()

tech_df = compute_indicators(price_df)
fund_info = load_fundamental_metrics(selected_symbol) if selected_symbol != "^JKSE" else {}
setup_plan = evaluate_trade_setup(tech_df, fund_info)

# Ambil metadata dari CSV untuk saham terpilih
csv_profile = {}
if not bei_df.empty and selected_symbol != "^JKSE":
    match_row = bei_df[bei_df["Ticker_Yahoo_Finance"] == selected_symbol]
    if not match_row.empty:
        csv_profile = match_row.iloc[0].to_dict()

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

m2.metric(f"Harga {selected_symbol.replace('.JK', '')}", f"Rp {last_px:,.0f}", f"{chg_pct:+.2f}%")
m3.metric("Sinyal Kuantitatif", setup_plan["signal"], f"Skor: {setup_plan['score']}")
m4.metric("Momentum RSI (14)", f"{tech_df['RSI_14'].iloc[-1]:.1f}", csv_profile.get("Papan_Pencatatan", "IDX"))
m5.metric("Risk / Reward Ratio", f"1 : {setup_plan['rrr']:.2f}", f"SL -{setup_plan['risk_pct']:.1f}% | TP1 +{setup_plan['reward_pct']:.1f}%")

st.divider()

# ==========================================
# 7. TABS VISUALISASI & DIREKTORI 1.011 EMITEN
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Analisis Teknikal & Sinyal Trading",
    "📑 Fundamental & Profil Pencatatan BEI",
    "🌐 Komparasi Kinerja MSCI & Big Caps",
    "🗂️ Direktori Lengkap 1.011 Saham BEI"
])

with tab1:
    col_chart, col_plan = st.columns([2.6, 1])
    with col_chart:
        st.plotly_chart(render_technical_chart(tech_df, selected_symbol, setup_plan), use_container_width=True)
    with col_plan:
        st.subheader("🎯 Rencana Eksekusi")
        st.markdown(
            f"<div style='background-color:{setup_plan['color']};padding:12px;border-radius:8px;text-align:center;color:white;font-weight:bold;font-size:20px;'>"
            f"REKOMENDASI: {setup_plan['signal']}</div>",
            unsafe_allow_html=True
        )
        if csv_profile:
            st.caption(
                f"**{csv_profile.get('Nama_Perusahaan')}** | Sektor: {csv_profile.get('Sektor_Indonesia')} | "
                f"Indeks: {csv_profile.get('Indeks_Utama')}"
            )
        st.markdown(f"""
        * **Harga Entry Acuan:** `Rp {setup_plan['entry']:,.0f}`
        * **Target Profit 1 (TP1):** `Rp {setup_plan['tp1']:,.0f}` (+{setup_plan['reward_pct']:.2f}%)
        * **Target Profit 2 (TP2):** `Rp {setup_plan['tp2']:,.0f}`
        * **Batas Stop Loss (SL):** `Rp {setup_plan['sl']:,.0f}` (-{setup_plan['risk_pct']:.2f}%)
        * **Support 20 Hari:** `Rp {setup_plan['support']:,.0f}`
        * **Resistance 20 Hari:** `Rp {setup_plan['resistance']:,.0f}`
        """)
        st.divider()
        st.subheader("🔍 Indikator Pendukung")
        for note in setup_plan["notes"]:
            st.markdown(f"- {note}")

with tab2:
    if selected_symbol == "^JKSE":
        st.info("Pilih salah satu dari 1.011 emiten BEI pada sidebar untuk melihat profil pencatatan dan rasio fundamental.")
    else:
        if csv_profile:
            st.subheader(f"🏛️ Profil Resmi BEI: {csv_profile.get('Nama_Perusahaan')} ({csv_profile.get('Kode_Saham')})")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Sektor BEI (IDX-IC)", csv_profile.get("Sektor_Indonesia", "-"))
            p2.metric("Papan Pencatatan", csv_profile.get("Papan_Pencatatan", "-"))
            p3.metric("Tanggal IPO", csv_profile.get("Tanggal_IPO_Teks", "-"))
            p4.metric("Jumlah Saham Tercatat", f"{int(csv_profile.get('Jumlah_Saham_Tercatat', 0)):,}")

            st.caption(
                f"**Kode Lintas Platform:** BEI: `{csv_profile.get('Ticker_BEI')}` | "
                f"TradingView: `{csv_profile.get('Ticker_TradingView')}` | "
                f"Yahoo: `{csv_profile.get('Ticker_Yahoo_Finance')}` | "
                f"Bloomberg: `{csv_profile.get('Ticker_Bloomberg')}` | "
                f"Indeks Utama: `{csv_profile.get('Indeks_Utama')}`"
            )
            st.divider()

        st.subheader("📑 Rasio Valuasi & Profitabilitas (Yahoo Finance)")
        k1, k2, k3, k4 = st.columns(4)
        mcap = fund_info.get("mcap")
        pe = fund_info.get("pe")
        pbv = fund_info.get("pbv")
        roe = fund_info.get("roe")
        der = fund_info.get("der")
        eps = fund_info.get("eps")
        div_y = fund_info.get("div_yield")
        h52 = fund_info.get("high_52w")

        k1.metric("Kapitalisasi Pasar", f"Rp {mcap/1e12:,.2f} T" if mcap else "N/A")
        k2.metric("PER (Trailing)", f"{pe:.2f}x" if pe else "N/A")
        k3.metric("PBV (Price to Book)", f"{pbv:.2f}x" if pbv else "N/A")
        k4.metric("ROE (Return on Equity)", f"{roe*100:.2f}%" if roe else "N/A")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("EPS (Laba per Saham)", f"Rp {eps:,.0f}" if eps else "N/A")
        k6.metric("DER (Debt to Equity)", f"{der:.2f}%" if der else "N/A")
        k7.metric("Dividend Yield", f"{div_y*100:.2f}%" if div_y else "N/A")
        k8.metric("Tertinggi 52 Minggu", f"Rp {h52:,.0f}" if h52 else "N/A")

with tab3:
    st.subheader("Perbandingan Return Relatif (6 Bulan): IHSG vs Konstituen Utama")
    bench_tickers = ["^JKSE", "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "AMMN.JK"]
    if selected_symbol not in bench_tickers:
        bench_tickers.append(selected_symbol)

    comp_df = load_benchmark_comparison(bench_tickers, period="6mo")
    if not comp_df.empty:
        norm_df = (comp_df / comp_df.ffill().bfill().iloc[0] - 1) * 100
        fig_rel = go.Figure()
        for col in norm_df.columns:
            width_val = 3.0 if col in ["^JKSE", selected_symbol] else 1.5
            fig_rel.add_trace(go.Scatter(
                x=norm_df.index, y=norm_df[col], mode="lines",
                name=str(col).replace(".JK", ""), line=dict(width=width_val)
            ))
        fig_rel.update_layout(
            height=500, template="plotly_dark",
            yaxis_title="Return Kumulatif (%)", xaxis_title="Tanggal", hovermode="x unified"
        )
        st.plotly_chart(fig_rel, use_container_width=True)

with tab4:
    st.subheader("🗂️ Database Lengkap 1.011 Emiten Bursa Efek Indonesia")
    if not bei_df.empty:
        search_q = st.text_input("🔍 Cari Kode Saham atau Nama Perusahaan:", "")
        view_df = bei_df.copy()
        if search_q:
            mask = (
                view_df["Kode_Saham"].str.contains(search_q, case=False, na=False) |
                view_df["Nama_Perusahaan"].str.contains(search_q, case=False, na=False) |
                view_df["Sektor_Indonesia"].str.contains(search_q, case=False, na=False)
            )
            view_df = view_df[mask]
        st.dataframe(view_df, use_container_width=True, height=520)
    else:
        st.info(f"Unggah file `{CSV_FILENAME}` ke repositori GitHub Anda untuk menampilkan tabel 1.011 emiten.")
