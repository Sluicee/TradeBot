#!/usr/bin/env python3
"""
Database migration script for TradeBot
Adds missing columns to trades_history table
"""
import os
import sys
from sqlalchemy import text, create_engine
from logger import logger


def migrate_database():
    """Migrate database to add missing columns"""
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
