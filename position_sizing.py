from typing import List, Dict, Any
from config import (
	POSITION_SIZE_STRONG, POSITION_SIZE_MEDIUM, POSITION_SIZE_WEAK,
	SIGNAL_STRENGTH_STRONG, SIGNAL_STRENGTH_MEDIUM,
	VOLATILITY_HIGH_THRESHOLD, VOLATILITY_LOW_THRESHOLD, VOLATILITY_ADJUSTMENT_MAX,
	# Kelly Criterion
	USE_KELLY_CRITERION, KELLY_FRACTION, MIN_TRADES_FOR_KELLY, KELLY_LOOKBACK_WINDOW,
	KELLY_NEGATIVE_MULTIPLIER,
	# Small Balance Settings
	SMALL_BALANCE_THRESHOLD, SMALL_BALANCE_MIN_ORDER, SMALL_BALANCE_POSITION_MULTIPLIER
)


def get_position_size_percent(
	signal_strength: int,
	atr: float = 0,
	price: float = 0,
	kelly_multiplier: float = 1.0,
	balance: float = None,
	symbol: str = None
) -> float:
	"""
	Возвращает процент от баланса для входа в позицию.
	Учитывает силу сигнала, волатильность (ATR) и Kelly Criterion.
	Для малых балансов использует адаптивный расчет.
	"""
	# Для малых балансов используем специальную логику
	if balance is not None and balance < SMALL_BALANCE_THRESHOLD:
		return calculate_position_size_for_small_balance(balance, signal_strength, atr, price, symbol)
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


def calculate_kelly_fraction(trades_history: List[Dict[str, Any]], atr_percent: float, balance: float = None) -> float:
	"""
	Рассчитывает Kelly fraction для оптимального размера позиции.
	Использует скользящее окно последних сделок.
	Нормализуется по волатильности актива.
	Отключается для малых балансов (<$50-100).
	"""
	if not USE_KELLY_CRITERION:
		return 1.0  # Нейтральный множитель
	
	# Отключаем Kelly для малых балансов (недостаточно истории)
	if balance is not None and balance < SMALL_BALANCE_THRESHOLD:
		return 1.0  # Нейтральный множитель для малых балансов
	
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
	
	# НОВОЕ: Проверка на отрицательный Kelly
	if kelly <= 0:
		# Отрицательный Kelly означает убыточную стратегию
		# Возвращаем минимальный множитель для консервативного подхода
		return KELLY_NEGATIVE_MULTIPLIER
	
	# Применяем консервативную дробь Kelly (например, 25%)
	kelly *= KELLY_FRACTION
	
	# Нормализация по волатильности: более агрессивное снижение при высокой волатильности
	volatility_adjustment = 1 / (1 + (atr_percent / 2) ** 1.2)
	kelly *= volatility_adjustment
	
	# Ограничиваем диапазон 0.5-1.5 (не более 50% уменьшение и 50% увеличение)
	kelly_multiplier = max(0.5, min(1.5, kelly))
	
	return kelly_multiplier


def calculate_position_size_for_small_balance(
	balance: float,
	signal_strength: int,
	atr: float = 0,
	price: float = 0,
	symbol: str = None
) -> float:
	"""
	Рассчитывает размер позиции для малых балансов с учетом минимумов Bybit.
	Использует гибридный подход: минимум $5, но растет с силой сигнала.
	
	Args:
		balance: Текущий баланс в USDT
		signal_strength: Сила сигнала (0-15)
		atr: ATR для корректировки волатильности
		price: Цена актива
		symbol: Торговая пара (для получения минимума из БД)
	
	Returns:
		Процент от баланса для входа в позицию
	"""
	# Если баланс больше порога - используем стандартный расчет
	if balance >= SMALL_BALANCE_THRESHOLD:
		return get_position_size_percent(signal_strength, atr, price)
	
	# Для малых балансов используем гибридный подход
	# Базовые размеры в зависимости от силы сигнала
	if signal_strength >= SIGNAL_STRENGTH_STRONG:
		base_amount = 8.0  # $8 для сильного сигнала
	elif signal_strength >= SIGNAL_STRENGTH_MEDIUM:
		base_amount = 6.0  # $6 для среднего сигнала
	else:
		base_amount = 5.0  # $5 для слабого сигнала
	
	# Корректировка на волатильность (если есть ATR)
	if atr > 0 and price > 0:
		atr_percent = (atr / price) * 100
		
		# При высокой волатильности уменьшаем размер
		if atr_percent > VOLATILITY_HIGH_THRESHOLD:
			volatility_factor = VOLATILITY_HIGH_THRESHOLD / atr_percent
			base_amount *= volatility_factor
		# При низкой волатильности можно чуть увеличить
		elif atr_percent < VOLATILITY_LOW_THRESHOLD:
			volatility_adjustment = min(VOLATILITY_ADJUSTMENT_MAX, VOLATILITY_LOW_THRESHOLD / atr_percent)
			base_amount *= volatility_adjustment
	
	# Ограничиваем минимальным и максимальным размером
	base_amount = max(SMALL_BALANCE_MIN_ORDER, min(base_amount, balance * 0.5))
	
	# Конвертируем в процент от баланса
	position_percent = base_amount / balance
	
	# Применяем множитель для малых балансов
	position_percent *= SMALL_BALANCE_POSITION_MULTIPLIER
	
	# Ограничиваем максимумом
	position_percent = min(position_percent, 0.8)  # Максимум 80% от баланса
	
	return position_percent
