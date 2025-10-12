#!/usr/bin/env python3
"""
Быстрый тест Multi-Timeframe анализа
"""

import asyncio
import aiohttp
from data_provider import DataProvider
from signal_generator import SignalGenerator
from config import STRATEGY_MODE

async def test_mtf():
	"""Тестирует MTF анализ"""
	
	symbol = "BTCUSDT"
	
	print(f"[*] Тестирование MTF анализа для {symbol}")
	print(f"[*] Стратегия: {STRATEGY_MODE}")
	print("="*60)
	
	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session)
		
		# Загружаем данные для основного таймфрейма
		print("\n[1] Загрузка данных...")
		klines = await provider.fetch_klines(symbol=symbol, interval="1h", limit=200)
		df = provider.klines_to_dataframe(klines)
		
		if df.empty:
			print("[!] Нет данных")
			return
		
		print(f"[+] Загружено {len(df)} свечей")
		
		# Single TF анализ
		print("\n[2] Single Timeframe анализ...")
		generator = SignalGenerator(df)
		generator.compute_indicators()
		
		if STRATEGY_MODE == "MEAN_REVERSION":
			single_result = generator.generate_signal_mean_reversion()
		elif STRATEGY_MODE == "HYBRID":
			single_result = generator.generate_signal_hybrid()
		else:
			single_result = generator.generate_signal()
		
		print(f"   Сигнал: {single_result['signal']}")
		print(f"   Цена: ${single_result['price']:.2f}")
		print(f"   RSI: {single_result.get('RSI', 0):.1f}")
		print(f"   ADX: {single_result.get('ADX', 0):.1f}")
		
		# MTF анализ
		print("\n[3] Multi-Timeframe анализ...")
		generator = SignalGenerator(df)
		generator.compute_indicators()
		
		mtf_result = await generator.generate_signal_multi_timeframe(
			data_provider=provider,
			symbol=symbol,
			strategy=STRATEGY_MODE
		)
		
		print(f"   Сигнал: {mtf_result['signal']}")
		print(f"   Согласованность: {mtf_result.get('alignment_strength', 0)*100:.0f}%")
		print(f"   BUY: {mtf_result.get('buy_count', 0)} | SELL: {mtf_result.get('sell_count', 0)} | HOLD: {mtf_result.get('hold_count', 0)}")
		
		# Детали по таймфреймам
		print("\n[4] Детали по таймфреймам:")
		timeframe_signals = mtf_result.get('timeframe_signals', {})
		for tf, tf_data in timeframe_signals.items():
			signal = tf_data.get('signal', 'HOLD')
			marker = "[+]" if signal == "BUY" else "[-]" if signal == "SELL" else "[?]"
			rsi = tf_data.get('RSI', 0)
			adx = tf_data.get('ADX', 0)
			weight = tf_data.get('weight', 0)
			
			print(f"   {marker} {tf:>4}: {signal:>5} (RSI: {rsi:5.1f}, ADX: {adx:5.1f}, вес: {weight:.2f})")
		
		# Причины
		print("\n[5] Причины (первые 5):")
		reasons = mtf_result.get('reasons', [])
		for reason in reasons[:5]:
			# Убираем emoji для совместимости с Windows console
			clean_reason = reason.encode('ascii', 'ignore').decode('ascii')
			if clean_reason.strip():
				print(f"   - {clean_reason}")
		
		print("\n" + "="*60)
		print("[+] Тест завершён успешно!")

if __name__ == "__main__":
	asyncio.run(test_mtf())

