import csv
import sqlite3
import re
import sys

def clean_value(value):
    """Clean CSV values"""
    if not value:
        return ""
    # Remove extra quotes and spaces
    value = str(value).strip().strip('"').strip("'")
    # Replace multiple spaces with single space
    value = re.sub(r'\s+', ' ', value)
    return value

def parse_csv_file(filename):
    """Parse your specific CSV format"""
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Skip the first line (title)
    data_lines = lines[1:]
    
    # Parse CSV
    reader = csv.reader(data_lines)
    headers = next(reader)  # Get header row
    
    # Map headers to our expected format
    header_map = {}
    for i, header in enumerate(headers):
        header_clean = header.strip().lower()
        if 'sl' in header_clean:
            header_map['SL'] = i
        elif 'link name' in header_clean:
            header_map['Link_Name'] = i
        elif 'location' in header_clean:
            header_map['Location_Branch'] = i
        elif 'district' in header_clean:
            header_map['District'] = i
        elif 'connection type' in header_clean:
            header_map['Connection_Type'] = i
        elif 'pop name' in header_clean:
            header_map['POP_Name'] = i
        elif 'radio model' in header_clean:
            header_map['Radio_Model'] = i
        elif 'bts ip' in header_clean:
            header_map['BTS_IP'] = i
        elif 'client ip' in header_clean:
            header_map['Client_IP'] = i
        elif 'channel' in header_clean:
            header_map['Channel'] = i
        elif 'rssi' in header_clean:
            header_map['RSSI'] = i
        elif 'ssid' in header_clean:
            header_map['SSID'] = i
        elif 'device mode' in header_clean:
            header_map['Device_Mode'] = i
        elif 'link type' in header_clean:
            header_map['Link_Type'] = i
        elif 'frequency type' in header_clean:
            header_map['Frequency_Type'] = i
        elif 'frequency used' in header_clean:
            header_map['Frequency_Used'] = i
    
    # Process rows
    parsed_data = []
    for row_num, row in enumerate(reader, start=2):
        if len(row) < 5:  # Skip empty rows
            continue
        
        # Extract values using header map
        item = {}
        for key, idx in header_map.items():
            if idx < len(row):
                item[key] = clean_value(row[idx])
            else:
                item[key] = ""
        
        # Only add if we have essential data
        if item.get('Client_IP') or item.get('Link_Name'):
            parsed_data.append(item)
    
    return parsed_data

def import_to_db(data, db_file='rf_data.db'):
    """Import data to SQLite database"""
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    # Create table if not exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sl TEXT,
            link_name TEXT,
            location_branch TEXT,
            district TEXT,
            connection_type TEXT,
            pop_name TEXT,
            radio_model TEXT,
            bts_ip TEXT,
            client_ip TEXT UNIQUE,
            channel TEXT,
            rssi TEXT,
            ssid TEXT,
            device_mode TEXT,
            link_type TEXT,
            frequency_type TEXT,
            frequency_used TEXT,
            gateway_ip TEXT,
            link_id TEXT,
            bts_name TEXT,
            client_name TEXT,
            base_ip TEXT,
            loopback_ip TEXT,
            location TEXT,
            operator TEXT,
            device_name TEXT,
            device_model TEXT,
            contact_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    imported = 0
    for item in data:
        try:
            c.execute('''
                INSERT OR REPLACE INTO inventory (
                    sl, link_name, location_branch, district,
                    connection_type, pop_name, radio_model,
                    bts_ip, client_ip, channel, rssi, ssid,
                    device_mode, link_type, frequency_type,
                    frequency_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get('SL', ''),
                item.get('Link_Name', ''),
                item.get('Location_Branch', ''),
                item.get('District', ''),
                item.get('Connection_Type', ''),
                item.get('POP_Name', ''),
                item.get('Radio_Model', ''),
                item.get('BTS_IP', ''),
                item.get('Client_IP', ''),
                item.get('Channel', ''),
                item.get('RSSI', ''),
                item.get('SSID', ''),
                item.get('Device_Mode', ''),
                item.get('Link_Type', ''),
                item.get('Frequency_Type', ''),
                item.get('Frequency_Used', '')
            ))
            imported += 1
        except Exception as e:
            print(f"Error importing {item.get('Client_IP', 'unknown')}: {e}")
    
    conn.commit()
    conn.close()
    return imported

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_csv.py <csv_filename>")
        sys.exit(1)
    
    filename = sys.argv[1]
    print(f"Parsing {filename}...")
    
    data = parse_csv_file(filename)
    print(f"Found {len(data)} records to import")
    
    imported = import_to_db(data)
    print(f"Successfully imported {imported} records to database")
