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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

# --- CONFIGURATION ---
DB_FILE = "rf_data.db"  # The new Database file
SNMP_COMMUNITY = "airspan"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - NOC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
# This ensures data sent from Frontend matches what we expect
class LinkItem(BaseModel):
    SL: Optional[str] = "N/A"  # Serial Number
    Link_Name: Optional[str] = "N/A"
    Location_Branch: Optional[str] = "N/A"  # Location/Branch
    District: Optional[str] = "N/A"
    Connection_Type: Optional[str] = "N/A"
    POP_Name: Optional[str] = "N/A"
    Radio_Model: Optional[str] = "N/A"  # Radio Model
    BTS_IP: Optional[str] = "N/A"  # BTS IP (Base IP)
    Client_IP: Optional[str] = "N/A"
    Channel: Optional[str] = "N/A"
    RSSI: Optional[str] = "N/A"
    SSID: Optional[str] = "N/A"
    Device_Mode: Optional[str] = "N/A"
    Link_Type: Optional[str] = "N/A"
    Frequency_Type: Optional[str] = "N/A"  # e.g., 5GHz, 2.4GHz
    Frequency_Used: Optional[str] = "N/A"  # e.g., 5180 MHz
    
    # Legacy fields for backward compatibility
    Link_ID: Optional[str] = None
    BTS_Name: Optional[str] = None
    Client_Name: Optional[str] = None
    Base_IP: Optional[str] = None
    Loopback_IP: Optional[str] = "N/A"
    Location: Optional[str] = None
    Operator: Optional[str] = "N/A"
    Device_Name: Optional[str] = "N/A"
    Device_Model: Optional[str] = None
    Gateway_IP: Optional[str] = None  # Calculated as base-1 if not provided

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
    conn.row_factory = sqlite3.Row  # Allows us to select columns by name
    return conn

# --- DIAGNOSTIC TOOLS ---
def ping_target(name, ip):
    if not ip or ip in ["N/A", "", "None"]: 
        return {"target": name, "ip": "N/A", "status": "SKIPPED", "loss": "N/A", "latency": "N/A", "data": {}}
    
    is_windows = platform.system().lower() == "windows"
    
    # Use fping on Linux/Unix, fallback to ping on Windows
    if is_windows:
        # Windows ping: ping -n 5 -w 500 <ip>
        cmd = ["ping", "-n", "5", "-w", "500", ip]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            loss = "100%"
            latency = "N/A"
            
            # Windows ping output parsing
            output = res.stdout + res.stderr
            
            # Extract packet loss: "Lost = 0 (0% loss)" or "Lost = 5 (100% loss)"
            match_loss = re.search(r"Lost = \d+ \((\d+)%", output)
            if match_loss:
                loss = f"{match_loss.group(1)}%"
            
            # Extract average latency: "Average = 15ms"
            match_latency = re.search(r"Average = (\d+)ms", output)
            if match_latency:
                latency = f"{match_latency.group(1)} ms"
            
            # Extract individual times for average calculation
            times = re.findall(r"time[<=](\d+)ms", output)
            if times and not match_latency:
                avg_time = sum(int(t) for t in times) / len(times)
                latency = f"{avg_time:.1f} ms"
            
            # Status based on packet loss
            loss_pct = int(re.search(r"\d+", loss).group()) if re.search(r"\d+", loss) else 100
            status = "UP" if loss_pct < 100 and res.returncode == 0 else "DOWN"
            
            return {"target": name, "ip": ip, "status": status, "loss": loss, "latency": latency, "data": {}}
        except Exception as e:
            logger.error(f"Ping error for {ip}: {e}")
            return {"target": name, "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}
    else:
        # Linux/Unix: Use fping if available, otherwise ping
        cmd = ["fping", "-c", "5", "-t", "500", "-p", "25", "-q", ip]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            loss = "100%"
            latency = "N/A"
            
            # Extract loss percentage from fping
            match_loss = re.search(r"%loss = .*/(\d+%)", res.stderr)
            if match_loss: 
                loss = match_loss.group(1)
            
            # Extract average latency
            match_latency = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+) ms", res.stderr)
            if match_latency:
                latency = f"{match_latency.group(2)} ms"  # Average latency
            
            status = "UP" if res.returncode == 0 else "DOWN"
            return {"target": name, "ip": ip, "status": status, "loss": loss, "latency": latency, "data": {}}
        except FileNotFoundError:
            # fping not available, fallback to ping
            logger.warning(f"fping not found, using ping for {ip}")
            cmd = ["ping", "-c", "5", "-W", "1", ip]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                loss = "100%"
                latency = "N/A"
                
                # Parse standard ping output
                output = res.stdout
                match_loss = re.search(r"(\d+)% packet loss", output)
                if match_loss:
                    loss = f"{match_loss.group(1)}%"
                
                match_latency = re.search(r"= [\d.]+/[\d.]+/([\d.]+)/[\d.]+", output)
                if match_latency:
                    latency = f"{match_latency.group(1)} ms"
                
                status = "UP" if res.returncode == 0 and "0% packet loss" in output else "DOWN"
                return {"target": name, "ip": ip, "status": status, "loss": loss, "latency": latency, "data": {}}
            except Exception as e:
                logger.error(f"Ping error for {ip}: {e}")
                return {"target": name, "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}
        except Exception as e:
            logger.error(f"Ping error for {ip}: {e}")
            return {"target": name, "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}

def get_snmp_value(ip, oid):
    cmd = ["snmpget", "-v", "2c", "-c", SNMP_COMMUNITY, "-O", "qv", ip, oid]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0: return res.stdout.strip().replace('"', '')
        return None
    except: return None

def check_radio_health(name, ip):
    # 1. Ping
    result = ping_target(name, ip)
    if result['status'] != "UP": 
        result['data'] = {"rssi": "N/A", "stability": "Offline", "lan_speed": "N/A"}
        return result 

    # 2. SNMP (Signal) - Take 3 samples for stability
    oid_1 = "1.3.6.1.4.1.43356.2.1.2.6.1.1.3.1"
    oid_2 = "1.3.6.1.4.1.43356.2.1.2.6.1.1.3.2"
    samples = []
    for _ in range(3):
        r1 = get_snmp_value(ip, oid_1)
        r2 = get_snmp_value(ip, oid_2)
        if r1 and r2:
            try:
                # Convert raw val (e.g. -500 to 50.0)
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

    # 3. LAN Speed
    speed_oid = "1.3.6.1.2.1.2.2.1.5.1"
    raw_speed = get_snmp_value(ip, speed_oid)
    final_speed = "N/A"
    if raw_speed:
        try: final_speed = f"{int(int(raw_speed)/1000000)} Mbps"
        except: pass
    
    result['data'] = {"rssi": final_rssi, "stability": stability, "lan_speed": final_speed}
    # latency is already set by ping_target call above
    return result

# --- API ENDPOINTS ---

@app.get("/api/inventory")
def get_inventory(operator: Optional[str] = None, bts: Optional[str] = None):
    """Read from SQL -> Send to Frontend with optional filtering"""
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
    
    # Convert SQL rows to JSON list with all fields
    data = []
    for row in rows:
        # Get BTS IP (check both new and legacy fields)
        bts_ip = row.get("bts_ip") or row.get("base_ip") or "N/A"
        client_ip = row.get("client_ip") or "N/A"
        gateway_ip = row.get("gateway_ip") or "N/A"
        
        # Calculate gateway if not set (bts_ip - 1)
        if gateway_ip == "N/A" and bts_ip != "N/A":
            try:
                gateway_ip = str(ipaddress.IPv4Address(bts_ip) - 1)
            except:
                pass
        
        data.append({
            # New standard fields
            "SL": row.get("sl") or "N/A",
            "Link_Name": row.get("link_name") or row.get("client_name") or row.get("link_id") or "N/A",
            "Location_Branch": row.get("location_branch") or row.get("location") or "N/A",
            "District": row.get("district") or "N/A",
            "Connection_Type": row.get("connection_type") or "N/A",
            "POP_Name": row.get("pop_name") or "N/A",
            "Radio_Model": row.get("radio_model") or row.get("device_model") or "N/A",
            "BTS_IP": bts_ip,
            "Client_IP": client_ip,
            "Channel": row.get("channel") or "N/A",
            "RSSI": row.get("rssi") or "N/A",
            "SSID": row.get("ssid") or "N/A",
            "Device_Mode": row.get("device_mode") or "N/A",
            "Link_Type": row.get("link_type") or "N/A",
            "Frequency_Type": row.get("frequency_type") or "N/A",
            "Frequency_Used": row.get("frequency_used") or "N/A",
            "Gateway_IP": gateway_ip,
            
            # Legacy fields for backward compatibility
            "Link_ID": row.get("link_id") or row.get("sl") or "N/A",
            "BTS_Name": row.get("bts_name") or "N/A",
            "Client_Name": row.get("client_name") or row.get("link_name") or "N/A",
            "Base_IP": bts_ip,
            "Loopback_IP": row.get("loopback_ip") or "N/A",
            "Location": row.get("location") or row.get("location_branch") or "N/A",
            "Operator": row.get("operator") or "N/A",
            "Device_Name": row.get("device_name") or "N/A",
            "Device_Model": row.get("device_model") or row.get("radio_model") or "N/A"
        })
    return data

@app.get("/api/operators")
def get_operators():
    """Get list of unique operators"""
    conn = get_db()
    rows = conn.execute('SELECT DISTINCT operator FROM inventory WHERE operator IS NOT NULL AND operator != "N/A"').fetchall()
    conn.close()
    return [row[0] for row in rows]

@app.get("/api/bts-list")
def get_bts_list(operator: Optional[str] = None):
    """Get list of unique BTS names, optionally filtered by operator"""
    conn = get_db()
    if operator and operator != "all":
        rows = conn.execute('SELECT DISTINCT bts_name FROM inventory WHERE operator = ? AND bts_name IS NOT NULL', (operator,)).fetchall()
    else:
        rows = conn.execute('SELECT DISTINCT bts_name FROM inventory WHERE bts_name IS NOT NULL').fetchall()
    conn.close()
    return [row[0] for row in rows]

@app.post("/api/inventory")
def sync_inventory(data: List[dict]):
    """Frontend sent new data (Import/Save). Wipe SQL table and Insert new data."""
    conn = get_db()
    c = conn.cursor()
    try:
        # 1. Clear old data
        c.execute("DELETE FROM inventory")
        
        # 2. Insert new data (Bulk)
        # Handle both dict and LinkItem objects from CSV imports
        rows_to_insert = []
        for d in data:
            # Support both dict and object access - handle all fields
            if isinstance(d, dict):
                sl = d.get('SL', '') or d.get('Link_ID', '')
                link_name = d.get('Link_Name', '') or d.get('Client_Name', '')
                location_branch = d.get('Location_Branch', '') or d.get('Location', 'N/A')
                district = d.get('District', 'N/A')
                connection_type = d.get('Connection_Type', 'N/A')
                pop_name = d.get('POP_Name', 'N/A')
                radio_model = d.get('Radio_Model', '') or d.get('Device_Model', 'N/A')
                bts_ip = d.get('BTS_IP', '') or d.get('Base_IP', 'N/A')
                client_ip = d.get('Client_IP', '')
                channel = d.get('Channel', 'N/A')
                rssi = d.get('RSSI', 'N/A')
                ssid = d.get('SSID', 'N/A')
                device_mode = d.get('Device_Mode', 'N/A')
                link_type = d.get('Link_Type', 'N/A')
                frequency_type = d.get('Frequency_Type', 'N/A')
                frequency_used = d.get('Frequency_Used', 'N/A')
                gateway_ip = d.get('Gateway_IP', None)
                
                # Legacy fields
                link_id = d.get('Link_ID', '') or sl
                bts_name = d.get('BTS_Name', 'N/A')
                client_name = d.get('Client_Name', '') or link_name
                base_ip = bts_ip
                loopback_ip = d.get('Loopback_IP', 'N/A')
                location = location_branch
                operator = d.get('Operator', 'N/A')
                device_name = d.get('Device_Name', 'N/A')
                device_model = radio_model
            else:
                # Handle object attributes
                sl = getattr(d, 'SL', None) or getattr(d, 'Link_ID', '') or ''
                link_name = getattr(d, 'Link_Name', None) or getattr(d, 'Client_Name', '') or ''
                location_branch = getattr(d, 'Location_Branch', None) or getattr(d, 'Location', 'N/A') or 'N/A'
                district = getattr(d, 'District', 'N/A') or 'N/A'
                connection_type = getattr(d, 'Connection_Type', 'N/A') or 'N/A'
                pop_name = getattr(d, 'POP_Name', 'N/A') or 'N/A'
                radio_model = getattr(d, 'Radio_Model', None) or getattr(d, 'Device_Model', 'N/A') or 'N/A'
                bts_ip = getattr(d, 'BTS_IP', None) or getattr(d, 'Base_IP', 'N/A') or 'N/A'
                client_ip = getattr(d, 'Client_IP', '') or ''
                channel = getattr(d, 'Channel', 'N/A') or 'N/A'
                rssi = getattr(d, 'RSSI', 'N/A') or 'N/A'
                ssid = getattr(d, 'SSID', 'N/A') or 'N/A'
                device_mode = getattr(d, 'Device_Mode', 'N/A') or 'N/A'
                link_type = getattr(d, 'Link_Type', 'N/A') or 'N/A'
                frequency_type = getattr(d, 'Frequency_Type', 'N/A') or 'N/A'
                frequency_used = getattr(d, 'Frequency_Used', 'N/A') or 'N/A'
                gateway_ip = getattr(d, 'Gateway_IP', None)
                
                # Legacy fields
                link_id = sl
                bts_name = getattr(d, 'BTS_Name', 'N/A') or 'N/A'
                client_name = link_name
                base_ip = bts_ip
                loopback_ip = getattr(d, 'Loopback_IP', 'N/A') or 'N/A'
                location = location_branch
                operator = getattr(d, 'Operator', 'N/A') or 'N/A'
                device_name = getattr(d, 'Device_Name', 'N/A') or 'N/A'
                device_model = radio_model
            
            # Calculate gateway IP if not provided (bts_ip - 1)
            if not gateway_ip or gateway_ip == "N/A":
                if bts_ip and bts_ip not in ["N/A", "", "None"]:
                    try:
                        gateway_ip = str(ipaddress.IPv4Address(bts_ip) - 1)
                    except:
                        gateway_ip = "N/A"
                else:
                    gateway_ip = "N/A"
            
            # Ensure required fields exist - Client_IP is required
            if not client_ip:
                logger.warning(f"Skipping invalid record: missing Client_IP")
                continue
            
            # Use SL or Client_IP as identifier
            if not sl:
                sl = client_ip
            
            rows_to_insert.append((
                sl, link_name, location_branch, district, connection_type,
                pop_name, radio_model, bts_ip, client_ip, channel,
                rssi, ssid, device_mode, link_type, frequency_type,
                frequency_used, gateway_ip,
                # Legacy fields
                link_id, bts_name, client_name, base_ip, loopback_ip,
                location, operator, device_name, device_model
            ))
        
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
    if not ip:
        raise HTTPException(status_code=400, detail="IP address is required")
    
    # 1. Find client in SQL DB
    conn = get_db()
    row = conn.execute('SELECT * FROM inventory WHERE client_ip = ?', (ip,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Client with IP {ip} not found in inventory")
    
    base_ip = row["base_ip"] if row else "N/A"
    
    gateway_ip = "N/A"
    try:
        if base_ip != "N/A": gateway_ip = str(ipaddress.IPv4Address(base_ip) - 1)
    except: pass

    # 2. Run Checks
    results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(check_radio_health, "Client Radio", ip)
        f2 = executor.submit(check_radio_health, "Base Radio", base_ip)
        f3 = executor.submit(ping_target, "Gateway (GW)", gateway_ip)
        for f in concurrent.futures.as_completed([f1, f2, f3]):
            results.append(f.result())

    # 3. Sort & Analyze
    order = {"Client Radio": 1, "Base Radio": 2, "Gateway (GW)": 3}
    results.sort(key=lambda x: order.get(x["target"], 4))

    client = next((r for r in results if r["target"] == "Client Radio"), None)
    base = next((r for r in results if r["target"] == "Base Radio"), None)
    gw = next((r for r in results if r["target"] == "Gateway (GW)"), None)

    # Ensure default values if None
    if client is None:
        client = {"target": "Client Radio", "ip": ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}
    if base is None:
        base = {"target": "Base Radio", "ip": base_ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}
    if gw is None:
        gw = {"target": "Gateway (GW)", "ip": gateway_ip, "status": "ERROR", "loss": "?", "latency": "N/A", "data": {}}

    final_status = "UNKNOWN"
    cause = "Analyzing..."

    if client and client.get('status') == "UP":
        stability = client.get('data', {}).get('stability', '')
        if "UNSTABLE" in stability:
            final_status = "UNSTABLE ⚠️"
            cause = "Signal Fluctuating"
        else:
            final_status = "LINK UP 🟢"
            cause = "Link Optimal."
    elif base and base.get('status') == "UP":
        final_status = "CLIENT DOWN 🔴"
        cause = "Base UP. Client Unreachable."
    elif gw and gw.get('status') == "UP":
        final_status = "SECTOR DOWN 🔴"
        cause = "Gateway UP. Base DOWN."
    else:
        final_status = "POP ISSUE ⚫"
        cause = "Gateway Unreachable."

    # Format response to match frontend expectations
    return {
        "final_status": final_status,
        "cause": cause,
        "steps": results,
        "topology": {
            "client": {
                "status": client.get("status", "UNKNOWN"),
                "loss": client.get("loss", "N/A"),
                "latency": client.get("latency", "N/A"),
                "data": client.get("data", {})
            },
            "base": {
                "status": base.get("status", "UNKNOWN"),
                "loss": base.get("loss", "N/A"),
                "latency": base.get("latency", "N/A"),
                "data": base.get("data", {})
            },
            "gw": {
                "status": gw.get("status", "UNKNOWN"),
                "loss": gw.get("loss", "N/A"),
                "latency": gw.get("latency", "N/A"),
                "data": gw.get("data", {})
            }
        }
    }

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
