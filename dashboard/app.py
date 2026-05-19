import json
import sqlite3
import time
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yaml

DB_PATH = Path("data/scalping_bot.db")
CONTROL_FILE = Path("data/bot_control.json")
CONFIG_PATH = Path("config/config.yaml")

st.set_page_config(
    page_title="Scalping Bot Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark theme CSS
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .metric-card {
        background: #1a1f2e;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #2d3748;
    }
    .profit { color: #00d4aa; }
    .loss { color: #ff4757; }
    .stDataFrame { font-size: 0.85em; }
    div[data-testid="stMetric"] {
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 8px;
        padding: 10px 15px;
    }
    div[data-testid="stMetric"] label { color: #8b95a5; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #e2e8f0; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #1a1f2e;
        border-radius: 6px;
        color: #8b95a5;
        border: 1px solid #2d3748;
    }
    .stTabs [aria-selected="true"] {
        background: #2d3748;
        color: #00d4aa;
    }
</style>
""", unsafe_allow_html=True)


def get_connection():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def send_command(command: str, params: dict = None):
    control = {"command": command, "timestamp": time.time()}
    if params:
        control["params"] = params
    CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTROL_FILE, "w") as f:
        json.dump(control, f)


def get_bot_status() -> str:
    if CONTROL_FILE.exists():
        with open(CONTROL_FILE) as f:
            data = json.load(f)
            cmd = data.get("command", "")
            if cmd == "stop":
                return "ARRETE"
            if cmd == "pause":
                return "PAUSE"
    return "ACTIF"


def load_trades(conn, limit=50) -> pd.DataFrame:
    query = "SELECT * FROM trades ORDER BY id DESC LIMIT ?"
    return pd.read_sql_query(query, conn, params=(limit,))


def load_stats(conn) -> dict:
    cursor = conn.execute("SELECT * FROM bot_stats ORDER BY date DESC LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        return {}
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def load_all_trades(conn) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM trades WHERE pnl_usdt IS NOT NULL ORDER BY id", conn)


def load_signals(conn, limit=100) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM signals ORDER BY id DESC LIMIT ?", conn, params=(limit,))


# ===== SIDEBAR (Controle) =====
with st.sidebar:
    st.markdown("## 🎛️ Contrôle du Bot")

    status = get_bot_status()
    status_color = {"ACTIF": "🟢", "PAUSE": "🟡", "ARRETE": "🔴"}
    st.markdown(f"### Statut : {status_color.get(status, '⚪')} {status}")

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("▶️ Start", use_container_width=True):
            send_command("start")
            st.rerun()
    with col_stop:
        if st.button("⏹️ Stop", use_container_width=True):
            send_command("stop")
            st.rerun()

    if st.button("⏸️ Pause", use_container_width=True):
        send_command("pause")
        st.rerun()

    st.divider()
    st.markdown("## ⚙️ Paramètres")

    config = load_config()

    new_tp = st.slider("Take Profit %", 0.1, 1.0, config.get("take_profit_percent", 0.3), 0.05)
    new_sl = st.slider("Stop Loss %", 0.05, 0.5, config.get("stop_loss_percent", 0.15), 0.05)
    new_capital = st.number_input("Capital (USDT)", 100, 100000, int(config.get("capital_usdt", 1000)), 100)
    new_leverage = st.slider("Levier", 1, 20, config.get("leverage", 5))
    new_max_pos = st.slider("Max Positions", 1, 10, config.get("max_open_positions", 3))

    available_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
    new_pairs = st.multiselect("Paires", available_pairs, config.get("pairs", ["BTC/USDT", "ETH/USDT"]))

    if st.button("💾 Appliquer", use_container_width=True, type="primary"):
        config["take_profit_percent"] = new_tp
        config["stop_loss_percent"] = new_sl
        config["capital_usdt"] = new_capital
        config["leverage"] = new_leverage
        config["max_open_positions"] = new_max_pos
        config["pairs"] = new_pairs
        save_config(config)
        send_command("reload_config")
        st.success("Configuration mise à jour !")

    st.divider()
    st.markdown(f"*Auto-refresh: 5s*")


# ===== MAIN CONTENT =====
conn = get_connection()
if conn is None:
    st.warning("⚠️ Base de données introuvable. Lancez le bot d'abord.")
    st.stop()

stats = load_stats(conn)
trades_df = load_trades(conn, limit=50)
all_trades_df = load_all_trades(conn)

# Header Metrics
st.markdown("## 📊 Scalping Bot — Trading Terminal")

col1, col2, col3, col4, col5 = st.columns(5)

total_pnl = stats.get("total_pnl", 0.0)
win_rate = stats.get("win_rate", 0.0)
total_trades = stats.get("total_trades", 0)
max_dd = stats.get("max_drawdown", 0.0)
open_count = len(trades_df[trades_df["exit_price"].isna()]) if not trades_df.empty and "exit_price" in trades_df.columns else 0

col1.metric("PnL Total", f"{total_pnl:+.2f} USDT")
col2.metric("Win Rate", f"{win_rate:.1f}%")
col3.metric("Total Trades", str(total_trades))
col4.metric("Max Drawdown", f"{max_dd:.1f}%")
col5.metric("Positions", str(open_count))

# Tabs
tab_chart, tab_trades, tab_performance = st.tabs(["📈 Chart", "📋 Trades", "📊 Performance"])

with tab_chart:
    if not all_trades_df.empty:
        # Equity curve as candlestick-style area chart
        pnls = all_trades_df["pnl_usdt"].tolist()
        equity = [0.0]
        for p in pnls:
            equity.append(equity[-1] + p)

        fig = go.Figure()
        colors = ["#00d4aa" if e >= 0 else "#ff4757" for e in equity]

        fig.add_trace(go.Scatter(
            y=equity,
            mode="lines",
            line=dict(color="#00d4aa", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 212, 170, 0.1)",
            name="Equity",
        ))

        # Mark trades
        for i, trade in all_trades_df.iterrows():
            color = "#00d4aa" if trade["pnl_usdt"] > 0 else "#ff4757"
            idx = i + 1
            if idx < len(equity):
                fig.add_trace(go.Scatter(
                    x=[idx], y=[equity[idx]],
                    mode="markers",
                    marker=dict(size=8, color=color, symbol="circle"),
                    showlegend=False,
                    hovertext=f"{trade['side']} {trade['pair']}<br>PnL: {trade['pnl_usdt']:+.2f}",
                ))

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            title="Equity Curve",
            yaxis_title="PnL (USDT)",
            xaxis_title="Trade #",
            height=450,
            margin=dict(l=50, r=20, t=50, b=50),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("En attente du premier trade...")

with tab_trades:
    if not trades_df.empty:
        display_df = trades_df.copy()
        display_cols = ["pair", "side", "entry_price", "exit_price", "pnl_usdt", "pnl_percent", "duration_s", "reason"]
        available_cols = [c for c in display_cols if c in display_df.columns]
        display_df = display_df[available_cols]

        def color_pnl(val):
            if pd.isna(val):
                return ""
            color = "#00d4aa" if val > 0 else "#ff4757"
            return f"color: {color}; font-weight: bold"

        if "pnl_usdt" in display_df.columns:
            styled = display_df.style.applymap(color_pnl, subset=["pnl_usdt"])
            if "pnl_percent" in display_df.columns:
                styled = styled.applymap(color_pnl, subset=["pnl_percent"])
            st.dataframe(styled, use_container_width=True, hide_index=True, height=400)
        else:
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("Aucun trade enregistré.")

with tab_performance:
    if not all_trades_df.empty:
        pnls = all_trades_df["pnl_usdt"].tolist()

        # Performance metrics
        col_a, col_b, col_c = st.columns(3)

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        with col_a:
            avg_win = sum(wins) / len(wins) if wins else 0
            st.metric("Gain moyen", f"{avg_win:+.2f} USDT")
            st.metric("Nb gagnants", str(len(wins)))

        with col_b:
            avg_loss = sum(losses) / len(losses) if losses else 0
            st.metric("Perte moyenne", f"{avg_loss:.2f} USDT")
            st.metric("Nb perdants", str(len(losses)))

        with col_c:
            profit_factor = sum(wins) / abs(sum(losses)) if losses else 0
            st.metric("Profit Factor", f"{profit_factor:.2f}")
            last_50 = pnls[-50:]
            wr_50 = (sum(1 for p in last_50 if p > 0) / len(last_50)) * 100 if last_50 else 0
            st.metric("Win Rate (50)", f"{wr_50:.1f}%")

        # Drawdown chart
        peak = 0.0
        equity = [0.0]
        drawdowns = [0.0]
        for p in pnls:
            eq = equity[-1] + p
            equity.append(eq)
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak * 100) if peak > 0 else 0
            drawdowns.append(dd)

        fig_dd = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)

        fig_dd.add_trace(go.Scatter(
            y=equity, mode="lines", line=dict(color="#00d4aa", width=1.5),
            name="Equity"
        ), row=1, col=1)

        fig_dd.add_trace(go.Scatter(
            y=drawdowns, mode="lines", fill="tozeroy",
            line=dict(color="#ff4757", width=1), fillcolor="rgba(255,71,87,0.2)",
            name="Drawdown %"
        ), row=2, col=1)

        fig_dd.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            height=400,
            margin=dict(l=50, r=20, t=30, b=30),
            showlegend=False,
        )
        fig_dd.update_yaxes(title_text="PnL (USDT)", row=1, col=1)
        fig_dd.update_yaxes(title_text="DD %", autorange="reversed", row=2, col=1)

        st.plotly_chart(fig_dd, use_container_width=True)

        # PnL distribution
        st.subheader("Distribution des PnL")
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=pnls,
            nbinsx=30,
            marker_color=["#00d4aa" if p > 0 else "#ff4757" for p in sorted(pnls)],
        ))
        fig_hist.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            height=250,
            margin=dict(l=50, r=20, t=20, b=30),
            xaxis_title="PnL (USDT)",
            yaxis_title="Fréquence",
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Pas assez de données pour les stats de performance.")

conn.close()

# Auto-refresh
time.sleep(5)
st.rerun()
