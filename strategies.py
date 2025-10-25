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
	# R:R контроль
	MIN_RR_RATIO, ENFORCE_MIN_RR,
	# Гибридная стратегия
	STRATEGY_HYBRID_MODE, HYBRID_ADX_MR_THRESHOLD, HYBRID_ADX_TF_THRESHOLD,
	HYBRID_ADX_MR_EXIT, HYBRID_ADX_TF_EXIT,
	HYBRID_TRANSITION_MODE, HYBRID_MIN_TIME_IN_MODE,
	# Индикаторы
	STOCH_OVERSOLD, STOCH_OVERBOUGHT, ADX_WINDOW, ATR_WINDOW,
	# Константы режимов
	MODE_MEAN_REVERSION, MODE_TREND_FOLLOWING, MODE_TRANSITION,
	# Пороги голосования
	VOTE_THRESHOLD_TRANSITIONING, VOTE_THRESHOLD_TRENDING, VOTE_THRESHOLD_RANGING
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
		# РАСЧЁТ Z-SCORE (ИСПРАВЛЕНО)
		# ====================================================================
		
		if len(self.df) >= MR_ZSCORE_WINDOW:
			close_prices = self.df["close"].astype(float)
			sma = close_prices.rolling(window=MR_ZSCORE_WINDOW).mean()
			std = close_prices.rolling(window=MR_ZSCORE_WINDOW).std()
			zscore_series = (close_prices - sma) / std
			zscore = zscore_series.iloc[-1] if not pd.isna(zscore_series.iloc[-1]) else 0
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
					reasons.append(f"✅ STRONG BUY: RSI={rsi:.1f} (<20), Z-score={zscore:.2f} (<{MR_ZSCORE_STRONG_BUY}) → позиция 70%")
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
					
					# НОВОЕ: Проверка и корректировка R:R
					if ENFORCE_MIN_RR and dynamic_sl is not None:
						current_rr = dynamic_tp / dynamic_sl if dynamic_sl > 0 else 0
						if current_rr < MIN_RR_RATIO:
							# Корректируем TP для обеспечения минимального R:R
							dynamic_tp = dynamic_sl * MIN_RR_RATIO
							# Проверяем, что не превышаем максимум
							if dynamic_tp > MR_ATR_TP_MAX:
								# Если не помещается в максимум, корректируем SL
								dynamic_sl = dynamic_tp / MIN_RR_RATIO
								if dynamic_sl < MR_ATR_SL_MIN:
									# Если SL стал слишком маленьким, блокируем вход
									reasons.append(f"🚫 R:R контроль: SL={dynamic_sl*100:.2f}% < {MR_ATR_SL_MIN*100:.1f}% → блокируем вход")
									signal = "HOLD"
									signal_emoji = "⚠️"
									# Выходим из метода
									return {
										"signal": signal,
										"signal_emoji": signal_emoji,
										"position_size_percent": 0,
										"confidence": 0,
										"reasons": reasons,
										"dynamic_sl": None,
										"dynamic_tp": None,
										"strategy": "MEAN_REVERSION",
										"bullish_votes": 0,
										"bearish_votes": 0
									}
							reasons.append(f"🎯 R:R контроль: TP скорректирован до {dynamic_tp*100:.2f}% (R:R={MIN_RR_RATIO:.2f})")
						else:
							reasons.append(f"🎯 Динамический TP: {dynamic_tp*100:.2f}% (ATR × {MR_ATR_TP_MULTIPLIER}, R:R={current_rr:.2f})")
					else:
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
	- ADX < 12 → Mean Reversion (боковой рынок)
	- ADX > 30 → Trend Following (трендовый рынок)
	- 12 <= ADX <= 30 → переходная зона (HOLD или последний режим)
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
		
		# Определяем текущий режим на основе ADX с гистерезисом
		# Гистерезис предотвращает частые переключения при ADX около порогов
		if last_mode == "MR":
			# В MR режиме: выходим только при ADX > MR_EXIT (20)
			if adx > HYBRID_ADX_MR_EXIT:
				current_mode = "TF"
				reasons.append(f"📊 ADX={adx:.1f} > {HYBRID_ADX_MR_EXIT} → выход из MR в TF")
			else:
				current_mode = "MR"
				reasons.append(f"📊 ADX={adx:.1f} ≤ {HYBRID_ADX_MR_EXIT} → остаемся в MR")
		elif last_mode == "TF":
			# В TF режиме: выходим только при ADX < TF_EXIT (15)
			if adx < HYBRID_ADX_TF_EXIT:
				current_mode = "MR"
				reasons.append(f"📊 ADX={adx:.1f} < {HYBRID_ADX_TF_EXIT} → выход из TF в MR")
			else:
				current_mode = "TF"
				reasons.append(f"📊 ADX={adx:.1f} ≥ {HYBRID_ADX_TF_EXIT} → остаемся в TF")
		else:
			# Первый запуск или TRANSITION: используем базовые пороги
			if adx < HYBRID_ADX_MR_THRESHOLD:
				current_mode = "MR"
				reasons.append(f"📊 ADX={adx:.1f} < {HYBRID_ADX_MR_THRESHOLD} → MEAN REVERSION режим")
			elif adx > HYBRID_ADX_TF_THRESHOLD:
				current_mode = "TF"
				reasons.append(f"📊 ADX={adx:.1f} > {HYBRID_ADX_TF_THRESHOLD} → TREND FOLLOWING режим")
			else:
				# Переходная зона
				if HYBRID_TRANSITION_MODE == "HOLD":
					current_mode = MODE_TRANSITION
					reasons.append(f"⏸ ADX={adx:.1f} в переходной зоне [{HYBRID_ADX_MR_THRESHOLD}, {HYBRID_ADX_TF_THRESHOLD}] → TRANSITION")
				else:  # LAST
					current_mode = last_mode if last_mode else MODE_TRANSITION
					reasons.append(f"🔄 ADX={adx:.1f} в переходной зоне → используем последний режим ({current_mode})")
		
		# Проверяем минимальное время в режиме (защита от частого переключения)
		# ИСКЛЮЧЕНИЕ: TRANSITION режим может переключаться в любой момент
		if (last_mode is not None and last_mode != current_mode and 
			last_mode_time < HYBRID_MIN_TIME_IN_MODE and 
			last_mode != MODE_TRANSITION):
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
			
			# Проверяем порог голосования для MR режима
			bullish_votes = signal_result.get("bullish_votes", 0)
			bearish_votes = signal_result.get("bearish_votes", 0)
			votes_delta = bullish_votes - bearish_votes
			
			# Дополнительная фильтрация для MR режима
			rsi = signal_result.get("RSI", 50)
			adx = signal_result.get("ADX", 0)
			
			# Если MR стратегия генерирует BUY, проверяем порог и дополнительные условия
			if signal_result.get("signal") == "BUY":
				# Проверяем силу сигнала
				if votes_delta < VOTE_THRESHOLD_RANGING:
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ MR: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_RANGING})")
					logger.info(f"❌ MR BLOCK: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_RANGING})")
				# Проверяем RSI для MR (должен быть в зоне перепроданности)
				elif rsi > 40:  # RSI слишком высокий для MR
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ MR: RSI слишком высокий ({rsi:.1f} > 40) для Mean Reversion")
					logger.info(f"❌ MR BLOCK: RSI слишком высокий ({rsi:.1f} > 40) для Mean Reversion")
				# Проверяем ADX для MR (должен быть низким)
				elif adx > 25:  # ADX слишком высокий для MR
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ MR: ADX слишком высокий ({adx:.1f} > 25) для Mean Reversion")
					logger.info(f"❌ MR BLOCK: ADX слишком высокий ({adx:.1f} > 25) для Mean Reversion")
				else:
					reasons.append(f"✅ MR: сильный сигнал (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_RANGING}, RSI={rsi:.1f}, ADX={adx:.1f})")
					logger.info(f"✅ MR BUY: сильный сигнал (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_RANGING}, RSI={rsi:.1f}, ADX={adx:.1f})")
			
			signal_result["active_mode"] = MODE_MEAN_REVERSION
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
			
		
		elif current_mode == "TF":
			signal_result = self.trend_following_strategy.generate_signal()
			
			# Проверяем порог голосования для TF режима
			bullish_votes = signal_result.get("bullish_votes", 0)
			bearish_votes = signal_result.get("bearish_votes", 0)
			votes_delta = bullish_votes - bearish_votes
			
			# Дополнительная фильтрация для TF режима
			rsi = signal_result.get("RSI", 50)
			adx = signal_result.get("ADX", 0)
			
			# Если TF стратегия генерирует BUY, проверяем порог и дополнительные условия
			if signal_result.get("signal") == "BUY":
				# Проверяем силу сигнала
				if votes_delta < VOTE_THRESHOLD_TRENDING:
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ TF: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_TRENDING})")
					logger.info(f"❌ TF BLOCK: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_TRENDING})")
				# Проверяем RSI для TF (не должен быть в экстремальных зонах)
				elif rsi < 30 or rsi > 70:  # RSI в экстремальных зонах для TF
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ TF: RSI в экстремальной зоне ({rsi:.1f}) для Trend Following")
					logger.info(f"❌ TF BLOCK: RSI в экстремальной зоне ({rsi:.1f}) для Trend Following")
				# Проверяем ADX для TF (должен быть достаточно высоким)
				elif adx < 20:  # ADX слишком низкий для TF
					signal_result["signal"] = "HOLD"
					signal_result["signal_emoji"] = "⚠️"
					reasons.append(f"⏸ TF: ADX слишком низкий ({adx:.1f} < 20) для Trend Following")
					logger.info(f"❌ TF BLOCK: ADX слишком низкий ({adx:.1f} < 20) для Trend Following")
				else:
					reasons.append(f"✅ TF: сильный сигнал (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_TRENDING}, RSI={rsi:.1f}, ADX={adx:.1f})")
					logger.info(f"✅ TF BUY: сильный сигнал (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_TRENDING}, RSI={rsi:.1f}, ADX={adx:.1f})")
			
			signal_result["active_mode"] = MODE_TREND_FOLLOWING
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			
			# Добавляем reasons о режиме в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		else:  # HOLD или TRANSITION
			# Если переходная зона, генерируем сигнал и проверяем силу
			logger.info(f"🔍 TRANSITION MODE: ADX={adx:.1f} в переходной зоне, генерируем TF сигнал")
			signal_result = self.trend_following_strategy.generate_signal()
			
			# В TRANSITION режиме разрешаем BUY только при очень сильных сигналах
			original_signal = signal_result.get("signal", "HOLD")
			bullish_votes = signal_result.get("bullish_votes", 0)
			bearish_votes = signal_result.get("bearish_votes", 0)
			votes_delta = bullish_votes - bearish_votes
			
			# Детальное логирование для отладки TRANSITION режима
			logger.info(f"🔍 TRANSITION DEBUG: original_signal={original_signal}, bullish={bullish_votes}, bearish={bearish_votes}, delta={votes_delta:+d}")
			
			# Разрешаем BUY в TRANSITION при сильном bullish сигнале (Delta >= VOTE_THRESHOLD_TRANSITIONING)
			# НЕЗАВИСИМО от того, что генерирует TF стратегия
			if votes_delta >= VOTE_THRESHOLD_TRANSITIONING:
				signal_result["signal"] = "BUY"  # Разрешаем сильный BUY в TRANSITION
				signal_result["signal_emoji"] = "🟢"
				reasons.append(f"🎯 TRANSITION: принудительный BUY (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_TRANSITIONING})")
				logger.info(f"✅ TRANSITION BUY: принудительный BUY (Delta={votes_delta:+d} >= {VOTE_THRESHOLD_TRANSITIONING})")
			else:
				signal_result["signal"] = "HOLD"  # Слабые сигналы блокируем
				signal_result["signal_emoji"] = "⚠️"
				reasons.append(f"⏸ TRANSITION: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_TRANSITIONING})")
				logger.info(f"❌ TRANSITION HOLD: слабый сигнал (Delta={votes_delta:+d} < {VOTE_THRESHOLD_TRANSITIONING})")
			
			signal_result["active_mode"] = MODE_TRANSITION
			signal_result["strategy"] = "HYBRID"
			# Добавляем информацию о времени в режиме
			signal_result["mode_time"] = last_mode_time
			signal_result["min_mode_time"] = HYBRID_MIN_TIME_IN_MODE
			# Добавляем reason о переходной зоне в начало
			signal_result["reasons"] = reasons + signal_result.get("reasons", [])
		
		return signal_result
