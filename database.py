"""
База данных для TradeBot
Поддерживает SQLite (по умолчанию) и PostgreSQL
"""
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
from sqlalchemy import (
	create_engine, Column, Integer, Float, String, Boolean, 
	DateTime, Text, ForeignKey, JSON, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.pool import StaticPool
from logger import logger

# База для моделей
Base = declarative_base()

# ====================================================================
# МОДЕЛИ
# ====================================================================

class PaperTradingState(Base):
	"""Состояние paper trading"""
	__tablename__ = "paper_trading_state"
	
	id = Column(Integer, primary_key=True)
	initial_balance = Column(Float, nullable=False)
	balance = Column(Float, nullable=False)
	is_running = Column(Boolean, default=False)
	start_time = Column(DateTime)
	total_trades = Column(Integer, default=0)
	winning_trades = Column(Integer, default=0)
	losing_trades = Column(Integer, default=0)
	total_commission = Column(Float, default=0.0)
	stop_loss_triggers = Column(Integer, default=0)
	take_profit_triggers = Column(Integer, default=0)
	trailing_stop_triggers = Column(Integer, default=0)
	updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Position(Base):
	"""Открытая позиция"""
	__tablename__ = "positions"
	
	id = Column(Integer, primary_key=True)
	symbol = Column(String(20), nullable=False, unique=True, index=True)
	entry_price = Column(Float, nullable=False)
	amount = Column(Float, nullable=False)
	entry_time = Column(DateTime, nullable=False)
	signal_strength = Column(Integer)
	invest_amount = Column(Float, nullable=False)
	entry_commission = Column(Float)
	atr = Column(Float, default=0.0)
	stop_loss_price = Column(Float)
	stop_loss_percent = Column(Float)
	take_profit_price = Column(Float)
	partial_closed = Column(Boolean, default=False)
	max_price = Column(Float)
	partial_close_profit = Column(Float, default=0.0)
	original_amount = Column(Float)
	averaging_count = Column(Integer, default=0)
	average_entry_price = Column(Float)
	pyramid_mode = Column(Boolean, default=False)
	total_invested = Column(Float)
	created_at = Column(DateTime, default=datetime.now)
	updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
	
	# Связи
	averaging_entries = relationship("AveragingEntry", back_populates="position", cascade="all, delete-orphan")


class AveragingEntry(Base):
	"""Запись о докупании позиции"""
	__tablename__ = "averaging_entries"
	
	id = Column(Integer, primary_key=True)
	position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
	price = Column(Float, nullable=False)
	amount = Column(Float, nullable=False)
	invest_amount = Column(Float, nullable=False)
	commission = Column(Float)
	mode = Column(String(20))  # AVERAGE_DOWN, PYRAMID_UP
	reason = Column(String(50))
	time = Column(DateTime, default=datetime.now)
	
	# Связь
	position = relationship("Position", back_populates="averaging_entries")
	
	__table_args__ = (Index('idx_averaging_position', 'position_id'),)


class TradeHistory(Base):
	"""История сделок"""
	__tablename__ = "trades_history"
	
	id = Column(Integer, primary_key=True)
	type = Column(String(20), nullable=False)  # BUY, SELL, STOP-LOSS, etc.
	symbol = Column(String(20), nullable=False, index=True)
	price = Column(Float, nullable=False)
	amount = Column(Float, nullable=False)
	time = Column(DateTime, default=datetime.now, index=True)
	
	# Для открытия
	invest_amount = Column(Float)
	commission = Column(Float)
	signal_strength = Column(Integer)
	balance_after = Column(Float)
	
	# Для закрытия
	sell_value = Column(Float)
	profit = Column(Float)
	profit_percent = Column(Float)
	holding_time = Column(String(50))
	
	# Для частичного закрытия
	closed_percent = Column(Float)
	
	# Для докупания
	reason = Column(String(100))
	averaging_count = Column(Integer)
	average_entry_price = Column(Float)
	
	# Метаданные
	extra_data = Column(JSON)  # Дополнительные данные
	
	# v5.5 сигнальные метаданные
	bullish_votes = Column(Integer, default=0)
	bearish_votes = Column(Integer, default=0)
	votes_delta = Column(Integer, default=0)
	position_size_percent = Column(Float)
	reasons = Column(JSON)  # Список причин сигнала
	
	__table_args__ = (
		Index('idx_trade_symbol_time', 'symbol', 'time'),
		Index('idx_trade_type', 'type'),
	)


class TrackedSymbol(Base):
	"""Отслеживаемые символы"""
	__tablename__ = "tracked_symbols"
	
	id = Column(Integer, primary_key=True)
	symbol = Column(String(20), nullable=False, unique=True, index=True)
	added_at = Column(DateTime, default=datetime.now)
	is_active = Column(Boolean, default=True)


class BotSettings(Base):
	"""Настройки бота"""
	__tablename__ = "bot_settings"
	
	id = Column(Integer, primary_key=True)
	chat_id = Column(Integer)
	poll_interval = Column(Integer, default=60)
	volatility_window = Column(Integer, default=10)
	volatility_threshold = Column(Float, default=0.05)
	updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Signal(Base):
	"""Лог сигналов"""
	__tablename__ = "signals"
	
	id = Column(Integer, primary_key=True)
	symbol = Column(String(20), nullable=False, index=True)
	interval = Column(String(10), nullable=False)
	signal = Column(String(10), nullable=False)  # BUY, SELL, HOLD
	price = Column(Float, nullable=False)
	reasons = Column(Text)  # JSON array
	time = Column(DateTime, default=datetime.now, index=True)
	
	# Дополнительная информация
	signal_strength = Column(Integer)
	market_regime = Column(String(20))
	adx = Column(Float)
	rsi = Column(Float)
	atr = Column(Float)
	extra_data = Column(JSON)
	
	__table_args__ = (
		Index('idx_signal_symbol_time', 'symbol', 'time'),
		Index('idx_signal_type', 'signal'),
	)


class BayesianSignalStats(Base):
	"""Статистика сигналов для Bayesian модели"""
	__tablename__ = "bayesian_signal_stats"
	
	id = Column(Integer, primary_key=True)
	signal_signature = Column(String(200), nullable=False, unique=True, index=True)
	total_signals = Column(Integer, default=0)
	profitable_signals = Column(Integer, default=0)
	losing_signals = Column(Integer, default=0)
	total_profit = Column(Float, default=0.0)
	total_loss = Column(Float, default=0.0)
	avg_profit = Column(Float, default=0.0)
	avg_loss = Column(Float, default=0.0)
	created_at = Column(DateTime, default=datetime.now)
	updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
	
	__table_args__ = (
		Index('idx_bayesian_signature', 'signal_signature'),
	)


class BayesianPendingSignal(Base):
	"""Ожидающие завершения сигналы"""
	__tablename__ = "bayesian_pending_signals"
	
	id = Column(Integer, primary_key=True)
	signal_signature = Column(String(200), nullable=False, index=True)
	signal_type = Column(String(10), nullable=False)  # BUY, SELL
	entry_price = Column(Float, nullable=False)
	created_at = Column(DateTime, default=datetime.now, index=True)
	
	__table_args__ = (
		Index('idx_pending_signature', 'signal_signature'),
		Index('idx_pending_created', 'created_at'),
	)


class Backtest(Base):
	"""Результаты бэктестов"""
	__tablename__ = "backtests"
	
	id = Column(Integer, primary_key=True)
	symbol = Column(String(20), nullable=False, index=True)
	interval = Column(String(10), nullable=False)
	start_date = Column(DateTime)
	end_date = Column(DateTime)
	created_at = Column(DateTime, default=datetime.now, index=True)
	
	# Результаты
	initial_balance = Column(Float)
	final_balance = Column(Float)
	total_return = Column(Float)
	total_return_percent = Column(Float)
	total_trades = Column(Integer)
	winning_trades = Column(Integer)
	losing_trades = Column(Integer)
	win_rate = Column(Float)
	max_drawdown = Column(Float)
	sharpe_ratio = Column(Float)
	profit_factor = Column(Float)
	avg_trade_duration = Column(String(50))
	
	# Статистика
	stats = Column(JSON)
	config = Column(JSON)  # Конфигурация стратегии
	
	# Связи
	trades = relationship("BacktestTrade", back_populates="backtest", cascade="all, delete-orphan")
	
	__table_args__ = (Index('idx_backtest_symbol_time', 'symbol', 'created_at'),)


class BacktestTrade(Base):
	"""Сделки в бэктесте"""
	__tablename__ = "backtest_trades"
	
	id = Column(Integer, primary_key=True)
	backtest_id = Column(Integer, ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False)
	
	type = Column(String(20), nullable=False)
	symbol = Column(String(20), nullable=False)
	price = Column(Float, nullable=False)
	amount = Column(Float)
	time = Column(DateTime)
	
	profit = Column(Float)
	profit_percent = Column(Float)
	balance_after = Column(Float)
	
	extra_data = Column(JSON)
	
	# Связь
	backtest = relationship("Backtest", back_populates="trades")
	
	__table_args__ = (Index('idx_backtest_trade', 'backtest_id'),)


# ====================================================================
# DATABASE MANAGER
# ====================================================================

class DatabaseManager:
	"""Менеджер базы данных"""
	
	def __init__(self, database_url: str = None):
		"""
		Инициализация БД
		
		Args:
			database_url: URL подключения к БД
				SQLite: sqlite:///data/tradebot.db
				PostgreSQL: postgresql://user:password@localhost/dbname
		"""
		if database_url is None:
			database_url = os.getenv("DATABASE_URL", "sqlite:///data/tradebot.db")
		
		self.database_url = database_url
		
		# Настройки для SQLite
		if database_url.startswith("sqlite"):
			self.engine = create_engine(
				database_url,
				connect_args={"check_same_thread": False},
				poolclass=StaticPool,
				echo=False
			)
		else:
			# PostgreSQL и другие
			self.engine = create_engine(database_url, echo=False, pool_pre_ping=True)
		
		# Session factory
		self.SessionLocal = scoped_session(sessionmaker(
			bind=self.engine, 
			autocommit=False, 
			autoflush=False,
			expire_on_commit=False  # Не отключать объекты после коммита
		))
		
		logger.info(f"База данных инициализирована: {database_url}")
	
	def create_tables(self):
		"""Создать все таблицы"""
		Base.metadata.create_all(bind=self.engine)
		logger.info("Таблицы созданы")
	
	def drop_tables(self):
		"""Удалить все таблицы"""
		Base.metadata.drop_all(bind=self.engine)
		logger.info("Таблицы удалены")
	
	@contextmanager
	def session_scope(self):
		"""Контекстный менеджер для работы с сессией"""
		session = self.SessionLocal()
		try:
			yield session
			session.commit()
		except Exception as e:
			session.rollback()
			logger.error(f"Ошибка БД: {e}")
			raise
		finally:
			session.close()
	
	# ================================================================
	# PAPER TRADING STATE
	# ================================================================
	
	def get_paper_state(self) -> Optional[PaperTradingState]:
		"""Получить состояние paper trading"""
		with self.session_scope() as session:
			return session.query(PaperTradingState).first()
	
	def save_paper_state(
		self,
		initial_balance: float,
		balance: float,
		is_running: bool,
		start_time: datetime,
		stats: Dict[str, Any]
	) -> PaperTradingState:
		"""Сохранить состояние paper trading"""
		with self.session_scope() as session:
			state = session.query(PaperTradingState).first()
			
			if state:
				# Обновляем
				state.initial_balance = initial_balance
				state.balance = balance
				state.is_running = is_running
				state.start_time = start_time
				state.total_trades = stats.get("total_trades", 0)
				state.winning_trades = stats.get("winning_trades", 0)
				state.losing_trades = stats.get("losing_trades", 0)
				state.total_commission = stats.get("total_commission", 0.0)
				state.stop_loss_triggers = stats.get("stop_loss_triggers", 0)
				state.take_profit_triggers = stats.get("take_profit_triggers", 0)
				state.trailing_stop_triggers = stats.get("trailing_stop_triggers", 0)
			else:
				# Создаём новую запись
				state = PaperTradingState(
					initial_balance=initial_balance,
					balance=balance,
					is_running=is_running,
					start_time=start_time,
					total_trades=stats.get("total_trades", 0),
					winning_trades=stats.get("winning_trades", 0),
					losing_trades=stats.get("losing_trades", 0),
					total_commission=stats.get("total_commission", 0.0),
					stop_loss_triggers=stats.get("stop_loss_triggers", 0),
					take_profit_triggers=stats.get("take_profit_triggers", 0),
					trailing_stop_triggers=stats.get("trailing_stop_triggers", 0),
				)
				session.add(state)
			
			session.commit()
			return state
	
	# ================================================================
	# POSITIONS
	# ================================================================
	
	def get_position(self, symbol: str) -> Optional[Position]:
		"""Получить позицию по символу"""
		with self.session_scope() as session:
			pos = session.query(Position).filter_by(symbol=symbol).first()
			if pos:
				# Отключаем от сессии для использования вне контекста
				session.expunge(pos)
			return pos
	
	def get_all_positions(self) -> List[Position]:
		"""Получить все открытые позиции"""
		with self.session_scope() as session:
			positions = session.query(Position).all()
			# Отключаем от сессии
			for pos in positions:
				session.expunge(pos)
			return positions
	
	def save_position(self, position_data: Dict[str, Any]) -> Position:
		"""Сохранить/обновить позицию"""
		with self.session_scope() as session:
			symbol = position_data["symbol"]
			pos = session.query(Position).filter_by(symbol=symbol).first()
			
			if pos:
				# Обновляем
				for key, value in position_data.items():
					if key != "averaging_entries" and hasattr(pos, key):
						setattr(pos, key, value)
			else:
				# Создаём новую
				pos = Position(**{k: v for k, v in position_data.items() if k != "averaging_entries"})
				session.add(pos)
			
			session.commit()
			session.refresh(pos)
			session.expunge(pos)
			return pos
	
	def delete_position(self, symbol: str):
		"""Удалить позицию"""
		with self.session_scope() as session:
			pos = session.query(Position).filter_by(symbol=symbol).first()
			if pos:
				session.delete(pos)
				session.commit()
	
	# ================================================================
	# AVERAGING ENTRIES
	# ================================================================
	
	def get_averaging_entries(self, position_id: int) -> List[Dict[str, Any]]:
		"""Получить все докупания для позиции"""
		with self.session_scope() as session:
			entries = session.query(AveragingEntry).filter_by(position_id=position_id).all()
			return [
				{
					"price": e.price,
					"amount": e.amount,
					"invest_amount": e.invest_amount,
					"commission": e.commission,
					"mode": e.mode,
					"reason": e.reason,
					"time": e.time.isoformat() if e.time else None
				}
				for e in entries
			]
	
	def add_averaging_entry(
		self,
		position_id: int,
		price: float,
		amount: float,
		invest_amount: float,
		commission: float,
		mode: str,
		reason: str,
		time: datetime
	):
		"""Добавить запись о докупании"""
		with self.session_scope() as session:
			entry = AveragingEntry(
				position_id=position_id,
				price=price,
				amount=amount,
				invest_amount=invest_amount,
				commission=commission,
				mode=mode,
				reason=reason,
				time=time
			)
			session.add(entry)
			session.commit()
	
	# ================================================================
	# TRADE HISTORY
	# ================================================================
	
	def add_trade(self, trade_data: Dict[str, Any]):
		"""Добавить запись в историю сделок"""
		with self.session_scope() as session:
			# Преобразуем time из строки в datetime если нужно
			if "time" in trade_data and isinstance(trade_data["time"], str):
				trade_data["time"] = datetime.fromisoformat(trade_data["time"])
			
			# Фильтруем только существующие поля для обратной совместимости
			valid_fields = {
				'type', 'symbol', 'price', 'amount', 'time', 'invest_amount', 
				'commission', 'signal_strength', 'balance_after', 'sell_value', 
				'profit', 'profit_percent', 'holding_time', 'closed_percent', 
				'reason', 'averaging_count', 'average_entry_price', 'extra_data',
				'bullish_votes', 'bearish_votes', 'votes_delta', 'position_size_percent', 'reasons'
			}
			
			filtered_data = {k: v for k, v in trade_data.items() if k in valid_fields}
			
			trade = TradeHistory(**filtered_data)
			session.add(trade)
			session.commit()
	
	def get_trades_history(
		self,
		symbol: Optional[str] = None,
		limit: int = 100,
		trade_type: Optional[str] = None
	) -> List[Dict[str, Any]]:
		"""Получить историю сделок"""
		with self.session_scope() as session:
			query = session.query(TradeHistory)
			
			if symbol:
				query = query.filter_by(symbol=symbol)
			
			if trade_type:
				query = query.filter_by(type=trade_type)
			
			trades = query.order_by(TradeHistory.time.desc()).limit(limit).all()
			
			return [
				{
					"id": t.id,
					"type": t.type,
					"symbol": t.symbol,
					"price": t.price,
					"amount": t.amount,
					"time": t.time.isoformat() if t.time else None,
					"invest_amount": t.invest_amount,
					"commission": t.commission,
					"signal_strength": t.signal_strength,
					"balance_after": t.balance_after,
					"sell_value": t.sell_value,
					"profit": t.profit,
					"profit_percent": t.profit_percent,
					"holding_time": t.holding_time,
					"closed_percent": t.closed_percent,
					"reason": t.reason,
					"averaging_count": t.averaging_count,
					"average_entry_price": t.average_entry_price,
					"extra_data": t.extra_data,
					# v5.5 новые поля (с безопасным доступом)
					"bullish_votes": getattr(t, 'bullish_votes', 0),
					"bearish_votes": getattr(t, 'bearish_votes', 0),
					"votes_delta": getattr(t, 'votes_delta', 0),
					"position_size_percent": getattr(t, 'position_size_percent', None),
					"reasons": getattr(t, 'reasons', None)
				}
				for t in trades
			]
	
	# ================================================================
	# TRACKED SYMBOLS
	# ================================================================
	
	def get_tracked_symbols(self) -> List[str]:
		"""Получить список отслеживаемых символов"""
		with self.session_scope() as session:
			symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
			return [s.symbol for s in symbols]
	
	def add_tracked_symbol(self, symbol: str):
		"""Добавить символ для отслеживания"""
		with self.session_scope() as session:
			existing = session.query(TrackedSymbol).filter_by(symbol=symbol).first()
			if existing:
				existing.is_active = True
			else:
				sym = TrackedSymbol(symbol=symbol)
				session.add(sym)
			session.commit()
	
	def remove_tracked_symbol(self, symbol: str):
		"""Удалить символ из отслеживания"""
		with self.session_scope() as session:
			sym = session.query(TrackedSymbol).filter_by(symbol=symbol).first()
			if sym:
				sym.is_active = False
				session.commit()
	
	# ================================================================
	# BOT SETTINGS
	# ================================================================
	
	def get_bot_settings(self) -> Optional[BotSettings]:
		"""Получить настройки бота"""
		with self.session_scope() as session:
			settings = session.query(BotSettings).first()
			if settings:
				session.expunge(settings)
			return settings
	
	def save_bot_settings(
		self,
		chat_id: int,
		poll_interval: int,
		volatility_window: int,
		volatility_threshold: float
	) -> BotSettings:
		"""Сохранить настройки бота"""
		with self.session_scope() as session:
			settings = session.query(BotSettings).first()
			
			if settings:
				settings.chat_id = chat_id
				settings.poll_interval = poll_interval
				settings.volatility_window = volatility_window
				settings.volatility_threshold = volatility_threshold
			else:
				settings = BotSettings(
					chat_id=chat_id,
					poll_interval=poll_interval,
					volatility_window=volatility_window,
					volatility_threshold=volatility_threshold
				)
				session.add(settings)
			
			session.commit()
			session.expunge(settings)
			return settings
	
	# ================================================================
	# SIGNALS
	# ================================================================
	
	def add_signal(
		self,
		symbol: str,
		interval: str,
		signal: str,
		price: float,
		reasons: List[str],
		signal_strength: int = None,
		market_regime: str = None,
		adx: float = None,
		rsi: float = None,
		atr: float = None,
		extra_data: Dict = None
	):
		"""Добавить сигнал в лог"""
		with self.session_scope() as session:
			import json
			sig = Signal(
				symbol=symbol,
				interval=interval,
				signal=signal,
				price=price,
				reasons=json.dumps(reasons, ensure_ascii=False),
				signal_strength=signal_strength,
				market_regime=market_regime,
				adx=adx,
				rsi=rsi,
				atr=atr,
				extra_data=extra_data
			)
			session.add(sig)
			session.commit()
	
	def get_signals(
		self,
		symbol: Optional[str] = None,
		limit: int = 100,
		signal_type: Optional[str] = None
	) -> List[Dict[str, Any]]:
		"""Получить логи сигналов"""
		with self.session_scope() as session:
			import json
			query = session.query(Signal)
			
			if symbol:
				query = query.filter_by(symbol=symbol)
			
			if signal_type:
				query = query.filter_by(signal=signal_type)
			
			signals = query.order_by(Signal.time.desc()).limit(limit).all()
			
			return [
				{
					"id": s.id,
					"symbol": s.symbol,
					"interval": s.interval,
					"signal": s.signal,
					"price": s.price,
					"reasons": json.loads(s.reasons) if s.reasons else [],
					"time": s.time.isoformat() if s.time else None,
					"signal_strength": s.signal_strength,
					"market_regime": s.market_regime,
					"adx": s.adx,
					"rsi": s.rsi,
					"atr": s.atr,
					"extra_data": s.extra_data
				}
				for s in signals
			]
	
	# ================================================================
	# BACKTESTS
	# ================================================================
	
	def add_backtest(self, backtest_data: Dict[str, Any]) -> int:
		"""Добавить результаты бэктеста"""
		with self.session_scope() as session:
			# Удаляем trades из основных данных
			trades = backtest_data.pop("trades", [])
			
			# Преобразуем даты
			for date_field in ["start_date", "end_date"]:
				if date_field in backtest_data and isinstance(backtest_data[date_field], str):
					backtest_data[date_field] = datetime.fromisoformat(backtest_data[date_field])
			
			backtest = Backtest(**backtest_data)
			session.add(backtest)
			session.flush()  # Получаем ID
			
			# Добавляем сделки
			for trade_data in trades:
				if "time" in trade_data and isinstance(trade_data["time"], str):
					trade_data["time"] = datetime.fromisoformat(trade_data["time"])
				
				trade = BacktestTrade(backtest_id=backtest.id, **trade_data)
				session.add(trade)
			
			session.commit()
			return backtest.id
	
	def get_backtest(self, backtest_id: int) -> Optional[Dict[str, Any]]:
		"""Получить результаты бэктеста"""
		with self.session_scope() as session:
			backtest = session.query(Backtest).filter_by(id=backtest_id).first()
			
			if not backtest:
				return None
			
			trades = session.query(BacktestTrade).filter_by(backtest_id=backtest_id).all()
			
			return {
				"id": backtest.id,
				"symbol": backtest.symbol,
				"interval": backtest.interval,
				"start_date": backtest.start_date.isoformat() if backtest.start_date else None,
				"end_date": backtest.end_date.isoformat() if backtest.end_date else None,
				"created_at": backtest.created_at.isoformat() if backtest.created_at else None,
				"initial_balance": backtest.initial_balance,
				"final_balance": backtest.final_balance,
				"total_return": backtest.total_return,
				"total_return_percent": backtest.total_return_percent,
				"total_trades": backtest.total_trades,
				"winning_trades": backtest.winning_trades,
				"losing_trades": backtest.losing_trades,
				"win_rate": backtest.win_rate,
				"max_drawdown": backtest.max_drawdown,
				"sharpe_ratio": backtest.sharpe_ratio,
				"profit_factor": backtest.profit_factor,
				"avg_trade_duration": backtest.avg_trade_duration,
				"stats": backtest.stats,
				"config": backtest.config,
				"trades": [
					{
						"type": t.type,
						"symbol": t.symbol,
						"price": t.price,
						"amount": t.amount,
						"time": t.time.isoformat() if t.time else None,
						"profit": t.profit,
						"profit_percent": t.profit_percent,
						"balance_after": t.balance_after,
						"extra_data": t.extra_data
					}
					for t in trades
				]
			}
	
	def get_backtests(
		self,
		symbol: Optional[str] = None,
		limit: int = 50
	) -> List[Dict[str, Any]]:
		"""Получить список бэктестов"""
		with self.session_scope() as session:
			query = session.query(Backtest)
			
			if symbol:
				query = query.filter_by(symbol=symbol)
			
			backtests = query.order_by(Backtest.created_at.desc()).limit(limit).all()
			
			return [
				{
					"id": b.id,
					"symbol": b.symbol,
					"interval": b.interval,
					"start_date": b.start_date.isoformat() if b.start_date else None,
					"end_date": b.end_date.isoformat() if b.end_date else None,
					"created_at": b.created_at.isoformat() if b.created_at else None,
					"final_balance": b.final_balance,
					"total_return_percent": b.total_return_percent,
					"total_trades": b.total_trades,
					"win_rate": b.win_rate,
					"max_drawdown": b.max_drawdown,
					"sharpe_ratio": b.sharpe_ratio
				}
				for b in backtests
			]
	
	def clear_backtests(self) -> int:
		"""Удалить все бэктесты из БД"""
		with self.session_scope() as session:
			# Сначала удаляем все сделки
			trades_count = session.query(BacktestTrade).delete()
			# Затем удаляем сами бэктесты
			backtests_count = session.query(Backtest).delete()
			session.commit()
			return backtests_count
	
	# ================================================================
	# BAYESIAN STATISTICS
	# ================================================================
	
	def get_bayesian_stats(self, signal_signature: str) -> Optional[Dict[str, Any]]:
		"""Получить статистику сигнала"""
		with self.session_scope() as session:
			stats = session.query(BayesianSignalStats).filter_by(signal_signature=signal_signature).first()
			if not stats:
				return None
			
			return {
				"signal_signature": stats.signal_signature,
				"total": stats.total_signals,
				"profitable": stats.profitable_signals,
				"losing": stats.losing_signals,
				"total_profit": stats.total_profit,
				"total_loss": stats.total_loss,
				"avg_profit": stats.avg_profit,
				"avg_loss": stats.avg_loss,
				"created_at": stats.created_at.isoformat() if stats.created_at else None,
				"updated_at": stats.updated_at.isoformat() if stats.updated_at else None
			}
	
	def update_bayesian_stats(self, signal_signature: str, stats_data: Dict[str, Any]):
		"""Обновить статистику сигнала"""
		with self.session_scope() as session:
			stats = session.query(BayesianSignalStats).filter_by(signal_signature=signal_signature).first()
			
			if stats:
				# Обновляем существующую запись
				for key, value in stats_data.items():
					if hasattr(stats, key):
						setattr(stats, key, value)
				stats.updated_at = datetime.now()
			else:
				# Создаем новую запись
				stats_data["signal_signature"] = signal_signature
				stats = BayesianSignalStats(**stats_data)
				session.add(stats)
			
			session.commit()
	
	def add_pending_signal(self, signal_signature: str, signal_type: str, entry_price: float) -> int:
		"""Добавить ожидающий сигнал"""
		with self.session_scope() as session:
			pending = BayesianPendingSignal(
				signal_signature=signal_signature,
				signal_type=signal_type,
				entry_price=entry_price
			)
			session.add(pending)
			session.commit()
			return pending.id
	
	def remove_pending_signal(self, signal_signature: str, entry_price: float):
		"""Удалить ожидающий сигнал"""
		with self.session_scope() as session:
			# Удаляем по сигнатуре и цене входа (точное совпадение)
			session.query(BayesianPendingSignal).filter_by(
				signal_signature=signal_signature,
				entry_price=entry_price
			).delete()
			session.commit()
	
	def get_pending_signals(self, signal_signature: str) -> List[Dict[str, Any]]:
		"""Получить все ожидающие сигналы для сигнатуры"""
		with self.session_scope() as session:
			pending = session.query(BayesianPendingSignal).filter_by(signal_signature=signal_signature).all()
			return [
				{
					"id": p.id,
					"signal_type": p.signal_type,
					"entry_price": p.entry_price,
					"created_at": p.created_at.isoformat() if p.created_at else None
				}
				for p in pending
			]
	
	def get_all_bayesian_stats(self) -> List[Dict[str, Any]]:
		"""Получить всю статистику Bayesian модели"""
		with self.session_scope() as session:
			stats = session.query(BayesianSignalStats).all()
			return [
				{
					"signal_signature": s.signal_signature,
					"total": s.total_signals,
					"profitable": s.profitable_signals,
					"losing": s.losing_signals,
					"total_profit": s.total_profit,
					"total_loss": s.total_loss,
					"avg_profit": s.avg_profit,
					"avg_loss": s.avg_loss,
					"created_at": s.created_at.isoformat() if s.created_at else None,
					"updated_at": s.updated_at.isoformat() if s.updated_at else None
				}
				for s in stats
			]
	
	def clear_bayesian_stats(self):
		"""Очистить всю Bayesian статистику"""
		with self.session_scope() as session:
			session.query(BayesianPendingSignal).delete()
			session.query(BayesianSignalStats).delete()
			session.commit()


# Глобальный экземпляр
db = DatabaseManager()

