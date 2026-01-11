import os
import pandas as pd
from sqlalchemy.orm import sessionmaker
from models import Link, engine, init_db

DB_FILE = "amberit_noc.db"
EXCEL_FILE = "Organized_Inventory_with_Radio_Data.xlsx"

def reset_and_import():
    print("--- AMBERIT NOC: FACTORY RESET TOOL ---")
    
    # 1. DELETE OLD DB
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"[OK] Deleted old {DB_FILE}")
        except PermissionError:
            print("[ERROR] Database is locked! Please CLOSE 'app.py' and 'scanner.py'.")
            return

    # 2. CREATE NEW DB
    print("[INFO] Initializing new database schema...")
    init_db()
    
    # 3. IMPORT DATA
    print(f"[INFO] Reading {EXCEL_FILE}...")
    try:
        df = pd.read_excel(EXCEL_FILE)
        df = df.fillna('') # Replace empty cells
        df.columns = df.columns.str.strip() # Clean headers
    except Exception as e:
        print(f"[ERROR] Could not read Excel file: {e}")
        return

    Session = sessionmaker(bind=engine)
    session = Session()
    
    count = 0
    seen_ids = set() # To track duplicates
    
    print("[INFO] Processing rows...")
    
    for index, row in df.iterrows():
        # Get ID
        lid = str(row.get('Link_ID', '')).strip()
        
        # Skip empty rows
        if not lid or lid.lower() == 'nan': continue
        
        # --- DUPLICATE FIXER ---
        # If we have seen this ID before, rename it to prevent crash
        if lid in seen_ids:
            original_lid = lid
            dup_counter = 1
            while lid in seen_ids:
                lid = f"{original_lid}_{dup_counter}"
                dup_counter += 1
            print(f"   [WARN] Row {index+2}: Duplicate ID '{original_lid}' -> Renamed to '{lid}'")
        
        seen_ids.add(lid)
        
        # --- NAME FIX ---
        raw_name = str(row.get('Link_Name', '')).strip()
        if not raw_name or raw_name.lower() == 'nan':
            raw_name = f"Link-{lid}" 
            
        # Hardware Info
        model = str(row.get('Radio Model', '')).strip()
        ip = str(row.get('Client_IP', '')).strip()
        
        # Determine Vendor
        vendor = "Generic"
        if "epmp" in model.lower() or "cambium" in model.lower(): vendor = "Cambium"
        elif "powerbeam" in model.lower() or "nano" in model.lower() or "ubiquiti" in model.lower(): vendor = "Ubiquiti"
        elif "mimosa" in model.lower(): vendor = "Mimosa"

        link = Link(
            link_id_str=lid,
            link_name=raw_name, 
            pop_name=str(row.get('POP_Name', '')).strip(),
            location=str(row.get('Location', '')).strip(),
            client_ip=ip,
            base_ip=str(row.get('Base_IP', '')).strip(),
            gateway_ip=str(row.get('Gateway_IP', '')).strip(),
            
            # Tech Details
            connection_type=str(row.get('Connection Type', '')),
            channel_width=str(row.get('Channel', '')),
            ssid=str(row.get('SSID', '')),
            device_mode=str(row.get('Device Mode', '')),
            link_type=str(row.get('Link Type', '')),
            frequency_type=str(row.get('Frequency Type', '')),
            frequency_used=str(row.get('Frequency Used', '')),
            model=model,
            vendor=vendor,
            
            # Default Status
            eth_speed="Unknown",
            eth_duplex="Unknown"
        )
        session.add(link)
        count += 1
        
    session.commit()
    session.close()
    print(f"\n[SUCCESS] Imported {count} links.")
    print("---------------------------------------")
    print("1. Close all python windows.")
    print("2. Run: python app.py")
    print("3. Run: python scanner.py")

if __name__ == "__main__":
    reset_and_import()