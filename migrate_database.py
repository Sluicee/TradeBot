#!/usr/bin/env python3
"""
Database migration script for TradeBot
Adds missing columns to trades_history table
"""
import os
import sys
from sqlalchemy import text, create_engine
from logger import logger


def migrate_real_trading_tables(connection):
    """Create Real Trading tables if they don't exist"""
    
    # Check existing tables
    result = connection.execute(text("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('real_trading_state', 'real_trades', 'bayesian_pending_signals')
    """))
    existing_tables = [row[0] for row in result.fetchall()]
    
    # Create real_trading_state table
    if 'real_trading_state' not in existing_tables:
        logger.info("Creating real_trading_state table...")
        connection.execute(text("""
            CREATE TABLE real_trading_state (
                id INTEGER PRIMARY KEY,
                is_running BOOLEAN DEFAULT FALSE,
                daily_pnl REAL DEFAULT 0.0,
                total_trades INTEGER DEFAULT 0,
                last_reset_date DATE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.commit()
        logger.info("✅ real_trading_state table created")
    else:
        logger.info("✅ real_trading_state table already exists")
    
    # Create real_trades table
    if 'real_trades' not in existing_tables:
        logger.info("Creating real_trades table...")
        connection.execute(text("""
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
        """))
        connection.commit()
        logger.info("✅ real_trades table created")
    else:
        logger.info("✅ real_trades table already exists")
    
    # Create bayesian_pending_signals table
    if 'bayesian_pending_signals' not in existing_tables:
        logger.info("Creating bayesian_pending_signals table...")
        connection.execute(text("""
            CREATE TABLE bayesian_pending_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_signature TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.commit()
        logger.info("✅ bayesian_pending_signals table created")
    else:
        logger.info("✅ bayesian_pending_signals table already exists")
    
    # Create indexes
    logger.info("Creating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_real_trades_symbol ON real_trades(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_real_trades_timestamp ON real_trades(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_real_trades_status ON real_trades(status)",
        "CREATE INDEX IF NOT EXISTS idx_bayesian_pending_signature ON bayesian_pending_signals(signal_signature)",
        "CREATE INDEX IF NOT EXISTS idx_bayesian_pending_created ON bayesian_pending_signals(created_at)"
    ]
    
    for index_sql in indexes:
        try:
            connection.execute(text(index_sql))
            connection.commit()
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    logger.info("✅ Real Trading tables migration completed")


def migrate_database():
    """Migrate database to add missing columns and Real Trading tables"""
    logger.info("=== DATABASE MIGRATION ===")
    
    # Get database URL from environment or use default
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/tradebot.db")
    logger.info(f"Database URL: {database_url}")
    
    try:
        # Create engine
        if database_url.startswith("sqlite"):
            engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False}
            )
        else:
            engine = create_engine(database_url)
        
        with engine.connect() as connection:
            # 1. Check and create Real Trading tables
            logger.info("Checking Real Trading tables...")
            migrate_real_trading_tables(connection)
            
            # 2. Check and add missing columns to trades_history
            # Check if columns exist
            result = connection.execute(text("""
                SELECT COUNT(*) as count 
                FROM pragma_table_info('trades_history') 
                WHERE name IN ('bullish_votes', 'bearish_votes', 'votes_delta', 'position_size_percent', 'reasons')
            """))
            
            existing_fields = result.fetchone()[0]
            logger.info(f"Found {existing_fields}/5 new fields")
            
            if existing_fields == 5:
                logger.info("✅ All fields already exist, migration not needed")
                return True
            
            # Add missing fields
            new_fields = [
                ("bullish_votes", "INTEGER DEFAULT 0"),
                ("bearish_votes", "INTEGER DEFAULT 0"), 
                ("votes_delta", "INTEGER DEFAULT 0"),
                ("position_size_percent", "REAL"),
                ("reasons", "TEXT")
            ]
            
            for field_name, field_type in new_fields:
                try:
                    # Check if field exists
                    check_result = connection.execute(text(f"""
                        SELECT COUNT(*) as count 
                        FROM pragma_table_info('trades_history') 
                        WHERE name = '{field_name}'
                    """))
                    
                    if check_result.fetchone()[0] == 0:
                        logger.info(f"Adding field: {field_name}")
                        connection.execute(text(f"ALTER TABLE trades_history ADD COLUMN {field_name} {field_type}"))
                        connection.commit()
                    else:
                        logger.info(f"Field {field_name} already exists")
                        
                except Exception as e:
                    logger.error(f"Error adding field {field_name}: {e}")
                    return False
            
            # Verify migration
            result = connection.execute(text("""
                SELECT COUNT(*) as count 
                FROM pragma_table_info('trades_history') 
                WHERE name IN ('bullish_votes', 'bearish_votes', 'votes_delta', 'position_size_percent', 'reasons')
            """))
            
            final_count = result.fetchone()[0]
            if final_count == 5:
                logger.info("✅ Migration completed successfully!")
                return True
            else:
                logger.error(f"❌ Migration failed: only {final_count}/5 fields found")
                return False
                
    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        return False


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
