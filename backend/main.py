import sqlite3
import subprocess
import logging
import platform
import ipaddress
import concurrent.futures
import re
import time
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# Note: StaticFiles import removed as it is not needed for backend-only deployment
from pydantic import BaseModel
from typing import List, Optional

# --- CONFIGURATION ---
DB_FILE = "rf_data.db"
SNMP_COMMUNITY = "airspan"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - NOC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- SQLITE ENGINE ---
def init_db():
    """Creates the database and table automatically on startup."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Create table with all required columns
    c.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            sl TEXT,
            link_name TEXT,
            location_branch TEXT,
            district TEXT,
            connection_type TEXT,
            pop_name TEXT,
            radio_model TEXT,
            bts_ip TEXT,
            client_ip TEXT PRIMARY KEY,
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
            device_model TEXT
        )
    ''')
    
    # Add new columns if table already exists (migration)
    new_columns = [
        ('sl', 'TEXT DEFAULT "N/A"'),
        ('link_name', 'TEXT DEFAULT "N/A"'),
        ('location_branch', 'TEXT DEFAULT "N/A"'),
        ('district', 'TEXT DEFAULT "N/A"'),
        ('connection_type', 'TEXT DEFAULT "N/A"'),
        ('radio_model', 'TEXT DEFAULT "N/A"'),
        ('channel', 'TEXT DEFAULT "N/A"'),
        ('ssid', 'TEXT DEFAULT "N/A"'),
        ('device_mode', 'TEXT DEFAULT "N/A"'),
        ('link_type', 'TEXT DEFAULT "N/A"'),
        ('frequency_type', 'TEXT DEFAULT "N/A"'),
        ('frequency_used', 'TEXT DEFAULT "N/A"'),
        ('gateway_ip', 'TEXT DEFAULT "N/A"'),
        ('operator', 'TEXT DEFAULT "N/A"'),
        ('device_name', 'TEXT DEFAULT "N/A"'),
    ]
    
    for col_name, col_def in new_columns:
        try:
            c.execute(f'ALTER TABLE inventory ADD COLUMN {col_name} {col_def}')
        except sqlite3.OperationalError:
            pass  # Column already exists
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()  # Create DB file
    if platform.system().lower() == "linux":
        try:
            subprocess.run(["fping", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            logger.warning("⚠️ Install fping: sudo apt install fping")
    yield
    # Shutdown (if needed)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATA MODEL ---
class LinkItem(BaseModel):
    SL: Optional[str] = "N/A"
    Link_Name: Optional[str] = "N/A"
    Location_Branch: Optional[str] = "N/A"
    District: Optional[str] = "N/A"
    Connection_Type: Optional[str] = "N/A"
    POP_Name: Optional[str] = "N/A"
    Radio_Model: Optional[str] = "N/A"
    BTS_IP: Optional[str] = "N/A"
    Client_IP: Optional[str] = "N/A"
    Channel: Optional[str] = "N/A"
    RSSI: Optional[str] = "N/A"
    SSID: Optional[str] = "N/A"
    Device_Mode: Optional[str] = "N/A"
    Link_Type: Optional[str] = "N/A"
    Frequency_Type: Optional[str] = "N/A"
    Frequency_Used: Optional[str] = "N/A"
    
    # Legacy fields
    Link_ID: Optional[str] = None
    BTS_Name: Optional[str] = None
    Client_Name: Optional[str] = None
    Base_IP: Optional[str] = None
    Loopback_IP: Optional[str] = "N/A"
    Location: Optional[str] = None
    Operator: Optional[str] = "N/A"
    Device_Name: Optional[str] = "N/A"
    Device_Model: Optional[str] = None
    Gateway_IP: Optional[str] = None

# --- DIAGNOSTIC TOOLS ---
def ping_target(name, ip):
    if not ip or ip in ["N/A", "", "None"]: 
        return {"target": name, "ip": "N/A", "status": "SKIPPED", "loss": "N/A", "latency": "N/A", "data": {}}
    
    is_windows = platform.system().lower() == "windows"
    
    if is_windows:
        cmd = ["ping", "-n", "5", "-w", "500", ip]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            loss = "100%"
            latency = "N/A"
            output = res.stdout + res.stderr
            match_loss = re.search(r"Lost = \d+ \((\d+)%", output)
            if match_loss: loss = f"{match_loss.group(1)}%"
            match_latency = re.search(r"Average = (\d+)ms", output)
            if match_latency: latency = f"{match_latency.group(1)} ms"
            
            loss_pct = int(re.search(r"\d+", loss).group()) if re.search(r"\d+", loss) else 100
            status = "UP" if loss_pct < 100 and res.returncode == 0 else "DOWN"
            return {"target": name, "ip": ip, "status": status, "loss": loss, "latency": latency, "data": {}}
        except Exception as e:
            return {"target": name, "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}
    else:
        cmd = ["fping", "-c", "5", "-t", "500", "-p", "25", "-q", ip]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            loss = "100%"
            latency = "N/A"
            match_loss = re.search(r"%loss = .*/(\d+%)", res.stderr)
            if match_loss: loss = match_loss.group(1)
            match_latency = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+) ms", res.stderr)
            if match_latency: latency = f"{match_latency.group(2)} ms"
            status = "UP" if res.returncode == 0 else "DOWN"
            return {"target": name, "ip": ip, "status": status, "loss": loss, "latency": latency, "data": {}}
        except:
            # Fallback to standard ping
            cmd = ["ping", "-c", "5", "-W", "1", ip]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                status = "UP" if res.returncode == 0 else "DOWN"
                return {"target": name, "ip": ip, "status": status, "loss": "N/A", "latency": "N/A", "data": {}}
            except:
                return {"target": name, "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}

def get_snmp_value(ip, oid):
    cmd = ["snmpget", "-v", "2c", "-c", SNMP_COMMUNITY, "-O", "qv", ip, oid]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0: return res.stdout.strip().replace('"', '')
        return None
    except: return None

def check_radio_health(name, ip):
    result = ping_target(name, ip)
    if result['status'] != "UP": 
        result['data'] = {"rssi": "N/A", "stability": "Offline", "lan_speed": "N/A"}
        return result 

    oid_1 = "1.3.6.1.4.1.43356.2.1.2.6.1.1.3.1"
    oid_2 = "1.3.6.1.4.1.43356.2.1.2.6.1.1.3.2"
    samples = []
    for _ in range(3):
        r1 = get_snmp_value(ip, oid_1)
        r2 = get_snmp_value(ip, oid_2)
        if r1 and r2:
            try:
                val = (abs(float(r1)/10) + abs(float(r2)/10)) / 2 * -1
                samples.append(val)
            except: pass
        time.sleep(0.2)

    final_rssi = "N/A"
    stability = "Unknown"
    
    if samples:
        avg = sum(samples) / len(samples)
        diff = max(samples) - min(samples)
        if diff < 2.5:
            stability = "Stable 🟢"
            final_rssi = f"{avg:.1f} dBm"
        elif diff < 6.0:
            stability = "Jittery ⚠️"
            final_rssi = f"{avg:.1f} dBm (±{diff:.1f})"
        else:
            stability = "UNSTABLE 🔴"
            final_rssi = f"{min(samples):.1f} ~ {max(samples):.1f} dBm"

    speed_oid = "1.3.6.1.2.1.2.2.1.5.1"
    raw_speed = get_snmp_value(ip, speed_oid)
    final_speed = "N/A"
    if raw_speed:
        try: final_speed = f"{int(int(raw_speed)/1000000)} Mbps"
        except: pass
    
    result['data'] = {"rssi": final_rssi, "stability": stability, "lan_speed": final_speed}
    return result

# --- API ENDPOINTS ---
@app.get("/api/inventory")
def get_inventory(operator: Optional[str] = None, bts: Optional[str] = None):
    conn = get_db()
    query = 'SELECT * FROM inventory WHERE 1=1'
    params = []
    
    if operator and operator != "all":
        query += ' AND operator = ?'
        params.append(operator)
    if bts and bts != "all":
        query += ' AND bts_name = ?'
        params.append(bts)
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    data = []
    for row in rows:
        bts_ip = row["bts_ip"] or row["base_ip"] or "N/A"
        client_ip = row["client_ip"] or "N/A"
        gateway_ip = row["gateway_ip"] or "N/A"
        
        if gateway_ip == "N/A" and bts_ip != "N/A":
            try: gateway_ip = str(ipaddress.IPv4Address(bts_ip) - 1)
            except: pass
        
        data.append({
            "SL": row["sl"] or "N/A",
            "Link_Name": row["link_name"] or row["client_name"] or row["link_id"] or "N/A",
            "Location_Branch": row["location_branch"] or row["location"] or "N/A",
            "District": row["district"] or "N/A",
            "Connection_Type": row["connection_type"] or "N/A",
            "POP_Name": row["pop_name"] or "N/A",
            "Radio_Model": row["radio_model"] or row["device_model"] or "N/A",
            "BTS_IP": bts_ip,
            "Client_IP": client_ip,
            "Channel": row["channel"] or "N/A",
            "RSSI": row["rssi"] or "N/A",
            "SSID": row["ssid"] or "N/A",
            "Device_Mode": row["device_mode"] or "N/A",
            "Link_Type": row["link_type"] or "N/A",
            "Frequency_Type": row["frequency_type"] or "N/A",
            "Frequency_Used": row["frequency_used"] or "N/A",
            "Gateway_IP": gateway_ip,
            "Link_ID": row["link_id"] or row["sl"] or "N/A",
            "BTS_Name": row["bts_name"] or "N/A",
            "Client_Name": row["client_name"] or row["link_name"] or "N/A",
            "Base_IP": bts_ip,
            "Loopback_IP": row["loopback_ip"] or "N/A",
            "Location": row["location"] or row["location_branch"] or "N/A",
            "Operator": row["operator"] or "N/A",
            "Device_Name": row["device_name"] or "N/A",
            "Device_Model": row["device_model"] or row["radio_model"] or "N/A"
        })
    return data

@app.get("/api/operators")
def get_operators():
    conn = get_db()
    rows = conn.execute('SELECT DISTINCT operator FROM inventory WHERE operator IS NOT NULL AND operator != "N/A"').fetchall()
    conn.close()
    return [row[0] for row in rows]

@app.get("/api/bts-list")
def get_bts_list(operator: Optional[str] = None):
    conn = get_db()
    if operator and operator != "all":
        rows = conn.execute('SELECT DISTINCT bts_name FROM inventory WHERE operator = ? AND bts_name IS NOT NULL', (operator,)).fetchall()
    else:
        rows = conn.execute('SELECT DISTINCT bts_name FROM inventory WHERE bts_name IS NOT NULL').fetchall()
    conn.close()
    return [row[0] for row in rows]

@app.post("/api/inventory")
def sync_inventory(data: List[dict]):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM inventory")
        rows_to_insert = []
        for d in data:
            # Safe extraction with defaults
            sl = d.get('SL') or d.get('Link_ID', '')
            link_name = d.get('Link_Name') or d.get('Client_Name', '')
            client_ip = d.get('Client_IP', '')
            
            if not client_ip: continue # Skip invalid
            if not sl: sl = client_ip

            # Map all fields safely
            row = (
                sl, 
                link_name,
                d.get('Location_Branch') or d.get('Location', 'N/A'),
                d.get('District', 'N/A'),
                d.get('Connection_Type', 'N/A'),
                d.get('POP_Name', 'N/A'),
                d.get('Radio_Model') or d.get('Device_Model', 'N/A'),
                d.get('BTS_IP') or d.get('Base_IP', 'N/A'),
                client_ip,
                d.get('Channel', 'N/A'),
                d.get('RSSI', 'N/A'),
                d.get('SSID', 'N/A'),
                d.get('Device_Mode', 'N/A'),
                d.get('Link_Type', 'N/A'),
                d.get('Frequency_Type', 'N/A'),
                d.get('Frequency_Used', 'N/A'),
                d.get('Gateway_IP', 'N/A'),
                # Legacy
                d.get('Link_ID', '') or sl,
                d.get('BTS_Name', 'N/A'),
                d.get('Client_Name', '') or link_name,
                d.get('Base_IP') or d.get('BTS_IP', 'N/A'),
                d.get('Loopback_IP', 'N/A'),
                d.get('Location') or d.get('Location_Branch', 'N/A'),
                d.get('Operator', 'N/A'),
                d.get('Device_Name', 'N/A'),
                d.get('Device_Model') or d.get('Radio_Model', 'N/A')
            )
            rows_to_insert.append(row)
        
        if rows_to_insert:
            c.executemany('''
                INSERT INTO inventory 
                (sl, link_name, location_branch, district, connection_type,
                 pop_name, radio_model, bts_ip, client_ip, channel,
                 rssi, ssid, device_mode, link_type, frequency_type,
                 frequency_used, gateway_ip,
                 link_id, bts_name, client_name, base_ip, loopback_ip,
                 location, operator, device_name, device_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows_to_insert)
        
        conn.commit()
        return {"status": "success", "count": len(rows_to_insert)}
    except Exception as e:
        logger.error(f"DB Error: {e}")
        conn.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        conn.close()

@app.post("/api/diagnose")
def run_diagnosis(item: dict = Body(...)):
    ip = item.get("ip")
    if not ip: raise HTTPException(status_code=400, detail="IP required")
    
    conn = get_db()
    row = conn.execute('SELECT * FROM inventory WHERE client_ip = ?', (ip,)).fetchone()
    conn.close()
    
    if not row: raise HTTPException(status_code=404, detail="Client not found")
    
    base_ip = row["base_ip"] or row["bts_ip"] or "N/A"
    gateway_ip = row["gateway_ip"] or "N/A"
    
    if gateway_ip == "N/A" and base_ip != "N/A":
        try: gateway_ip = str(ipaddress.IPv4Address(base_ip) - 1)
        except: pass

    results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(check_radio_health, "Client Radio", ip)
        f2 = executor.submit(check_radio_health, "Base Radio", base_ip)
        f3 = executor.submit(ping_target, "Gateway (GW)", gateway_ip)
        for f in concurrent.futures.as_completed([f1, f2, f3]):
            results.append(f.result())

    order = {"Client Radio": 1, "Base Radio": 2, "Gateway (GW)": 3}
    results.sort(key=lambda x: order.get(x["target"], 4))

    client = next((r for r in results if r["target"] == "Client Radio"), {})
    base = next((r for r in results if r["target"] == "Base Radio"), {})
    gw = next((r for r in results if r["target"] == "Gateway (GW)"), {})

    final_status = "UNKNOWN"
    cause = "Analyzing..."

    if client.get('status') == "UP":
        if "UNSTABLE" in client.get('data', {}).get('stability', ''):
            final_status = "UNSTABLE ⚠️"
            cause = "Signal Fluctuating"
        else:
            final_status = "LINK UP 🟢"
            cause = "Link Optimal."
    elif base.get('status') == "UP":
        final_status = "CLIENT DOWN 🔴"
        cause = "Base UP. Client Unreachable."
    elif gw.get('status') == "UP":
        final_status = "SECTOR DOWN 🔴"
        cause = "Gateway UP. Base DOWN."
    else:
        final_status = "POP ISSUE ⚫"
        cause = "Gateway Unreachable."

    return {
        "final_status": final_status,
        "cause": cause,
        "steps": results,
        "topology": {"client": client, "base": base, "gw": gw}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
