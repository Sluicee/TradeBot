import os
import pandas as pd
from data_provider import DataProvider
from signal_generator import SignalGenerator
import aiohttp
import asyncio
import json

# --- Бэктест стратегии ---
async def run_backtest(symbol: str, interval: str = "15m", period_hours: int = 24, start_balance: float = 100.0):
    candles_per_hour = int(60 / int(interval.replace('m',''))) if 'm' in interval else 1
    limit = period_hours * candles_per_hour

    async with aiohttp.ClientSession() as session:
        provider = DataProvider(session)
        df = await provider.fetch_klines(symbol=symbol, interval=interval, limit=limit)

        if df is None or df.empty:
            print("Нет данных для бэктеста.")
            return

        generator = SignalGenerator(df)
        generator.compute_indicators()
        signals = []
        min_window = 14  # минимальное количество строк для индикаторов

        for i in range(len(df)):
            sub_df = df.iloc[:i+1]
            if len(sub_df) < min_window:
                signals.append({
                    "time": sub_df.index[-1],
                    "price": sub_df["close"].iloc[-1],
                    "signal": "HOLD",
                    "reasons": ["Недостаточно данных для анализа"]
                })
                continue
            gen = SignalGenerator(sub_df)
            gen.compute_indicators()
            res = gen.generate_signal()
            signals.append({
                "time": sub_df.index[-1],
                "price": res["price"],
                "signal": res["signal"],
                "reasons": res["reasons"]
            })

        # --- Бэктест: расчёт баланса за период ---
        balance = start_balance
        position = 0.0
        entry_price = None
        trades = []

        for s in signals:
            price = s["price"]
            sig = s["signal"]
            if sig == "BUY" and position == 0:
                position = balance / price
                entry_price = price
                balance = 0.0
                trades.append(f"BUY {position:.6f} @ {price}")
            elif sig == "SELL" and position > 0:
                balance = position * price
                trades.append(f"SELL {position:.6f} @ {price}")
                position = 0.0
                entry_price = None

        # Если позиция осталась открытой — закрываем по последней цене
        if position > 0:
            balance = position * signals[-1]["price"]

        profit = balance - start_balance
        print(f"Бэктест за {period_hours} часов: итоговый баланс = ${balance:.2f}, доходность = {profit:.2f} USD")
        print("Торговые действия:")
        for t in trades:
            print(t)

        # --- Сохраняем результат ---
        output_dir = "backtests"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"backtest_{symbol}_{interval}.json")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2, default=str)

        print(f"Бэктест завершён. Результаты сохранены в {output_file}")


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
    period_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    start_balance = float(sys.argv[4]) if len(sys.argv) > 4 else 100.0
    asyncio.run(run_backtest(symbol, interval, period_hours, start_balance))
    # Пример запуска: python backtest.py BTCUSDT 15m 24 100