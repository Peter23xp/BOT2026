# Scalping Bot — Phase 1 : Core Trading Engine

## Vue d'ensemble

Bot de scalping automatique pour Binance Futures (testnet), architecture event-driven en pipeline asyncio. Phase 1 couvre le moteur de trading complet : data feed, strategy, risk management, order execution, et PnL tracking.

## Décisions techniques

| Choix | Décision | Raison |
|-------|----------|--------|
| Exchange | Binance Futures Testnet | API la plus documentée, ccxt excellent support |
| Data feed | ccxt.pro (WebSocket) | Reconnexion intégrée, portabilité multi-exchange |
| Architecture | Pipeline asyncio.Queue | Flux explicite, composants testables en isolation |
| Mode dev | Dry-run local + Testnet | Dev rapide sans connexion, validation sur testnet |
| Tests | Critiques uniquement | strategy, risk_manager, pnl_tracker |
| DB | SQLite (aiosqlite) | Simple, pas de serveur, suffisant pour Phase 1 |
| Scope | Phases incrémentales | Phase 1 = core, Phase 2 = backtest, Phase 3 = dashboard+alertes |

## Structure des fichiers

```
scalping-bot/
├── config/
│   ├── config.yaml          # Paires, timeframe, capital, risque
│   └── secrets.env          # API keys (gitignored)
├── core/
│   ├── __init__.py
│   ├── data_feed.py         # WebSocket ccxt.pro (OHLCV + order book)
│   ├── strategy.py          # Logique de signal multi-confirmation
│   ├── risk_manager.py      # Taille position, stop-loss, drawdown
│   ├── order_executor.py    # Placement ordres (live + dry-run)
│   └── pnl_tracker.py      # Calcul PnL, enregistrement DB
├── db/
│   ├── __init__.py
│   └── models.py            # SQLite tables (trades, signals, bot_stats)
├── models/
│   ├── __init__.py
│   └── events.py            # Dataclasses pour événements inter-composants
├── tests/
│   ├── test_strategy.py
│   ├── test_risk_manager.py
│   └── test_pnl_tracker.py
├── main.py                  # Point d'entrée, orchestration coroutines
├── pyproject.toml           # Dépendances
├── .env.example             # Template API keys
└── .gitignore
```

## Modèle d'événements

Dataclasses typées passées via `asyncio.Queue` entre composants :

### MarketData
- `timestamp: float`
- `pair: str`
- `ohlcv: list[float]` (open, high, low, close, volume)
- `bid: float`
- `ask: float`
- `volume: float`

### Signal
- `timestamp: float`
- `pair: str`
- `side: Literal["LONG", "SHORT"]`
- `rsi: float`
- `ema_distance: float`
- `volume_ratio: float`
- `spread: float`

### OrderRequest
- `signal: Signal`
- `size: float`
- `entry_price: float`
- `stop_loss: float`
- `take_profit: float`

### OrderResult
- `order_id: str`
- `pair: str`
- `side: Literal["LONG", "SHORT"]`
- `fill_price: float`
- `size: float`
- `status: Literal["filled", "partial", "failed"]`
- `timestamp: float`

### TradeClose
- `order_id: str`
- `exit_price: float`
- `pnl_usdt: float`
- `pnl_percent: float`
- `duration_s: float`
- `reason: Literal["TP", "SL", "TIMEOUT", "TRAILING"]`

## Composants détaillés

### DataFeed (`core/data_feed.py`)

**Responsabilité :** Fournir un flux continu de données de marché enrichies.

**Comportement :**
- Mode live : écoute `watchOHLCV` + `watchOrderBook` via ccxt.pro
- Mode dry-run : lit un fichier CSV de données historiques et les rejoue avec timing simulé
- Calcule en streaming : RSI(7), EMA(20), ratio de volume (current / mean(20))
- Émet des `MarketData` enrichis dans la queue sortante
- Reconnexion automatique avec backoff exponentiel (géré par ccxt.pro)

**Interface :**
```python
async def run(output_queue: asyncio.Queue[MarketData], mode: str = "live") -> None
```

### Strategy (`core/strategy.py`)

**Responsabilité :** Évaluer les conditions d'entrée/sortie et émettre des signaux.

**Conditions d'entrée LONG (toutes simultanées) :**
1. RSI(7) < 35 ET RSI remonte (RSI[0] > RSI[1])
2. Prix > EMA(20)
3. Volume actuel > 1.5× moyenne(20 bougies)
4. Spread bid/ask < 0.05%
5. Pas de position ouverte sur cette paire

**Conditions d'entrée SHORT :** symétriques inverses (RSI > 65 ET descend, prix < EMA, etc.)

**Conditions de sortie :**
- Take profit : +0.3%
- Stop loss : -0.15%
- Timeout : 5 minutes sans TP/SL touché
- Trailing stop : activé si profit > +0.2%, suit le prix à -0.15%

**Interface :**
```python
async def run(input_queue: asyncio.Queue[MarketData], output_queue: asyncio.Queue[Signal]) -> None
```

### RiskManager (`core/risk_manager.py`)

**Responsabilité :** Valider les signaux et calculer la taille de position.

**Règles (non négociables) :**
- Risque max par trade : 1% du capital
- Drawdown journalier max : 5% → arrêt du bot
- Drawdown total max : 15% → arrêt + alerte critique
- Levier max : 5x
- Max 3 positions ouvertes simultanément
- Calcul taille : `(capital × risk%) / (entry_price × stop_loss%)`

**Interface :**
```python
async def run(input_queue: asyncio.Queue[Signal], output_queue: asyncio.Queue[OrderRequest]) -> None
def approve(signal: Signal) -> tuple[bool, str]  # (approved, reason)
def calculate_size(entry_price: float) -> float
```

### OrderExecutor (`core/order_executor.py`)

**Responsabilité :** Placer et suivre les ordres sur l'exchange.

**Comportement :**
- Mode live : place via ccxt (`create_order`)
- Mode dry-run : simule le fill au prix demandé (+ slippage configurable 0.01%)
- Retry 3× avec backoff exponentiel (1s, 2s, 4s) sur erreurs exchange
- Gère les ordres conditionnels (SL/TP) ou monitore les prix pour déclencher la sortie
- Log chaque tentative et résultat

**Interface :**
```python
async def run(input_queue: asyncio.Queue[OrderRequest], output_queue: asyncio.Queue[OrderResult]) -> None
async def close_position(order_id: str, reason: str) -> TradeClose
async def close_all_positions() -> list[TradeClose]
```

### PnLTracker (`core/pnl_tracker.py`)

**Responsabilité :** Calculer et persister les statistiques de performance.

**Métriques calculées :**
- PnL par trade (USDT et %)
- PnL cumulé (jour et total)
- Win rate
- Profit factor
- Max drawdown
- Sharpe ratio (annualisé)

**Interface :**
```python
async def run(input_queue: asyncio.Queue[OrderResult | TradeClose]) -> None
def get_daily_stats() -> dict
def get_total_stats() -> dict
```

### PositionMonitor (intégré dans `order_executor.py`)

**Responsabilité :** Surveiller les positions ouvertes pour déclencher TP/SL/timeout/trailing.

**Comportement :**
- Coroutine séparée qui vérifie les positions ouvertes toutes les 100ms
- Compare le prix actuel (reçu du DataFeed) aux seuils TP/SL
- Active le trailing stop si le profit dépasse le seuil d'activation
- Déclenche la fermeture après 5 min de timeout
- Émet `TradeClose` vers PnLTracker

## Base de données (SQLite)

### Table `trades`
| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Auto-increment |
| pair | TEXT | Ex: "BTC/USDT" |
| side | TEXT | "LONG" ou "SHORT" |
| entry_price | REAL | Prix d'entrée |
| exit_price | REAL | Prix de sortie (NULL si ouvert) |
| size | REAL | Taille en unités |
| pnl_usdt | REAL | Profit/perte en USDT |
| pnl_percent | REAL | Profit/perte en % |
| duration_s | REAL | Durée du trade en secondes |
| reason | TEXT | TP, SL, TIMEOUT, TRAILING |
| timestamp_open | TEXT | ISO 8601 |
| timestamp_close | TEXT | ISO 8601 (NULL si ouvert) |

### Table `signals`
| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Auto-increment |
| pair | TEXT | Paire concernée |
| timestamp | TEXT | ISO 8601 |
| side | TEXT | LONG ou SHORT |
| rsi | REAL | Valeur RSI au moment du signal |
| ema_distance | REAL | Distance au EMA en % |
| volume_ratio | REAL | Ratio volume/moyenne |
| spread | REAL | Spread bid/ask en % |
| triggered | INTEGER | 1 si le signal a mené à un trade |

### Table `bot_stats`
| Colonne | Type | Description |
|---------|------|-------------|
| date | TEXT PK | YYYY-MM-DD |
| total_trades | INTEGER | Nombre de trades du jour |
| wins | INTEGER | Trades gagnants |
| losses | INTEGER | Trades perdants |
| win_rate | REAL | wins / total_trades |
| total_pnl | REAL | PnL du jour en USDT |
| max_drawdown | REAL | Drawdown max du jour en % |
| sharpe_ratio | REAL | Sharpe du jour |

## Flux d'exécution principal

```python
async def main():
    config = load_config("config/config.yaml")
    db = await init_database()
    
    market_queue = asyncio.Queue(maxsize=100)
    signal_queue = asyncio.Queue(maxsize=50)
    order_queue = asyncio.Queue(maxsize=20)
    result_queue = asyncio.Queue(maxsize=50)
    
    mode = "dry_run" if config.get("dry_run") else "live"
    
    tasks = [
        asyncio.create_task(data_feed.run(market_queue, mode=mode)),
        asyncio.create_task(strategy.run(market_queue, signal_queue)),
        asyncio.create_task(risk_manager.run(signal_queue, order_queue)),
        asyncio.create_task(order_executor.run(order_queue, result_queue)),
        asyncio.create_task(pnl_tracker.run(result_queue)),
    ]
    
    # Gestion graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown(tasks))
    
    await asyncio.gather(*tasks)
```

## Shutdown propre

Sur SIGINT/SIGTERM :
1. Signal d'arrêt au DataFeed (stop les WebSocket)
2. Drain des queues (traiter les messages en cours)
3. Fermer toutes les positions ouvertes au marché
4. Flush final dans la DB
5. Log résumé de session (trades, PnL, durée)
6. Exit code 0

## Configuration

```yaml
# config/config.yaml
exchange: binance
testnet: true
dry_run: false
pairs:
  - BTC/USDT
  - ETH/USDT
timeframe: 1m
capital_usdt: 1000
risk_per_trade_percent: 1.0
max_drawdown_percent: 15.0
daily_drawdown_limit: 5.0
leverage: 5
max_open_positions: 3
take_profit_percent: 0.3
stop_loss_percent: 0.15
trailing_stop: true
trailing_activation_percent: 0.2
timeout_seconds: 300
slippage_percent: 0.01
fees_percent: 0.04
```

## Dépendances (pyproject.toml)

```
ccxt >= 4.0
pandas >= 2.0
pandas-ta >= 0.3
aiosqlite >= 0.19
pyyaml >= 6.0
python-dotenv >= 1.0
loguru >= 0.7
```

Dev :
```
pytest >= 7.0
pytest-asyncio >= 0.21
```

## Tests Phase 1

### test_strategy.py
- Signal LONG émis quand toutes les 5 conditions sont vraies
- Pas de signal si une condition manque (tester chaque condition individuellement)
- Signal SHORT avec conditions symétriques
- Pas de signal si position déjà ouverte sur la paire

### test_risk_manager.py
- Calcul correct de la taille de position
- Refus si drawdown journalier dépassé
- Refus si drawdown total dépassé
- Refus si max positions atteint
- Approbation dans des conditions normales

### test_pnl_tracker.py
- Calcul PnL correct (long et short)
- Win rate correct
- Drawdown calculé correctement
- Stats journalières agrégées

## Critères de succès Phase 1

- [ ] Le bot tourne 1h en mode dry-run sans crash
- [ ] Les signaux sont correctement générés selon les conditions
- [ ] Le risk manager bloque les trades quand les limites sont atteintes
- [ ] Les ordres sont exécutés (dry-run simule, testnet place réellement)
- [ ] Le PnL est correctement calculé et persisté en DB
- [ ] Shutdown propre ferme les positions et flush la DB
- [ ] Tests unitaires passent (strategy, risk_manager, pnl_tracker)

## Phases futures (hors scope Phase 1)

- **Phase 2 :** Backtesting engine (download historique, simulation fidèle, rapport)
- **Phase 3 :** Dashboard Streamlit + alertes Telegram + rapport quotidien
