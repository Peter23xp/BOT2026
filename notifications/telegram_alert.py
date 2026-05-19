import os

from loguru import logger

try:
    from telegram import Bot
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class TelegramAlert:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id and HAS_TELEGRAM)

        if not HAS_TELEGRAM:
            logger.warning("python-telegram-bot non installe — alertes Telegram desactivees")
        elif not self.token or not self.chat_id:
            logger.warning("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant — alertes desactivees")
        else:
            logger.info("Alertes Telegram activees")

    async def _send(self, message: str) -> None:
        if not self.enabled:
            return
        try:
            bot = Bot(token=self.token)
            await bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erreur envoi Telegram: {e}")

    async def notify_open(self, pair: str, side: str, price: float, size: float) -> None:
        emoji = "\U0001f4c8" if side == "LONG" else "\U0001f4c9"
        msg = f"{emoji} <b>{side} {pair}</b>\nPrix: {price:.2f} | Taille: {size:.5f}"
        await self._send(msg)

    async def notify_close(self, pair: str, side: str, pnl: float, pnl_day: float) -> None:
        emoji = "✅" if pnl > 0 else "❌"
        msg = (
            f"{emoji} <b>Ferme {side} {pair}</b>\n"
            f"PnL trade: {pnl:+.2f} USDT\n"
            f"PnL jour: {pnl_day:+.2f} USDT"
        )
        await self._send(msg)

    async def notify_drawdown_warning(self, percent: float) -> None:
        msg = f"⚠️ <b>Drawdown {percent:.1f}%</b> — surveillance active"
        await self._send(msg)

    async def notify_critical_stop(self, percent: float) -> None:
        msg = f"\U0001f6d1 <b>ARRET CRITIQUE</b>\nDrawdown {percent:.1f}% — bot arrete"
        await self._send(msg)

    async def notify_daily_report(self, stats: dict) -> None:
        msg = (
            f"\U0001f4ac <b>Rapport quotidien</b>\n"
            f"Trades: {stats.get('total_trades', 0)}\n"
            f"Win rate: {stats.get('win_rate', 0):.1f}%\n"
            f"PnL jour: {stats.get('total_pnl', 0):+.2f} USDT\n"
            f"Max DD: {stats.get('max_drawdown', 0):.1f}%"
        )
        await self._send(msg)
