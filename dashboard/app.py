import sqlite3
import time
from pathlib import Path

import streamlit as st
import pandas as pd

DB_PATH = Path("data/scalping_bot.db")

st.set_page_config(page_title="Scalping Bot", layout="wide")


def get_connection():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def load_trades(conn, limit=50) -> pd.DataFrame:
    query = "SELECT * FROM trades ORDER BY id DESC LIMIT ?"
    df = pd.read_sql_query(query, conn, params=(limit,))
    return df


def load_stats(conn) -> dict:
    cursor = conn.execute("SELECT * FROM bot_stats ORDER BY date DESC LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        return {}
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def load_all_trades_pnl(conn) -> list[float]:
    cursor = conn.execute("SELECT pnl_usdt FROM trades WHERE pnl_usdt IS NOT NULL ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def main():
    st.title("Scalping Bot — Dashboard")

    conn = get_connection()
    if conn is None:
        st.warning("Base de donnees introuvable. Lancez le bot d'abord.")
        return

    # Header metrics
    stats = load_stats(conn)
    trades_df = load_trades(conn, limit=50)
    all_pnls = load_all_trades_pnl(conn)

    col1, col2, col3, col4 = st.columns(4)

    total_pnl = stats.get("total_pnl", 0.0)
    win_rate = stats.get("win_rate", 0.0)
    total_trades = stats.get("total_trades", 0)
    max_dd = stats.get("max_drawdown", 0.0)

    col1.metric("PnL Total", f"{total_pnl:+.2f} USDT")
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Trades", str(total_trades))
    col4.metric("Max Drawdown", f"{max_dd:.1f}%")

    st.divider()

    # Equity curve
    if all_pnls:
        equity = [0.0]
        for pnl in all_pnls:
            equity.append(equity[-1] + pnl)

        st.subheader("Equity Curve")
        chart_df = pd.DataFrame({"PnL Cumule (USDT)": equity})
        st.line_chart(chart_df)
    else:
        st.info("Aucun trade enregistre pour le moment.")

    st.divider()

    # Win rate glissant (50 derniers)
    if len(all_pnls) > 0:
        last_50 = all_pnls[-50:]
        wins_50 = sum(1 for p in last_50 if p > 0)
        wr_50 = (wins_50 / len(last_50)) * 100
        st.subheader(f"Win Rate (50 derniers) : {wr_50:.1f}%")

    # Trades table
    st.subheader("Derniers Trades")
    if not trades_df.empty:
        display_cols = ["pair", "side", "entry_price", "exit_price", "pnl_usdt", "pnl_percent", "duration_s", "reason", "timestamp_close"]
        available_cols = [c for c in display_cols if c in trades_df.columns]
        st.dataframe(trades_df[available_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Aucun trade.")

    conn.close()

    # Auto-refresh every 5 seconds
    time.sleep(5)
    st.rerun()


if __name__ == "__main__":
    main()
