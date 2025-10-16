import pandas as pd
import numpy as np
import ta
from typing import Dict, Any, Optional
from logger import logger
from config import (
	# Mean Reversion
	MR_RSI_OVERSOLD, MR_RSI_EXIT, MR_ZSCORE_BUY_THRESHOLD, MR_ZSCORE_SELL_THRESHOLD,
	MR_ZSCORE_STRONG_BUY, MR_ADX_MAX, MR_EMA_DIVERGENCE_MAX, MR_ZSCORE_WINDOW,
	MR_POSITION_SIZE_STRONG, MR_POSITION_SIZE_MEDIUM, MR_POSITION_SIZE_WEAK,
	# Фильтры "падающего ножа" v5
	NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT, NO_BUY_IF_EMA200_SLOPE_NEG, EMA200_NEG_SLOPE_THRESHOLD,
	USE_RED_CANDLES_FILTER, USE_VOLUME_FILTER, VOLUME_SPIKE_THRESHOLD,
	# Динамический SL/TP v5
	USE_DYNAMIC_SL_FOR_MR, MR_ATR_SL_MULTIPLIER, MR_ATR_SL_MIN, MR_ATR_SL_MAX,
	ADAPTIVE_SL_ON_RISK, ADAPTIVE_SL_MULTIPLIER,
	USE_DYNAMIC_TP_FOR_MR, MR_ATR_TP_MULTIPLIER, MR_ATR_TP_MIN, MR_ATR_TP_MAX,
	# Гибридная стратегия
	STRATEGY_HYBRID_MODE, HYBRID_ADX_MR_THRESHOLD, HYBRID_ADX_TF_THRESHOLD,
	HYBRID_TRANSITION_MODE, HYBRID_MIN_TIME_IN_MODE,
	# Индикаторы
	STOCH_OVERSOLD, STOCH_OVERBOUGHT, ADX_WINDOW, ATR_WINDOW
)

class MeanReversionStrategy:
	"""
	🔄 MEAN REVERSION STRATEGY
	
	Логика: покупка на сильной перепроданности, быстрый выход на возврате к среднему.
	Цель: короткие сделки 1-4% в боковом/падающем рынке.
	"""
	
	def __init__(self, df: pd.DataFrame):
		self.df = df.copy()
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)
	
	def generate_signal(self) -> Dict[str, Any]:
		"""
		🔄 MEAN REVERSION STRATEGY
		
		Логика: покупка на сильной перепроданности, быстрый выход на возврате к среднему.
		Цель: короткие сделки 1-4% в боковом/падающем рынке.
		"""
		if self.df.empty:
			raise ValueError("DataFrame is empty")
		
		last = self.df.iloc[-1]
		price = float(last["close"])
		
		# Индикаторы
		ema_12 = float(last.get("EMA_12", 0))
		ema_26 = float(last.get("EMA_26", 0))
		rsi = float(last.get("RSI", 50))
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		atr = float(last.get(f"ATR_{ATR_WINDOW}", 0))
		stoch_k = float(last.get("Stoch_K", 0))
		
		# ====================================================================
		# РАСЧЁТ Z-SCORE
		# ====================================================================
		
		if len(self.df) >= MR_ZSCORE_WINDOW:
			close_prices = self.df["close"].iloc[-MR_ZSCORE_WINDOW:].astype(float)
			sma = close_prices.mean()
			std = close_prices.std()
			zscore = (price - sma) / std if std > 0 else 0
		else:
			zscore = 0
		
		# ====================================================================
		# ПРОВЕРКА РЕЖИМА РЫНКА
		# ====================================================================
		
		# 1. ADX - не должен быть высоким (исключаем трендовый рынок)
		is_not_trending = adx < MR_ADX_MAX
		
		# 2. EMA дивергенция - EMA12 и EMA26 должны быть близки (флэт)
		if ema_12 > 0 and ema_26 > 0:
			ema_divergence = abs(ema_12 - ema_26) / ema_26
			is_sideways = ema_divergence < MR_EMA_DIVERGENCE_MAX
		else:
			is_sideways = False
		
		# ====================================================================
		# ФИЛЬТРЫ "ПАДАЮЩЕГО НОЖА" (КРИТИЧНО!)
		# ====================================================================
		
		reasons = []  # Инициализируем список причин
		falling_knife_detected = False
		
		# 1. Проверка: цена ниже минимума последних 24 часов на X%
		if len(self.df) >= 24:
			low_24h = self.df["low"].iloc[-24:].min()
			price_vs_24h_low = (price - low_24h) / low_24h if low_24h > 0 else 0
			
			if price_vs_24h_low < -NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT:
				falling_knife_detected = True
				reasons.append(f"🚫 ПАДАЮЩИЙ НОЖ: цена ${price:.2f} ниже min(24h)=${low_24h:.2f} на {abs(price_vs_24h_low)*100:.1f}% (>{NO_BUY_IF_PRICE_BELOW_N_DAY_LOW_PERCENT*100}%)")
		
		# 2. Проверка: отрицательный наклон EMA200
		if NO_BUY_IF_EMA200_SLOPE_NEG and len(self.df) >= 200 + 24:
			ema_200 = float(last.get("EMA_200", 0))
			if ema_200 > 0:
				# Берём EMA200 24 свечи назад
				ema_200_24h_ago = float(self.df["EMA_200"].iloc[-24])
				if ema_200_24h_ago > 0:
					ema200_slope = (ema_200 - ema_200_24h_ago) / ema_200_24h_ago
					
					if ema200_slope < EMA200_NEG_SLOPE_THRESHOLD:
						falling_knife_detected = True
						reasons.append(f"🚫 EMA200 ПАДАЕТ: slope={ema200_slope*100:.2f}% за 24h (< {EMA200_NEG_SLOPE_THRESHOLD*100:.1f}%)")
		
		# 3. Проверка: последовательность красных свечей (v5: ВКЛЮЧЕН ОБРАТНО)
		if USE_RED_CANDLES_FILTER and len(self.df) >= 5:
			# Берём последние 5 свечей
			recent_candles = self.df.tail(5)
			red_candles = 0
			total_drop = 0.0
			
			for idx in range(len(recent_candles)):
				candle = recent_candles.iloc[idx]
				open_price = float(candle["open"])
				close_price = float(candle["close"])
				candle_change = (close_price - open_price) / open_price if open_price > 0 else 0
				
				if candle_change < 0:  # Красная свеча
					red_candles += 1
					total_drop += abs(candle_change)
			
			# Если 4+ красных свечей подряд и общее падение > 3%
			if red_candles >= 4 and total_drop > 0.03:
				falling_knife_detected = True
				reasons.append(f"🚫 СЕРИЯ КРАСНЫХ СВЕЧЕЙ: {red_candles}/5 свечей, падение {total_drop*100:.1f}% (>3%)")
			
			# Или если последние 3 свечи все красные и падение > 2%
			last_3_candles = self.df.tail(3)
			last_3_red = 0
			last_3_drop = 0.0
			for idx in range(len(last_3_candles)):
				candle = last_3_candles.iloc[idx]
				open_price = float(candle["open"])
				close_price = float(candle["close"])
				candle_change = (close_price - open_price) / open_price if open_price > 0 else 0
				if candle_change < 0:
					last_3_red += 1
					last_3_drop += abs(candle_change)
			
			if last_3_red == 3 and last_3_drop > 0.02:
				falling_knife_detected = True
				reasons.append(f"🚫 3 КРАСНЫЕ СВЕЧИ ПОДРЯД: падение {last_3_drop*100:.1f}% (>2%)")
		
		# 4. v5: Проверка всплеска объёма (НОВОЕ)
		if USE_VOLUME_FILTER and "volume" in self.df.columns and len(self.df) >= 24:
			current_volume = float(self.df["volume"].iloc[-1])
			avg_volume_24h = float(self.df["volume"].iloc[-24:].mean())
			
			if avg_volume_24h > 0:
				volume_ratio = current_volume / avg_volume_24h
				if volume_ratio > VOLUME_SPIKE_THRESHOLD:
					falling_knife_detected = True
					reasons.append(f"🚫 ВСПЛЕСК ОБЪЁМА: {volume_ratio:.2f}x средний за 24h (> {VOLUME_SPIKE_THRESHOLD}x)")
		
		# ====================================================================
		# ЛОГИКА СИГНАЛОВ
		# ====================================================================
		
		signal = "HOLD"
		signal_emoji = "⚠️"
		position_size_percent = 0
		confidence = 0
		dynamic_sl = None  # Динамический SL на основе ATR
		dynamic_tp = None  # Динамический TP на основе ATR (v4)
		
		# --- УСЛОВИЯ ПОКУПКИ ---
		is_rsi_oversold = rsi < MR_RSI_OVERSOLD
		is_zscore_low = zscore < MR_ZSCORE_BUY_THRESHOLD
		is_strong_oversold = rsi < 20 and zscore < MR_ZSCORE_STRONG_BUY
		
		# v5: БЛОКИРУЕМ ВХОД ПРИ FALLING KNIFE (если адаптивный SL отключен)
		if is_rsi_oversold and is_zscore_low and not falling_knife_detected:
			# Вход разрешён - нет падающего ножа
			# Дополнительная фильтрация: желательно боковик или слабый тренд
			if is_not_trending or is_sideways:
				signal = "BUY"
				signal_emoji = "🟢"
				
				# Адаптивный размер позиции
				if is_strong_oversold:
					position_size_percent = MR_POSITION_SIZE_STRONG
					reasons.append(f"✅ STRONG BUY: RSI={rsi:.1f} (<20), Z-score={zscore:.2f} (<-2.5) → позиция 70%")
				elif rsi < 25 and zscore < -2.0:
					position_size_percent = MR_POSITION_SIZE_MEDIUM
					reasons.append(f"✅ MEDIUM BUY: RSI={rsi:.1f} (<25), Z-score={zscore:.2f} (<-2.0) → позиция 50%")
				else:
					position_size_percent = MR_POSITION_SIZE_WEAK
					reasons.append(f"✅ WEAK BUY: RSI={rsi:.1f}, Z-score={zscore:.2f} → позиция 30%")
				
				confidence = min(1.0, (abs(zscore) / abs(MR_ZSCORE_BUY_THRESHOLD)) * 0.5 + ((MR_RSI_OVERSOLD - rsi) / MR_RSI_OVERSOLD) * 0.5)
				
				reasons.append(f"📊 RSI={rsi:.1f} < {MR_RSI_OVERSOLD} (перепродан)")
				reasons.append(f"📉 Z-score={zscore:.2f} < {MR_ZSCORE_BUY_THRESHOLD} (сильно ниже среднего)")
				reasons.append(f"🎯 ADX={adx:.1f} {'<' if is_not_trending else '≥'} {MR_ADX_MAX} ({'нет сильного тренда' if is_not_trending else 'тренд есть!'})")
				
				if is_sideways:
					reasons.append(f"📈 EMA12≈EMA26 (дивергенция {ema_divergence*100:.2f}% < 1%) - боковик ✓")
				
				if stoch_k < STOCH_OVERSOLD:
					reasons.append(f"📉 Stoch={stoch_k:.1f} < {STOCH_OVERSOLD} - дополнительное подтверждение перепроданности")
				
				# Рассчитываем динамический SL на основе ATR
				if USE_DYNAMIC_SL_FOR_MR and atr > 0:
					atr_percent = (atr / price) * 100
					dynamic_sl = (atr / price) * MR_ATR_SL_MULTIPLIER
					dynamic_sl = max(MR_ATR_SL_MIN, min(dynamic_sl, MR_ATR_SL_MAX))
					
					# v4: АДАПТИВНЫЙ SL при риске падающего ножа
					if falling_knife_detected and ADAPTIVE_SL_ON_RISK:
						dynamic_sl *= ADAPTIVE_SL_MULTIPLIER  # Увеличиваем на 50%
						reasons.append(f"🛡️ Адаптивный SL: {dynamic_sl*100:.2f}% (риск падающего ножа, увеличен на {(ADAPTIVE_SL_MULTIPLIER-1)*100:.0f}%)")
					else:
						reasons.append(f"🛡️ Динамический SL: {dynamic_sl*100:.2f}% (ATR={atr_percent:.2f}% × {MR_ATR_SL_MULTIPLIER})")
				
				# v4: Рассчитываем динамический TP на основе ATR
				if USE_DYNAMIC_TP_FOR_MR and atr > 0:
					atr_percent = (atr / price) * 100
					dynamic_tp = (atr / price) * MR_ATR_TP_MULTIPLIER
					dynamic_tp = max(MR_ATR_TP_MIN, min(dynamic_tp, MR_ATR_TP_MAX))
					reasons.append(f"🎯 Динамический TP: {dynamic_tp*100:.2f}% (ATR × {MR_ATR_TP_MULTIPLIER}, R:R={MR_ATR_TP_MULTIPLIER/MR_ATR_SL_MULTIPLIER:.1f})")
			else:
				signal = "HOLD"
				reasons.append(f"⏸ HOLD: RSI и Z-score перепроданы, но ADX={adx:.1f} > {MR_ADX_MAX} (сильный тренд) → пропускаем")
		
		elif is_rsi_oversold and is_zscore_low and falling_knife_detected:
			# v5: Падающий нож обнаружен
			if ADAPTIVE_SL_ON_RISK:
				# v4 режим: разрешаем вход с увеличенным SL
				# (этот код не выполнится в v5, т.к. ADAPTIVE_SL_ON_RISK=False)
				pass  # логика выше уже обработана
			else:
				# v5 режим: блокируем вход
				signal = "HOLD"
				# reasons уже содержит причины блокировки от фильтров
		
		# --- УСЛОВИЯ ПРОДАЖИ (выход из позиции) ---
		is_rsi_normal = rsi > MR_RSI_EXIT
		is_zscore_normalized = zscore > MR_ZSCORE_SELL_THRESHOLD
		
		if is_rsi_normal or is_zscore_normalized:
			signal = "SELL"
			signal_emoji = "🔴"
			confidence = min(1.0, (rsi - MR_RSI_EXIT) / (70 - MR_RSI_EXIT) * 0.5 + (zscore / 2.0) * 0.5)
			
			reasons.append(f"✅ EXIT: Возврат к среднему")
			if is_rsi_normal:
				reasons.append(f"📊 RSI={rsi:.1f} > {MR_RSI_EXIT} (вернулся к норме)")
			if is_zscore_normalized:
				reasons.append(f"📈 Z-score={zscore:.2f} > {MR_ZSCORE_SELL_THRESHOLD} (цена вернулась к среднему)")
		
		# Если не BUY и не SELL - HOLD
		if signal == "HOLD" and not reasons:
			reasons.append(f"⏸ HOLD: RSI={rsi:.1f}, Z-score={zscore:.2f}")
			reasons.append(f"📊 ADX={adx:.1f}, EMA дивергенция={(abs(ema_12-ema_26)/ema_26*100 if ema_26 > 0 else 0):.2f}%")
			reasons.append("🔍 Ожидаем перепроданности (RSI<30, Z<-2.5)")
		
		return {
			"signal": signal,
			"signal_emoji": signal_emoji,
			"price": price,
			"RSI": rsi,
			"zscore": zscore,
			"ADX": adx,
			"ATR": atr,
			"EMA_12": ema_12,
			"EMA_26": ema_26,
			"ema_divergence": abs(ema_12 - ema_26) / ema_26 if ema_26 > 0 else 0,
			"stoch_k": stoch_k,
			"is_not_trending": is_not_trending,
			"is_sideways": is_sideways,
			"position_size_percent": position_size_percent,
			"confidence": confidence,
			"falling_knife_detected": falling_knife_detected,
			"dynamic_sl": dynamic_sl,  # Динамический SL для бэктеста
			"dynamic_tp": dynamic_tp,  # Динамический TP для бэктеста (v4)
			"reasons": reasons,
			"strategy": "MEAN_REVERSION",
			"bullish_votes": 0,  # Mean reversion не использует систему голосования
			"bearish_votes": 0
		}

class HybridStrategy:
	"""
	🔀 ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
	
	Логика:
	- ADX < 20 → Mean Reversion (боковой рынок)
	- ADX > 25 → Trend Following (трендовый рынок)
	- 20 <= ADX <= 25 → переходная зона (HOLD или последний режим)
	"""
	
	def __init__(self, df: pd.DataFrame, trend_following_strategy, mean_reversion_strategy):
		self.df = df.copy()
		self.trend_following_strategy = trend_following_strategy
		self.mean_reversion_strategy = mean_reversion_strategy
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)
	
	def generate_signal(self, last_mode: str = None, last_mode_time: float = 0) -> Dict[str, Any]:
		"""
		🔀 ГИБРИДНАЯ СТРАТЕГИЯ (MR + TF с переключением по ADX)
		
		Логика:
		- ADX < 20 → Mean Reversion (боковой рынок)
		- ADX > 25 → Trend Following (трендовый рынок)
		- 20 <= ADX <= 25 → переходная зона (HOLD или последний режим)
		
		Параметры:
		- last_mode: последний активный режим ("MR" или "TF")
		- last_mode_time: время в последнем режиме (часы)
		
		Возвращает сигнал с указанием активного режима.
		"""
		# Логирование для отладки времени
		logger.info(f"🔀 HYBRID: last_mode={last_mode}, last_mode_time={last_mode_time:.2f}h, min_time={HYBRID_MIN_TIME_IN_MODE}h")
		if self.df.empty:
			return {
				"signal": "HOLD",
				"signal_emoji": "⚠️",
				"price": 0,
				"ADX": 0,
				"active_mode": "NONE",
				"reasons": ["⚠️ DataFrame пустой"],
				"strategy": "HYBRID",
				"bullish_votes": 0,
				"bearish_votes": 0
			}
		
		reasons = []
		
		# Получаем ADX и цену из последней строки DataFrame
		last = self.df.iloc[-1]
		price = float(last["close"])
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		
		# Логирование для отладки данных
		logger.info(f"📊 HYBRID DATA: len(df)={len(self.df)}, price={price:.2f}, adx={adx:.2f}, ADX_WINDOW={ADX_WINDOW}")
		
		if np.isnan(adx) or adx == 0 or price == 0:
			return {
				"signal": "HOLD",
				"signal_emoji": "⚠️",
				"price": price,
				"ADX": adx,
				"active_mode": "NONE",
				"reasons": ["⚠️ Недостаточно данных для расчёта индикаторов"],
				"strategy": "HYBRID",
				"bullish_votes": 0,
				"bearish_votes": 0
			}
		
		# Определяем текущий режим на основе ADX
		if adx < HYBRID_ADX_MR_THRESHOLD:
			current_mode = "MR"
			reasons.append(f"📊 ADX={adx:.1f} < {HYBRID_ADX_MR_THRESHOLD} → MEAN REVERSION режим")
		elif adx > HYBRID_ADX_TF_THRESHOLD:
			current_mode = "TF"
			reasons.append(f"📊 ADX={adx:.1f} > {HYBRID_ADX_TF_THRESHOLD} → TREND FOLLOWING режим")
		else:
			# Переходная зона
			if HYBRID_TRANSITION_MODE == "HOLD":
				current_mode = "TRANSITION"  # Исправлено: должно быть TRANSITION, не HOLD
				reasons.append(f"⏸ ADX={adx:.1f} в переходной зоне [{HYBRID_ADX_MR_THRESHOLD}, {HYBRID_ADX_TF_THRESHOLD}] → TRANSITION")
			else:  # LAST
				current_mode = last_mode if last_mode else "TRANSITION"  # Исправлено: TRANSITION по умолчанию
				reasons.append(f"🔄 ADX={adx:.1f} в переходной зоне → используем последний режим ({current_mode})")
		
		# Проверяем минимальное время в режиме (защита от частого переключения)
		# ИСКЛЮЧЕНИЕ: TRANSITION режим может переключаться в любой момент
		if (last_mode is not None and last_mode != current_mode and 
			last_mode_time < HYBRID_MIN_TIME_IN_MODE and 
			last_mode != "TRANSITION"):
			current_mode = last_mode
			time_remaining = HYBRID_MIN_TIME_IN_MODE - last_mode_time
			reasons.append(f"⏱ ЗАЩИТА ОТ ПЕРЕКЛЮЧЕНИЯ: Остаёмся в режиме {last_mode}")
			reasons.append(f"   📊 Время в режиме: {last_mode_time:.2f}h / {HYBRID_MIN_TIME_IN_MODE}h (осталось {time_remaining:.2f}h)")
			reasons.append(f"   🎯 Требуется минимум {HYBRID_MIN_TIME_IN_MODE}h для смены режима")
			logger.info(f"⏱ ЗАЩИТА ОТ ПЕРЕКЛЮЧЕНИЯ: {last_mode} → {current_mode}, время: {last_mode_time:.2f}h < {HYBRID_MIN_TIME_IN_MODE}h")
		else:
			logger.info(f"✅ РЕЖИМ ОБНОВЛЁН: {last_mode} → {current_mode}, время: {last_mode_time:.2f}h")
		
		# Генерируем сигнал в зависимости от режима
		if current_mode == "MR":
			signal_result = self.mean_reversion_strategy.generate_signal()
			signal_result["active_mode"] = "MEAN_REVERSION"
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
			
			# 🔴 SHORT v2.1: Проверяем SHORT в режиме MR при сильном страхе
			# Если MR режим и есть медвежий тренд, проверяем активацию SHORT
			if signal_result.get("signal") == "SELL":
				ema_short = signal_result.get("EMA_12", 0)
				ema_long = signal_result.get("EMA_26", 0)
				bearish_votes = signal_result.get("bearish_votes", 0)
				bullish_votes = signal_result.get("bullish_votes", 0)
				
				# Медвежий тренд: EMA_short < EMA_long и bearish > bullish
				if ema_short < ema_long and bearish_votes > bullish_votes + 1:
					# Получаем SHORT данные из результата
					short_score = signal_result.get("short_score", 0.0)
					short_enabled = signal_result.get("short_enabled", False)
					short_conditions = signal_result.get("short_conditions", [])
					
					# Логирование для отладки SHORT
					logger.info(f"🔴 SHORT CHECK (MR): EMA_short={ema_short:.2f} < EMA_long={ema_long:.2f}, "
							   f"bearish={bearish_votes} > bullish={bullish_votes}+1, "
							   f"short_enabled={short_enabled}, conditions={len(short_conditions)}, "
							   f"short_score={short_score:.2f}")
					
					# Если SHORT активен и скор достаточно высокий
					if short_enabled and len(short_conditions) >= 2:
						signal_result["signal"] = "SHORT"
						signal_result["signal_emoji"] = "🔴📉"
						reasons.append(f"🔴 SHORT ACTIVATED: Медвежий тренд в MR режиме, скор {short_score:.2f}")
						logger.info(f"🔴 SHORT ACTIVATED (MR): {short_conditions}")
					else:
						logger.info(f"🔴 SHORT BLOCKED (MR): enabled={short_enabled}, conditions={len(short_conditions)}")
		
		elif current_mode == "TF":
			signal_result = self.trend_following_strategy.generate_signal()
			signal_result["active_mode"] = "TREND_FOLLOWING"
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			
			# 🔴 SHORT v2.1: Проверяем медвежий тренд для SHORT сигнала
			# Если TF режим и сигнал SELL, проверяем активацию SHORT
			if signal_result.get("signal") == "SELL":
				ema_short = signal_result.get("EMA_12", 0)
				ema_long = signal_result.get("EMA_26", 0)
				bearish_votes = signal_result.get("bearish_votes", 0)
				bullish_votes = signal_result.get("bullish_votes", 0)
				
				# Медвежий тренд: EMA_short < EMA_long и bearish > bullish
				if ema_short < ema_long and bearish_votes > bullish_votes + 1:
					# Получаем SHORT данные из результата
					short_score = signal_result.get("short_score", 0.0)
					short_enabled = signal_result.get("short_enabled", False)
					short_conditions = signal_result.get("short_conditions", [])
					
					# Логирование для отладки SHORT
					logger.info(f"🔴 SHORT CHECK: EMA_short={ema_short:.2f} < EMA_long={ema_long:.2f}, "
							   f"bearish={bearish_votes} > bullish={bullish_votes}+1, "
							   f"short_enabled={short_enabled}, conditions={len(short_conditions)}, "
							   f"short_score={short_score:.2f}")
					
					# Если SHORT активен и скор достаточно высокий
					if short_enabled and len(short_conditions) >= 2:
						signal_result["signal"] = "SHORT"
						signal_result["signal_emoji"] = "🔴📉"
						reasons.append(f"🔴 SHORT ACTIVATED: Медвежий тренд в TF режиме, скор {short_score:.2f}")
						logger.info(f"🔴 SHORT ACTIVATED: {short_conditions}")
					else:
						logger.info(f"🔴 SHORT BLOCKED: enabled={short_enabled}, conditions={len(short_conditions)}")
			
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		else:  # HOLD или TRANSITION
			# Если переходная зона, всё равно генерируем полный сигнал для аналитики
			# но переопределяем его на HOLD
			signal_result = self.trend_following_strategy.generate_signal()
			signal_result["signal"] = "HOLD"  # Принудительно HOLD в переходной зоне
			signal_result["signal_emoji"] = "⚠️"
			signal_result["active_mode"] = "TRANSITION"
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			# Добавляем reason о переходной зоне в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		return signal_result
