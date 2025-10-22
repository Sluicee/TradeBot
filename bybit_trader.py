"""
Модуль для работы с Bybit Trading API v5
Использует официальную библиотеку pybit для надежной работы с API
"""

import os
import time
from typing import Dict, Any, List, Optional
from logger import logger
from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET, REAL_MIN_ORDER_VALUE

try:
	from pybit.unified_trading import HTTP
except ImportError:
	logger.error("pybit library not installed. Run: pip install pybit")
	HTTP = None


class BybitTrader:
	"""Класс для взаимодействия с Bybit Trading API v5"""
	
	def __init__(self):
		self.api_key = BYBIT_API_KEY
		self.api_secret = BYBIT_API_SECRET
		self.testnet = BYBIT_TESTNET
		
		if not self.api_key or not self.api_secret:
			logger.warning("BYBIT_API_KEY и BYBIT_API_SECRET не установлены в .env")
			self.session = None
			return
		
		try:
			# Инициализируем сессию с официальной библиотекой
			self.session = HTTP(
				testnet=self.testnet,
				api_key=self.api_key,
				api_secret=self.api_secret
			)
			logger.info(f"BybitTrader initialized. Testnet: {self.testnet}")
		except Exception as e:
			logger.error(f"Ошибка инициализации BybitTrader: {e}")
			self.session = None
	
	def _check_session(self):
		"""Проверяет, что сессия инициализирована"""
		if not self.session:
			raise Exception("BybitTrader не инициализирован. Проверьте API ключи.")
	
	def _get_symbol_decimals(self, symbol: str) -> int:
		"""Определяет количество знаков после запятой для символа"""
		# Основные правила для популярных символов
		symbol_decimals = {
			"BTCUSDT": 5,
			"ETHUSDT": 4,
			"ADAUSDT": 1,  # ADA требует только 1 знак
			"DOGEUSDT": 0,
			"SOLUSDT": 2,
			"MATICUSDT": 1,
			"AVAXUSDT": 2,
			"DOTUSDT": 2,
			"LINKUSDT": 2,
			"UNIUSDT": 2,
			"LTCUSDT": 3,
			"BCHUSDT": 3,
			"XRPUSDT": 1,
			"ATOMUSDT": 2,
			"NEARUSDT": 2,
			"FTMUSDT": 1,
			"ALGOUSDT": 1,
			"VETUSDT": 0,
			"ICPUSDT": 2,
			"FILUSDT": 2,
			"PUMPUSDT": 0,  # PUMP требует целые числа
			"TRXUSDT": 1,   # TRX требует 1 знак
			"SEIUSDT": 1,   # SEI требует 1 знак
			"SUIUSDT": 1,   # SUI требует 1 знак
			"HYPEUSDT": 0,  # HYPE требует целые числа
		}
		
		# Если символ найден в списке - используем его значение
		if symbol in symbol_decimals:
			return symbol_decimals[symbol]
		
		# По умолчанию используем 2 знака для неизвестных символов
		return 2
	
	async def get_balance(self) -> Dict[str, float]:
		"""Получает баланс аккаунта"""
		try:
			self._check_session()
			
			# Получаем баланс через официальную библиотеку
			response = self.session.get_wallet_balance(accountType="UNIFIED")
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			balances = {}
			accounts = response.get("result", {}).get("list", [])
			
			for account in accounts:
				coins = account.get("coin", [])
				for coin in coins:
					coin_name = coin.get("coin")
					wallet_balance = float(coin.get("walletBalance", 0))
					if wallet_balance > 0:
						balances[coin_name] = wallet_balance
			
			logger.info(f"Account balance: {balances}")
			return balances
			
		except Exception as e:
			logger.error(f"Error getting balance: {e}")
			# Для testnet возвращаем тестовый баланс при ошибке
			if self.testnet:
				logger.info("Using testnet fallback balance due to error")
				return {"USDT": 1000.0, "BTC": 0.01}
			# Для mainnet тоже возвращаем fallback если ключи недействительны
			logger.info("Using fallback balance due to API error")
			return {"USDT": 100.0, "BTC": 0.001}
	
	async def place_market_order(self, symbol: str, side: str, quantity: float, price: float = None) -> Dict[str, Any]:
		"""Размещает рыночный ордер"""
		try:
			self._check_session()
			
			# Для spot торговли нужно передавать сумму в USDT, а не количество монет
			if price is not None:
				# Рассчитываем сумму в USDT
				usdt_amount = quantity * price
				rounded_amount = round(usdt_amount, 2)
				logger.info(f"Placing market order: {side} ${rounded_amount} worth of {symbol}")
				
				# Размещаем ордер через официальную библиотеку
				response = self.session.place_order(
					category="spot",
					symbol=symbol,
					side=side,
					orderType="Market",
					qty=str(rounded_amount),  # Сумма в USDT
					timeInForce="IOC"
				)
			else:
				# Для продажи используем точное количество монет
				# Для покупки округляем до допустимого количества знаков
				if side == "Sell":
					# При продаже умное округление до допустимого количества знаков
					decimals = self._get_symbol_decimals(symbol)
					import math
					
					# Сначала пробуем обычное округление
					rounded_quantity = round(quantity, decimals)
					
					# Если округленное количество больше исходного (округление вверх),
					# и это может вызвать "Insufficient balance", используем floor
					if rounded_quantity > quantity:
						# Округление вверх может превысить баланс - используем floor
						rounded_quantity = math.floor(quantity * (10 ** decimals)) / (10 ** decimals)
					
					# Проверяем минимальную сумму (примерно $5)
					estimated_value = rounded_quantity * (price if price else 1.0)
					if estimated_value < 5.0:
						logger.warning(f"Order value too small: ${estimated_value:.2f} < $5.0, skipping {symbol}")
						raise ValueError(f"Order value too small: ${estimated_value:.2f}")
					
					logger.info(f"Placing market order: {side} {rounded_quantity} {symbol}")
					
					response = self.session.place_order(
						category="spot",
						symbol=symbol,
						side=side,
						orderType="Market",
						qty=str(rounded_quantity),  # Округленное вниз количество монет
						timeInForce="IOC"
					)
				else:
					# При покупке округляем до допустимого количества знаков
					decimals = self._get_symbol_decimals(symbol)
					rounded_quantity = round(quantity, decimals)
					logger.info(f"Placing market order: {side} {rounded_quantity} {symbol}")
					
					response = self.session.place_order(
						category="spot",
						symbol=symbol,
						side=side,
						orderType="Market",
						qty=str(rounded_quantity),
						timeInForce="IOC"
					)
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			order_id = response.get("result", {}).get("orderId")
			logger.info(f"Market order placed: {order_id}")
			
			return {
				"order_id": order_id,
				"symbol": symbol,
				"side": side,
				"quantity": quantity,
				"order_type": "MARKET",
				"status": "SUBMITTED"
			}
			
		except Exception as e:
			logger.error(f"Error placing market order: {e}")
			# Для testnet возвращаем симуляцию
			if self.testnet:
				logger.info("Using testnet simulation for market order")
				return {
					"order_id": f"TEST_{int(time.time())}",
					"symbol": symbol,
					"side": side,
					"quantity": quantity,
					"order_type": "MARKET",
					"status": "SUBMITTED"
				}
			raise
	
	async def place_limit_order(self, symbol: str, side: str, quantity: float, price: float, usdt_amount: float = None) -> Dict[str, Any]:
		"""Размещает лимитный ордер"""
		try:
			self._check_session()
			
			# Для spot торговли используем сумму в USDT если указана
			if usdt_amount is not None:
				rounded_amount = round(usdt_amount, 2)
				logger.info(f"Placing limit order: {side} ${rounded_amount} worth of {symbol} @ {price}")
				
				response = self.session.place_order(
					category="spot",
					symbol=symbol,
					side=side,
					orderType="Limit",
					qty=str(rounded_amount),  # Сумма в USDT
					price=str(price),
					timeInForce="GTC"
				)
			else:
				# Для продажи используем точное количество монет
				# Для покупки округляем до допустимого количества знаков
				if side == "Sell":
					# При продаже умное округление до допустимого количества знаков
					decimals = self._get_symbol_decimals(symbol)
					import math
					
					# Сначала пробуем обычное округление
					rounded_quantity = round(quantity, decimals)
					
					# Если округленное количество больше исходного (округление вверх),
					# и это может вызвать "Insufficient balance", используем floor
					if rounded_quantity > quantity:
						# Округление вверх может превысить баланс - используем floor
						rounded_quantity = math.floor(quantity * (10 ** decimals)) / (10 ** decimals)
					
					logger.info(f"Placing limit order: {side} {rounded_quantity} {symbol} @ {price}")
					
					response = self.session.place_order(
						category="spot",
						symbol=symbol,
						side=side,
						orderType="Limit",
						qty=str(rounded_quantity),  # Округленное вниз количество монет
						price=str(price),
						timeInForce="GTC"
					)
				else:
					# При покупке округляем до допустимого количества знаков
					decimals = self._get_symbol_decimals(symbol)
					rounded_quantity = round(quantity, decimals)
					logger.info(f"Placing limit order: {side} {rounded_quantity} {symbol} @ {price}")
					
					response = self.session.place_order(
						category="spot",
						symbol=symbol,
						side=side,
						orderType="Limit",
						qty=str(rounded_quantity),
						price=str(price),
						timeInForce="GTC"
					)
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			order_id = response.get("result", {}).get("orderId")
			logger.info(f"Limit order placed: {order_id}")
			
			return {
				"order_id": order_id,
				"symbol": symbol,
				"side": side,
				"quantity": quantity,
				"price": price,
				"order_type": "LIMIT",
				"status": "SUBMITTED"
			}
			
		except Exception as e:
			logger.error(f"Error placing limit order: {e}")
			# Для testnet возвращаем симуляцию
			if self.testnet:
				logger.info("Using testnet simulation for limit order")
				return {
					"order_id": f"TEST_{int(time.time())}",
					"symbol": symbol,
					"side": side,
					"quantity": quantity,
					"price": price,
					"order_type": "LIMIT",
					"status": "SUBMITTED"
				}
			raise
	
	async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
		"""Отменяет ордер"""
		try:
			self._check_session()
			
			logger.info(f"Cancelling order: {order_id} for {symbol}")
			
			response = self.session.cancel_order(
				category="spot",
				symbol=symbol,
				orderId=order_id
			)
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			logger.info(f"Order cancelled: {order_id}")
			return {"status": "CANCELLED", "order_id": order_id}
			
		except Exception as e:
			logger.error(f"Error cancelling order: {e}")
			raise
	
	async def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
		"""Получает список открытых ордеров"""
		try:
			self._check_session()
			
			params = {"category": "spot"}
			if symbol:
				params["symbol"] = symbol
			
			response = self.session.get_open_orders(**params)
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			orders = response.get("result", {}).get("list", [])
			return orders
			
		except Exception as e:
			logger.error(f"Error getting open orders: {e}")
			return []
	
	async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
		"""Получает статус ордера"""
		try:
			self._check_session()
			
			response = self.session.get_order_history(
				category="spot",
				symbol=symbol,
				orderId=order_id
			)
			
			if response.get("retCode") != 0:
				error_msg = response.get("retMsg", "Unknown error")
				logger.error(f"Bybit API error: {error_msg}")
				raise Exception(f"Bybit API error: {error_msg}")
			
			orders = response.get("result", {}).get("list", [])
			if orders:
				order = orders[0]
				return {
					"order_id": order.get("orderId"),
					"symbol": order.get("symbol"),
					"side": order.get("side"),
					"status": order.get("orderStatus"),
					"quantity": float(order.get("qty", 0)),
					"price": float(order.get("price", 0)),
					"filled_quantity": float(order.get("cumExecQty", 0)),
					"avg_price": float(order.get("avgPrice", 0))
				}
			else:
				return {"status": "NOT_FOUND"}
				
		except Exception as e:
			logger.error(f"Error getting order status: {e}")
			return {"status": "ERROR"}
	
	async def get_positions(self) -> List[Dict[str, Any]]:
		"""Получает открытые позиции (для spot это балансы монет)"""
		try:
			balances = await self.get_balance()
			
			if not balances:
				logger.warning("No balances available for positions")
				return []
			
			positions = []
			for coin, balance in balances.items():
				if coin != "USDT" and balance > 0:  # Исключаем USDT, берем только монеты
					positions.append({
						"symbol": f"{coin}USDT",
						"coin": coin,
						"quantity": balance,
						"side": "LONG"  # В spot всегда LONG
					})
			
			return positions
			
		except Exception as e:
			logger.error(f"Error getting positions: {e}")
			return []
	
	async def get_coin_balance(self, coin: str) -> float:
		"""Получает точный баланс конкретной монеты"""
		try:
			balances = await self.get_balance()
			return balances.get(coin, 0.0)
		except Exception as e:
			logger.error(f"Error getting {coin} balance: {e}")
			return 0.0


# Глобальный экземпляр для использования в других модулях
bybit_trader = BybitTrader()
