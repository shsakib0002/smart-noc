import pandas as pd
import os

def create_organized_sheet():
    source_file = "import csv.xlsx"
    
    print(f"Loading '{source_file}'...")
    if not os.path.exists(source_file):
        print(f"ERROR: Could not find '{source_file}' in the folder.")
        return

    # 1. Load all sheets from the Excel file
    try:
        xls = pd.read_excel(source_file, sheet_name=None)
        print(f"Found sheets: {list(xls.keys())}")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # 2. Identify the Main Inventory and Radio Sheets smartly
    df_main = pd.DataFrame()
    df_radio = pd.DataFrame()
    
    for sheet_name, df in xls.items():
        cols = [str(c).lower() for c in df.columns]
        
        # Look for Main Inventory (Keywords: link_id, gateway_ip)
        if 'link_id' in cols or 'gateway_ip' in cols:
            print(f"-> Detected Main Inventory in sheet: '{sheet_name}'")
            df_main = df
            
        # Look for Radio Info (Keywords: rssi, radio model)
        if 'rssi' in cols or 'radio model' in cols:
            print(f"-> Detected Radio Data in sheet: '{sheet_name}'")
            df_radio = df

    if df_main.empty or df_radio.empty:
        print("ERROR: Could not automatically identify the correct sheets.")
        print("Ensure one sheet has 'Link_ID' and another has 'RSSI'.")
        return

    # 3. Clean and Merge
    print("Merging data...")
    # Normalize Client IP for matching
    # Note: Adjust column names if they are slightly different in your specific Excel version
    main_ip_col = next((c for c in df_main.columns if 'client' in str(c).lower() and 'ip' in str(c).lower()), 'Client_IP')
    radio_ip_col = next((c for c in df_radio.columns if 'client' in str(c).lower() and 'ip' in str(c).lower()), 'Client IP')

    df_main['Client_IP_Match'] = df_main[main_ip_col].astype(str).str.strip()
    df_radio['Client_IP_Match'] = df_radio[radio_ip_col].astype(str).str.strip()

    merged = pd.merge(
        df_main, 
        df_radio, 
        left_on='Client_IP_Match', 
        right_on='Client_IP_Match', 
        how='left', 
        suffixes=('', '_Radio')
    )

    # 4. Map Columns for Final Output
    # We safely get columns, defaulting to None if missing
    def get_col(df, keyword):
        # Helper to find column case-insensitively
        for c in df.columns:
            if keyword.lower() == str(c).lower():
                return df[c]
        return None

    final_df = pd.DataFrame()
    final_df['Link_ID'] = get_col(merged, 'Link_ID')
    final_df['Link_Name'] = get_col(merged, 'Client_Name') 
    final_df['POP_Name'] = get_col(merged, 'POP_Name')
    final_df['Client_IP'] = get_col(merged, 'Client_IP')
    final_df['Base_IP'] = get_col(merged, 'Base_IP')
    final_df['Gateway_IP'] = get_col(merged, 'Gateway_IP')
    final_df['Location'] = get_col(merged, 'Location')
    
    # Radio Columns (Try to find them in the merged result)
    # The merge might have suffixed them if duplicates existed, or they kept original names
    final_df['Connection Type'] = get_col(merged, 'Connection Type')
    final_df['Channel'] = get_col(merged, 'Channel')
    final_df['RSSI'] = get_col(merged, 'RSSI')
    final_df['SSID'] = get_col(merged, 'SSID')
    final_df['Device Mode'] = get_col(merged, 'Device Mode')
    final_df['Link Type'] = get_col(merged, 'Link Type')
    final_df['Frequency Type'] = get_col(merged, 'Frequency Type')
    final_df['Frequency Used'] = get_col(merged, 'Frequency Used')
    final_df['Radio Model'] = get_col(merged, 'Radio Model')

    # 5. Save
    final_df = final_df.dropna(subset=['Link_ID'])
    output_filename = "Organized_Inventory_with_Radio_Data.xlsx"
    final_df.to_excel(output_filename, index=False)
    
    print(f"SUCCESS! Created '{output_filename}' with {len(final_df)} links.")

if __name__ == "__main__":
    create_organized_sheet()