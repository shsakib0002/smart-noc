import pandas as pd

FILE = "Organized_Inventory_with_Radio_Data.xlsx"

try:
    df = pd.read_excel(FILE)
    print("\n✅ SUCCESS: Excel File Loaded!")
    print("\n👇 HERE ARE YOUR EXACT COLUMN NAMES:")
    print("--------------------------------------------------")
    for col in df.columns:
        print(f"  • {col}")
    print("--------------------------------------------------")
    print("Look for the one that has the Client Name (e.g., 'Link Name', 'Site', 'Customer').")
except Exception as e:
    print(f"❌ ERROR: {e}")