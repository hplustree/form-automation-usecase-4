#!/usr/bin/env python3
"""Initialize database and run migrations."""

import os
import sys
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from alembic.config import Config
from alembic import command
from app.logging_config import logger


def create_database_if_not_exists():
    """Create the siso_pipeline database if it doesn't exist."""
    max_retries = 30
    retry_delay = 2
    
    # Connection parameters for PostgreSQL
    db_params = {
        'host': os.getenv('DB_HOST', 'postgres'),
        'port': os.getenv('DB_PORT', '5432'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '1234')
    }
    
    for attempt in range(max_retries):
        try:
            # Connect to PostgreSQL server (not a specific database)
            conn = psycopg2.connect(
                host=db_params['host'],
                port=db_params['port'],
                user=db_params['user'],
                password=db_params['password'],
                database='postgres'  # Connect to default postgres database
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = 'siso_pipeline'"
            )
            exists = cursor.fetchone()
            
            if not exists:
                # Create database
                cursor.execute('CREATE DATABASE siso_pipeline')
                logger.info("Created database 'siso_pipeline'")
            else:
                logger.info("Database 'siso_pipeline' already exists")
            
            cursor.close()
            conn.close()
            return True
            
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"PostgreSQL not ready, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to PostgreSQL after {max_retries} attempts: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Error creating database: {str(e)}")
            return False
    
    return False


def run_migrations():
    """Run Alembic migrations."""
    try:
        # Create Alembic configuration
        alembic_cfg = Config("alembic.ini")
        
        # Override the database URL from environment if available
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:1234@postgres:5432/siso_pipeline"
        )
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        
        # Create migration if needed (first time)
        try:
            # Generate initial migration
            command.revision(
                alembic_cfg,
                autogenerate=True,
                message="Initial migration"
            )
            logger.info("Generated initial migration")
        except Exception as e:
            # Migration might already exist
            logger.info(f"Migration generation skipped: {str(e)}")
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error running migrations: {str(e)}")
        return False


def main():
    """Main initialization function."""
    logger.info("Starting database initialization...")
    
    # Create database if it doesn't exist
    if not create_database_if_not_exists():
        logger.error("Failed to create database")
        sys.exit(1)
    
    # Run migrations
    if not run_migrations():
        logger.error("Failed to run migrations")
        sys.exit(1)
    
    logger.info("Database initialization completed successfully")


if __name__ == "__main__":
    main()
