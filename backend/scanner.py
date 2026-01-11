import subprocess
import re
import time
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from models import Link, MonitoringLog, engine

# SNMP LIBRARY
try:
    from pysnmp.hlapi import *
    HAS_SNMP = True
except ImportError:
    HAS_SNMP = False
    print("WARNING: 'pysnmp' not installed. Run: pip install pysnmp")

PING_TIMEOUT_MS = 1000
COMMUNITY_STRING = 'public' 

def snmp_get(ip, oid):
    """Real SNMP Query Function"""
    if not HAS_SNMP: return None
    try:
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(COMMUNITY_STRING, mpModel=1), # SNMP v2c
            UdpTransportTarget((ip, 161), timeout=1, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        
        if errorIndication or errorStatus:
            return None
        
        for varBind in varBinds:
            return varBind[1]
    except:
        return None
    return None

def get_real_stats(ip, vendor):
    """Fetches REAL data from devices based on Vendor."""
    rssi = 0
    speed = "Unknown"
    duplex = "Unknown"
    
    # Defaults
    if not vendor: vendor = "Unknown"

    # --- CAMBIUM ePMP ---
    if "cambium" in vendor.lower() or "epmp" in vendor.lower():
        val = snmp_get(ip, '1.3.6.1.4.1.17713.21.1.2.1.0')
        if val: rssi = int(val)

        # LAN Speed (Port 1)
        lan_val = snmp_get(ip, '1.3.6.1.2.1.2.2.1.5.1') 
        if lan_val:
            s = int(lan_val)
            if s == 100000000: speed = "100Mbps"
            elif s == 1000000000: speed = "1Gbps"
            elif s == 10000000: speed = "10Mbps"
            duplex = "Full" 

    # --- UBIQUITI ---
    elif "ubiquiti" in vendor.lower() or "powerbeam" in vendor.lower() or "nano" in vendor.lower():
        val = snmp_get(ip, '1.3.6.1.4.1.41112.1.4.5.1.5.1')
        if val: rssi = int(val)
        
        lan_val = snmp_get(ip, '1.3.6.1.2.1.2.2.1.5.1')
        if lan_val:
            s = int(lan_val)
            if s == 100000000: speed = "100Mbps"
            elif s == 1000000000: speed = "1Gbps"
            duplex = "Full"

    return rssi, speed, duplex

def ping_host(ip):
    if not ip or ip.lower() == 'nan' or ip == '': return 0, 100.0
    try:
        res = subprocess.run(['ping', '-n', '1', '-w', str(PING_TIMEOUT_MS), ip], 
                             stdout=subprocess.PIPE, text=True)
        if "Received = 1" in res.stdout:
            match = re.search(r"time[=<](\d+)ms", res.stdout)
            return int(match.group(1)) if match else 1, 0.0
        return 0, 100.0
    except:
        return 0, 100.0

def scan_cycle():
    Session = sessionmaker(bind=engine)
    session = Session()
    links = session.query(Link).filter_by(is_active=True).all()
    
    print(f"--- REAL SCAN STARTED: {len(links)} Links ---")
    
    for link in links:
        # 1. Ping
        lat, loss = ping_host(link.client_ip)
        
        # 2. SNMP
        rssi = 0
        if loss == 0 and HAS_SNMP:
            vendor = link.vendor or link.model or "Unknown"
            rssi_val, speed_val, duplex_val = get_real_stats(link.client_ip, vendor)
            
            rssi = rssi_val
            link.eth_speed = speed_val
            link.eth_duplex = duplex_val
        
        # 3. Status
        status = "UP"
        if loss == 100: status = "DOWN"
        elif rssi != 0 and rssi < -75: status = "DEGRADED"
        
        # 4. Save
        log = MonitoringLog(link_id=link.id, status=status, latency=lat, loss=loss, rssi=rssi)
        session.add(log)
        
        # 5. Console Print (SAFE VERSION)
        icon = "🟢" if status == "UP" else ("🔴" if status == "DOWN" else "🟠")
        safe_name = (link.link_name or "Unknown")[:15] # <--- FIX HERE
        print(f"{icon} {safe_name:<15} | {link.client_ip} | {rssi}dBm | {link.eth_speed}")

    session.commit()
    session.close()

if __name__ == "__main__":
    while True:
        scan_cycle()
        time.sleep(30)