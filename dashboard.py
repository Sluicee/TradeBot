import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
import sys
import subprocess
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import numpy as np
from scipy import stats as scipy_stats
from database import db, Signal, PaperTradingState
from logger import logger

# Импорты опциональные (могут не работать на всех системах)
try:
	import psutil
except ImportError:
	psutil = None

# Настройка страницы
st.set_page_config(
	page_title="TradeBot Dashboard",
	page_icon="📈",
	layout="wide",
	initial_sidebar_state="expanded"
)

# Константы
SETTINGS_FILE = "dashboard_settings.json"
LOG_DIR = "logs"
PROCESS_NAME = "main.py"

# Конфигурация Plotly для графиков
PLOTLY_CONFIG = {
	'displaylogo': False,
	'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d']
}

def get_latest_log_file() -> Optional[str]:
	"""Получает путь к последнему файлу логов"""
	if not os.path.exists(LOG_DIR):
		return None
	
	log_files = [f for f in os.listdir(LOG_DIR) if f.startswith("log_") and f.endswith(".txt")]
	if not log_files:
		return None
	
	# Сортируем по времени модификации (самый новый первый)
	log_files_with_time = [(f, os.path.getmtime(os.path.join(LOG_DIR, f))) for f in log_files]
	log_files_with_time.sort(key=lambda x: x[1], reverse=True)
	return os.path.join(LOG_DIR, log_files_with_time[0][0])

# ====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ====================================================================

def get_current_prices() -> Dict[str, float]:
	"""Получает текущие цены из последних сигналов в БД"""
	try:
		with db.session_scope() as session:
			from sqlalchemy import func
			
			# Получаем последнюю цену для каждого символа из сигналов
			subquery = session.query(
				Signal.symbol,
				func.max(Signal.time).label('max_time')
			).group_by(Signal.symbol).subquery()
			
			latest_signals = session.query(Signal).join(
				subquery,
				(Signal.symbol == subquery.c.symbol) & (Signal.time == subquery.c.max_time)
			).all()
			
			prices = {signal.symbol: signal.price for signal in latest_signals}
			return prices
	except Exception as e:
		logger.error(f"Ошибка получения цен из БД: {e}")
		return {}

@st.cache_data(ttl=10)
def load_paper_trader_state() -> Optional[Dict[str, Any]]:
	"""Загружает состояние paper trader из БД"""
	try:
		# Загружаем основное состояние
		db_state = db.get_paper_state()
		if not db_state:
			return None
		
		# Получаем текущие цены из БД
		current_prices = get_current_prices()
		
		# Загружаем позиции
		positions = {}
		db_positions = db.get_all_positions()
		for pos in db_positions:
			# Используем текущую цену из БД или entry_price если нет данных
			current_price = current_prices.get(pos.symbol, pos.entry_price)
			
			positions[pos.symbol] = {
				"symbol": pos.symbol,
				"entry_price": pos.entry_price,
				"current_price": current_price,  # Добавляем текущую цену
				"amount": pos.amount,
				"entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
				"signal_strength": pos.signal_strength,
				"invest_amount": pos.invest_amount,
				"entry_commission": pos.entry_commission,
				"atr": pos.atr,
				"stop_loss_price": pos.stop_loss_price,
				"stop_loss_percent": pos.stop_loss_percent,
				"take_profit_price": pos.take_profit_price,
				"partial_closed": pos.partial_closed,
				"max_price": pos.max_price,
				"partial_close_profit": pos.partial_close_profit,
				"original_amount": pos.original_amount,
				"averaging_count": pos.averaging_count,
				"average_entry_price": pos.average_entry_price,
				"pyramid_mode": pos.pyramid_mode,
				"total_invested": pos.total_invested,
				"averaging_entries": db.get_averaging_entries(pos.id)
			}
		
		# Загружаем историю сделок
		trades_history = db.get_trades_history(limit=1000)
		
		# Формируем структуру как раньше
		state = {
			"initial_balance": db_state.initial_balance,
			"balance": db_state.balance,
			"positions": positions,
			"current_prices": current_prices,  # Добавляем текущие цены
			"trades_history": trades_history,
			"stats": {
				"total_trades": db_state.total_trades,
				"winning_trades": db_state.winning_trades,
				"losing_trades": db_state.losing_trades,
				"total_commission": db_state.total_commission,
				"stop_loss_triggers": db_state.stop_loss_triggers,
				"take_profit_triggers": db_state.take_profit_triggers,
				"trailing_stop_triggers": db_state.trailing_stop_triggers
			},
			"is_running": db_state.is_running,
			"start_time": db_state.start_time.isoformat() if db_state.start_time else None,
			"max_positions": 3  # TODO: получить из config
		}
		
		return state
		
	except Exception as e:
		st.error(f"Ошибка загрузки состояния из БД: {e}")
		return None

def check_bot_status() -> Dict[str, Any]:
	"""Проверяет состояние торгового бота"""
	log_file = get_latest_log_file()
	status = {
		"is_running": False,
		"last_update": None,
		"state_file_exists": False,
		"state_file_age": None,
		"log_file_exists": log_file is not None and os.path.exists(log_file),
		"process_found": False,
		"uptime": None
	}
	
	# Проверка БД и последнего обновления
	try:
		db_state = db.get_paper_state()
		if db_state:
			status["state_file_exists"] = True
			if db_state.updated_at:
				status["last_update"] = db_state.updated_at
				age_seconds = (datetime.now() - db_state.updated_at).total_seconds()
				status["state_file_age"] = age_seconds
				
				# Считаем бот живым если БД обновлялась в последние 5 минут
				if age_seconds < 300:
					status["is_running"] = True
			# Также проверяем флаг is_running
			if db_state.is_running:
				status["is_running"] = True
	except Exception as e:
		pass
	
	# Проверка процесса (опционально, может быть медленно на Windows)
	if psutil:
		try:
			for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
				try:
					cmdline = proc.info.get('cmdline', [])
					# Проверяем различные варианты имен процессов
					if cmdline and any(name in ' '.join(cmdline) for name in ['bot.py', 'main.py', 'telegram_bot.py', 'paper_trader.py']):
						status["process_found"] = True
						status["uptime"] = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
						status["is_running"] = True
						break
				except (psutil.NoSuchProcess, psutil.AccessDenied):
					continue
		except Exception:
			pass  # psutil может не работать, не критично
	
	return status

def read_recent_logs(num_lines: int = 50) -> List[str]:
	"""Читает последние N строк из лог-файла"""
	log_file = get_latest_log_file()
	if not log_file or not os.path.exists(log_file):
		return ["Лог-файл не найден"]
	
	try:
		with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
			lines = f.readlines()
			return lines[-num_lines:] if len(lines) > num_lines else lines
	except Exception as e:
		return [f"Ошибка чтения логов: {e}"]

def parse_log_line(line: str) -> Dict[str, str]:
	"""Парсит строку лога и возвращает уровень и сообщение"""
	line = line.strip()
	if not line:
		return {"level": "INFO", "message": ""}
	
	# Пытаемся определить уровень логирования
	for level in ["ERROR", "WARNING", "INFO", "DEBUG", "CRITICAL"]:
		if level in line.upper():
			return {"level": level, "message": line}
	
	return {"level": "INFO", "message": line}

@st.cache_data(ttl=300)
def load_backtest_results() -> Dict[str, Any]:
	"""Загружает результаты всех бэктестов из БД"""
	results = {}
	
	try:
		# Загружаем бэктесты из БД
		backtests = db.get_backtests(limit=50)
		
		for backtest_data in backtests:
			# Создаём ключ для совместимости с UI
			key = f"{backtest_data['symbol']}_{backtest_data['interval']}_{backtest_data['created_at'][:10]}.json"
			
			# Формируем данные в формате как раньше
			results[key] = {
				"symbol": backtest_data["symbol"],
				"interval": backtest_data["interval"],
				"start_date": backtest_data.get("start_date"),
				"end_date": backtest_data.get("end_date"),
				"initial_balance": backtest_data["initial_balance"],
				"final_balance": backtest_data["final_balance"],
				"total_return": backtest_data["total_return"],
				"roi_percent": backtest_data["total_return_percent"],
				"total_trades": backtest_data["total_trades"],
				"winning_trades": backtest_data["winning_trades"],
				"losing_trades": backtest_data["losing_trades"],
				"win_rate": backtest_data["win_rate"],
				"max_drawdown_percent": backtest_data["max_drawdown"],
				"sharpe_ratio": backtest_data["sharpe_ratio"],
				"profit_factor": backtest_data["profit_factor"],
				"stats": backtest_data.get("stats", {}),
				"trades": []  # Можно загрузить отдельно если нужно
			}
			
			# Загружаем детали если нужны trades
			full_backtest = db.get_backtest(backtest_data["id"])
			if full_backtest:
				results[key]["trades"] = full_backtest.get("trades", [])
		
	except Exception as e:
		st.warning(f"Ошибка загрузки бэктестов из БД: {e}")
	
	return results

def load_settings() -> Dict[str, Any]:
	"""Загружает настройки dashboard"""
	if os.path.exists(SETTINGS_FILE):
		try:
			with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
				return json.load(f)
		except:
			pass
	return {
		"kelly_enabled": True,
		"averaging_enabled": True,
		"pyramid_enabled": True,
		"kelly_fraction": 0.25,
		"max_averaging": 2,
		"averaging_drop": 5.0
	}

def save_settings(settings: Dict[str, Any]):
	"""Сохраняет настройки dashboard"""
	try:
		with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
			json.dump(settings, f, indent=2)
	except Exception as e:
		st.error(f"Ошибка сохранения настроек: {e}")

def format_price(price: float) -> str:
	"""Форматирует цену с правильным количеством знаков после запятой"""
	if price == 0:
		return "$0.00"
	elif price < 0.01:
		return f"${price:.8f}"
	elif price < 1:
		return f"${price:.6f}"
	elif price < 100:
		return f"${price:.4f}"
	else:
		return f"${price:.2f}"

def calculate_metrics(trades: List[Dict[str, Any]]) -> Dict[str, float]:
	"""Рассчитывает торговые метрики"""
	if not trades:
		return {}
	
	# Фильтруем только закрытые сделки с profit
	closed_trades = [t for t in trades if "profit" in t and t.get("profit") is not None]
	
	if not closed_trades:
		return {}
	
	profits = [t["profit"] for t in closed_trades]
	profit_percents = [t.get("profit_percent", 0) for t in closed_trades]
	
	winning_trades = [t for t in closed_trades if t["profit"] > 0]
	losing_trades = [t for t in closed_trades if t["profit"] <= 0]
	
	total_trades = len(closed_trades)
	win_count = len(winning_trades)
	loss_count = len(losing_trades)
	
	win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
	
	avg_win = np.mean([t["profit"] for t in winning_trades]) if winning_trades else 0
	avg_loss = np.mean([abs(t["profit"]) for t in losing_trades]) if losing_trades else 0
	
	total_wins = sum(t["profit"] for t in winning_trades)
	total_losses = abs(sum(t["profit"] for t in losing_trades))
	
	profit_factor = total_wins / total_losses if total_losses > 0 else 0
	
	# Sharpe Ratio (годовой)
	if len(profit_percents) > 1:
		# Фильтруем None значения
		valid_percents = [p for p in profit_percents if p is not None]
		if len(valid_percents) > 1:
			returns_std = np.std(valid_percents)
			avg_return = np.mean(valid_percents)
			sharpe = (avg_return / returns_std) * np.sqrt(252) if returns_std > 0 else 0
		else:
			sharpe = 0
	else:
		sharpe = 0
	
	# Sortino Ratio
	downside_returns = [p for p in profit_percents if p is not None and p < 0]
	if downside_returns and len(downside_returns) > 1:
		downside_std = np.std(downside_returns)
		avg_return = np.mean([p for p in profit_percents if p is not None])
		sortino = (avg_return / downside_std) * np.sqrt(252) if downside_std > 0 else 0
	else:
		sortino = 0
	
	# Max consecutive wins/losses
	max_consecutive_wins = 0
	max_consecutive_losses = 0
	current_wins = 0
	current_losses = 0
	
	for trade in closed_trades:
		if trade["profit"] > 0:
			current_wins += 1
			current_losses = 0
			max_consecutive_wins = max(max_consecutive_wins, current_wins)
		else:
			current_losses += 1
			current_wins = 0
			max_consecutive_losses = max(max_consecutive_losses, current_losses)
	
	return {
		"total_trades": total_trades,
		"win_rate": win_rate,
		"winning_trades": win_count,
		"losing_trades": loss_count,
		"avg_win": avg_win,
		"avg_loss": avg_loss,
		"profit_factor": profit_factor,
		"sharpe_ratio": sharpe,
		"sortino_ratio": sortino,
		"max_consecutive_wins": max_consecutive_wins,
		"max_consecutive_losses": max_consecutive_losses,
		"total_profit": sum(profits),
		"max_profit": max(profits) if profits else 0,
		"max_loss": min(profits) if profits else 0
	}

def calculate_drawdown(trades: List[Dict[str, Any]], initial_balance: float) -> pd.DataFrame:
	"""Рассчитывает просадку по времени"""
	if not trades:
		return pd.DataFrame()
	
	# Создаём equity curve
	balance = initial_balance
	equity_data = [{"time": None, "balance": initial_balance, "peak": initial_balance, "drawdown": 0}]
	
	for trade in trades:
		if "profit" in trade and trade["profit"] is not None:
			balance += trade["profit"]
		elif "invest_amount" in trade and trade.get("type") == "BUY":
			balance -= trade["invest_amount"]
		
		peak = max(equity_data[-1]["peak"], balance)
		drawdown = ((peak - balance) / peak) * 100 if peak > 0 else 0
		
		equity_data.append({
			"time": trade.get("time"),
			"balance": balance,
			"peak": peak,
			"drawdown": drawdown
		})
	
	return pd.DataFrame(equity_data)

# ====================================================================
# СТРАНИЦА 1: ОБЗОР
# ====================================================================

def overview_page(state: Dict[str, Any]):
	"""Страница обзора с KPI и equity curve"""
	st.header("📊 Обзор")
	
	if not state:
		st.warning("Нет данных для отображения. Запустите paper trading.")
		return
	
	# Рассчитываем стоимость активов
	balance = state.get("balance", 0)
	initial = state.get("initial_balance", 100)
	positions = state.get("positions", {})
	
	# Суммируем стоимость открытых позиций
	positions_value = 0
	for symbol, pos in positions.items():
		# Используем текущую цену из БД
		current_price = pos.get("current_price", pos.get("entry_price", 0))
		amount = pos.get("amount", 0)
		positions_value += current_price * amount
	
	total_equity = balance + positions_value
	total_profit = total_equity - initial
	profit_percent = (total_profit / initial) * 100 if initial > 0 else 0
	
	positions_count = len(positions)
	
	trades = state.get("trades_history", [])
	metrics = calculate_metrics(trades)
	win_rate = metrics.get("win_rate", 0)
	
	# KPI карточки - 5 колонок теперь
	col1, col2, col3, col4, col5 = st.columns(5)
	
	with col1:
		st.metric("Свободно", f"${balance:.2f}")
	
	with col2:
		st.metric("В позициях", f"${positions_value:.2f}")
	
	with col3:
		st.metric("Всего капитал", f"${total_equity:.2f}", f"{total_profit:+.2f} USD")
	
	with col4:
		st.metric("P&L", f"{profit_percent:+.2f}%", f"{total_profit:+.2f} USD")
	
	with col5:
		st.metric("Win Rate", f"{win_rate:.1f}%", f"{metrics.get('winning_trades', 0)}/{metrics.get('total_trades', 0)}")
	
	st.divider()
	
	# Equity Curve
	if trades:
		st.subheader("Equity Curve")
		
		# Сортируем сделки по времени (от старых к новым)
		sorted_trades = sorted(trades, key=lambda x: x.get("time", ""))
		
		balance_history = initial
		equity_data = []
		
		for trade in sorted_trades:
			time = trade.get("time")
			if "profit" in trade and trade["profit"] is not None:
				balance_history += trade["profit"]
			
			equity_data.append({
				"time": time,
				"balance": balance_history
			})
		
		if equity_data:
			df_equity = pd.DataFrame(equity_data)
			df_equity["time"] = pd.to_datetime(df_equity["time"])
			
			fig = go.Figure()
			fig.add_trace(go.Scatter(
				x=df_equity["time"],
				y=df_equity["balance"],
				mode='lines',
				name='Balance',
				line=dict(color='#00cc96', width=2),
				fill='tozeroy',
				fillcolor='rgba(0, 204, 150, 0.1)'
			))
			
			fig.add_hline(y=initial, line_dash="dash", line_color="gray")
			
			fig.update_layout(
				xaxis_title="Время",
				yaxis_title="Баланс (USD)",
				hovermode='x unified',
				height=400
			)
			
			st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
	
	st.divider()
	
	# Последние 5 сделок
	st.subheader("Последние сделки")
	
	if trades:
		recent_trades = trades[:5]  # Первые 5 (уже отсортированы по времени DESC)
		
		for trade in recent_trades:
			trade_type = trade.get("type", "N/A")
			symbol = trade.get("symbol", "N/A")
			price = trade.get("price", 0)
			profit = trade.get("profit", 0)
			profit_pct = trade.get("profit_percent", 0)
			time = trade.get("time", "N/A")
			
			# Цвет в зависимости от типа и прибыли
			if profit and profit > 0:
				color = "green"
				emoji = "✅"
			elif profit and profit < 0:
				color = "red"
				emoji = "❌"
			else:
				color = "gray"
				emoji = "⚪"
			
			if "AVERAGE" in trade_type:
				emoji = "🔄"
			
			col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])
			
			with col1:
				st.write(emoji)
			with col2:
				st.write(f"**{trade_type}**")
			with col3:
				st.write(f"{symbol} @ {format_price(price)}")
			with col4:
				if profit and profit != 0:
					st.markdown(f":{color}[{profit:+.2f} USD ({profit_pct:+.2f}%)]")
			with col5:
				st.write(time[:19] if len(time) > 19 else time)

# ====================================================================
# СТРАНИЦА 2: ТЕКУЩИЕ ПОЗИЦИИ
# ====================================================================

def positions_page(state: Dict[str, Any]):
	"""Страница текущих позиций"""
	st.header("💼 Текущие позиции")
	
	if not state:
		st.warning("Нет данных для отображения.")
		return
	
	positions = state.get("positions", {})
	
	if not positions:
		st.info("Нет открытых позиций.")
		return
	
	# Таблица позиций
	positions_data = []
	for symbol, pos in positions.items():
		entry_price = pos.get("entry_price", 0)
		amount = pos.get("amount", 0)
		avg_entry = pos.get("average_entry_price", entry_price)
		sl = pos.get("stop_loss_price", 0)
		tp = pos.get("take_profit_price", 0)
		entry_time = pos.get("entry_time", "")
		averaging_count = pos.get("averaging_count", 0)
		pyramid_mode = pos.get("pyramid_mode", False)
		
		# Считаем текущий P&L с реальной ценой из БД
		current_price = pos.get("current_price", entry_price)
		pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
		pnl_usd = (current_price - avg_entry) * amount if avg_entry > 0 else 0
		
		mode = "PYRAMID" if pyramid_mode else "AVERAGE"
		
		positions_data.append({
			"Символ": symbol,
			"Вход": format_price(entry_price),
			"Сейчас": format_price(current_price),
			"Средняя": format_price(avg_entry) if averaging_count > 0 else "-",
			"Количество": f"{amount:.4f}",
			"P&L": f"${pnl_usd:+.2f}",
			"P&L%": f"{pnl_pct:+.2f}%",
			"SL": format_price(sl),
			"TP": format_price(tp),
			"Докупания": f"{averaging_count} ({mode})" if averaging_count > 0 else "0",
			"Время": entry_time[:19] if len(entry_time) > 19 else entry_time
		})
	
	df_positions = pd.DataFrame(positions_data)
	st.dataframe(df_positions, width='stretch', hide_index=True)
	
	# Детали каждой позиции (expandable)
	st.divider()
	st.subheader("Детали позиций")
	
	for symbol, pos in positions.items():
		current_price = pos.get("current_price", pos.get("entry_price", 0))
		avg_entry = pos.get("average_entry_price", pos.get("entry_price", 0))
		amount = pos.get("amount", 0)
		pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
		pnl_usd = (current_price - avg_entry) * amount if avg_entry > 0 else 0
		
		with st.expander(f"📊 {symbol} • {format_price(current_price)} • {pnl_pct:+.2f}%"):
			col1, col2, col3 = st.columns(3)
			
			with col1:
				st.metric("Цена входа", format_price(pos.get('entry_price', 0)))
				st.metric("Текущая цена", format_price(current_price), f"{pnl_pct:+.2f}%")
				st.metric("Средняя цена", format_price(avg_entry))
			
			with col2:
				st.metric("Stop Loss", format_price(pos.get('stop_loss_price', 0)))
				st.metric("Take Profit", format_price(pos.get('take_profit_price', 0)))
				st.metric("P&L", f"${pnl_usd:+.2f}", f"{pnl_pct:+.2f}%")
			
			with col3:
				st.metric("Докупания", pos.get("averaging_count", 0))
				st.metric("Инвестировано", f"${pos.get('total_invested', pos.get('invest_amount', 0)):.2f}")
				st.metric("Количество", f"{amount:.4f}")
			
			# История докупаний
			averaging_entries = pos.get("averaging_entries", [])
			if averaging_entries:
				st.write("**История докупаний:**")
				for i, entry in enumerate(averaging_entries, 1):
					st.write(f"{i}. {entry.get('mode', 'N/A')} @ {format_price(entry.get('price', 0))} - {entry.get('reason', 'N/A')}")

# ====================================================================
# СТРАНИЦА 3: ИСТОРИЯ СДЕЛОК
# ====================================================================

def history_page(state: Dict[str, Any]):
	"""Страница истории сделок"""
	st.header("📜 История сделок")
	
	if not state:
		st.warning("Нет данных для отображения.")
		return
	
	trades = state.get("trades_history", [])
	
	if not trades:
		st.info("История сделок пуста.")
		return
	
	# Фильтры
	col1, col2, col3 = st.columns(3)
	
	symbols = list(set(t.get("symbol", "N/A") for t in trades))
	types = list(set(t.get("type", "N/A") for t in trades))
	
	with col1:
		filter_symbol = st.multiselect("Символ", ["Все"] + symbols, default=["Все"])
	
	with col2:
		filter_type = st.multiselect("Тип", ["Все"] + types, default=["Все"])
	
	with col3:
		filter_profit = st.selectbox("P&L", ["Все", "Прибыльные", "Убыточные"], index=0)
	
	# Применяем фильтры
	filtered_trades = trades
	
	if "Все" not in filter_symbol:
		filtered_trades = [t for t in filtered_trades if t.get("symbol") in filter_symbol]
	
	if "Все" not in filter_type:
		filtered_trades = [t for t in filtered_trades if t.get("type") in filter_type]
	
	if filter_profit == "Прибыльные":
		filtered_trades = [t for t in filtered_trades if t.get("profit", 0) > 0]
	elif filter_profit == "Убыточные":
		filtered_trades = [t for t in filtered_trades if t.get("profit", 0) < 0]
	
	# Таблица
	if filtered_trades:
		trades_data = []
		for trade in filtered_trades:
			profit = trade.get('profit')
			profit_pct = trade.get('profit_percent')
			trades_data.append({
				"Время": trade.get("time", "N/A")[:19],
				"Тип": trade.get("type", "N/A"),
				"Символ": trade.get("symbol", "N/A"),
				"Цена": format_price(trade.get('price', 0)),
				"Количество": f"{trade.get('amount', 0):.4f}",
				"P&L": f"${profit:.2f}" if profit is not None else "-",
				"P&L%": f"{profit_pct:.2f}%" if profit_pct is not None else "-",
				"Баланс": f"${trade.get('balance_after', 0):.2f}"
			})
		
		df_trades = pd.DataFrame(trades_data)
		st.dataframe(df_trades, width='stretch', hide_index=True, height=400)
		
		# Распределение P&L
		st.divider()
		st.subheader("Распределение P&L")
		
		closed_trades = [t for t in filtered_trades if "profit" in t]
		if closed_trades:
			profits = [t["profit"] for t in closed_trades]
			
			fig = go.Figure()
			fig.add_trace(go.Histogram(
				x=profits,
				nbinsx=30,
				marker_color='#00cc96',
				name='P&L'
			))
			
			fig.add_vline(x=0, line_dash="dash", line_color="red")
			
			fig.update_layout(
				xaxis_title="Прибыль/Убыток (USD)",
				yaxis_title="Количество сделок",
				showlegend=False,
				height=300
			)
			
			st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
	else:
		st.info("Нет сделок, соответствующих фильтрам.")
	
	# Экспорт CSV
	if st.button("📥 Экспорт в CSV"):
		df_export = pd.DataFrame(filtered_trades)
		csv = df_export.to_csv(index=False)
		st.download_button(
			label="Скачать CSV",
			data=csv,
			file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
			mime="text/csv"
		)

# ====================================================================
# СТРАНИЦА 4: МЕТРИКИ
# ====================================================================

def metrics_page(state: Dict[str, Any]):
	"""Страница метрик"""
	st.header("📈 Метрики")
	
	if not state:
		st.warning("Нет данных для отображения.")
		return
	
	trades = state.get("trades_history", [])
	
	if not trades:
		st.info("Нет данных для расчёта метрик.")
		return
	
	metrics = calculate_metrics(trades)
	
	if not metrics:
		st.info("Недостаточно данных для метрик.")
		return
	
	# Основные метрики
	st.subheader("Основные метрики")
	
	col1, col2, col3 = st.columns(3)
	
	with col1:
		st.metric("Total Trades", metrics.get("total_trades", 0))
		st.metric("Win Rate", f"{metrics.get('win_rate', 0):.2f}%")
		st.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
	
	with col2:
		st.metric("Winning Trades", metrics.get("winning_trades", 0))
		st.metric("Losing Trades", metrics.get("losing_trades", 0))
		st.metric("Avg Win", f"${metrics.get('avg_win', 0):.2f}")
	
	with col3:
		st.metric("Max Consecutive Wins", metrics.get("max_consecutive_wins", 0))
		st.metric("Max Consecutive Losses", metrics.get("max_consecutive_losses", 0))
		st.metric("Avg Loss", f"${metrics.get('avg_loss', 0):.2f}")
	
	st.divider()
	
	# Продвинутые метрики
	st.subheader("Продвинутые метрики")
	
	col1, col2, col3 = st.columns(3)
	
	with col1:
		sharpe = metrics.get("sharpe_ratio", 0)
		st.metric("Sharpe Ratio", f"{sharpe:.2f}")
	
	with col2:
		sortino = metrics.get("sortino_ratio", 0)
		st.metric("Sortino Ratio", f"{sortino:.2f}")
	
	with col3:
		# Maximum Drawdown
		dd_df = calculate_drawdown(trades, state.get("initial_balance", 100))
		if not dd_df.empty:
			max_dd = dd_df["drawdown"].max()
			st.metric("Max Drawdown", f"{max_dd:.2f}%")
		else:
			st.metric("Max Drawdown", "N/A")
	
	# Kelly Criterion рекомендация
	st.divider()
	st.subheader("Kelly Criterion")
	
	win_rate = metrics.get("win_rate", 0) / 100
	avg_win = abs(metrics.get("avg_win", 0))
	avg_loss = abs(metrics.get("avg_loss", 1))
	
	if avg_win > 0 and avg_loss > 0:
		kelly_full = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
		kelly_quarter = kelly_full * 0.25
		
		col1, col2 = st.columns(2)
		with col1:
			st.metric("Kelly (полный)", f"{kelly_full:.2%}")
		with col2:
			st.metric("Kelly (1/4)", f"{kelly_quarter:.2%}")
		
		if kelly_full > 0:
			st.success(f"✅ Рекомендуемый размер позиции: {kelly_quarter:.1%} от баланса")
		else:
			st.warning("⚠️ Kelly отрицательный - стратегия убыточна")
	
	st.divider()
	
	# Equity Drawdown Chart
	st.subheader("Equity Drawdown")
	
	# Сортируем сделки для правильного отображения
	dd_df = calculate_drawdown(sorted(trades, key=lambda x: x.get("time", "")), state.get("initial_balance", 100))
	
	if not dd_df.empty:
		fig = make_subplots(
			rows=2, cols=1,
			row_heights=[0.7, 0.3],
			shared_xaxes=True,
			vertical_spacing=0.05,
			subplot_titles=("Balance", "Drawdown %")
		)
		
		# Balance
		fig.add_trace(
			go.Scatter(x=dd_df.index, y=dd_df["balance"], name="Balance", line=dict(color='#00cc96')),
			row=1, col=1
		)
		
		fig.add_trace(
			go.Scatter(x=dd_df.index, y=dd_df["peak"], name="Peak", line=dict(color='gray', dash='dash')),
			row=1, col=1
		)
		
		# Drawdown
		fig.add_trace(
			go.Scatter(
				x=dd_df.index, y=dd_df["drawdown"], name="Drawdown", 
				fill='tozeroy', line=dict(color='red'), fillcolor='rgba(255, 0, 0, 0.2)'
			),
			row=2, col=1
		)
		
		fig.update_xaxes(title_text="Trades", row=2, col=1)
		fig.update_yaxes(title_text="USD", row=1, col=1)
		fig.update_yaxes(title_text="%", row=2, col=1)
		
		fig.update_layout(height=600, showlegend=True)
		
		st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
	
	# Box plot P&L
	st.divider()
	st.subheader("Распределение P&L")
	
	closed_trades = [t for t in trades if "profit" in t]
	if closed_trades:
		profits = [t["profit"] for t in closed_trades]
		
		fig = go.Figure()
		fig.add_trace(go.Box(y=profits, name="P&L", marker_color='#00cc96'))
		
		fig.update_layout(
			yaxis_title="Прибыль/Убыток (USD)",
			showlegend=False,
			height=400
		)
		
		st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

# ====================================================================
# СТРАНИЦА 5: БЭКТЕСТЫ
# ====================================================================

def backtests_page():
	"""Страница бэктестов"""
	st.header("🧪 Бэктесты")
	
	# Форма запуска нового бэктеста
	with st.expander("▶️ Запустить новый бэктест", expanded=False):
		st.subheader("Параметры бэктеста")
		
		col1, col2 = st.columns(2)
		
		with col1:
			# Популярные символы
			popular_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"]
			symbol_choice = st.selectbox("Выбрать символ", popular_symbols + ["Другой..."], index=0)
			
			if symbol_choice == "Другой...":
				symbol = st.text_input("Введите символ", value="BTCUSDT", help="Торговая пара")
			else:
				symbol = symbol_choice
			
			interval = st.selectbox("Таймфрейм", ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"], index=3)
			initial_balance = st.number_input("Начальный баланс", value=100.0, min_value=1.0, step=10.0)
		
		with col2:
			# Период
			days_back = st.number_input("Дней назад (от сегодня)", value=90, min_value=1, max_value=365, help="Сколько дней истории использовать")
			period_hours = days_back * 24  # Конвертируем в часы
			
			# Тип бэктеста
			backtest_type = st.selectbox("Тип бэктеста", 
				["Обычный", "Multi-Timeframe", "Walk-Forward"],
				help="Выберите тип бэктеста для запуска")
		
		# Кнопка запуска
		if st.button("🚀 Запустить бэктест", type="primary"):
			# Валидация символа
			if not symbol or len(symbol) < 4:
				st.error("❌ Укажите корректный символ (например: BTCUSDT)")
				return
			
			status_container = st.empty()
			progress_bar = st.progress(0)
			
			try:
				status_container.info(f"🔄 Подготовка бэктеста {symbol} {interval}...")
				progress_bar.progress(10)
				
				# Определяем скрипт и формируем команду с правильными аргументами
				if backtest_type == "Multi-Timeframe":
					# backtest_multitf.py: symbol interval lookback_days
					cmd = [
						sys.executable,
						"backtest_multitf.py",
						symbol,
						interval,
						str(days_back)
					]
				elif backtest_type == "Walk-Forward":
					# backtest_walkforward.py: symbol interval is_hours oos_hours balance
					is_hours = int(period_hours * 0.7)  # 70% для обучения
					oos_hours = int(period_hours * 0.3)  # 30% для теста
					cmd = [
						sys.executable,
						"backtest_walkforward.py",
						symbol,
						interval,
						str(is_hours),
						str(oos_hours),
						str(initial_balance)
					]
				else:
					# backtest.py: symbol interval period_hours start_balance
					cmd = [
						sys.executable,
						"backtest.py",
						symbol,
						interval,
						str(period_hours),
						str(initial_balance)
					]
				
				status_container.info(f"🔄 Загрузка данных и выполнение бэктеста...")
				progress_bar.progress(30)
				
				# Запускаем процесс
				result = subprocess.run(
					cmd,
					capture_output=True,
					text=True,
					timeout=300  # 5 минут таймаут
				)
				
				progress_bar.progress(90)
				
				if result.returncode == 0:
					progress_bar.progress(100)
					status_container.success(f"✅ Бэктест завершён успешно!")
					
					# Показываем вывод (последние 1000 символов)
					if result.stdout:
						with st.expander("📋 Вывод бэктеста"):
							st.code(result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout, language="text")
					
					st.balloons()
					
					# Обновляем страницу
					st.rerun()
				else:
					progress_bar.empty()
					status_container.error(f"❌ Ошибка выполнения бэктеста")
					st.code(result.stderr if result.stderr else "Неизвестная ошибка", language="text")
					
			except subprocess.TimeoutExpired:
				progress_bar.empty()
				status_container.error("❌ Таймаут выполнения (>5 минут)")
				st.warning("Попробуйте уменьшить период или выбрать больший таймфрейм")
			except Exception as e:
				progress_bar.empty()
				status_container.error(f"❌ Ошибка: {e}")
				st.code(traceback.format_exc(), language="text")
		
		st.info("💡 Бэктест сохранится в БД и появится в списке ниже")
	
	st.divider()
	
	# Список существующих бэктестов
	col1, col2 = st.columns([3, 1])
	with col1:
		st.subheader("📂 Результаты бэктестов")
	with col2:
		if st.button("🗑️ Очистить все", help="Удалить все бэктесты из БД"):
			try:
				# Очистка всех бэктестов
				count = db.clear_backtests()
				st.success(f"✅ Удалено {count} бэктестов")
				st.rerun()
			except Exception as e:
				st.error(f"Ошибка: {e}")
	
	backtests = load_backtest_results()
	
	if not backtests:
		st.info("Нет результатов бэктестов.")
		return
	
	# Выбор файла
	selected_files = st.multiselect(
		"Выберите бэктесты для сравнения",
		list(backtests.keys()),
		default=[list(backtests.keys())[0]] if backtests else []
	)
	
	if not selected_files:
		st.info("Выберите хотя бы один бэктест.")
		return
	
	# Показываем метрики для каждого
	for filename in selected_files:
		with st.expander(f"📊 {filename}", expanded=True):
			data = backtests[filename]
			
			# Проверяем структуру данных (может быть список или словарь)
			if isinstance(data, list):
				# Старый формат - просто список сделок
				trades = data
				initial = 100.0
				# Сортируем сделки по времени
				sorted_trades = sorted(trades, key=lambda x: x.get("time", ""))
				# Рассчитываем метрики из сделок
				metrics = calculate_metrics(sorted_trades)
				
				# Рассчитываем equity
				balance = initial
				for trade in sorted_trades:
					if "profit" in trade and trade["profit"] is not None:
						balance += trade["profit"]
				final_balance = balance
				roi = ((final_balance - initial) / initial) * 100 if initial > 0 else 0
				
				col1, col2, col3, col4 = st.columns(4)
				
				with col1:
					st.metric("ROI", f"{roi:.2f}%")
				
				with col2:
					st.metric("Win Rate", f"{metrics.get('win_rate', 0):.2f}%")
				
				with col3:
					st.metric("Trades", metrics.get('total_trades', 0))
				
				with col4:
					st.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
				
				# Используем sorted_trades дальше
				trades = sorted_trades
				
			else:
				# Новый формат - словарь с метриками
				# Метрики
				col1, col2, col3, col4 = st.columns(4)
				
				with col1:
					roi = data.get("roi_percent", 0)
					st.metric("ROI", f"{roi:.2f}%")
				
				with col2:
					win_rate = data.get("win_rate", 0)
					st.metric("Win Rate", f"{win_rate:.2f}%")
				
				with col3:
					total_trades = data.get("total_trades", 0)
					st.metric("Trades", total_trades)
				
				with col4:
					sharpe = data.get("sharpe_ratio", 0)
					st.metric("Sharpe", f"{sharpe:.2f}")
				
				trades = data.get("trades", [])
				initial = data.get("initial_balance", 100)
			
			# Equity curve
			if trades:
				# Сортируем сделки по времени
				sorted_trades = sorted(trades, key=lambda x: x.get("time", ""))
				
				balance_history = [initial]
				balance = initial
				
				for trade in sorted_trades:
					if "balance_after" in trade:
						balance_history.append(trade["balance_after"])
					elif "profit" in trade and trade["profit"] is not None:
						balance += trade["profit"]
						balance_history.append(balance)
				
				if len(balance_history) > 1:
					fig = go.Figure()
					fig.add_trace(go.Scatter(
						y=balance_history,
						mode='lines',
						name=filename,
						line=dict(width=2)
					))
					
					fig.add_hline(y=initial, line_dash="dash", line_color="gray")
					
					fig.update_layout(
						xaxis_title="Сделки",
						yaxis_title="Баланс (USD)",
						height=300
					)
					
					st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
			else:
				st.info("Нет данных о сделках в этом бэктесте")
	
	# Сравнение
	if len(selected_files) > 1:
		st.divider()
		st.subheader("Сравнение")
		
		comparison_data = []
		for filename in selected_files:
			data = backtests[filename]
			
			# Обработка разных форматов
			if isinstance(data, list):
				trades = data
				initial = 100.0
				# Сортируем сделки для правильного расчёта
				sorted_trades = sorted(trades, key=lambda x: x.get("time", ""))
				metrics = calculate_metrics(sorted_trades)
				
				balance = initial
				for trade in sorted_trades:
					if "profit" in trade:
						balance += trade["profit"]
				roi = ((balance - initial) / initial) * 100 if initial > 0 else 0
				
				comparison_data.append({
					"Файл": filename,
					"ROI%": roi,
					"Win Rate%": metrics.get("win_rate", 0),
					"Trades": metrics.get("total_trades", 0),
					"Sharpe": metrics.get("sharpe_ratio", 0),
					"Max DD%": 0
				})
			else:
				comparison_data.append({
					"Файл": filename,
					"ROI%": data.get("roi_percent", 0),
					"Win Rate%": data.get("win_rate", 0),
					"Trades": data.get("total_trades", 0),
					"Sharpe": data.get("sharpe_ratio", 0),
					"Max DD%": data.get("max_drawdown_percent", 0)
				})
		
		df_comparison = pd.DataFrame(comparison_data)
		st.dataframe(df_comparison, width='stretch', hide_index=True)
		
		# Overlay equity curves
		st.subheader("Overlay Equity Curves")
		
		fig = go.Figure()
		
		for filename in selected_files:
			data = backtests[filename]
			
			# Обработка разных форматов
			if isinstance(data, list):
				trades = data
				initial = 100.0
			else:
				trades = data.get("trades", [])
				initial = data.get("initial_balance", 100)
			
			if trades:
				# Сортируем сделки по времени
				sorted_trades = sorted(trades, key=lambda x: x.get("time", ""))
				
				balance_history = [initial]
				balance = initial
				
				for trade in sorted_trades:
					if "balance_after" in trade:
						balance_history.append(trade["balance_after"])
					elif "profit" in trade and trade["profit"] is not None:
						balance += trade["profit"]
						balance_history.append(balance)
				
				if len(balance_history) > 1:
					fig.add_trace(go.Scatter(
						y=balance_history,
						mode='lines',
						name=filename,
						line=dict(width=2)
					))
		
		fig.update_layout(
			xaxis_title="Сделки",
			yaxis_title="Баланс (USD)",
			height=400
		)
		
		st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

# ====================================================================
# СТРАНИЦА 6: НАСТРОЙКИ
# ====================================================================

def settings_page():
	"""Страница настроек"""
	st.header("⚙️ Настройки")
	
	settings = load_settings()
	
	st.subheader("Управление стратегией")
	
	# Toggles
	col1, col2, col3 = st.columns(3)
	
	with col1:
		kelly_enabled = st.toggle("Kelly Criterion", value=settings.get("kelly_enabled", True))
	
	with col2:
		averaging_enabled = st.toggle("Averaging", value=settings.get("averaging_enabled", True))
	
	with col3:
		pyramid_enabled = st.toggle("Pyramid Mode", value=settings.get("pyramid_enabled", True))
	
	st.divider()
	
	# Параметры
	st.subheader("Параметры")
	
	col1, col2, col3 = st.columns(3)
	
	with col1:
		kelly_fraction = st.slider(
			"Kelly Fraction",
			min_value=0.1,
			max_value=0.5,
			value=settings.get("kelly_fraction", 0.25),
			step=0.05,
			help="Процент от полного Kelly (0.25 = 25%)"
		)
	
	with col2:
		max_averaging = st.slider(
			"Max Averaging Attempts",
			min_value=0,
			max_value=5,
			value=settings.get("max_averaging", 2),
			step=1,
			help="Максимальное количество докупаний на позицию"
		)
	
	with col3:
		averaging_drop = st.slider(
			"Averaging Drop %",
			min_value=1.0,
			max_value=10.0,
			value=settings.get("averaging_drop", 5.0),
			step=0.5,
			help="Процент падения для триггера усреднения"
		)
	
	# Сохранение
	if st.button("💾 Сохранить настройки"):
		new_settings = {
			"kelly_enabled": kelly_enabled,
			"averaging_enabled": averaging_enabled,
			"pyramid_enabled": pyramid_enabled,
			"kelly_fraction": kelly_fraction,
			"max_averaging": max_averaging,
			"averaging_drop": averaging_drop
		}
		save_settings(new_settings)
		st.success("✅ Настройки сохранены!")
		st.info("⚠️ Обновите config.py для применения изменений к боту")
	
	st.divider()
	
	# Действия
	st.subheader("Действия")
	
	col1, col2 = st.columns(2)
	
	with col1:
		st.write("**Сброс Paper Trading**")
		confirm = st.checkbox("Подтвердите сброс (все данные будут удалены)")
		if st.button("🔄 Сбросить", type="primary") and confirm:
				try:
					# Сброс БД
					with db.session_scope() as session:
						# Удаляем все данные
						session.query(PaperTradingState).delete()
						session.commit()
					
					st.success("✅ Paper trading сброшен!")
					st.rerun()
				except Exception as e:
					st.error(f"Ошибка: {e}")
	
	with col2:
		st.write("**Информация**")
		try:
			# Статистика БД
			state = db.get_paper_state()
			if state:
				st.info(f"Записей в БД: {state.total_trades} сделок")
			else:
				st.info("БД не инициализирована")
		except Exception as e:
			st.warning(f"Ошибка получения данных: {e}")

# ====================================================================
# СТРАНИЦА: ЛОГИ
# ====================================================================

def logs_page():
	"""Страница просмотра логов"""
	st.title("📋 Логи системы")
	
	# Показываем текущий файл логов
	log_file = get_latest_log_file()
	if log_file:
		st.caption(f"📄 Текущий файл: `{log_file}`")
	else:
		st.warning("Файлы логов не найдены")
	
	# Настройки отображения
	col1, col2, col3 = st.columns([2, 2, 1])
	
	with col1:
		num_lines = st.select_slider(
			"Количество строк",
			options=[20, 50, 100, 200, 500],
			value=100
		)
	
	with col2:
		log_level_filter = st.multiselect(
			"Фильтр по уровню",
			options=["ERROR", "WARNING", "INFO", "DEBUG", "CRITICAL"],
			default=["ERROR", "WARNING", "INFO"]
		)
	
	with col3:
		if st.button("🔄 Обновить"):
			st.rerun()
	
	st.divider()
	
	# Чтение логов
	log_lines = read_recent_logs(num_lines)
	
	if not log_lines or log_lines == ["Лог-файл не найден"]:
		st.warning("Лог-файл не найден или пуст")
		st.info(f"Ожидается файл в директории: `{LOG_DIR}/log_*.txt`")
		log_file = get_latest_log_file()
		if log_file:
			st.info(f"Последний лог: `{log_file}`")
		return
	
	# Парсинг и фильтрация
	parsed_logs = [parse_log_line(line) for line in log_lines]
	filtered_logs = [log for log in parsed_logs if log["level"] in log_level_filter or not log_level_filter]
	
	# Статистика
	col1, col2, col3, col4 = st.columns(4)
	
	error_count = sum(1 for log in parsed_logs if "ERROR" in log["level"])
	warning_count = sum(1 for log in parsed_logs if "WARNING" in log["level"])
	info_count = sum(1 for log in parsed_logs if "INFO" in log["level"])
	
	with col1:
		st.metric("Всего строк", len(log_lines))
	with col2:
		st.metric("Ошибки", error_count, delta=None if error_count == 0 else f"-{error_count}", delta_color="inverse")
	with col3:
		st.metric("Предупреждения", warning_count, delta=None if warning_count == 0 else f"-{warning_count}", delta_color="inverse")
	with col4:
		st.metric("Инфо", info_count)
	
	st.divider()
	
	# Вкладки для разных представлений
	tab1, tab2 = st.tabs(["📜 Консоль", "📊 Таблица"])
	
	with tab1:
		# Консольное отображение с цветовой кодировкой
		st.subheader("Последние события")
		
		log_container = st.container()
		with log_container:
			for log in reversed(filtered_logs):  # Новые сверху
				message = log["message"]
				level = log["level"]
				
				if "ERROR" in level or "CRITICAL" in level:
					st.error(message)
				elif "WARNING" in level:
					st.warning(message)
				elif "DEBUG" in level:
					st.code(message, language=None)
				else:
					st.text(message)
	
	with tab2:
		# Табличное отображение
		if filtered_logs:
			# Создаём DataFrame
			df_logs = pd.DataFrame(filtered_logs)
			
			# Добавляем цвет в зависимости от уровня
			def color_level(val):
				if "ERROR" in val or "CRITICAL" in val:
					return 'background-color: #ff4444; color: white'
				elif "WARNING" in val:
					return 'background-color: #ffaa00; color: black'
				elif "DEBUG" in val:
					return 'background-color: #aaaaaa; color: white'
				return ''
			
			# Отображаем таблицу (без стилей для совместимости)
			st.dataframe(df_logs, width='stretch', height=600)
		else:
			st.info("Нет логов соответствующих фильтру")
	
	# Дополнительная информация
	st.divider()
	
	with st.expander("ℹ️ Информация о логировании"):
		st.markdown("""
		**Уровни логирования:**
		- 🔴 **ERROR/CRITICAL**: Критические ошибки требующие внимания
		- 🟡 **WARNING**: Предупреждения о потенциальных проблемах
		- 🔵 **INFO**: Информационные сообщения о работе системы
		- ⚪ **DEBUG**: Детальная отладочная информация
		
		**Полезные паттерны для поиска:**
		- Ошибки API: `ERROR.*API`
		- Открытие позиций: `BUY.*@`
		- Закрытие позиций: `SELL.*@`
		- Averaging: `AVERAGING`
		- Kelly: `Kelly`
		""")
	
	# Кнопка очистки логов (опасно!)
	st.divider()
	with st.expander("⚠️ Опасная зона"):
		st.warning("Очистка всех лог-файлов необратима!")
		if st.button("🗑️ Очистить все логи", type="secondary"):
			try:
				if os.path.exists(LOG_DIR):
					log_files = [f for f in os.listdir(LOG_DIR) if f.startswith("log_") and f.endswith(".txt")]
					for log_file in log_files:
						os.remove(os.path.join(LOG_DIR, log_file))
					st.success(f"Удалено {len(log_files)} лог-файлов")
				else:
					st.warning("Директория логов не найдена")
				st.rerun()
			except Exception as e:
				st.error(f"Ошибка очистки: {e}")

# ====================================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ====================================================================

def render_bot_status_widget():
	"""Отображает виджет состояния бота в sidebar"""
	status = check_bot_status()
	
	st.subheader("🤖 Состояние бота")
	
	# Статус работы
	if status["is_running"]:
		st.success("✅ Работает")
	else:
		st.error("❌ Не работает")
	
	# Последнее обновление
	# Приоритет: время UI обновления > время БД обновления
	ui_refresh_time = st.session_state.get('last_ui_refresh')
	
	if ui_refresh_time:
		# Показываем время последнего обновления UI
		age = (datetime.now() - ui_refresh_time).total_seconds()
		if age < 60:
			age_str = f"{int(age)} сек назад"
		elif age < 3600:
			age_str = f"{int(age/60)} мин назад"
		else:
			age_str = f"{int(age/3600)} ч назад"
		st.caption(f"📝 Обновлено: {age_str}")
	elif status["last_update"]:
		# Показываем время обновления БД
		age = status["state_file_age"]
		if age < 60:
			age_str = f"{int(age)} сек назад"
		elif age < 3600:
			age_str = f"{int(age/60)} мин назад"
		else:
			age_str = f"{int(age/3600)} ч назад"
		st.caption(f"📝 Обновлено: {age_str}")
	else:
		st.caption("📝 Нет данных")
	
	# Uptime (если процесс найден)
	if status["uptime"]:
		hours = int(status["uptime"].total_seconds() / 3600)
		minutes = int((status["uptime"].total_seconds() % 3600) / 60)
		st.caption(f"⏱️ Uptime: {hours}ч {minutes}м")
	
	# Индикаторы файлов
	col1, col2 = st.columns(2)
	with col1:
		if status["state_file_exists"]:
			st.caption("💾 БД ✓")
		else:
			st.caption("💾 БД ✗")
	with col2:
		if status["log_file_exists"]:
			st.caption("📋 Logs ✓")
		else:
			st.caption("📋 Logs ✗")
	
	# Информация о кэше
	st.caption(f"🔄 Кэш: 60с TTL")

def main():
	"""Главная функция dashboard"""
	
	# Боковая панель
	with st.sidebar:
		st.title("📈 TradeBot")
		st.divider()
		
		# Индикатор состояния бота
		render_bot_status_widget()
		st.divider()
		
		# Навигация
		page = st.radio(
			"Навигация",
			["📊 Обзор", "💼 Текущие позиции", "📜 История сделок", 
			 "📈 Метрики", "🧪 Бэктесты", "📋 Логи", "⚙️ Настройки"]
		)
		
		st.divider()
		
		# Автообновление
		auto_refresh = st.checkbox("Автообновление (60с)", value=False)
		
		# Кнопка обновления
		if st.button("🔄 Обновить сейчас"):
			# Запоминаем время обновления UI
			st.session_state.last_ui_refresh = datetime.now()
			st.rerun()
		
		# Автообновление через session state
		if auto_refresh:
			# Используем session state для отслеживания времени последнего обновления
			if 'last_refresh' not in st.session_state:
				st.session_state.last_refresh = time.time()
			
			current_time = time.time()
			time_since_refresh = current_time - st.session_state.last_refresh
			
			# Показываем прогресс
			progress = min(time_since_refresh / 60, 1.0)
			st.progress(progress, text=f"Автообновление через {int(60 - time_since_refresh)}с")
			
			# Обновляем каждые 60 секунд
			if time_since_refresh >= 60:
				st.session_state.last_refresh = current_time
				st.session_state.last_ui_refresh = datetime.now()
				st.rerun()
	
	# Загрузка состояния
	state = load_paper_trader_state()
	
	# Роутинг страниц
	if page == "📊 Обзор":
		overview_page(state)
	elif page == "💼 Текущие позиции":
		positions_page(state)
	elif page == "📜 История сделок":
		history_page(state)
	elif page == "📈 Метрики":
		metrics_page(state)
	elif page == "🧪 Бэктесты":
		backtests_page()
	elif page == "📋 Логи":
		logs_page()
	elif page == "⚙️ Настройки":
		settings_page()

if __name__ == "__main__":
	main()

