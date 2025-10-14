"""
Тест фильтров Mean Reversion для диагностики
"""
import asyncio
import aiohttp
from data_provider import DataProvider
from signal_generator import SignalGenerator
from config import (
	MR_RSI_OVERSOLD, MR_ZSCORE_BUY_THRESHOLD, MR_ADX_MAX,
	USE_RED_CANDLES_FILTER, VOLUME_SPIKE_THRESHOLD,
	NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT
)

async def main():
	print("="*80)
	print("ДИАГНОСТИКА ФИЛЬТРОВ MEAN REVERSION V5.1")
	print("="*80)
	print(f"\nПараметры фильтров:")
	print(f"  MR_RSI_OVERSOLD: {MR_RSI_OVERSOLD}")
	print(f"  MR_ZSCORE_BUY_THRESHOLD: {MR_ZSCORE_BUY_THRESHOLD}")
	print(f"  MR_ADX_MAX: {MR_ADX_MAX}")
	print(f"  USE_RED_CANDLES_FILTER: {USE_RED_CANDLES_FILTER}")
	print(f"  VOLUME_SPIKE_THRESHOLD: {VOLUME_SPIKE_THRESHOLD}")
	print(f"  NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT: {NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT}")
	print("\n" + "="*80)
	
	# Получаем данные
	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session)
		df = await provider.fetch_klines("BTCUSDT", "1h", limit=1000)
		
		if df is None or df.empty:
			print("Ошибка: не удалось загрузить данные")
			return
		
		print(f"Загружено {len(df)} свечей")
		
		# Проходим по последним 50 свечам и ищем потенциальные сигналы
		buy_signals_found = 0
		blocked_by_filters = 0
		rsi_zscore_match = 0  # Подходящие RSI+Z-score но заблокированные
		
		for i in range(max(200, len(df)-50), len(df)):
			sub_df = df.iloc[:i+1]
			gen = SignalGenerator(sub_df)
			gen.compute_indicators()
			result = gen.generate_signal_mean_reversion()
			
			# Проверяем базовые условия вручную
			rsi = result.get("RSI", 100)
			zscore = result.get("zscore", 0)
			adx = result.get("ADX", 100)
			
			is_rsi_oversold = rsi < MR_RSI_OVERSOLD
			is_zscore_low = zscore < MR_ZSCORE_BUY_THRESHOLD
			is_adx_ok = adx < MR_ADX_MAX
			
			if result["signal"] == "BUY":
				buy_signals_found += 1
				print(f"\n✅ BUY сигнал на свече {i}:")
				print(f"  Цена: ${result['price']:.2f}")
				print(f"  RSI: {rsi:.1f}")
				print(f"  Z-score: {zscore:.2f}")
				print(f"  ADX: {adx:.1f}")
				print(f"  Размер позиции: {result['position_size_percent']*100:.0f}%")
			elif result.get("falling_knife_detected", False):
				blocked_by_filters += 1
				if is_rsi_oversold and is_zscore_low:
					rsi_zscore_match += 1
					if rsi_zscore_match <= 3:  # Показываем первые 3 примера
						print(f"\n⚠️ БЛОКИРОВАН свеча {i} (RSI+Z подходят, но фильтры блокируют):")
						print(f"  Цена: ${result['price']:.2f}")
						print(f"  RSI: {rsi:.1f} (<{MR_RSI_OVERSOLD}) ✓")
						print(f"  Z-score: {zscore:.2f} (<{MR_ZSCORE_BUY_THRESHOLD}) ✓")
						print(f"  ADX: {adx:.1f} {'✓' if is_adx_ok else '✗'}")
						print(f"  Причины блокировки:")
						for reason in result.get("reasons", []):
							if "🚫" in reason:
								print(f"    {reason}")
		
		print("\n" + "="*80)
		print(f"РЕЗУЛЬТАТЫ:")
		print(f"  BUY сигналов: {buy_signals_found}")
		print(f"  Заблокировано фильтрами: {blocked_by_filters}")
		print(f"  Из них RSI+Z-score подходили: {rsi_zscore_match}")
		print(f"  Проверено свечей: 50")
		print("="*80)

if __name__ == "__main__":
	asyncio.run(main())

