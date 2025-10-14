"""
Детальная диагностика HYBRID: почему нет BUY сигналов
"""

import asyncio
import pandas as pd
from datetime import datetime
from data_provider import DataProvider
from signal_generator import SignalGenerator
import config

async def diagnose():
	print("\n" + "="*80)
	print("ДЕТАЛЬНАЯ ДИАГНОСТИКА HYBRID")
	print("="*80)
	
	# Загружаем данные BNB (показал +32% рост)
	import aiohttp
	async with aiohttp.ClientSession() as session:
		provider = DataProvider(session=session)
		df = await provider.fetch_klines(symbol="BNBUSDT", interval="1h", limit=720)
		
		print(f"\nДанные: BNBUSDT, 1h, {len(df)} свечей")
		print(f"Период: {df.index[0]} -> {df.index[-1]}")
		print(f"Цена: ${df['close'].iloc[0]:.2f} -> ${df['close'].iloc[-1]:.2f} ({((df['close'].iloc[-1]/df['close'].iloc[0])-1)*100:+.1f}%)")
		
		# Генерируем индикаторы
		gen = SignalGenerator(df)
		gen.compute_indicators()
		
		print(f"\n{'='*80}")
		print("АНАЛИЗ ПОСЛЕДНИХ 10 СВЕЧЕЙ")
		print(f"{'='*80}")
		
		# Проверяем последние 10 свечей
		buy_votes_history = []
		
		for i in range(len(gen.df) - 10, len(gen.df)):
			sub_df = gen.df.iloc[:i+1].copy()
			temp_gen = SignalGenerator(sub_df)
			temp_gen.df = sub_df
			
			result = temp_gen.generate_signal_hybrid(last_mode="HOLD", last_mode_time=0)
			
			date = gen.df.index[i]
			price = gen.df['close'].iloc[i]
			signal = result['signal']
			bullish = result.get('bullish_votes', 0)
			bearish = result.get('bearish_votes', 0)
			delta = bullish - bearish
			mode = result.get('active_mode', 'N/A')
			regime = result.get('market_regime', 'N/A')
			
			buy_votes_history.append(delta)
			
			print(f"\n{date.strftime('%Y-%m-%d %H:%M')} | ${price:.2f}")
			print(f"  Signal: {signal} | Mode: {mode} | Regime: {regime}")
			print(f"  Votes: {bullish} bull vs {bearish} bear → delta={delta:+d} (need +5 for BUY)")
			
			# Показываем ключевые индикаторы
			if f'ADX_{config.ADX_WINDOW}' in sub_df.columns:
				adx = sub_df[f'ADX_{config.ADX_WINDOW}'].iloc[-1]
				print(f"  ADX: {adx:.1f}")
			
			if f'RSI_{config.RSI_WINDOW}' in sub_df.columns:
				rsi = sub_df[f'RSI_{config.RSI_WINDOW}'].iloc[-1]
				print(f"  RSI: {rsi:.1f}")
			
			# Показываем причины
			reasons = result.get('reasons', [])
			if reasons:
				print(f"  Причины:")
				for reason in reasons[:5]:
					print(f"    - {reason}")
		
		print(f"\n{'='*80}")
		print("СТАТИСТИКА ПО ГОЛОСАМ")
		print(f"{'='*80}")
		
		# Статистика за весь период
		all_votes = []
		buy_signal_count = 0
		max_delta = -999
		max_delta_date = None
		
		for i in range(200, len(gen.df)):
			sub_df = gen.df.iloc[:i+1].copy()
			temp_gen = SignalGenerator(sub_df)
			temp_gen.df = sub_df
			
			result = temp_gen.generate_signal_hybrid(last_mode="HOLD", last_mode_time=0)
			
			if result['signal'] == 'BUY':
				buy_signal_count += 1
			
			bullish = result.get('bullish_votes', 0)
			bearish = result.get('bearish_votes', 0)
			delta = bullish - bearish
			
			all_votes.append(delta)
			
			if delta > max_delta:
				max_delta = delta
				max_delta_date = gen.df.index[i]
		
		print(f"Всего проверено свечей: {len(all_votes)}")
		print(f"BUY сигналов (votes >= 5): {buy_signal_count}")
		print(f"\nСтатистика votes delta:")
		print(f"  Min: {min(all_votes):+d}")
		print(f"  Max: {max_delta:+d} (дата: {max_delta_date})")
		print(f"  Avg: {sum(all_votes)/len(all_votes):+.1f}")
		print(f"  Median: {sorted(all_votes)[len(all_votes)//2]:+d}")
		
		# Распределение
		print(f"\nРаспределение votes delta:")
		ranges = [
			(float('-inf'), -5, "Сильно bearish (<-5)"),
			(-5, -3, "Средне bearish (-5 to -3)"),
			(-3, 0, "Слабо bearish (-3 to 0)"),
			(0, 3, "Слабо bullish (0 to 3)"),
			(3, 5, "Средне bullish (3 to 5)"),
			(5, float('inf'), "Сильно bullish (>=5) 🎯")
		]
		
		for low, high, label in ranges:
			count = len([v for v in all_votes if low <= v < high])
			pct = count / len(all_votes) * 100
			print(f"  {label}: {count} ({pct:.1f}%)")
		
		print(f"\n{'='*80}")
		print("РЕКОМЕНДАЦИИ")
		print(f"{'='*80}")
		
		if max_delta < 5:
			print(f"❌ Максимальный votes delta = {max_delta} < 5")
			print(f"   Порог 5 голосов НИКОГДА не достигается!")
			print(f"\n💡 РЕШЕНИЕ:")
			print(f"   1. Снизить порог с 5 до 3 голосов")
			print(f"   2. Или использовать адаптивный порог:")
			print(f"      - 3 голоса = 30% позиция")
			print(f"      - 4 голоса = 40% позиция")
			print(f"      - 5+ голосов = 50% позиция")
		elif buy_signal_count > 0:
			print(f"✅ Сигналы генерируются ({buy_signal_count} шт)")
			print(f"   Но их может быть недостаточно для прибыльной торговли")
		
		# Проверяем конфликты
		conflicts = len([r for r in all_votes if -2 <= r <= 2])
		conflict_pct = conflicts / len(all_votes) * 100
		
		print(f"\n📊 Конфликтов индикаторов: {conflicts} ({conflict_pct:.1f}%)")
		if conflict_pct > 30:
			print(f"   ⚠️ Слишком много конфликтов! Упростить фильтры")

if __name__ == "__main__":
	asyncio.run(diagnose())

