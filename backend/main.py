<script>
        const API_BASE = window.API_BASE || window.location.origin;
        console.log("Connected to:", API_BASE);
        
        let inventoryData = [];
        let currentClient = null;

        document.addEventListener('DOMContentLoaded', () => {
            lucide.createIcons();
            loadInventory();
        });

        async function loadInventory() {
            try {
                const res = await fetch(`${API_BASE}/api/inventory`);
                if (!res.ok) throw new Error("Fetch Failed");
                inventoryData = await res.json();
                renderTable(inventoryData);
            } catch (e) {
                console.error(e);
                document.getElementById('inventoryTable').innerHTML = `<tr><td colspan="6" style="text-align:center; color:#ef4444; padding:20px;">Connection Error. Check Backend.</td></tr>`;
            }
        }

        function renderTable(data) {
            const tbody = document.getElementById('inventoryTable');
            if (!data || data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 40px; color: #555;">No Data Found. Import CSV.</td></tr>`;
                return;
            }
            
            tbody.innerHTML = data.map((item, index) => `
                <tr>
                    <td style="font-weight: 500; color: white;">${item.Link_Name || item.Client_Name || 'Unknown'}</td>
                    <td class="font-mono">${item.Client_IP || '--'}</td>
                    <td class="font-mono">${item.BTS_Name || item.Base_IP || item.BTS_IP || '--'}</td>
                    <td>${item.Location_Branch || item.Location || '--'}</td>
                    <td>${item.District || '--'}</td>
                    <td style="text-align: right;">
                        <button class="btn-inspect" onclick='openPanel(${index})'>Inspect</button>
                    </td>
                </tr>
            `).join('');
            lucide.createIcons();
        }

        function filterTable() {
            const term = document.getElementById('searchInput').value.toLowerCase();
            const filtered = inventoryData.filter(item => 
                (item.Link_Name && item.Link_Name.toLowerCase().includes(term)) ||
                (item.Client_IP && item.Client_IP.includes(term)) ||
                (item.BTS_Name && item.BTS_Name.toLowerCase().includes(term)) ||
                (item.Location_Branch && item.Location_Branch.toLowerCase().includes(term))
            );
            renderTable(filtered);
        }

        function openPanel(index) {
            currentClient = inventoryData[index];
            document.getElementById('diagPanel').classList.add('open');

            // --- POPULATE DATA ---
            setText('p-name', currentClient.Link_Name || currentClient.Client_Name);
            setText('p-ip', currentClient.Client_IP);
            setText('p-sl', currentClient.SL || currentClient.Link_ID);
            setText('p-pop', currentClient.POP_Name);
            setText('p-loc', currentClient.Location_Branch || currentClient.Location);
            setText('p-dist', currentClient.District);

            setText('p-model', currentClient.Radio_Model || currentClient.Device_Model);
            setText('p-mode', currentClient.Device_Mode);
            setText('p-conn', currentClient.Connection_Type);
            setText('p-linktype', currentClient.Link_Type);

            setText('p-bts-name', currentClient.BTS_Name || 'N/A');
            setText('p-bts-ip', currentClient.BTS_IP || currentClient.Base_IP);
            setText('p-ssid', currentClient.SSID);
            setText('p-freq', (currentClient.Frequency_Used || '') + ' ' + (currentClient.Frequency_Type || ''));
            setText('p-chan', currentClient.Channel);
            setText('p-rssi', currentClient.RSSI);
            setText('p-gw', currentClient.Gateway_IP || 'Calculating...');

            document.getElementById('resultsArea').style.display = 'none';
            const btn = document.getElementById('btnRun');
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="play"></i> Run Live Diagnostics`;
            lucide.createIcons();
        }

        function setText(id, val) {
            document.getElementById(id).innerText = (val && val !== "N/A" && val !== "") ? val : "--";
        }

        function closePanel() {
            document.getElementById('diagPanel').classList.remove('open');
        }

        async function runDiagnostics() {
            if (!currentClient) return;
            const btn = document.getElementById('btnRun');
            btn.disabled = true;
            btn.innerHTML = `<i data-lucide="loader-2" class="spin"></i> Diagnosing...`;
            lucide.createIcons();

            try {
                const res = await fetch(`${API_BASE}/api/diagnose`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ ip: currentClient.Client_IP })
                });
                const data = await res.json();
                
                document.getElementById('resultsArea').style.display = 'block';
                const statusEl = document.getElementById('res-status');
                statusEl.innerText = data.final_status;
                
                statusEl.style.color = data.final_status.includes('UP') ? '#10b981' : (data.final_status.includes('UNSTABLE') ? '#f59e0b' : '#ef4444');
                document.getElementById('res-cause').innerText = data.cause;

                setNode('n-client', data.topology?.client?.status);
                setNode('n-base', data.topology?.base?.status);
                setNode('n-gw', data.topology?.gw?.status);

            } catch (e) {
                alert("Diagnostics Failed: " + e.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<i data-lucide="rotate-cw"></i> Re-Run Test`;
                lucide.createIcons();
            }
        }

        function setNode(id, status) {
            const el = document.getElementById(id);
            el.className = 'node';
            if (status === 'UP') el.classList.add('up');
            else if (status === 'DOWN') el.classList.add('down');
        }

        // --- SMART CSV PARSER ---
        document.getElementById('csvInput').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = async (ev) => {
                const text = ev.target.result;
                const lines = text.split('\n').filter(l => l.trim());
                if (lines.length < 2) return alert("CSV is empty!");

                // Helper to split CSV lines correctly (handling quotes)
                const parseLine = (row) => {
                    const res = [];
                    let cur = '', inQuote = false;
                    for (let c of row) {
                        if (c === '"') { inQuote = !inQuote; }
                        else if (c === ',' && !inQuote) { res.push(cur.trim()); cur = ''; }
                        else { cur += c; }
                    }
                    res.push(cur.trim());
                    return res;
                };

                // 1. Find Header Index
                const headers = parseLine(lines[0]).map(h => h.toLowerCase().replace(/[\s_"]/g, ''));
                console.log("Found Headers:", headers);

                // 2. Map Columns (Find where 'Client IP' or 'Link Name' actually is)
                const idx = {
                    linkName: headers.findIndex(h => h.includes('linkname') || h.includes('clientname')),
                    ip: headers.findIndex(h => h.includes('clientip') || h.includes('ipaddress')),
                    baseIp: headers.findIndex(h => h.includes('btsip') || h.includes('baseip')),
                    location: headers.findIndex(h => h.includes('location') || h.includes('branch')),
                    district: headers.findIndex(h => h.includes('district')),
                    sl: headers.findIndex(h => h.includes('sl') || h.includes('linkid')),
                    // Add extra fields
                    model: headers.findIndex(h => h.includes('model')),
                    ssid: headers.findIndex(h => h.includes('ssid')),
                    freq: headers.findIndex(h => h.includes('frequency')),
                    rssi: headers.findIndex(h => h.includes('rssi'))
                };

                // 3. Parse Data
                const payload = lines.slice(1).map(line => {
                    const col = parseLine(line);
                    // Must have at least an IP or Name
                    if (!col[idx.ip] && !col[idx.linkName]) return null;

                    return {
                        "Link_Name": col[idx.linkName] || col[idx.ip],
                        "Client_IP": col[idx.ip],
                        "BTS_IP": col[idx.baseIp],
                        "Location": col[idx.location],
                        "District": col[idx.district],
                        "SL": col[idx.sl],
                        "Radio_Model": col[idx.model],
                        "SSID": col[idx.ssid],
                        "Frequency_Used": col[idx.freq],
                        "RSSI": col[idx.rssi]
                    };
                }).filter(x => x);

                console.log("Payload to Send:", payload);

                if (payload.length === 0) return alert("Could not match columns! Check CSV headers.");

                // 4. Send
                await fetch(`${API_BASE}/api/inventory`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                
                alert(`Success! Imported ${payload.length} items.`);
                loadInventory();
            };
            reader.readAsText(file);
        });
    </script>
