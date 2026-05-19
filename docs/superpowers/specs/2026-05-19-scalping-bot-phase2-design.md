# Scalping Bot — Phase 2 : Backtesting Engine

## Vue d'ensemble

Moteur de backtesting qui simule la stratégie de scalping sur données historiques avec frais réels et slippage. Réutilise directement `ScalpingStrategy` et `RiskManager` de la Phase 1 pour garantir la fidélité entre backtest et live.

## Décisions techniques

| Choix | Décision | Raison |
|-------|----------|--------|
| Données | 3 mois OHLCV 1m via ccxt | Suffisant pour valider win rate > 55% |
| Cache | CSV local dans data/historical/ | Evite de re-télécharger à chaque run |
| Stratégie | Réutilisation directe de ScalpingStrategy | Pas de divergence backtest/live |
| Simulation | Synchrone (pas d'asyncio) | Le backtest n'a pas besoin de temps réel |
| Rapport | Terminal + CSV + PNG matplotlib | Stats claires, equity curve visuelle |
| Frais | 0.04% taker (configurable) | Frais réels Binance Futures |
| Slippage | 0.01% (configurable) | Estimation conservatrice pour scalping |

## Structure des fichiers

```
backtest/
├── __init__.py
├── data_loader.py      # Téléchargement + cache OHLCV via ccxt
├── engine.py           # Boucle de simulation principale + CLI
├── simulator.py        # Exécution simulée (fees + slippage + TP/SL intra-bougie)
└── report.py           # Stats, export CSV, graphique PNG
```

## Composants détaillés

### DataLoader (`backtest/data_loader.py`)

**Responsabilité :** Fournir les données historiques OHLCV, avec cache local.

**Comportement :**
- Télécharge via `ccxt.fetch_ohlcv()` avec pagination (limit 1000 par appel)
- Stocke en CSV : `data/historical/{pair_sanitized}_{timeframe}_{days}d.csv`
- Si le cache existe et couvre la période demandée, retourne directement le CSV
- Retourne un `pd.DataFrame` avec colonnes : timestamp, open, high, low, close, volume

**Interface :**
```python
class DataLoader:
    def __init__(self, exchange_id: str = "binance", testnet: bool = False):
        ...
    
    def load(self, pair: str, timeframe: str = "1m", days: int = 90) -> pd.DataFrame:
        """Charge les données (cache ou download). Retourne DataFrame OHLCV."""
        ...
```

### BacktestEngine (`backtest/engine.py`)

**Responsabilité :** Orchestrer la simulation bougie par bougie.

**Comportement :**
1. Charge les données via DataLoader
2. Initialise ScalpingStrategy et RiskManager avec les paramètres config
3. Itère sur chaque bougie :
   - Maintient un buffer de 21 bougies pour les indicateurs
   - Calcule RSI(7), EMA(20), volume ratio (même logique que DataFeed)
   - Construit un MarketData et appelle `strategy.evaluate()`
   - Si signal → passe au RiskManager → SimulatedExecutor
   - Pour chaque position ouverte : vérifie TP/SL/timeout/trailing sur la bougie courante
4. À la fin, génère le rapport

**Interface :**
```python
class BacktestEngine:
    def __init__(self, config: dict):
        ...
    
    def run(self, pair: str, days: int = 90) -> BacktestResult:
        """Execute le backtest complet. Retourne les résultats."""
        ...
```

**BacktestResult (dataclass) :**
- trades: list[dict] (tous les trades simulés)
- equity_curve: list[float]
- stats: dict (win_rate, profit_factor, max_drawdown, sharpe, total_pnl, etc.)

### SimulatedExecutor (`backtest/simulator.py`)

**Responsabilité :** Simuler l'exécution des ordres et la gestion des positions.

**Comportement :**
- `open_position()` : simule le fill avec slippage, enregistre la position
- `check_exit()` : pour une bougie donnée, vérifie si :
  - Le high touche le TP (LONG) ou le low touche le TP (SHORT)
  - Le low touche le SL (LONG) ou le high touche le SL (SHORT)
  - Le timeout est atteint (nb bougies × timeframe)
  - Le trailing stop est activé/touché
- Priorité des exits : SL > TP > TRAILING > TIMEOUT (le SL est vérifié en premier car plus défavorable)
- Applique les frais sur entry et exit

**Interface :**
```python
class SimulatedExecutor:
    def __init__(self, fees_percent: float = 0.04, slippage_percent: float = 0.01):
        ...
    
    def open_position(self, signal: Signal, size: float, stop_loss: float, take_profit: float) -> dict:
        ...
    
    def check_exit(self, position: dict, candle: dict, elapsed_candles: int) -> dict | None:
        """Retourne le trade fermé ou None si pas de sortie."""
        ...
```

### BacktestReport (`backtest/report.py`)

**Responsabilité :** Calculer les métriques et générer les outputs.

**Métriques calculées :**
- Total trades
- Win rate (%)
- Profit factor (gross profit / gross loss)
- Total PnL (USDT et %)
- Max drawdown (%)
- Sharpe ratio (annualisé, basé sur les returns par trade)
- Average trade duration (secondes)
- Best/worst trade

**Outputs :**
- Affichage terminal formaté (tableau de stats)
- Export CSV : `data/backtest_results/{pair}_{timestamp}.csv`
- Graphique PNG : `data/backtest_results/{pair}_{timestamp}_equity.png`
  - Equity curve (ligne bleue)
  - Drawdown zones (fill rouge)

**Interface :**
```python
class BacktestReport:
    def __init__(self, result: BacktestResult, config: dict):
        ...
    
    def print_summary(self) -> None:
        """Affiche les stats dans le terminal."""
        ...
    
    def export_csv(self) -> Path:
        """Exporte les trades en CSV. Retourne le chemin."""
        ...
    
    def plot_equity(self) -> Path:
        """Génère le graphique PNG. Retourne le chemin."""
        ...
```

## Interface CLI

```bash
# Backtest avec config par défaut
python -m backtest.engine

# Paramètres custom
python -m backtest.engine --pair BTC/USDT --days 90 --capital 1000
```

Le script lit `config/config.yaml` pour les paramètres par défaut et accepte des overrides CLI.

## Dépendances additionnelles

```
matplotlib>=3.7
```

(ajouté dans pyproject.toml)

## Vérification intra-bougie (détail important)

Pour chaque bougie, les exits sont vérifiées dans cet ordre :
1. **SL d'abord** : si le low (LONG) ou high (SHORT) touche le SL, exit au prix SL
2. **TP ensuite** : si le high (LONG) ou low (SHORT) touche le TP, exit au prix TP
3. **Trailing** : si le trailing est actif et le prix revient au trailing stop
4. **Timeout** : si le nombre de bougies écoulées × 60s >= timeout_seconds

Cette priorité est conservatrice (assume le pire cas d'abord).

## Critères de succès

- [ ] Backtest BTC/USDT 3 mois en < 30 secondes
- [ ] Résultats reproductibles (même données = même résultat)
- [ ] CSV et PNG générés correctement
- [ ] La stratégie utilisée est exactement ScalpingStrategy (pas de copie)
- [ ] Les frais et slippage sont appliqués correctement
- [ ] Le rapport affiche toutes les métriques requises
