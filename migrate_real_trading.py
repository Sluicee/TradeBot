#!/usr/bin/env python3
"""
Миграция для Real Trading - создание таблиц и инициализация
"""

import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def migrate_real_trading():
    """Выполняет миграцию для Real Trading"""
    
    print("🔄 Real Trading Migration...")
    print()
    
    # Путь к базе данных
    db_path = "data/tradebot.db"
    
    # Создаем директорию если не существует
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("📊 Проверка существующих таблиц...")
        
        # Проверяем существующие таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        print(f"   Найдено таблиц: {len(existing_tables)}")
        
        # Создаем таблицу real_trading_state если не существует
        if 'real_trading_state' not in existing_tables:
            print("📝 Создание таблицы real_trading_state...")
            cursor.execute('''
                CREATE TABLE real_trading_state (
                    id INTEGER PRIMARY KEY,
                    is_running BOOLEAN DEFAULT FALSE,
                    daily_pnl REAL DEFAULT 0.0,
                    total_trades INTEGER DEFAULT 0,
                    last_reset_date DATE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("   ✅ Таблица real_trading_state создана")
        else:
            print("   ✅ Таблица real_trading_state уже существует")
        
        # Создаем таблицу real_trades если не существует
        if 'real_trades' not in existing_tables:
            print("📝 Создание таблицы real_trades...")
            cursor.execute('''
                CREATE TABLE real_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    order_id TEXT,
                    status TEXT DEFAULT 'PENDING',
                    commission REAL DEFAULT 0.0,
                    realized_pnl REAL DEFAULT 0.0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    exchange_order_id TEXT,
                    avg_price REAL,
                    filled_quantity REAL DEFAULT 0.0
                )
            ''')
            print("   ✅ Таблица real_trades создана")
        else:
            print("   ✅ Таблица real_trades уже существует")
        
        # Создаем индексы для оптимизации
        print("🔍 Создание индексов...")
        
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_real_trades_symbol ON real_trades(symbol)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_real_trades_timestamp ON real_trades(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_real_trades_status ON real_trades(status)')
            print("   ✅ Индексы созданы")
        except sqlite3.Error as e:
            print(f"   ⚠️  Предупреждение при создании индексов: {e}")
        
        # Инициализируем состояние real trading если не существует
        print("🚀 Инициализация состояния real trading...")
        
        cursor.execute('SELECT COUNT(*) FROM real_trading_state')
        state_count = cursor.fetchone()[0]
        
        if state_count == 0:
            print("   📝 Создание начального состояния...")
            cursor.execute('''
                INSERT INTO real_trading_state (is_running, daily_pnl, total_trades, last_reset_date)
                VALUES (FALSE, 0.0, 0, ?)
            ''', (datetime.now().strftime('%Y-%m-%d'),))
            print("   ✅ Начальное состояние создано")
        else:
            print("   ✅ Состояние real trading уже инициализировано")
        
        # Коммитим изменения
        conn.commit()
        print()
        print("✅ Миграция Real Trading завершена успешно!")
        
        # Показываем статистику
        cursor.execute('SELECT COUNT(*) FROM real_trades')
        trades_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM real_trading_state')
        state_count = cursor.fetchone()[0]
        
        print()
        print("📊 Статистика:")
        print(f"   Real trades: {trades_count}")
        print(f"   Trading state records: {state_count}")
        print(f"   Database: {db_path}")
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка базы данных: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
    
    return True

def check_requirements():
    """Проверяет требования для миграции"""
    
    print("🔍 Проверка требований...")
    
    # Проверяем Python версию
    if sys.version_info < (3, 7):
        print("❌ Требуется Python 3.7+")
        return False
    
    # Проверяем наличие необходимых файлов
    required_files = [
        'config.py',
        'database.py',
        'real_trader.py',
        'bybit_trader.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    print("✅ Все требования выполнены")
    return True

if __name__ == "__main__":
    print("🚀 Real Trading Migration Script")
    print("=" * 50)
    print()
    
    # Проверяем требования
    if not check_requirements():
        print("❌ Миграция не может быть выполнена")
        sys.exit(1)
    
    # Выполняем миграцию
    if migrate_real_trading():
        print()
        print("🎉 Миграция Real Trading завершена успешно!")
        print("   Теперь можно использовать реальную торговлю")
        sys.exit(0)
    else:
        print()
        print("❌ Миграция завершилась с ошибками")
        sys.exit(1)