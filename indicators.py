import pandas as pd
import numpy as np
import ta
from typing import Dict, Any, Optional
from logger import logger
from config import (
	# Индикаторы
	SMA_PERIODS, EMA_PERIODS, EMA_SHORT_WINDOW, EMA_LONG_WINDOW,
	RSI_WINDOW, RSI_OVERSOLD, RSI_OVERSOLD_NEAR, RSI_OVERBOUGHT, RSI_OVERBOUGHT_NEAR,
	RSI_BUY_RANGE, RSI_SELL_RANGE,
	MACD_FAST, MACD_SLOW, MACD_SIGNAL,
	ADX_WINDOW, ADX_TRENDING, ADX_RANGING, ADX_STRONG, ADX_MODERATE,
	STOCH_WINDOW, STOCH_SMOOTH_WINDOW, STOCH_OVERSOLD, STOCH_OVERBOUGHT,
	ATR_WINDOW, VOLUME_MA_WINDOW, VOLUME_HIGH_RATIO, VOLUME_MODERATE_RATIO, VOLUME_LOW_RATIO
)

class IndicatorsCalculator:
	"""
	🧮 КАЛЬКУЛЯТОР ИНДИКАТОРОВ
	
	Отвечает за вычисление всех технических индикаторов
	с динамической адаптацией параметров на основе волатильности.
	"""
	
	def __init__(self, df: pd.DataFrame):
		self.df = df.copy()
		if "close" not in self.df.columns:
			raise ValueError("DataFrame must contain 'close' column")
		self.df.sort_index(inplace=True)
	
	def compute_indicators(
		self, ema_short_window=None, ema_long_window=None, rsi_window=None,
		macd_fast=None, macd_slow=None, macd_signal=None
	) -> pd.DataFrame:
		"""
		📊 ВЫЧИСЛЕНИЕ ВСЕХ ИНДИКАТОРОВ
		
		С динамической адаптацией параметров на основе волатильности.
		"""
		# ====================================================================
		# ДИНАМИЧЕСКАЯ АДАПТАЦИЯ ПАРАМЕТРОВ НА ОСНОВЕ ВОЛАТИЛЬНОСТИ
		# ====================================================================
		
		# Сначала вычисляем ATR для оценки волатильности
		close = self.df["close"].astype(float)
		high = self.df["high"].astype(float)
		low = self.df["low"].astype(float)
		
		# Временный ATR для адаптации параметров
		if len(self.df) >= ATR_WINDOW:
			temp_atr = ta.volatility.average_true_range(high, low, close, window=ATR_WINDOW).iloc[-1]
			current_price = close.iloc[-1]
			volatility_percent = (temp_atr / current_price) * 100 if current_price > 0 else 1.5
		else:
			volatility_percent = 1.5  # Средняя волатильность по умолчанию
		
		# Адаптируем параметры на основе волатильности
		# При высокой волатильности (>3%) → увеличиваем периоды (сглаживаем шум)
		# При низкой волатильности (<1%) → уменьшаем периоды (быстрее реагируем)
		
		volatility_factor = 1.0  # Базовый множитель
		if volatility_percent > 3.0:
			volatility_factor = 1.3  # Увеличиваем периоды на 30%
		elif volatility_percent > 2.0:
			volatility_factor = 1.15  # Увеличиваем на 15%
		elif volatility_percent < 0.8:
			volatility_factor = 0.85  # Уменьшаем на 15%
		elif volatility_percent < 1.2:
			volatility_factor = 0.95  # Уменьшаем на 5%
		
		# Используем значения из config с адаптацией, если не переданы явно
		if ema_short_window is None:
			ema_short_window = max(5, int(EMA_SHORT_WINDOW * volatility_factor))
		if ema_long_window is None:
			ema_long_window = max(10, int(EMA_LONG_WINDOW * volatility_factor))
		if rsi_window is None:
			rsi_window = max(7, int(RSI_WINDOW * volatility_factor))
		if macd_fast is None:
			macd_fast = max(8, int(MACD_FAST * volatility_factor))
		if macd_slow is None:
			macd_slow = max(16, int(MACD_SLOW * volatility_factor))
		if macd_signal is None:
			macd_signal = max(5, int(MACD_SIGNAL * volatility_factor))
		
		close = self.df["close"].astype(float)
		high = self.df["high"].astype(float)
		low = self.df["low"].astype(float)
		volume = self.df["volume"].astype(float)

		# Скользящие средние - из config
		for w in SMA_PERIODS:
			if len(self.df) >= w:
				self.df[f"SMA_{w}"] = ta.trend.sma_indicator(close, window=w)
			else:
				self.df[f"SMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		for w in EMA_PERIODS:
			if len(self.df) >= w:
				self.df[f"EMA_{w}"] = ta.trend.ema_indicator(close, window=w)
			else:
				self.df[f"EMA_{w}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# ATR для волатильности (КРИТИЧНО для динамического SL)
		if len(self.df) >= ATR_WINDOW:
			self.df[f"ATR_{ATR_WINDOW}"] = ta.volatility.average_true_range(high, low, close, window=ATR_WINDOW)
		else:
			self.df[f"ATR_{ATR_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# Объём
		if len(self.df) >= VOLUME_MA_WINDOW:
			self.df[f"Volume_MA_{VOLUME_MA_WINDOW}"] = volume.rolling(window=VOLUME_MA_WINDOW).mean()
		else:
			self.df[f"Volume_MA_{VOLUME_MA_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

		# Осцилляторы - только самые важные
		self.df[f"RSI_{RSI_WINDOW}"] = ta.momentum.rsi(close, window=RSI_WINDOW) if len(self.df) >= RSI_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# ADX - сила тренда (критично!)
		if (
			len(self.df) >= ADX_WINDOW
			and len(self.df.tail(ADX_WINDOW)) == ADX_WINDOW
			and self.df[["high", "low", "close"]].tail(ADX_WINDOW).isna().sum().sum() == 0
		):
			try:
				self.df[f"ADX_{ADX_WINDOW}"] = ta.trend.adx(high, low, close, window=ADX_WINDOW)
				logger.info(f"✅ ADX рассчитан: len(df)={len(self.df)}, ADX_WINDOW={ADX_WINDOW}")
			except Exception as e:
				logger.warning(f"❌ Ошибка расчёта ADX: {e}")
				self.df[f"ADX_{ADX_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		else:
			logger.warning(f"❌ ADX не рассчитан: len(df)={len(self.df)}, ADX_WINDOW={ADX_WINDOW}, NaN_count={self.df[['high', 'low', 'close']].tail(ADX_WINDOW).isna().sum().sum()}")
			self.df[f"ADX_{ADX_WINDOW}"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
		
		# Stochastic - для перекупленности/перепроданности
		self.df["Stoch_K"] = ta.momentum.stoch(high, low, close, window=STOCH_WINDOW, smooth_window=STOCH_SMOOTH_WINDOW) if len(self.df) >= STOCH_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)
		self.df["Stoch_D"] = ta.momentum.stoch_signal(high, low, close, window=STOCH_WINDOW, smooth_window=STOCH_SMOOTH_WINDOW) if len(self.df) >= STOCH_WINDOW else pd.Series([np.nan]*len(self.df), index=self.df.index)

		# Базовые индикаторы
		self.df["EMA_short"] = ta.trend.ema_indicator(close, window=ema_short_window) if len(self.df) >= ema_short_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
		self.df["EMA_long"] = ta.trend.ema_indicator(close, window=ema_long_window) if len(self.df) >= ema_long_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
		self.df["RSI"] = ta.momentum.rsi(close, window=rsi_window) if len(self.df) >= rsi_window else pd.Series([np.nan]*len(self.df), index=self.df.index)
		if len(self.df) >= max(macd_slow, macd_fast, macd_signal):
			macd = ta.trend.MACD(close, window_slow=macd_slow, window_fast=macd_fast, window_sign=macd_signal)
			self.df["MACD"] = macd.macd()
			self.df["MACD_signal"] = macd.macd_signal()
			self.df["MACD_hist"] = macd.macd_diff()
		else:
			self.df["MACD"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
			self.df["MACD_signal"] = pd.Series([np.nan]*len(self.df), index=self.df.index)
			self.df["MACD_hist"] = pd.Series([np.nan]*len(self.df), index=self.df.index)

		self.df.ffill(inplace=True)
		self.df.bfill(inplace=True)
		return self.df
	
	def get_indicators_data(self) -> Dict[str, Any]:
		"""
		📊 ПОЛУЧЕНИЕ ДАННЫХ ИНДИКАТОРОВ
		
		Возвращает словарь с текущими значениями всех индикаторов.
		"""
		if self.df.empty:
			raise ValueError("DataFrame is empty")
		
		last = self.df.iloc[-1]
		price = float(last["close"])
		
		# Индикаторы
		ema_s = float(last["EMA_short"])
		ema_l = float(last["EMA_long"])
		ema_20 = float(last.get("EMA_20", 0))
		ema_50 = float(last.get("EMA_50", 0))
		ema_200 = float(last.get("EMA_200", 0))
		sma_20 = float(last.get("SMA_20", 0))
		sma_50 = float(last.get("SMA_50", 0))
		rsi = float(last["RSI"])
		macd_hist = float(last["MACD_hist"])
		macd = float(last["MACD"])
		macd_signal = float(last["MACD_signal"])
		adx = float(last.get(f"ADX_{ADX_WINDOW}", 0))
		stoch_k = float(last.get("Stoch_K", 0))
		stoch_d = float(last.get("Stoch_D", 0))
		atr = float(last.get(f"ATR_{ATR_WINDOW}", 0))
		
		# Объём
		volume = float(last["volume"])
		volume_ma = float(last.get(f"Volume_MA_{VOLUME_MA_WINDOW}", volume))
		
		return {
			"price": price,
			"EMA_short": ema_s,
			"EMA_long": ema_l,
			"EMA_20": ema_20,
			"EMA_50": ema_50,
			"EMA_200": ema_200,
			"SMA_20": sma_20,
			"SMA_50": sma_50,
			"RSI": rsi,
			"MACD": macd,
			"MACD_signal": macd_signal,
			"MACD_hist": macd_hist,
			"ADX": adx,
			"Stoch_K": stoch_k,
			"Stoch_D": stoch_d,
			"ATR": atr,
			"volume": volume,
			"volume_ma": volume_ma,
			"volume_ratio": volume / volume_ma if volume_ma > 0 else 1.0
		}
