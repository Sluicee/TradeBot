import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import numpy as np
from scipy import stats as scipy_stats

# Настройка страницы
st.set_page_config(
	page_title="TradeBot Dashboard",
	page_icon="📈",
	layout="wide",
	initial_sidebar_state="expanded"
)

# Константы
STATE_FILE = "paper_trading_state.json"
SETTINGS_FILE = "dashboard_settings.json"
BACKTESTS_DIR = "backtests"

# ====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ====================================================================

@st.cache_data(ttl=60)
def load_paper_trader_state() -> Optional[Dict[str, Any]]:
	"""Загружает состояние paper trader"""
	if not os.path.exists(STATE_FILE):
		return None
	try:
		with open(STATE_FILE, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception as e:
		st.error(f"Ошибка загрузки состояния: {e}")
		return None

@st.cache_data(ttl=300)
def load_backtest_results() -> Dict[str, Any]:
	"""Загружает результаты всех бэктестов"""
	results = {}
	if not os.path.exists(BACKTESTS_DIR):
		return results
	
	for filename in os.listdir(BACKTESTS_DIR):
		if filename.endswith(".json"):
			try:
				with open(os.path.join(BACKTESTS_DIR, filename), "r", encoding="utf-8") as f:
					results[filename] = json.load(f)
			except Exception as e:
				st.warning(f"Не удалось загрузить {filename}: {e}")
	
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
		returns_std = np.std(profit_percents)
		avg_return = np.mean(profit_percents)
		sharpe = (avg_return / returns_std) * np.sqrt(252) if returns_std > 0 else 0
	else:
		sharpe = 0
	
	# Sortino Ratio
	downside_returns = [p for p in profit_percents if p < 0]
	if downside_returns and len(downside_returns) > 1:
		downside_std = np.std(downside_returns)
		sortino = (np.mean(profit_percents) / downside_std) * np.sqrt(252) if downside_std > 0 else 0
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
		if "profit" in trade:
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
	
	# KPI карточки
	col1, col2, col3, col4 = st.columns(4)
	
	balance = state.get("balance", 0)
	initial = state.get("initial_balance", 100)
	total_profit = balance - initial
	profit_percent = (total_profit / initial) * 100 if initial > 0 else 0
	
	positions_count = len(state.get("positions", {}))
	
	trades = state.get("trades_history", [])
	metrics = calculate_metrics(trades)
	win_rate = metrics.get("win_rate", 0)
	
	with col1:
		st.metric("Баланс", f"${balance:.2f}", f"{total_profit:+.2f} USD")
	
	with col2:
		st.metric("P&L", f"{profit_percent:+.2f}%", f"{total_profit:+.2f} USD")
	
	with col3:
		st.metric("Win Rate", f"{win_rate:.1f}%", f"{metrics.get('winning_trades', 0)}/{metrics.get('total_trades', 0)}")
	
	with col4:
		st.metric("Позиции", positions_count, f"из {state.get('max_positions', 3)}")
	
	st.divider()
	
	# Equity Curve
	if trades:
		st.subheader("Equity Curve")
		
		balance_history = initial
		equity_data = []
		
		for trade in trades:
			time = trade.get("time")
			if "profit" in trade:
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
			
			fig.add_hline(y=initial, line_dash="dash", line_color="gray", annotation_text="Initial")
			
			fig.update_layout(
				xaxis_title="Время",
				yaxis_title="Баланс (USD)",
				hovermode='x unified',
				height=400
			)
			
			st.plotly_chart(fig, use_container_width=True)
	
	st.divider()
	
	# Последние 5 сделок
	st.subheader("Последние сделки")
	
	if trades:
		recent_trades = trades[-5:][::-1]  # Последние 5 в обратном порядке
		
		for trade in recent_trades:
			trade_type = trade.get("type", "N/A")
			symbol = trade.get("symbol", "N/A")
			price = trade.get("price", 0)
			profit = trade.get("profit", 0)
			profit_pct = trade.get("profit_percent", 0)
			time = trade.get("time", "N/A")
			
			# Цвет в зависимости от типа и прибыли
			if profit > 0:
				color = "green"
				emoji = "✅"
			elif profit < 0:
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
				st.write(f"{symbol} @ ${price:.2f}")
			with col4:
				if profit != 0:
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
		
		# Считаем текущий P&L (нужна текущая цена, пока используем entry)
		current_price = entry_price  # TODO: получить реальную цену
		pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
		
		mode = "PYRAMID" if pyramid_mode else "AVERAGE"
		
		positions_data.append({
			"Символ": symbol,
			"Вход": f"${entry_price:.2f}",
			"Средняя": f"${avg_entry:.2f}" if averaging_count > 0 else "-",
			"Количество": f"{amount:.4f}",
			"P&L%": f"{pnl_pct:+.2f}%",
			"SL": f"${sl:.2f}",
			"TP": f"${tp:.2f}",
			"Докупания": f"{averaging_count} ({mode})" if averaging_count > 0 else "0",
			"Время": entry_time[:19] if len(entry_time) > 19 else entry_time
		})
	
	df_positions = pd.DataFrame(positions_data)
	st.dataframe(df_positions, use_container_width=True, hide_index=True)
	
	# Детали каждой позиции (expandable)
	st.divider()
	st.subheader("Детали позиций")
	
	for symbol, pos in positions.items():
		with st.expander(f"📊 {symbol}"):
			col1, col2, col3 = st.columns(3)
			
			with col1:
				st.metric("Цена входа", f"${pos.get('entry_price', 0):.2f}")
				st.metric("Средняя цена", f"${pos.get('average_entry_price', pos.get('entry_price', 0)):.2f}")
			
			with col2:
				st.metric("Stop Loss", f"${pos.get('stop_loss_price', 0):.2f}")
				st.metric("Take Profit", f"${pos.get('take_profit_price', 0):.2f}")
			
			with col3:
				st.metric("Докупания", pos.get("averaging_count", 0))
				st.metric("Инвестировано", f"${pos.get('total_invested', pos.get('invest_amount', 0)):.2f}")
			
			# История докупаний
			averaging_entries = pos.get("averaging_entries", [])
			if averaging_entries:
				st.write("**История докупаний:**")
				for i, entry in enumerate(averaging_entries, 1):
					st.write(f"{i}. {entry.get('mode', 'N/A')} @ ${entry.get('price', 0):.2f} - {entry.get('reason', 'N/A')}")

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
		filter_symbol = st.multiselect("Символ", ["Все"] + symbols, default="Все")
	
	with col2:
		filter_type = st.multiselect("Тип", ["Все"] + types, default="Все")
	
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
			trades_data.append({
				"Время": trade.get("time", "N/A")[:19],
				"Тип": trade.get("type", "N/A"),
				"Символ": trade.get("symbol", "N/A"),
				"Цена": f"${trade.get('price', 0):.2f}",
				"Количество": f"{trade.get('amount', 0):.4f}",
				"P&L": f"${trade.get('profit', 0):.2f}" if "profit" in trade else "-",
				"P&L%": f"{trade.get('profit_percent', 0):.2f}%" if "profit_percent" in trade else "-",
				"Баланс": f"${trade.get('balance_after', 0):.2f}"
			})
		
		df_trades = pd.DataFrame(trades_data)
		st.dataframe(df_trades, use_container_width=True, hide_index=True, height=400)
		
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
			
			st.plotly_chart(fig, use_container_width=True)
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
		
		st.plotly_chart(fig, use_container_width=True)
	
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
		
		st.plotly_chart(fig, use_container_width=True)

# ====================================================================
# СТРАНИЦА 5: БЭКТЕСТЫ
# ====================================================================

def backtests_page():
	"""Страница бэктестов"""
	st.header("🧪 Бэктесты")
	
	backtests = load_backtest_results()
	
	if not backtests:
		st.info("Нет результатов бэктестов. Запустите backtest.py")
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
				# Рассчитываем метрики из сделок
				metrics = calculate_metrics(trades)
				
				# Рассчитываем equity
				balance = initial
				for trade in trades:
					if "profit" in trade:
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
				balance_history = [initial]
				balance = initial
				
				for trade in trades:
					if "balance_after" in trade:
						balance_history.append(trade["balance_after"])
					elif "profit" in trade:
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
					
					st.plotly_chart(fig, use_container_width=True)
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
				metrics = calculate_metrics(trades)
				
				balance = initial
				for trade in trades:
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
		st.dataframe(df_comparison, use_container_width=True, hide_index=True)
		
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
				balance_history = [initial]
				balance = initial
				
				for trade in trades:
					if "balance_after" in trade:
						balance_history.append(trade["balance_after"])
					elif "profit" in trade:
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
		
		st.plotly_chart(fig, use_container_width=True)

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
		if st.button("🔄 Сбросить", type="primary"):
			if os.path.exists(STATE_FILE):
				confirm = st.checkbox("Подтвердите сброс (все данные будут удалены)")
				if confirm:
					try:
						os.remove(STATE_FILE)
						st.success("✅ Paper trading сброшен!")
						st.cache_data.clear()
					except Exception as e:
						st.error(f"Ошибка: {e}")
	
	with col2:
		st.write("**Информация**")
		if os.path.exists(STATE_FILE):
			file_size = os.path.getsize(STATE_FILE) / 1024  # KB
			st.info(f"Размер файла состояния: {file_size:.2f} KB")

# ====================================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ====================================================================

def main():
	"""Главная функция dashboard"""
	
	# Боковая панель
	with st.sidebar:
		st.title("📈 TradeBot")
		st.divider()
		
		# Навигация
		page = st.radio(
			"Навигация",
			["📊 Обзор", "💼 Текущие позиции", "📜 История сделок", 
			 "📈 Метрики", "🧪 Бэктесты", "⚙️ Настройки"]
		)
		
		st.divider()
		
		# Автообновление
		auto_refresh = st.checkbox("Автообновление (60с)", value=False)
		
		if auto_refresh:
			import time
			time.sleep(60)
			st.rerun()
		
		if st.button("🔄 Обновить сейчас"):
			st.cache_data.clear()
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
	elif page == "⚙️ Настройки":
		settings_page()

if __name__ == "__main__":
	main()

