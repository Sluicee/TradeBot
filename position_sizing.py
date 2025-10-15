from typing import List, Dict, Any
from config import (
	POSITION_SIZE_STRONG, POSITION_SIZE_MEDIUM, POSITION_SIZE_WEAK,
	SIGNAL_STRENGTH_STRONG, SIGNAL_STRENGTH_MEDIUM,
	VOLATILITY_HIGH_THRESHOLD, VOLATILITY_LOW_THRESHOLD, VOLATILITY_ADJUSTMENT_MAX,
	# Kelly Criterion
	USE_KELLY_CRITERION, KELLY_FRACTION, MIN_TRADES_FOR_KELLY, KELLY_LOOKBACK_WINDOW
)


def get_position_size_percent(
	signal_strength: int,
	atr: float = 0,
	price: float = 0,
	kelly_multiplier: float = 1.0
) -> float:
	"""
	Возвращает процент от баланса для входа в позицию.
	Учитывает силу сигнала, волатильность (ATR) и Kelly Criterion.
	"""
	# Базовый размер по силе сигнала
	if signal_strength >= SIGNAL_STRENGTH_STRONG:
		base_size = POSITION_SIZE_STRONG
		strength_level = "STRONG"
	elif signal_strength >= SIGNAL_STRENGTH_MEDIUM:
		base_size = POSITION_SIZE_MEDIUM
		strength_level = "MEDIUM"
	else:
		base_size = POSITION_SIZE_WEAK
		strength_level = "WEAK"
	
	# Корректировка на волатильность (если есть ATR)
	if atr > 0 and price > 0:
		atr_percent = (atr / price) * 100
		
		# Если волатильность высокая (>VOLATILITY_HIGH_THRESHOLD%), уменьшаем размер позиции
		if atr_percent > VOLATILITY_HIGH_THRESHOLD:
			volatility_factor = VOLATILITY_HIGH_THRESHOLD / atr_percent  # Обратная пропорция
			base_size *= volatility_factor
		# Если волатильность низкая (<VOLATILITY_LOW_THRESHOLD%), можно чуть увеличить
		elif atr_percent < VOLATILITY_LOW_THRESHOLD:
			volatility_adjustment = min(VOLATILITY_ADJUSTMENT_MAX, VOLATILITY_LOW_THRESHOLD / atr_percent)
			base_size *= volatility_adjustment
	
	# Применяем Kelly multiplier (0.5-1.5)
	base_size *= kelly_multiplier
	
	final_size = min(base_size, POSITION_SIZE_STRONG * 1.2)  # Максимум 120% от STRONG
	
	return final_size


def calculate_kelly_fraction(trades_history: List[Dict[str, Any]], atr_percent: float) -> float:
	"""
	Рассчитывает Kelly fraction для оптимального размера позиции.
	Использует скользящее окно последних сделок.
	Нормализуется по волатильности актива.
	"""
	if not USE_KELLY_CRITERION:
		return 1.0  # Нейтральный множитель
	
	# Берём только закрытые сделки (BUY и соответствующие closes)
	closed_trades = [
		t for t in trades_history 
		if t.get("type") in ["SELL", "STOP-LOSS", "TRAILING-STOP", "TIME-EXIT"]
		and t.get("profit") is not None
	]
	
	# Недостаточно данных для расчёта Kelly
	if len(closed_trades) < MIN_TRADES_FOR_KELLY:
		return 1.0
	
	# Используем скользящее окно последних N сделок
	recent_trades = closed_trades[-KELLY_LOOKBACK_WINDOW:]
	
	# Рассчитываем win rate и средние значения
	winning_trades = [t for t in recent_trades if t.get("profit", 0) > 0]
	losing_trades = [t for t in recent_trades if t.get("profit", 0) <= 0]
	
	total_trades = len(recent_trades)
	win_count = len(winning_trades)
	
	if total_trades == 0:
		return 1.0
	
	win_rate = win_count / total_trades
	
	# Средний выигрыш и проигрыш (в процентах)
	if winning_trades:
		avg_win = sum(t.get("profit_percent", 0) for t in winning_trades) / len(winning_trades)
	else:
		avg_win = 0.0
	
	if losing_trades:
		avg_loss = abs(sum(t.get("profit_percent", 0) for t in losing_trades) / len(losing_trades))
	else:
		avg_loss = 1.0  # Избегаем деления на 0
	
	# Kelly formula: (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
	if avg_win <= 0 or avg_loss <= 0:
		return 1.0
	
	kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
	
	# Применяем консервативную дробь Kelly (например, 25%)
	kelly *= KELLY_FRACTION
	
	# Нормализация по волатильности: уменьшаем размер при высокой волатильности
	volatility_adjustment = 1 / (1 + atr_percent / 2)
	kelly *= volatility_adjustment
	
	# Ограничиваем диапазон 0.5-1.5 (не более 50% уменьшение и 50% увеличение)
	kelly_multiplier = max(0.5, min(1.5, kelly))
	
	return kelly_multiplier
