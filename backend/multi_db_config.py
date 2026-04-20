import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typing import Dict, List, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MultiDatabaseManager:
    def __init__(self):
        self.engines: Dict[str, Engine] = {}
        self.initialize_databases()
    
    def initialize_databases(self):
        """Initialize connections to all three databases"""
        try:
            # PostgreSQL from DATABASE_URL first (preferred)
            database_url = os.getenv('DATABASE_URL')
            if database_url and database_url.startswith('postgresql'):
                self.engines['postgresql'] = create_engine(database_url, echo=False)
                logger.info("PostgreSQL connection (DATABASE_URL) established")
            else:
                # Fallback to discrete POSTGRES_* vars
                if os.getenv('POSTGRES_DB') and os.getenv('POSTGRES_USER') and os.getenv('POSTGRES_PASSWORD'):
                    postgres_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB')}"
                    self.engines['postgresql'] = create_engine(postgres_url, echo=False)
                    logger.info("PostgreSQL connection (POSTGRES_*) established")
                else:
                    logger.warning("PostgreSQL environment variables not found")
            
            # MySQL
            if os.getenv('MYSQL_DB') and os.getenv('MYSQL_USER') and os.getenv('MYSQL_PASSWORD'):
                mysql_url = f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}/{os.getenv('MYSQL_DB')}"
                self.engines['mysql'] = create_engine(mysql_url, echo=False)
                logger.info("MySQL connection established")
            else:
                logger.warning("MySQL environment variables not found")
            
            # SQLite
            sqlite_path = os.getenv('SQLITE_PATH', 'healthcare_data.db')
            sqlite_url = f"sqlite:///{sqlite_path}"
            self.engines['sqlite'] = create_engine(sqlite_url, echo=False)
            logger.info("SQLite connection established")
            
        except Exception as e:
            logger.error(f"Error initializing databases: {e}")
            raise
    
    def get_engine(self, db_type: str) -> Engine:
        """Get engine for specific database type"""
        if db_type not in self.engines:
            raise ValueError(f"Database type '{db_type}' not available. Available: {list(self.engines.keys())}")
        return self.engines[db_type]
    
    def get_all_engines(self) -> Dict[str, Engine]:
        """Get all available database engines"""
        return self.engines
    
    def execute_on_all_databases(self, operation_func, *args, **kwargs) -> Dict[str, Any]:
        """Execute an operation on all databases and return results"""
        results = {}
        
        for db_type, engine in self.engines.items():
            try:
                with engine.connect() as connection:
                    with connection.begin():
                        result = operation_func(connection, *args, **kwargs)
                        results[db_type] = {"status": "success", "result": result}
                        logger.info(f"Operation completed successfully on {db_type}")
            except Exception as e:
                results[db_type] = {"status": "error", "error": str(e)}
                logger.error(f"Operation failed on {db_type}: {e}")
        
        return results
    
    def test_connections(self) -> Dict[str, bool]:
        """Test all database connections"""
        connection_status = {}
        
        for db_type, engine in self.engines.items():
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                    connection_status[db_type] = True
                    logger.info(f"{db_type} connection test: PASSED")
            except Exception as e:
                connection_status[db_type] = False
                logger.error(f"{db_type} connection test: FAILED - {e}")
        
        return connection_status
    
    def close_all_connections(self):
        """Close all database connections"""
        for db_type, engine in self.engines.items():
            try:
                engine.dispose()
                logger.info(f"{db_type} connections closed")
            except Exception as e:
                logger.error(f"Error closing {db_type} connections: {e}")

# Global instance
db_manager = MultiDatabaseManager()

def get_multi_db_manager() -> MultiDatabaseManager:
    """Get the global multi-database manager instance"""
    return db_manager

def get_db_engine(db_type: str = "postgresql") -> Engine:
    """Get engine for specific database type (defaults to postgresql for backward compatibility)"""
    return db_manager.get_engine(db_type)

def get_all_db_engines() -> Dict[str, Engine]:
    """Get all available database engines"""
    return db_manager.get_all_engines()
