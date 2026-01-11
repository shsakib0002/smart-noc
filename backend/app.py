from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy.orm import sessionmaker
from sqlalchemy import desc
from models import Link, MonitoringLog, engine
from scanner import ping_host, get_real_stats  # <--- FIXED IMPORT

app = Flask(__name__)
CORS(app)
app.secret_key = 'AmberIT_Secret_Key'

Session = sessionmaker(bind=engine)

@app.route('/api/inventory')
def get_inventory():
    s = Session()
    links = s.query(Link).all()
    data = []
    for l in links:
        last = s.query(MonitoringLog).filter_by(link_id=l.id).order_by(desc(MonitoringLog.id)).first()
        status = last.status if last else "UNKNOWN"
        rssi = last.rssi if last else 0
        
        data.append({
            "id": l.id,
            "link_id_str": l.link_id_str,
            "name": l.link_name or "Unknown Client",
            "pop": l.pop_name,
            "ip": l.client_ip,
            "status": status,
            "rssi": rssi,
            "model": l.model,
            "vendor": l.vendor,
            "eth_speed": l.eth_speed,
            "eth_duplex": l.eth_duplex
        })
    s.close()
    return jsonify(data)

@app.route('/api/scan/<int:link_id>', methods=['POST'])
def scan_triple_hop(link_id):
    s = Session()
    link = s.query(Link).get(link_id)
    if not link: return jsonify({"error": "Not Found"}), 404
    
    hops = [
        {"label": "Gateway", "ip": link.gateway_ip},
        {"label": "Base Station", "ip": link.base_ip},
        {"label": "Client Radio", "ip": link.client_ip}
    ]
    
    results = []
    for hop in hops:
        if hop["ip"] and hop["ip"].lower() != 'none':
            lat, loss = ping_host(hop["ip"])
            results.append({"label": hop["label"], "ip": hop["ip"], "latency": lat, "status": "UP" if loss == 0 else "DOWN"})
        else:
            results.append({"label": hop["label"], "ip": "N/A", "status": "SKIP"})

    # REAL STATS FETCH
    vendor = link.vendor or link.model or "Unknown"
    rssi, speed, duplex = get_real_stats(link.client_ip, vendor) # <--- FIXED CALL
    
    s.close()
    
    return jsonify({
        "hops": results,
        "rssi": rssi,
        "eth_speed": speed,
        "eth_duplex": duplex,
        "final_status": "UP" if rssi != 0 else "DOWN"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)