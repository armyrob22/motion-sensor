#!/usr/bin/env python3

import serial
import psycopg2
from psycopg2.extras import execute_batch
import re
import time
import logging
from datetime import datetime

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200  # Adjust if your STM32 uses different baud rate
DB_HOST = '10.107.210.5'
DB_PORT = 5432
DB_NAME = 'motion_data'
DB_USER = 'armyrob'
DB_PASSWORD = 'Pepper122'  # Replace with actual password

BATCH_SIZE = 40  # Insert after this many samples
BATCH_TIMEOUT = 4  # Or insert after this many seconds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/armyrob/stm32_ingestion.log'),
        logging.StreamHandler()
    ]
)

def parse_decoded_line(line):
    """Parse a line like: 'Decoded: X: +1.081g | Y: -0.082g | Z: -0.158g | Change: 316'"""
    pattern = r'X:\s*([-+]?\d+\.\d+)g\s*\|\s*Y:\s*([-+]?\d+\.\d+)g\s*\|\s*Z:\s*([-+]?\d+\.\d+)g\s*\|\s*Change:\s*(\d+)'
    match = re.search(pattern, line)
    
    if match:
        return {
            'x': float(match.group(1)),
            'y': float(match.group(2)),
            'z': float(match.group(3)),
            'change': int(match.group(4))
        }
    return None

def connect_to_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5
        )
        logging.info("Connected to PostgreSQL database")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def insert_batch(conn, data_batch):
    """Insert a batch of samples into the database"""
    try:
        cursor = conn.cursor()
        
        insert_query = """
            INSERT INTO vibration_data (x_accel, y_accel, z_accel, change_value)
            VALUES (%s, %s, %s, %s)
        """
        
        data_tuples = [(d['x'], d['y'], d['z'], d['change']) for d in data_batch]
        execute_batch(cursor, insert_query, data_tuples)
        
        conn.commit()
        cursor.close()
        logging.info(f"Inserted {len(data_batch)} samples into database")
        
    except Exception as e:
        logging.error(f"Failed to insert batch: {e}")
        conn.rollback()

def main():
    logging.info("Starting STM32 vibration monitoring ingestion service")
    
    # Connect to database
    db_conn = connect_to_db()
    if not db_conn:
        logging.error("Cannot start without database connection")
        return
    
    # Connect to serial port
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        logging.info(f"Connected to serial port {SERIAL_PORT} at {BAUD_RATE} baud")
    except Exception as e:
        logging.error(f"Failed to open serial port: {e}")
        return
    
    data_batch = []
    last_insert_time = time.time()
    
    try:
        while True:
            try:
                # Read line from serial
               # Read line from serial
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if not line:
                    continue

                # Only process "Decoded:" lines
                if line.startswith('X:'):
                    data = parse_decoded_line(line)
                    
                    if data:
                        data_batch.append(data)
                        
                        # Insert if batch is full or timeout reached
                        current_time = time.time()
                        time_since_last_insert = current_time - last_insert_time
                        
                        if len(data_batch) >= BATCH_SIZE or time_since_last_insert >= BATCH_TIMEOUT:
                            insert_batch(db_conn, data_batch)
                            data_batch = []
                            last_insert_time = current_time
                            data_batch = []
                            last_insert_time = current_time
                
            except serial.SerialException as e:
                logging.error(f"Serial error: {e}")
                time.sleep(1)
                # Try to reconnect
                try:
                    ser.close()
                    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                    logging.info("Reconnected to serial port")
                except:
                    logging.error("Failed to reconnect to serial port")
                    time.sleep(5)
            
            except psycopg2.OperationalError as e:
                logging.error(f"Database connection lost: {e}")
                # Try to reconnect
                db_conn = connect_to_db()
                if not db_conn:
                    logging.error("Failed to reconnect to database, waiting 10 seconds")
                    time.sleep(10)
    
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
        
        # Insert any remaining data
        if data_batch:
            insert_batch(db_conn, data_batch)
        
        ser.close()
        db_conn.close()
        logging.info("Service stopped")

if __name__ == "__main__":
    main()
