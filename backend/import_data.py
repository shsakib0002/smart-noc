import pandas as pd
from sqlalchemy.orm import sessionmaker
from models import Link, engine, init_db

def import_excel_to_db(filename="Organized_Inventory_with_Radio_Data.xlsx"):
    init_db()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    print(f"Reading {filename}...")
    try:
        df = pd.read_excel(filename)
        df = df.fillna('') # Handle empty cells
    except Exception as e:
        print(f"Error: {e}")
        return
    
    count = 0
    for _, row in df.iterrows():
        # Skip rows without Link ID
        lid = str(row['Link_ID']).strip()
        if not lid or lid.lower() == 'nan': continue
        
        # Avoid Duplicates
        exists = session.query(Link).filter_by(link_id_str=lid).first()
        if not exists:
            link = Link(
                link_id_str=lid,
                link_name=row.get('Client_Name') or row.get('Link Name'),
                pop_name=row.get('POP_Name'),
                location=row.get('Location'),
                client_ip=row.get('Client_IP'),
                base_ip=row.get('Base_IP'),
                gateway_ip=row.get('Gateway_IP'),
                connection_type=row.get('Connection Type'),
                model=row.get('Radio Model'),
                frequency_used=str(row.get('Frequency Used')),
                frequency_type=row.get('Frequency Type'),
                channel_width=row.get('Channel'),
                device_mode=row.get('Device Mode'),
                link_type=row.get('Link Type'),
                ssid=row.get('SSID')
            )
            session.add(link)
            count += 1
            
    session.commit()
    print(f"Successfully imported {count} links into the database.")

if __name__ == "__main__":
    import_excel_to_db()