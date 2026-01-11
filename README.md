# 🌐 AmberIT NOC Core (OS V2.5)

**A Next-Gen Network Operations Center (NOC) Dashboard.**
Active monitoring, real-time diagnostics, and geospatial visualization for ISP infrastructure. Built with Python, Flask, and a Cyberpunk-inspired frontend.

![Dashboard Preview](https://via.placeholder.com/1000x500.png?text=Dashboard+Preview+Image)
*(Replace this link with a screenshot of your actual dashboard)*

---

## 🚀 Key Features

* **Command Center HUD:** Live stats for Total Inventory, Online Links, Critical Outages, and Degraded Signals.
* **Real-Time Monitoring:** Background scanner checks connectivity (Ping) and Health (SNMP) for 700+ links continuously.
* **Live Trace Route:** Interactive "Deep Dive" terminal that performs a 3-hop diagnostic (Gateway -> Base -> Client) in real-time.
* **Smart Inventory:** Searchable, paginated grid view capable of handling large datasets without browser lag.
* **Hardware Inspection:** Detects Vendor (Cambium/Ubiquiti), Ethernet Speed (100Mbps/1Gbps), Duplex Mode, and RSSI Signal Strength.
* **Geospatial Map:** Live visualization of node status using Leaflet.js.
* **Auto-Healing Database:** Custom import script detects Excel duplicates and corrects "Unknown" client names automatically.

---

## 🛠️ Tech Stack

* **Backend:** Python 3.x, Flask, SQLAlchemy (SQLite), PySNMP.
* **Frontend:** HTML5, CSS3 (Glassmorphism/Cyberpunk UI), JavaScript (Vanilla), Leaflet.js.
* **Data Processing:** Pandas (Excel Import).
* **Tunneling:** Ngrok (For remote mobile monitoring).

---

## 📦 Installation & Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/your-username/smart-noc.git](https://github.com/your-username/smart-noc.git)
cd smart-noc
2. Install Dependencies
Make sure you have Python installed. Then run:

Bash

pip install flask flask-cors sqlalchemy pandas openpyxl pysnmp
3. Prepare Inventory Data
Place your inventory Excel file in the project root.

Filename: Organized_Inventory_with_Radio_Data.xlsx

Required Columns: Link_ID, Link_Name, Client_IP, Radio Model, POP_Name.

4. Initialize Database
Run the factory reset tool to create the database and import data (handles duplicates automatically).

Bash

python reset_db.py
Wait for the [SUCCESS] message.

🖥️ How to Run (The 3-Terminal Method)
To run the full system, you need 3 separate terminal windows open at the same time:

Terminal 1: Backend API
Starts the web server.

Bash

python app.py
Terminal 2: Network Scanner
Starts the background ping/SNMP poller.

Bash

python scanner.py
Terminal 3: Remote Access (Optional)
Exposes the dashboard to the internet (for mobile access).

Bash

ngrok http 5000
⚙️ Configuration
Updating the Frontend
If you restart Ngrok, the URL changes. You must update the frontend code to point to the new URL.

Open index.html.

Find the line:

JavaScript

const API_BASE = "[https://your-new-url.ngrok-free.app](https://your-new-url.ngrok-free.app)";
Paste your new Ngrok URL there.

Upload index.html to GitHub Pages (or open it locally).

🧩 Project Structure
Plaintext

/AmberIT_NOC
│
├── app.py              # Flask Backend (API Routes)
├── scanner.py          # Background Service (Ping & SNMP)
├── models.py           # Database Schema (SQLAlchemy)
├── reset_db.py         # Database Reset & Excel Import Tool
├── requirements.txt    # Python Dependencies
├── index.html          # Frontend Dashboard (The UI)
└── Organized_Inv...xlsx # Source Data
⚠️ Troubleshooting
"Database is locked": This happens if you try to reset the DB while the app is running. Close app.py and scanner.py before running reset_db.py.

"Page Unresponsive": Ensure you are using the latest index.html with Pagination enabled (V2.5).

"Connection Error" on Phone: Check if the API_BASE in index.html matches your current Ngrok URL.

Developed for AmberIT Network Operations.


***

### How to use this:
1.  Create a file named `requirements.txt` in your folder and paste this list inside so people know what to install:
    ```text
    flask
    flask-cors
    sqlalchemy
    pandas
    openpyxl
    pysnmp
    ```
2.  Create the `README.md` file and paste the markdown code above.
3.  Upload both to your GitHub repository.

