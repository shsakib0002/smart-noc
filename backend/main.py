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
from pydantic import BaseModel
from typing import List, Optional
import json

# --- CONFIGURATION ---
DB_FILE = "rf_data.db"
SNMP_COMMUNITY = "public"  # Change to your SNMP community
SNMP_TIMEOUT = 3000  # 3 seconds timeout for SNMP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - NOC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- RADIO MODEL SPECIFIC OIDs ---
RADIO_OIDS = {
    # Mimosa C5x/C5c Series
    "mimosa c5x": {
        "rssi": "1.3.6.1.4.1.43356.2.1.2.6.1.1.3",  # Mimosa RSSI OID
        "frequency": "1.3.6.1.4.1.43356.2.1.2.6.1.1.4",
        "tx_power": "1.3.6.1.4.1.43356.2.1.2.6.1.1.5",
        "rx_power": "1.3.6.1.4.1.43356.2.1.2.6.1.1.6",
        "capacity": "1.3.6.1.4.1.43356.2.1.2.6.1.1.7"
    },
    # Cambium ePMP Series (Force 180/190/200/300)
    "epmp": {
        "rssi": "1.3.6.1.4.1.17713.22.1.1.1.1.5",  # Cambium RSSI
        "frequency": "1.3.6.1.4.1.17713.22.1.1.1.1.2",
        "tx_power": "1.3.6.1.4.1.17713.22.1.1.1.1.7",
        "rx_power": "1.3.6.1.4.1.17713.22.1.1.1.1.8",
        "capacity": "1.3.6.1.4.1.17713.22.1.1.1.1.9"
    },
    # Ubiquiti PowerBeam M5
    "powerbeam m5": {
        "rssi": "1.3.6.1.4.1.41112.1.10.1.4.1.1",  # Ubiquiti RSSI
        "frequency": "1.3.6.1.4.1.41112.1.10.1.2.1",
        "tx_power": "1.3.6.1.4.1.41112.1.10.1.3.1",
        "rx_power": "1.3.6.1.4.1.41112.1.10.1.4.1",
        "capacity": "1.3.6.1.4.1.41112.1.10.1.5.1"
    },
    # Ubiquiti AirFiber
    "air fiber": {
        "rssi": "1.3.6.1.4.1.41112.1.10.1.4.1.1",
        "frequency": "1.3.6.1.4.1.41112.1.10.1.2.1",
        "tx_power": "1.3.6.1.4.1.41112.1.10.1.3.1",
        "rx_power": "1.3.6.1.4.1.41112.1.10.1.4.1",
        "capacity": "1.3.6.1.4.1.41112.1.10.1.5.1"
    },
    # Ubiquiti NanoStation
    "nano": {
        "rssi": "1.3.6.1.4.1.41112.1.10.1.4.1.1",
        "frequency": "1.3.6.1.4.1.41112.1.10.1.2.1",
        "tx_power": "1.3.6.1.4.1.41112.1.10.1.3.1",
        "rx_power": "1.3.6.1.4.1.41112.1.10.1.4.1",
        "capacity": "1.3.6.1.4.1.41112.1.10.1.5.1"
    }
}

# --- SQLITE ENGINE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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
    
    # Create indexes for faster queries
    c.execute('CREATE INDEX IF NOT EXISTS idx_client_ip ON inventory(client_ip)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_link_name ON inventory(link_name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_district ON inventory(district)')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Check for required tools
    if platform.system().lower() == "linux":
        try:
            subprocess.run(["which", "fping"], capture_output=True)
        except:
            logger.warning("⚠️ fping not installed. Install with: sudo apt install fping")
    if platform.system().lower() == "windows":
        try:
            subprocess.run(["ping", "/?"], capture_output=True)
        except:
            logger.warning("⚠️ Ping command not available")
    yield

app = FastAPI(lifespan=lifespan, title="Smart NOC API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DIAGNOSTIC TOOLS ---
def detect_radio_model(model_string):
    """Detect radio model from description"""
    if not model_string:
        return "unknown"
    
    model_lower = model_string.lower()
    
    if "mimosa" in model_lower:
        if "c5x" in model_lower or "c5c" in model_lower:
            return "mimosa c5x"
        return "mimosa"
    elif "epmp" in model_lower or "cambium" in model_lower:
        return "epmp"
    elif "powerbeam" in model_lower or "pbm5" in model_lower:
        return "powerbeam m5"
    elif "air fiber" in model_lower or "airfiber" in model_lower:
        return "air fiber"
    elif "nano" in model_lower:
        return "nano"
    elif "tp-link" in model_lower or "cpe" in model_lower:
        return "tp-link"
    else:
        return "generic"

def ping_target(ip, count=4, timeout=2000):
    """Enhanced ping function with better error handling"""
    if not ip or ip in ["N/A", "", "None", None]:
        return {"status": "SKIPPED", "loss": "100%", "latency": "N/A", "packets_sent": 0}
    
    try:
        # Validate IP
        ipaddress.ip_address(ip)
    except:
        return {"status": "INVALID", "loss": "100%", "latency": "N/A", "packets_sent": 0}
    
    is_windows = platform.system().lower() == "windows"
    
    if is_windows:
        cmd = ["ping", "-n", str(count), "-w", str(timeout), ip]
    else:
        # Use fping if available, fallback to ping
        try:
            cmd = ["fping", "-c", str(count), "-t", str(timeout), "-q", ip]
        except:
            cmd = ["ping", "-c", str(count), "-W", "2", ip]
    
    try:
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            timeout=10
        )
        
        output = result.stdout + result.stderr
        
        # Parse results
        loss_match = re.search(r"(\d+)% packet loss", output) or re.search(r"Lost = \d+ \((\d+)%", output)
        latency_match = re.search(r"min/avg/max/\w+ = [\d\.]+/([\d\.]+)/[\d\.]+", output) or \
                       re.search(r"Average = (\d+)ms", output)
        
        loss_pct = int(loss_match.group(1)) if loss_match else 100
        latency = f"{latency_match.group(1)} ms" if latency_match else "N/A"
        
        if loss_pct == 100:
            status = "DOWN"
        elif loss_pct > 50:
            status = "UNSTABLE"
        else:
            status = "UP"
            
        return {
            "status": status,
            "loss": f"{loss_pct}%",
            "latency": latency,
            "packets_sent": count,
            "output": output[:500]  # Truncate long output
        }
        
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "loss": "100%", "latency": "N/A", "packets_sent": 0}
    except Exception as e:
        return {"status": "ERROR", "loss": "100%", "latency": "N/A", "packets_sent": 0, "error": str(e)}

def get_snmp_metric(ip, oid, retries=2):
    """Get SNMP metric with retries"""
    for attempt in range(retries):
        try:
            cmd = [
                "snmpget", "-v", "2c", "-c", SNMP_COMMUNITY,
                "-t", str(SNMP_TIMEOUT // 1000),  # Convert ms to seconds
                "-r", "1",  # 1 retry
                ip, oid
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Extract value
                value = result.stdout.strip()
                # Remove quotes and split by =
                if "=" in value:
                    value = value.split("=")[-1].strip()
                # Remove any remaining quotes
                value = value.replace('"', '').replace("'", "")
                return value
            
            time.sleep(0.5)  # Small delay between retries
            
        except Exception as e:
            logger.debug(f"SNMP attempt {attempt+1} failed for {ip}: {e}")
            continue
    
    return None

def check_radio_metrics(ip, radio_model_desc):
    """Check radio-specific metrics via SNMP"""
    model_type = detect_radio_model(radio_model_desc)
    metrics = {
        "rssi": "N/A",
        "tx_power": "N/A",
        "rx_power": "N/A",
        "frequency": "N/A",
        "capacity": "N/A",
        "model_detected": model_type
    }
    
    if model_type == "unknown" or not ip:
        return metrics
    
    # Get OIDs for this radio model
    model_config = RADIO_OIDS.get(model_type, {})
    
    # Try to get RSSI (most important metric)
    if "rssi" in model_config:
        rssi_value = get_snmp_metric(ip, model_config["rssi"])
        if rssi_value:
            try:
                rssi_num = float(rssi_value)
                # Convert to negative dBm if positive
                if rssi_num > 0:
                    rssi_num = -rssi_num
                metrics["rssi"] = f"{rssi_num:.1f} dBm"
                
                # Determine signal quality
                if rssi_num >= -60:
                    metrics["signal_quality"] = "Excellent 🟢"
                elif rssi_num >= -70:
                    metrics["signal_quality"] = "Good 🟡"
                elif rssi_num >= -80:
                    metrics["signal_quality"] = "Fair 🟠"
                else:
                    metrics["signal_quality"] = "Poor 🔴"
                    
            except:
                metrics["rssi"] = rssi_value
    
    # Get TX Power
    if "tx_power" in model_config:
        tx_value = get_snmp_metric(ip, model_config["tx_power"])
        if tx_value:
            metrics["tx_power"] = tx_value
    
    # Get RX Power
    if "rx_power" in model_config:
        rx_value = get_snmp_metric(ip, model_config["rx_power"])
        if rx_value:
            metrics["rx_power"] = rx_value
    
    return metrics

def calculate_link_stability(ip, radio_model):
    """Calculate link stability based on multiple pings and SNMP"""
    stability_result = {
        "overall": "UNKNOWN",
        "ping_stability": "UNKNOWN",
        "signal_stability": "UNKNOWN",
        "recommendation": "Check device"
    }
    
    # Step 1: Ping test
    ping_results = []
    for i in range(3):  # 3 quick pings
        result = ping_target(ip, count=2, timeout=1000)
        ping_results.append(result)
        time.sleep(0.3)
    
    # Analyze ping stability
    success_count = sum(1 for r in ping_results if r.get("status") == "UP")
    success_rate = (success_count / len(ping_results)) * 100
    
    if success_rate == 100:
        stability_result["ping_stability"] = "STABLE 🟢"
    elif success_rate >= 70:
        stability_result["ping_stability"] = "MODERATE 🟡"
    else:
        stability_result["ping_stability"] = "UNSTABLE 🔴"
    
    # Step 2: SNMP metrics (if available)
    radio_metrics = check_radio_metrics(ip, radio_model)
    
    # Analyze signal stability
    if radio_metrics.get("rssi") != "N/A":
        try:
            rssi_str = radio_metrics["rssi"]
            rssi_value = float(rssi_str.split()[0])  # Extract number
            
            if rssi_value >= -65:
                stability_result["signal_stability"] = "STRONG 🟢"
                stability_result["recommendation"] = "Link optimal"
            elif rssi_value >= -75:
                stability_result["signal_stability"] = "GOOD 🟡"
                stability_result["recommendation"] = "Monitor signal"
            elif rssi_value >= -85:
                stability_result["signal_stability"] = "WEAK 🟠"
                stability_result["recommendation"] = "Consider adjustment"
            else:
                stability_result["signal_stability"] = "POOR 🔴"
                stability_result["recommendation"] = "Needs intervention"
                
        except:
            stability_result["signal_stability"] = radio_metrics.get("signal_quality", "UNKNOWN")
    
    # Determine overall stability
    if stability_result["ping_stability"].startswith("STABLE") and \
       stability_result["signal_stability"].startswith(("STRONG", "GOOD")):
        stability_result["overall"] = "STABLE 🟢"
    elif stability_result["ping_stability"].startswith("UNSTABLE") or \
         stability_result["signal_stability"].startswith("POOR"):
        stability_result["overall"] = "UNSTABLE 🔴"
    else:
        stability_result["overall"] = "MODERATE 🟡"
    
    return stability_result, radio_metrics

# --- API ENDPOINTS ---
@app.get("/")
def read_root():
    return {"message": "Smart NOC API v2.0", "status": "running", "clients": "600+"}

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "database": "connected" if os.path.exists(DB_FILE) else "missing"
    }

@app.get("/api/inventory")
def get_inventory():
    """Get all inventory items"""
    conn = get_db()
    rows = conn.execute('SELECT * FROM inventory ORDER BY sl, link_name').fetchall()
    conn.close()
    
    data = []
    for row in rows:
        bts_ip = row["bts_ip"] or row["base_ip"] or "N/A"
        client_ip = row["client_ip"] or "N/A"
        gateway_ip = row["gateway_ip"] or "N/A"
        
        # Calculate gateway IP if not set
        if gateway_ip == "N/A" and bts_ip != "N/A":
            try:
                gateway_ip = str(ipaddress.IPv4Address(bts_ip) - 1)
            except:
                pass
        
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
            "Contact_Number": row["contact_number"] or "N/A",
            
            # Legacy fields for compatibility
            "Link_ID": row["link_id"] or row["sl"] or "N/A",
            "BTS_Name": row["bts_name"] or "N/A",
            "Client_Name": row["client_name"] or row["link_name"] or "N/A",
            "Base_IP": bts_ip,
            "Location": row["location"] or row["location_branch"] or "N/A",
            "Operator": row["operator"] or "N/A",
            "Device_Model": row["device_model"] or row["radio_model"] or "N/A"
        })
    return data

@app.post("/api/inventory/bulk")
def bulk_import(data: List[dict]):
    """Bulk import inventory data (for your CSV)"""
    conn = get_db()
    c = conn.cursor()
    
    imported = 0
    updated = 0
    errors = []
    
    try:
        for idx, item in enumerate(data):
            try:
                # Extract and clean fields
                sl = item.get('SL', '').strip() or str(idx + 1)
                link_name = item.get('Link Name', item.get('Link_Name', '')).strip()
                client_ip = item.get('Client IP', item.get('Client_IP', '')).strip()
                
                if not client_ip:
                    continue  # Skip entries without IP
                
                # Check if exists
                existing = c.execute(
                    'SELECT id FROM inventory WHERE client_ip = ?',
                    (client_ip,)
                ).fetchone()
                
                if existing:
                    # Update existing
                    c.execute('''
                        UPDATE inventory SET
                            sl = ?, link_name = ?, location_branch = ?, district = ?,
                            connection_type = ?, pop_name = ?, radio_model = ?,
                            bts_ip = ?, channel = ?, rssi = ?, ssid = ?,
                            device_mode = ?, link_type = ?, frequency_type = ?,
                            frequency_used = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE client_ip = ?
                    ''', (
                        sl,
                        link_name,
                        item.get('Location/Branch', item.get('Location_Branch', '')).strip(),
                        item.get('District', '').strip(),
                        item.get('Connection Type', item.get('Connection_Type', '')).strip(),
                        item.get('POP Name', item.get('POP_Name', '')).strip(),
                        item.get('Radio Model', item.get('Radio_Model', '')).strip(),
                        item.get('BTS IP', item.get('BTS_IP', '')).strip(),
                        item.get('Channel', '').strip(),
                        item.get('RSSI', '').strip(),
                        item.get('SSID', '').strip(),
                        item.get('Device Mode', item.get('Device_Mode', '')).strip(),
                        item.get('Link Type', item.get('Link_Type', '')).strip(),
                        item.get('Frequency Type', item.get('Frequency_Type', '')).strip(),
                        item.get('Frequency Used', item.get('Frequency_Used', '')).strip(),
                        client_ip
                    ))
                    updated += 1
                else:
                    # Insert new
                    c.execute('''
                        INSERT INTO inventory (
                            sl, link_name, location_branch, district,
                            connection_type, pop_name, radio_model,
                            bts_ip, client_ip, channel, rssi, ssid,
                            device_mode, link_type, frequency_type,
                            frequency_used
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        sl,
                        link_name,
                        item.get('Location/Branch', item.get('Location_Branch', '')).strip(),
                        item.get('District', '').strip(),
                        item.get('Connection Type', item.get('Connection_Type', '')).strip(),
                        item.get('POP Name', item.get('POP_Name', '')).strip(),
                        item.get('Radio Model', item.get('Radio_Model', '')).strip(),
                        item.get('BTS IP', item.get('BTS_IP', '')).strip(),
                        client_ip,
                        item.get('Channel', '').strip(),
                        item.get('RSSI', '').strip(),
                        item.get('SSID', '').strip(),
                        item.get('Device Mode', item.get('Device_Mode', '')).strip(),
                        item.get('Link Type', item.get('Link_Type', '')).strip(),
                        item.get('Frequency Type', item.get('Frequency_Type', '')).strip(),
                        item.get('Frequency Used', item.get('Frequency_Used', '')).strip()
                    ))
                    imported += 1
                    
            except Exception as e:
                errors.append(f"Row {idx}: {str(e)}")
                continue
        
        conn.commit()
        
        return {
            "status": "success",
            "imported": imported,
            "updated": updated,
            "errors": errors[:10] if errors else None,
            "message": f"Processed {imported + updated} records"
        }
        
    except Exception as e:
        conn.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        conn.close()

@app.post("/api/diagnose")
def run_diagnosis(item: dict = Body(...)):
    """Run comprehensive diagnostics for a client"""
    ip = item.get("ip")
    if not ip:
        raise HTTPException(status_code=400, detail="IP address required")
    
    conn = get_db()
    row = conn.execute('SELECT * FROM inventory WHERE client_ip = ?', (ip,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Client not found in database")
    
    base_ip = row["bts_ip"] or row["base_ip"] or "N/A"
    gateway_ip = row["gateway_ip"] or "N/A"
    radio_model = row["radio_model"] or "Unknown"
    
    # Calculate gateway if not set
    if gateway_ip == "N/A" and base_ip != "N/A":
        try:
            gateway_ip = str(ipaddress.IPv4Address(base_ip) - 1)
        except:
            pass
    
    results = {
        "client": {"ip": ip, "name": row["link_name"]},
        "base": {"ip": base_ip, "name": row["bts_name"] or "Base Station"},
        "gateway": {"ip": gateway_ip, "name": "Gateway"},
        "diagnostics": {},
        "recommendations": []
    }
    
    # Run parallel diagnostics
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Ping tests
        future_client_ping = executor.submit(ping_target, ip)
        future_base_ping = executor.submit(ping_target, base_ip) if base_ip != "N/A" else None
        future_gw_ping = executor.submit(ping_target, gateway_ip) if gateway_ip != "N/A" else None
        
        # Radio metrics (only for client)
        future_radio_metrics = executor.submit(check_radio_metrics, ip, radio_model)
        future_stability = executor.submit(calculate_link_stability, ip, radio_model)
    
    # Collect ping results
    results["diagnostics"]["ping"] = {
        "client": future_client_ping.result(),
        "base": future_base_ping.result() if future_base_ping else {"status": "SKIPPED"},
        "gateway": future_gw_ping.result() if future_gw_ping else {"status": "SKIPPED"}
    }
    
    # Collect radio metrics
    radio_metrics_result = future_radio_metrics.result()
    stability_result, detailed_metrics = future_stability.result()
    
    results["diagnostics"]["radio"] = radio_metrics_result
    results["diagnostics"]["stability"] = stability_result
    results["diagnostics"]["detailed_metrics"] = detailed_metrics
    
    # Determine overall status
    client_ping_status = results["diagnostics"]["ping"]["client"]["status"]
    base_ping_status = results["diagnostics"]["ping"]["base"]["status"]
    gw_ping_status = results["diagnostics"]["ping"]["gateway"]["status"]
    overall_stability = stability_result["overall"]
    
    # Generate recommendations
    if client_ping_status == "UP":
        if overall_stability.startswith("STABLE"):
            results["overall_status"] = "OPERATIONAL 🟢"
            results["status_code"] = "up"
        elif overall_stability.startswith("MODERATE"):
            results["overall_status"] = "DEGRADED 🟡"
            results["status_code"] = "warning"
            results["recommendations"].append("Signal quality moderate - monitor closely")
        else:
            results["overall_status"] = "UNSTABLE 🔴"
            results["status_code"] = "unstable"
            results["recommendations"].append("Poor signal stability - needs attention")
    elif base_ping_status == "UP":
        results["overall_status"] = "CLIENT DOWN 🔴"
        results["status_code"] = "client_down"
        results["recommendations"].append("Client device offline but base is up")
    elif gw_ping_status == "UP":
        results["overall_status"] = "SECTOR DOWN 🔴"
        results["status_code"] = "sector_down"
        results["recommendations"].append("Base station offline - check sector equipment")
    else:
        results["overall_status"] = "POP ISSUE ⚫"
        results["status_code"] = "pop_down"
        results["recommendations"].append("Gateway unreachable - POP issue detected")
    
    # Add device-specific recommendations
    rssi = radio_metrics_result.get("rssi", "N/A")
    if rssi != "N/A" and "dBm" in rssi:
        try:
            rssi_value = float(rssi.split()[0])
            if rssi_value < -85:
                results["recommendations"].append("Signal very weak - consider antenna alignment")
            elif rssi_value < -75:
                results["recommendations"].append("Signal weak - check for interference")
        except:
            pass
    
    return results

@app.get("/api/stats")
def get_statistics():
    """Get system statistics"""
    conn = get_db()
    
    total = conn.execute('SELECT COUNT(*) FROM inventory').fetchone()[0]
    districts = conn.execute('SELECT COUNT(DISTINCT district) FROM inventory').fetchone()[0]
    pop_count = conn.execute('SELECT COUNT(DISTINCT pop_name) FROM inventory').fetchone()[0]
    
    # Radio model distribution
    radio_stats = conn.execute('''
        SELECT radio_model, COUNT(*) as count 
        FROM inventory 
        WHERE radio_model IS NOT NULL AND radio_model != ''
        GROUP BY radio_model 
        ORDER BY count DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return {
        "total_clients": total,
        "districts": districts,
        "pop_locations": pop_count,
        "radio_distribution": [dict(row) for row in radio_stats],
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }

# --- CSV IMPORT UTILITY ---
@app.post("/api/import/csv")
async def import_csv_file():
    """Endpoint to handle CSV file upload"""
    # This would handle file upload - implement as needed
    return {"message": "Use /api/inventory/bulk for CSV data import"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
