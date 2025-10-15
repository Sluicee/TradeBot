import asyncio
import pandas as pd
from typing import Dict, Any, Optional
from logger import logger
from config import (
	USE_MULTI_TIMEFRAME, MTF_TIMEFRAMES, MTF_WEIGHTS, MTF_MIN_AGREEMENT, MTF_FULL_ALIGNMENT_BONUS
)

class MultiTimeframeAnalyzer:
	"""
	🔀 MULTI-TIMEFRAME ANALYSIS
	
	Анализирует сигналы на нескольких таймфреймах (15m, 1h, 4h) и
	объединяет их через weighted voting для повышения точности.
	"""
	
	def __init__(self, signal_generator_factory):
		"""
		Инициализация с фабрикой для создания генераторов сигналов
		
		Параметры:
		- signal_generator_factory: функция для создания SignalGenerator
		"""
		self.signal_generator_factory = signal_generator_factory
	
	async def generate_signal_multi_timeframe(
		self,
		data_provider,
		symbol: str,
		strategy: str = "TREND_FOLLOWING"
	) -> Dict[str, Any]:
		"""
		🔀 MULTI-TIMEFRAME ANALYSIS
		
		Анализирует сигналы на нескольких таймфреймах (15m, 1h, 4h) и
		объединяет их через weighted voting для повышения точности.
		
		Параметры:
		- data_provider: объект DataProvider для загрузки данных
		- symbol: торговая пара (например, "BTCUSDT")
		- strategy: "TREND_FOLLOWING", "MEAN_REVERSION", или "HYBRID"
		
		Возвращает:
		- Объединённый сигнал с информацией по каждому таймфрейму
		"""
		if not USE_MULTI_TIMEFRAME:
			# Fallback: используем текущий DataFrame если MTF отключен
			sg = self.signal_generator_factory()
			if strategy == "MEAN_REVERSION":
				return sg.generate_signal_mean_reversion()
			elif strategy == "HYBRID":
				return sg.generate_signal_hybrid()
			else:
				return sg.generate_signal()
		
		reasons = []
		timeframe_signals = {}
		
		# ====================================================================
		# 1. ЗАГРУЗКА ДАННЫХ ДЛЯ КАЖДОГО ТАЙМФРЕЙМА
		# ====================================================================
		
		async def fetch_all_timeframes():
			"""Параллельная загрузка всех таймфреймов"""
			tasks = []
			for tf in MTF_TIMEFRAMES:
				tasks.append(data_provider.fetch_klines(symbol, tf, limit=200))
			return await asyncio.gather(*tasks, return_exceptions=True)
		
		# Запускаем загрузку
		logger.info(f"MTF: загрузка данных для {symbol} на таймфреймах {MTF_TIMEFRAMES}")
		try:
			# Если уже в async контексте, используем gather, иначе создаём event loop
			try:
				loop = asyncio.get_running_loop()
				# Мы уже в async контексте - просто await
				tf_data = await fetch_all_timeframes()
				logger.info(f"MTF: данные загружены, получено {len(tf_data)} результатов")
			except RuntimeError:
				# Нет running loop - создаём новый
				tf_data = asyncio.run(fetch_all_timeframes())
				logger.info(f"MTF: данные загружены (new loop), получено {len(tf_data)} результатов")
		except Exception as e:
			logger.error(f"Ошибка загрузки MTF данных: {e}", exc_info=True)
			# Fallback на single TF
			sg = self.signal_generator_factory()
			if strategy == "MEAN_REVERSION":
				return sg.generate_signal_mean_reversion()
			elif strategy == "HYBRID":
				return sg.generate_signal_hybrid()
			else:
				return sg.generate_signal()
		
		# ====================================================================
		# 2. ГЕНЕРАЦИЯ СИГНАЛОВ ДЛЯ КАЖДОГО ТАЙМФРЕЙМА
		# ====================================================================
		
		for i, tf in enumerate(MTF_TIMEFRAMES):
			logger.debug(f"MTF: обработка {tf} (index={i})")
			if isinstance(tf_data[i], Exception):
				logger.warning(f"MTF: ошибка данных для {tf}: {tf_data[i]}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": str(tf_data[i])
				}
				continue
			
			df = tf_data[i]
			logger.debug(f"MTF: DataFrame для {tf}: {len(df) if not df.empty else 0} строк")
			if df.empty:
				logger.warning(f"MTF: пустой DataFrame для {tf}")
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": "Empty dataframe"
				}
				continue
			
			# Создаём отдельный генератор для этого таймфрейма
			try:
				sg = self.signal_generator_factory(df)
				sg.compute_indicators()
				
				# Генерируем сигнал в зависимости от стратегии
				if strategy == "MEAN_REVERSION":
					signal_result = sg.generate_signal_mean_reversion()
				elif strategy == "HYBRID":
					signal_result = sg.generate_signal_hybrid()
				else:
					signal_result = sg.generate_signal()
				
				# Сохраняем результат
				signal = signal_result.get("signal", "HOLD")
				price = signal_result.get("price", 0)
				rsi = signal_result.get("RSI", 0)
				adx = signal_result.get("ADX", 0)
				
				logger.info(f"MTF: {tf} → {signal} (цена={price:.2f}, RSI={rsi:.1f}, ADX={adx:.1f})")
				
				timeframe_signals[tf] = {
					"signal": signal,
					"price": price,
					"RSI": rsi,
					"ADX": adx,
					"MACD_hist": signal_result.get("MACD_hist", 0),
					"market_regime": signal_result.get("market_regime", "NEUTRAL"),
					"bullish_votes": signal_result.get("bullish_votes", 0),
					"bearish_votes": signal_result.get("bearish_votes", 0),
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": signal_result.get("confidence", 0)
				}
				
			except Exception as e:
				logger.error(f"Ошибка генерации сигнала для {tf}: {e}", exc_info=True)
				timeframe_signals[tf] = {
					"signal": "HOLD",
					"price": 0,
					"RSI": 0,
					"ADX": 0,
					"MACD_hist": 0,
					"market_regime": "NEUTRAL",
					"bullish_votes": 0,
					"bearish_votes": 0,
					"weight": MTF_WEIGHTS.get(tf, 0),
					"confidence": 0,
					"error": str(e)
				}
		
		# ====================================================================
		# 3. WEIGHTED VOTING
		# ====================================================================
		
		buy_score = 0.0
		sell_score = 0.0
		hold_score = 0.0
		
		buy_count = 0
		sell_count = 0
		hold_count = 0
		
		for tf, sig_data in timeframe_signals.items():
			signal = sig_data.get("signal", "HOLD")
			weight = sig_data.get("weight", 0)
			confidence = sig_data.get("confidence", 0.5)
			
			# Взвешиваем по весу таймфрейма и уверенности сигнала
			weighted_score = weight * (1 + confidence)
			
			if signal == "BUY":
				buy_score += weighted_score
				buy_count += 1
				reasons.append(f"📊 {tf}: BUY (вес={weight:.2f}, conf={confidence:.2f})")
			elif signal == "SELL":
				sell_score += weighted_score
				sell_count += 1
				reasons.append(f"📊 {tf}: SELL (вес={weight:.2f}, conf={confidence:.2f})")
			else:
				hold_score += weighted_score
				hold_count += 1
				reasons.append(f"📊 {tf}: HOLD (вес={weight:.2f})")
		
		# ====================================================================
		# 4. ПРОВЕРКА СОГЛАСОВАННОСТИ (ALIGNMENT)
		# ====================================================================
		
		total_tf = len(MTF_TIMEFRAMES)
		alignment_strength = 0
		final_signal = "HOLD"
		signal_emoji = "⚠️"
		
		# Проверяем полное согласие (все 3 TF показывают одинаково)
		if buy_count == total_tf:
			alignment_strength = 1.0
			final_signal = "BUY"
			signal_emoji = "🟢🔥"
			buy_score *= MTF_FULL_ALIGNMENT_BONUS
			reasons.append(f"✅ ПОЛНОЕ СОГЛАСИЕ: все {total_tf} таймфрейма показывают BUY! (бонус {MTF_FULL_ALIGNMENT_BONUS}x)")
		elif sell_count == total_tf:
			alignment_strength = 1.0
			final_signal = "SELL"
			signal_emoji = "🔴🔥"
			sell_score *= MTF_FULL_ALIGNMENT_BONUS
			reasons.append(f"✅ ПОЛНОЕ СОГЛАСИЕ: все {total_tf} таймфрейма показывают SELL! (бонус {MTF_FULL_ALIGNMENT_BONUS}x)")
		
		# Проверяем частичное согласие (минимум MTF_MIN_AGREEMENT)
		elif buy_count >= MTF_MIN_AGREEMENT and buy_score > sell_score:
			alignment_strength = buy_count / total_tf
			final_signal = "BUY"
			signal_emoji = "🟢"
			reasons.append(f"✓ Частичное согласие: {buy_count}/{total_tf} таймфреймов показывают BUY")
		elif sell_count >= MTF_MIN_AGREEMENT and sell_score > buy_score:
			alignment_strength = sell_count / total_tf
			final_signal = "SELL"
			signal_emoji = "🔴"
			reasons.append(f"✓ Частичное согласие: {sell_count}/{total_tf} таймфреймов показывают SELL")
		
		# Конфликт таймфреймов - остаёмся в HOLD
		else:
			final_signal = "HOLD"
			signal_emoji = "⚠️"
			reasons.append(f"⚠️ КОНФЛИКТ ТАЙМФРЕЙМОВ: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
			reasons.append(f"   Weighted scores: BUY={buy_score:.2f}, SELL={sell_score:.2f}, HOLD={hold_score:.2f}")
		
		# ====================================================================
		# 5. ФИНАЛЬНЫЙ РЕЗУЛЬТАТ
		# ====================================================================
		
		# Берём данные из основного таймфрейма (обычно 1h)
		main_tf = '1h' if '1h' in timeframe_signals else MTF_TIMEFRAMES[0]
		main_data = timeframe_signals.get(main_tf, {})
		
		# Расчёт итоговой силы сигнала (для адаптивного размера позиции)
		signal_strength = 0
		if final_signal == "BUY":
			signal_strength = int(buy_score * 3)  # Нормализуем к scale ~3-15
		elif final_signal == "SELL":
			signal_strength = int(sell_score * 3)
		
		result = {
			"signal": final_signal,
			"signal_emoji": signal_emoji,
			"price": main_data.get("price", 0),
			"strategy": f"{strategy}_MTF",
			
			# Multi-timeframe данные
			"mtf_enabled": True,
			"timeframe_signals": timeframe_signals,
			"alignment_strength": alignment_strength,
			"buy_score": buy_score,
			"sell_score": sell_score,
			"hold_score": hold_score,
			"buy_count": buy_count,
			"sell_count": sell_count,
			"hold_count": hold_count,
			
			# Данные из основного таймфрейма
			"RSI": main_data.get("RSI", 0),
			"ADX": main_data.get("ADX", 0),
			"MACD_hist": main_data.get("MACD_hist", 0),
			"market_regime": main_data.get("market_regime", "NEUTRAL"),
			
			# Голоса (для совместимости)
			"bullish_votes": signal_strength if final_signal == "BUY" else 0,
			"bearish_votes": signal_strength if final_signal == "SELL" else 0,
			
			# Причины
			"reasons": reasons
		}
		
		return result
