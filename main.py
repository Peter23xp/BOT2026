import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from core.data_feed import DataFeed
from core.strategy import ScalpingStrategy
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from core.pnl_tracker import PnLCalculator
from db.models import init_database, insert_trade, insert_signal, update_daily_stats
from models.events import MarketData, Signal, OrderRequest, OrderResult, TradeClose
from notifications.telegram_alert import TelegramAlert


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan> - {message}",
    level="INFO",
)
logger.add("logs/bot_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", level="DEBUG")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


async def strategy_loop(
    market_queue: asyncio.Queue,
    signal_queue: asyncio.Queue,
    strategy: ScalpingStrategy,
    executor: OrderExecutor,
) -> None:
    while True:
        data: MarketData = await market_queue.get()
        executor.update_price(data.pair, data.close)

        sig = strategy.evaluate(data)
        if sig:
            await signal_queue.put(sig)

        market_queue.task_done()


async def risk_loop(
    signal_queue: asyncio.Queue,
    order_queue: asyncio.Queue,
    risk_manager: RiskManager,
    db,
) -> None:
    while True:
        sig: Signal = await signal_queue.get()

        signal_record = {
            "pair": sig.pair,
            "timestamp": datetime.fromtimestamp(sig.timestamp, tz=timezone.utc).isoformat(),
            "side": sig.side,
            "rsi": sig.rsi,
            "ema_distance": sig.ema_distance,
            "volume_ratio": sig.volume_ratio,
            "spread": sig.spread,
            "triggered": 0,
        }

        approved, reason = risk_manager.approve(sig)
        if approved:
            order_request = risk_manager.build_order_request(sig)
            await order_queue.put(order_request)
            signal_record["triggered"] = 1
            logger.info(f"Signal approuve: {sig.side} {sig.pair} size={order_request.size}")
        else:
            logger.info(f"Signal rejete: {sig.side} {sig.pair} — {reason}")

        await insert_signal(db, signal_record)
        signal_queue.task_done()


async def execution_loop(
    order_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    executor: OrderExecutor,
    strategy: ScalpingStrategy,
    risk_manager: RiskManager,
    telegram: TelegramAlert,
) -> None:
    while True:
        request: OrderRequest = await order_queue.get()

        result = await executor.execute_order(request)
        if result.status == "filled":
            strategy.open_positions.add(result.pair)
            risk_manager.open_position_count += 1
            await result_queue.put(result)
            await telegram.notify_open(result.pair, result.side, result.fill_price, result.size)

        order_queue.task_done()


async def position_monitor_loop(
    result_queue: asyncio.Queue,
    executor: OrderExecutor,
    strategy: ScalpingStrategy,
    risk_manager: RiskManager,
    pnl_calc: PnLCalculator,
    db,
    telegram: TelegramAlert,
) -> None:
    while True:
        closes = executor.check_positions()
        for close in closes:
            strategy.open_positions.discard(close.pair)
            risk_manager.open_position_count -= 1
            risk_manager.record_trade_result(close.pnl_usdt)
            pnl_calc.record_trade(close.pnl_usdt)
            await telegram.notify_close(close.pair, close.side, close.pnl_usdt, risk_manager.daily_pnl)

            daily_dd = abs(risk_manager.daily_pnl) / risk_manager.capital * 100
            if risk_manager.daily_pnl < 0 and daily_dd >= 10 and not risk_manager.is_halted:
                await telegram.notify_drawdown_warning(daily_dd)
            if risk_manager.is_halted:
                total_dd = abs(risk_manager.total_pnl) / risk_manager.capital * 100
                await telegram.notify_critical_stop(total_dd)

            trade_record = {
                "pair": close.pair,
                "side": close.side,
                "entry_price": close.entry_price,
                "exit_price": close.exit_price,
                "size": close.size,
                "pnl_usdt": close.pnl_usdt,
                "pnl_percent": close.pnl_percent,
                "duration_s": close.duration_s,
                "reason": close.reason,
                "timestamp_open": datetime.fromtimestamp(close.timestamp - close.duration_s, tz=timezone.utc).isoformat(),
                "timestamp_close": datetime.fromtimestamp(close.timestamp, tz=timezone.utc).isoformat(),
            }
            await insert_trade(db, trade_record)

            logger.info(
                f"Trade ferme: {close.side} {close.pair} | "
                f"PnL={close.pnl_usdt:+.2f} USDT | Raison={close.reason} | "
                f"Win rate={pnl_calc.win_rate:.1f}%"
            )

        await asyncio.sleep(0.1)


async def main() -> None:
    load_dotenv("config/secrets.env")
    config = load_config()

    logger.info("=" * 50)
    logger.info("SCALPING BOT — Demarrage")
    logger.info(f"Mode: {'DRY-RUN' if config.get('dry_run') else 'LIVE (testnet)' if config.get('testnet') else 'LIVE'}")
    logger.info(f"Paires: {config['pairs']}")
    logger.info(f"Capital: {config['capital_usdt']} USDT | Levier: {config['leverage']}x")
    logger.info("=" * 50)

    db = await init_database()

    exchange = None
    if not config.get("dry_run"):
        import ccxt.pro as ccxtpro
        import os
        exchange_class = getattr(ccxtpro, config["exchange"])
        exchange = exchange_class({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET"),
            "sandbox": config.get("testnet", True),
            "options": {"defaultType": "future"},
        })
        await exchange.load_markets()

    mode = "dry_run" if config.get("dry_run") else "live"

    data_feed = DataFeed(
        exchange=exchange,
        pairs=config["pairs"],
        timeframe=config["timeframe"],
        mode=mode,
    )

    strategy = ScalpingStrategy(
        rsi_long_threshold=35.0,
        rsi_short_threshold=65.0,
        volume_ratio_min=1.5,
        spread_max_percent=0.05,
    )

    risk_manager = RiskManager(
        capital=config["capital_usdt"],
        risk_per_trade_percent=config["risk_per_trade_percent"],
        max_drawdown_percent=config["max_drawdown_percent"],
        daily_drawdown_limit=config["daily_drawdown_limit"],
        max_open_positions=config["max_open_positions"],
        leverage=config["leverage"],
        stop_loss_percent=config["stop_loss_percent"],
        take_profit_percent=config["take_profit_percent"],
    )

    executor = OrderExecutor(
        exchange=exchange,
        mode=mode,
        slippage_percent=config.get("slippage_percent", 0.01),
        timeout_seconds=config.get("timeout_seconds", 300),
        trailing_activation_percent=config.get("trailing_activation_percent", 0.2),
        trailing_stop_percent=config.get("stop_loss_percent", 0.15),
        fees_percent=config.get("fees_percent", 0.04),
    )

    pnl_calc = PnLCalculator(fees_percent=config.get("fees_percent", 0.04))
    telegram = TelegramAlert()

    market_queue: asyncio.Queue[MarketData] = asyncio.Queue(maxsize=100)
    signal_queue: asyncio.Queue[Signal] = asyncio.Queue(maxsize=50)
    order_queue: asyncio.Queue[OrderRequest] = asyncio.Queue(maxsize=20)
    result_queue: asyncio.Queue[OrderResult] = asyncio.Queue(maxsize=50)

    shutdown_event = asyncio.Event()

    async def graceful_shutdown():
        logger.warning("Arret en cours...")
        data_feed.shutdown()
        closes = await executor.close_all_positions()
        for close in closes:
            pnl_calc.record_trade(close.pnl_usdt)
            risk_manager.record_trade_result(close.pnl_usdt)

        stats = pnl_calc.get_daily_stats()
        await update_daily_stats(db, stats)
        await db.close()

        logger.info(f"Session terminee | Trades: {stats['total_trades']} | PnL: {stats['total_pnl']:+.2f} USDT | Win rate: {stats['win_rate']:.1f}%")
        shutdown_event.set()

    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(graceful_shutdown()))
    else:
        def win_handler(sig, frame):
            asyncio.create_task(graceful_shutdown())
        signal.signal(signal.SIGINT, win_handler)

    tasks = [
        asyncio.create_task(data_feed.run(market_queue)),
        asyncio.create_task(strategy_loop(market_queue, signal_queue, strategy, executor)),
        asyncio.create_task(risk_loop(signal_queue, order_queue, risk_manager, db)),
        asyncio.create_task(execution_loop(order_queue, result_queue, executor, strategy, risk_manager, telegram)),
        asyncio.create_task(position_monitor_loop(result_queue, executor, strategy, risk_manager, pnl_calc, db, telegram)),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception():
                logger.error(f"Tache terminee avec erreur: {task.exception()}")
    except asyncio.CancelledError:
        pass
    finally:
        if not shutdown_event.is_set():
            await graceful_shutdown()
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
