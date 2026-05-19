# Scalping Bot — Phase 3 : Dashboard + Alertes Telegram

## Vue d'ensemble

Dashboard Streamlit temps réel (lecture DB toutes les 5s) + alertes Telegram asynchrones intégrées au bot principal. Mode graceful si Telegram non configuré.

## Structure des fichiers

```
dashboard/
└── app.py              # Dashboard Streamlit
notifications/
├── __init__.py
└── telegram_alert.py   # Client Telegram async
```

## Dashboard Streamlit (`dashboard/app.py`)

**Rafraîchissement :** toutes les 5 secondes via `st.rerun` avec timer.

**Layout :**
- **Header** : statut du bot, PnL total, PnL du jour (métriques st.metric)
- **Equity curve** : graphique des PnL cumulés (st.line_chart)
- **Tableau des derniers trades** : 50 derniers trades (pair, side, PnL, durée, raison)
- **Win rate glissant** : calculé sur les 50 derniers trades

**Source de données :** lecture directe de `data/scalping_bot.db` (SQLite, mode read-only).

**Commande :** `streamlit run dashboard/app.py`

## Alertes Telegram (`notifications/telegram_alert.py`)

**Bibliothèque :** `python-telegram-bot>=21.0` (asyncio natif)

**Mode graceful :** Si `TELEGRAM_BOT_TOKEN` ou `TELEGRAM_CHAT_ID` absent de l'environnement, le module log un warning au démarrage et toutes les méthodes d'envoi deviennent des no-ops.

**Messages :**
- `notify_open(pair, side, price, size)` → "📈 LONG BTC/USDT @ 50000 | Size: 0.13"
- `notify_close(pair, side, pnl, pnl_day)` → "📉 Fermé BTC/USDT | PnL: +10.5 USDT | Jour: +25.3 USDT"
- `notify_drawdown_warning(percent)` → "⚠️ Drawdown 10.2% — surveillance"
- `notify_critical_stop(percent)` → "🛑 ARRÊT CRITIQUE — Drawdown 15.1%"
- `notify_daily_report(stats)` → "💓 Rapport quotidien — Trades: 45 | Win: 62% | PnL: +85 USDT"

**Interface :**
```python
class TelegramAlert:
    def __init__(self):
        # Lit TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID depuis os.environ
        # Si absent → self.enabled = False
    
    async def notify_open(self, pair, side, price, size) -> None: ...
    async def notify_close(self, pair, side, pnl, pnl_day) -> None: ...
    async def notify_drawdown_warning(self, percent) -> None: ...
    async def notify_critical_stop(self, percent) -> None: ...
    async def notify_daily_report(self, stats: dict) -> None: ...
```

## Intégration dans main.py

- Instancier `TelegramAlert()` au démarrage
- Appeler `notify_open()` après un fill réussi dans `execution_loop`
- Appeler `notify_close()` après un trade fermé dans `position_monitor_loop`
- Appeler `notify_drawdown_warning()` dans `risk_manager.approve()` quand drawdown > 10%
- Appeler `notify_critical_stop()` quand le bot s'arrête pour drawdown critique

## Configuration

Ajout à `.env.example` :
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

## Dépendances additionnelles

```
streamlit>=1.30
python-telegram-bot>=21.0
```

## Critères de succès

- [ ] Dashboard affiche les trades et stats en temps réel
- [ ] Dashboard fonctionne même si la DB est vide
- [ ] Alertes Telegram envoyées correctement (testable avec un vrai token)
- [ ] Bot fonctionne normalement si Telegram non configuré (no-op graceful)
- [ ] Rapport quotidien envoyé
