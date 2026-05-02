# MT5 AI Trader (Python)

Sakerhetsfokuserad trading-bot for MetaTrader 5 med OpenAI som signalanalytiker.

## Mal
- MT5 for marknadsdata och orderlaggning.
- OpenAI for signalgenerering (aldrig okontrollerad orderratt).
- Regelbaserad riskmotor i Python som alltid kan blockera signaler.
- Lokal UI med Streamlit for status, signaler, risk och godkannande.

## Version 1 scope
- En symbol at gangen.
- Primart SIGNAL_ONLY och SEMI_AUTO.
- FULL_AUTO finns i UI men med extra varning och tydlig status.
- Fokus: stabil arkitektur, loggning, risk, skyddsracken.

## Filstruktur
- main.py
- config.py
- mt5_client.py
- openai_signal.py
- risk_manager.py
- strategy_features.py
- trade_executor.py
- app_ui.py
- models.py
- logs/
- .env.example
- requirements.txt
- README.md

## Implementation plan (steg for steg)
1. Grundkonfiguration
- Lasa miljovariabler fran `.env`.
- Definiera default: `SIGNAL_ONLY`, `TRADING_ENABLED=false`.
- Etablera typed modeller (signal, risk, settings, beslut).

2. MT5 integration
- Bygg en robust MT5-klient med anslutning/avslut.
- Hamta kontoinfo, spread, candles och oppna positioner.
- Exponera orderfunktion med tydlig request/response-logg.

3. Feature engineering i Python
- Berakna EMA 20/50/200, RSI, ATR, trend, volatilitet.
- Komprimera marknadstillstand till en liten JSON payload.
- Undvik att skicka stora candle-serier till OpenAI.

4. OpenAI signalmodul med schema
- Definiera JSON schema for signalrespons.
- Validera svar med Pydantic.
- Hantera timeout, parse-fel och fallback till WAIT.

5. Riskmotor (regelbaserad)
- Regler: confidence, daily loss cap, max trades/day, max oppna, spread, SL-krav.
- Berakna lot-size utifran risk%, balans och stop-loss.
- Returnera tillat/blockera + blockeringsorsaker.

6. Trade execution workflow
- SIGNAL_ONLY: analysera och logga, inga order.
- SEMI_AUTO: skapa forslag och krava explicit UI-godkannande.
- FULL_AUTO: tillat endast med explicit mode + risk godkand.
- Emergency stop och trading_enabled ska alltid kunna blockera exekvering.

7. Logging och audit trail
- JSONL-loggar for ai_requests, ai_responses, blocked_trades, orders.
- Alla beslut (inkl. blockerade) ska vara synliga i UI.

8. Streamlit UI
- Visa status, senaste signal, konto, positioner, loggar.
- Redigerbara riskinställningar.
- Knappar: Analyze now, Approve trade, Emergency stop.
- Tydlig varning nar FULL_AUTO ar aktivt.

9. Main loop
- Orkestrera cykel: data -> features -> AI -> risk -> exekvering/logg.
- Tidsstyrning via `LOOP_SECONDS` i CLI-lage.
- UI kan kalla samma backend-funktion for ett steg i taget.

## Sakerhet
- Inga hemligheter i kod. Allt via `.env`.
- OpenAI far aldrig direkt orderratt.
- Riskmotor ar sista gate innan order.
- Default startup i SIGNAL_ONLY.

## Marknadstider och auto-paus
- Auto-korning kan pausa analyser nar marknaden ar stangd.
- UI visar aktuell UTC-tid, om marknaden ar oppen/stangd, och nedrakning till nasta open/close.
- Styrs via:
   - `MARKET_HOURS_ENABLED=true|false`
   - `MARKET_OPEN_DAY`, `MARKET_OPEN_TIME_UTC`
   - `MARKET_CLOSE_DAY`, `MARKET_CLOSE_TIME_UTC`

## Kom igang
1. Installera Python 3.11+.
2. Installera MT5 terminal i Windows och logga in pa demo-konto.
3. Kopiera `.env.example` till `.env` och fyll i vardena.
4. Installera dependencies:
   - `pip install -r requirements.txt`
5. Starta UI:
   - `streamlit run app_ui.py`
6. Alternativt kora backend-loop:
   - `python main.py`

## Viktigt om Windows + MT5
MetaTrader5 Python API kraver lokal installerad MT5-terminal (vanligtvis pa Windows). Om du utvecklar pa annan miljö, kor mot Windows-maskinen dar MT5 ar installerat.
