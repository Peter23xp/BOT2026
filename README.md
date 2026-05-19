# Scalping Bot — Phase 1

Bot de scalping automatique pour Binance Futures (testnet).

## Installation

```bash
pip install -e ".[dev]"
cp .env.example config/secrets.env
# Editer config/secrets.env avec vos API keys Binance Futures Testnet
```

## Utilisation

```bash
# Mode dry-run (simulation locale, pas de connexion exchange)
python main.py

# Mode testnet (editer config/config.yaml: dry_run: false)
python main.py
```

## Tests

```bash
pytest tests/ -v
```

## Configuration

Editer `config/config.yaml` pour ajuster :
- Paires de trading
- Capital et risque par trade
- Take profit / Stop loss
- Levier et nombre max de positions

## Architecture

Pipeline asyncio event-driven :

```
DataFeed → [Queue] → Strategy → [Queue] → RiskManager → [Queue] → OrderExecutor → PnLTracker → DB
```

## Strategie

Signal LONG quand toutes les conditions sont vraies :
1. RSI(7) < 35 et remonte
2. Prix > EMA(20)
3. Volume > 1.5x moyenne
4. Spread < 0.05%
5. Pas de position ouverte sur la paire

Signal SHORT : conditions symetriques inverses.

## Gestion du risque

- 1% du capital par trade
- Drawdown journalier max : 5% (arret automatique)
- Drawdown total max : 15% (arret critique)
- Max 3 positions simultanees
- Levier max : 5x
