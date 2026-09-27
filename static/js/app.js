let currentActiveTab = 'tab-live';
let activeCameraId = null;
let liveWs = null;
let currentHistoryPage = 1;
let totalHistoryPages = 1;

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

async function initDashboard() {
    await loadCameras();
    await loadStats();
    await loadAlerts();
    await loadAlertRules();

    // Auto-refresh stats and alerts every 15s
    setInterval(loadStats, 15000);
    setInterval(loadAlerts, 15000);
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.add('hidden');
        el.classList.remove('block');
    });
    document.querySelectorAll('.nav-tab').forEach(el => {
        el.classList.remove('bg-blue-600', 'text-white');
        el.classList.add('text-slate-400');
    });

    const activeEl = document.getElementById(tabId);
    if (activeEl) {
        activeEl.classList.remove('hidden');
        activeEl.classList.add('block');
    }
    const btn = document.getElementById(`btn-${tabId}`);
    if (btn) {
        btn.classList.add('bg-blue-600', 'text-white');
        btn.classList.remove('text-slate-400');
    }

    if (tabId === 'tab-history') {
        loadDetectionHistory(1);
    }
}

// ==================== CAMERAS ====================
async function loadCameras() {
    try {
        const res = await fetch('/api/cameras');
        const cameras = await res.json();
        
        // Update KPI
        const activeCount = cameras.filter(c => c.is_active && c.status === 'online').length;
        document.getElementById('stat-online-cams').innerText = `${activeCount} / ${cameras.length}`;

        // Populate Selects
        const selectLive = document.getElementById('select-camera');
        const filterHist = document.getElementById('filter-history-camera');
        const ruleCam = document.getElementById('rule-camera-select');

        selectLive.innerHTML = '<option value="">-- Pilih Kamera --</option>';
        filterHist.innerHTML = '<option value="">Semua CCTV</option>';
        ruleCam.innerHTML = '<option value="">Semua Kamera</option>';

        cameras.forEach(c => {
            const opt = `<option value="${c.id}">${c.name} (${c.location || 'No Loc'})</option>`;
            selectLive.innerHTML += opt;
            filterHist.innerHTML += opt;
            ruleCam.innerHTML += opt;
        });

        // Set default camera if none selected
        if (!activeCameraId && cameras.length > 0) {
            changeLiveCamera(cameras[0].id);
            selectLive.value = cameras[0].id;
        }

        // Render camera cards in tab-cameras
        renderCameraCards(cameras);
    } catch (e) {
        console.error('Failed to load cameras:', e);
    }
}

function renderCameraCards(cameras) {
    const grid = document.getElementById('camera-cards-grid');
    if (!cameras || cameras.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                <i class="fa-solid fa-video-slash text-3xl mb-2"></i>
                <p>Belum ada sumber CCTV yang didaftarkan.</p>
                <button onclick="openAddCameraModal()" class="mt-3 text-xs text-blue-400 hover:underline">+ Tambah CCTV Pertama</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = cameras.map(c => {
        const isOnline = c.status === 'online';
        const badgeColor = isOnline ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20';
        return `
            <div class="bg-slate-850 border border-slate-800 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition">
                <div>
                    <div class="flex items-start justify-between">
                        <div>
                            <h3 class="font-bold text-white text-sm">${c.name}</h3>
                            <p class="text-xs text-slate-400"><i class="fa-solid fa-location-dot mr-1"></i>${c.location || 'Lokasi tidak diset'}</p>
                        </div>
                        <span class="text-[11px] px-2 py-0.5 rounded-full border font-semibold ${badgeColor}">
                            ${c.status.toUpperCase()}
                        </span>
                    </div>
                    <p class="text-[11px] font-mono text-slate-500 truncate mt-3 bg-slate-900 px-2 py-1 rounded" title="${c.stream_url}">
                        ${c.stream_url}
                    </p>
                </div>
                <div class="flex items-center justify-between mt-4 pt-3 border-t border-slate-800 text-xs">
                    <span class="text-slate-400">FPS: <strong class="text-slate-200">${c.fps || '0.0'}</strong></span>
                    <div class="flex space-x-2">
                        <button onclick="changeLiveCamera(${c.id}); switchTab('tab-live')" class="text-blue-400 hover:text-blue-300 font-medium">Live</button>
                        <button onclick="openEditCameraModal(${JSON.stringify(c).replace(/"/g, '&quot;')})" class="text-amber-400 hover:text-amber-300 font-medium">Edit</button>
                        <button onclick="deleteCamera(${c.id})" class="text-rose-400 hover:text-rose-300 font-medium">Hapus</button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ==================== LIVE STREAM & WEBSOCKET ====================
function changeLiveCamera(cameraId) {
    if (!cameraId) {
        activeCameraId = null;
        document.getElementById('live-video-player').classList.add('hidden');
        document.getElementById('live-placeholder').classList.remove('hidden');
        document.getElementById('live-cam-title').innerText = 'Tidak Ada Kamera Dipilih';
        if (liveWs) { liveWs.close(); liveWs = null; }
        return;
    }

    activeCameraId = parseInt(cameraId);
    const player = document.getElementById('live-video-player');
    const placeholder = document.getElementById('live-placeholder');
    const select = document.getElementById('select-camera');
    
    select.value = cameraId;
    const selectedOption = select.options[select.selectedIndex];
    document.getElementById('live-cam-title').innerText = selectedOption ? selectedOption.text : `Kamera #${cameraId}`;

    placeholder.classList.add('hidden');
    player.classList.remove('hidden');
    player.src = `/api/live/${cameraId}/stream?t=${Date.now()}`;

    // Setup live websocket
    setupLiveWebSocket(cameraId);
}

function refreshLiveFeed() {
    if (activeCameraId) {
        changeLiveCamera(activeCameraId);
    }
}

function setupLiveWebSocket(cameraId) {
    if (liveWs) {
        liveWs.close();
    }

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/api/live/ws/${cameraId}`;
    
    liveWs = new WebSocket(wsUrl);
    liveWs.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateLiveStats(data);
        } catch (e) {
            console.error(e);
        }
    };
    liveWs.onclose = () => {
        // Reconnect after 3s if still on live tab
        if (activeCameraId === cameraId && currentActiveTab === 'tab-live') {
            setTimeout(() => setupLiveWebSocket(cameraId), 3000);
        }
    };
}

function updateLiveStats(data) {
    document.getElementById('live-fps').innerText = data.fps || '0.0';
    const statusEl = document.getElementById('live-stream-status');
    if (data.is_connected) {
        statusEl.innerText = 'Tersambung (Online)';
        statusEl.className = 'text-emerald-400 font-bold';
    } else {
        statusEl.innerText = data.last_error ? `Error: ${data.last_error}` : 'Terputus (Offline)';
        statusEl.className = 'text-rose-400 font-bold';
    }

    const summary = data.latest_summary || {};
    const objectsList = document.getElementById('live-objects-list');
    const totalCountBadge = document.getElementById('live-total-count-badge');

    const entries = Object.entries(summary);
    const totalCount = entries.reduce((acc, [, cnt]) => acc + cnt, 0);
    totalCountBadge.innerText = `${totalCount} Objek`;

    if (entries.length === 0) {
        objectsList.innerHTML = `<p class="text-xs text-slate-500 text-center py-4">Tidak ada target objek dalam frame.</p>`;
        return;
    }

    objectsList.innerHTML = entries.map(([cls, cnt]) => `
        <div class="flex items-center justify-between p-2.5 bg-slate-800/70 border border-slate-700/60 rounded-xl">
            <div class="flex items-center space-x-2.5">
                <span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                <span class="capitalize text-xs font-semibold text-white">${cls}</span>
            </div>
            <span class="text-xs font-bold bg-slate-900 px-2.5 py-1 rounded-lg text-blue-400">${cnt} unit</span>
        </div>
    `).join('');
}

async function takeInstantSnapshot() {
    if (!activeCameraId) return;
    try {
        const res = await fetch(`/api/live/${activeCameraId}/snapshot`);
        if (!res.ok) throw new Error('Gagal mengambil frame');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        showImageModal(url);
    } catch (e) {
        alert('Gagal mengambil snapshot: ' + e.message);
    }
}

// ==================== STATS & ALERTS ====================
async function loadStats() {
    try {
        const res = await fetch('/api/detections/stats?hours=24');
        const data = await res.json();
        document.getElementById('stat-total-objects').innerText = (data.total_objects_detected || 0).toLocaleString();
    } catch (e) {
        console.error(e);
    }
}

async function loadAlerts() {
    try {
        const res = await fetch('/api/alerts?limit=20');
        const alerts = await res.json();
        document.getElementById('stat-total-alerts').innerText = alerts.length;

        // Render recent alerts in live tab sidebar
        const recentEl = document.getElementById('recent-alerts-list');
        if (alerts.length === 0) {
            recentEl.innerHTML = `<p class="text-xs text-slate-500 text-center py-2">Tidak ada alert terkini</p>`;
        } else {
            recentEl.innerHTML = alerts.slice(0, 3).map(a => `
                <div class="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs">
                    <p class="font-semibold text-amber-300">${a.details}</p>
                    <p class="text-[10px] text-slate-400 mt-1">${new Date(a.triggered_at).toLocaleTimeString()}</p>
                </div>
            `).join('');
        }

        // Render alerts table in tab-alerts
        const tbody = document.getElementById('alerts-table-body');
        if (alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" class="px-4 py-6 text-center text-slate-500">Belum ada peringatan yang tercatat.</td></tr>`;
        } else {
            tbody.innerHTML = alerts.map(a => `
                <tr class="hover:bg-slate-800/40">
                    <td class="px-4 py-3 text-slate-400 whitespace-nowrap">${new Date(a.triggered_at).toLocaleString()}</td>
                    <td class="px-4 py-3 font-semibold text-white whitespace-nowrap">${a.camera_name || 'Kamera #' + a.camera_id}</td>
                    <td class="px-4 py-3 text-amber-300">${a.details}</td>
                </tr>
            `).join('');
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadAlertRules() {
    try {
        const res = await fetch('/api/alerts/rules');
        const rules = await res.json();
        const list = document.getElementById('rules-list');
        if (rules.length === 0) {
            list.innerHTML = `<p class="text-xs text-slate-500">Belum ada aturan alert.</p>`;
            return;
        }

        list.innerHTML = rules.map(r => `
            <div class="flex items-center justify-between p-2.5 bg-slate-800 rounded-lg text-xs">
                <div>
                    <span class="font-bold text-white capitalize">${r.object_class}</span> &ge; <strong class="text-amber-400">${r.threshold_count}</strong>
                    <span class="text-slate-400 block text-[11px]">${r.camera_name}</span>
                </div>
                <button onclick="deleteAlertRule(${r.id})" class="text-rose-400 hover:text-rose-300"><i class="fa-solid fa-trash"></i></button>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function submitAlertRule(e) {
    e.preventDefault();
    const camVal = document.getElementById('rule-camera-select').value;
    const payload = {
        camera_id: camVal ? parseInt(camVal) : null,
        object_class: document.getElementById('rule-class-select').value,
        threshold_count: parseInt(document.getElementById('rule-threshold').value),
        time_window_seconds: 60
    };

    try {
        const res = await fetch('/api/alerts/rules', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Gagal menyimpan aturan alert');
        await loadAlertRules();
        alert('Aturan alert berhasil ditambahkan!');
    } catch (err) {
        alert(err.message);
    }
}

async function deleteAlertRule(ruleId) {
    if (!confirm('Hapus aturan alert ini?')) return;
    try {
        await fetch(`/api/alerts/rules/${ruleId}`, { method: 'DELETE' });
        loadAlertRules();
    } catch (e) {
        alert(e.message);
    }
}

// ==================== DETECTION HISTORY ====================
async function loadDetectionHistory(page = 1) {
    currentHistoryPage = page;
    const camId = document.getElementById('filter-history-camera').value;
    const objClass = document.getElementById('filter-history-class').value;
    const start = document.getElementById('filter-history-start').value;
    const end = document.getElementById('filter-history-end').value;

    const params = new URLSearchParams({
        page: page,
        page_size: 20
    });
    if (camId) params.append('camera_id', camId);
    if (objClass) params.append('object_class', objClass);
    if (start) params.append('start_date', new Date(start).toISOString());
    if (end) params.append('end_date', new Date(end).toISOString());

    const tbody = document.getElementById('history-table-body');
    tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-slate-500">Memuat data...</td></tr>`;

    try {
        const res = await fetch(`/api/detections?${params.toString()}`);
        const data = await res.json();
        
        totalHistoryPages = Math.ceil(data.total / data.page_size) || 1;
        document.getElementById('history-pagination-info').innerText = `Halaman ${data.page} dari ${totalHistoryPages} (Total: ${data.total} catatan)`;
        document.getElementById('btn-page-prev').disabled = data.page <= 1;
        document.getElementById('btn-page-next').disabled = data.page >= totalHistoryPages;

        if (data.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-slate-500">Tidak ada riwayat deteksi yang sesuai filter.</td></tr>`;
            return;
        }

        tbody.innerHTML = data.items.map(item => `
            <tr class="hover:bg-slate-800/40">
                <td class="px-4 py-3 whitespace-nowrap text-slate-400">${new Date(item.detected_at).toLocaleString()}</td>
                <td class="px-4 py-3 font-semibold text-white whitespace-nowrap">${item.camera_name || 'Kamera #' + item.camera_id}</td>
                <td class="px-4 py-3 capitalize"><span class="px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded-md font-semibold">${item.object_class}</span></td>
                <td class="px-4 py-3 font-bold text-white">${item.object_count}</td>
                <td class="px-4 py-3 text-slate-400">${item.avg_confidence ? (item.avg_confidence * 100).toFixed(1) + '%' : '-'}</td>
                <td class="px-4 py-3">
                    ${item.snapshot_path ? `
                        <button onclick="showImageModal('/${item.snapshot_path}')" class="text-blue-400 hover:text-blue-300 font-medium flex items-center">
                            <i class="fa-solid fa-image mr-1"></i> Lihat Foto
                        </button>
                    ` : '<span class="text-slate-600">-</span>'}
                </td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-rose-400">Gagal memuat histori: ${e.message}</td></tr>`;
    }
}

function changeHistoryPage(direction) {
    const target = currentHistoryPage + direction;
    if (target >= 1 && target <= totalHistoryPages) {
        loadDetectionHistory(target);
    }
}

function exportCSV() {
    const camId = document.getElementById('filter-history-camera').value;
    const objClass = document.getElementById('filter-history-class').value;
    const start = document.getElementById('filter-history-start').value;
    const end = document.getElementById('filter-history-end').value;

    const params = new URLSearchParams();
    if (camId) params.append('camera_id', camId);
    if (objClass) params.append('object_class', objClass);
    if (start) params.append('start_date', new Date(start).toISOString());
    if (end) params.append('end_date', new Date(end).toISOString());

    window.open(`/api/detections/export/csv?${params.toString()}`, '_blank');
}

// ==================== CAMERA MODAL & CRUD ====================
function openAddCameraModal() {
    document.getElementById('modal-camera-title').innerText = 'Tambah Sumber CCTV';
    document.getElementById('camera-form-id').value = '';
    document.getElementById('camera-form-name').value = '';
    document.getElementById('camera-form-location').value = '';
    document.getElementById('camera-form-url').value = '';
    document.getElementById('camera-form-active').checked = true;
    document.getElementById('url-test-feedback').classList.add('hidden');
    document.getElementById('modal-camera').classList.remove('hidden');
}

function openEditCameraModal(cam) {
    document.getElementById('modal-camera-title').innerText = 'Edit Sumber CCTV';
    document.getElementById('camera-form-id').value = cam.id;
    document.getElementById('camera-form-name').value = cam.name;
    document.getElementById('camera-form-location').value = cam.location || '';
    document.getElementById('camera-form-url').value = cam.stream_url;
    document.getElementById('camera-form-active').checked = cam.is_active;
    document.getElementById('url-test-feedback').classList.add('hidden');
    document.getElementById('modal-camera').classList.remove('hidden');
}

function closeModalCamera() {
    document.getElementById('modal-camera').classList.add('hidden');
}

async function testUrlBeforeSave() {
    const url = document.getElementById('camera-form-url').value.trim();
    const feedback = document.getElementById('url-test-feedback');
    if (!url) {
        alert('Masukkan URL stream terlebih dahulu');
        return;
    }

    feedback.innerText = 'Menguji koneksi stream...';
    feedback.className = 'text-[11px] mt-1 text-blue-400 block';
    
    try {
        const res = await fetch(`/api/cameras/validate-url?stream_url=${encodeURIComponent(url)}`, { method: 'POST' });
        const data = await res.json();
        if (data.valid) {
            feedback.innerText = '✓ ' + data.message;
            feedback.className = 'text-[11px] mt-1 text-emerald-400 block font-semibold';
        } else {
            feedback.innerText = '✗ ' + data.message;
            feedback.className = 'text-[11px] mt-1 text-rose-400 block font-semibold';
        }
    } catch (e) {
        feedback.innerText = '✗ Gagal menguji URL: ' + e.message;
        feedback.className = 'text-[11px] mt-1 text-rose-400 block font-semibold';
    }
}

async function submitCameraForm(e) {
    e.preventDefault();
    const camId = document.getElementById('camera-form-id').value;
    const payload = {
        name: document.getElementById('camera-form-name').value.trim(),
        location: document.getElementById('camera-form-location').value.trim(),
        stream_url: document.getElementById('camera-form-url').value.trim(),
        is_active: document.getElementById('camera-form-active').checked
    };

    const isEdit = !!camId;
    const url = isEdit ? `/api/cameras/${camId}` : '/api/cameras';
    const method = isEdit ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Gagal menyimpan kamera');
        }

        closeModalCamera();
        await loadCameras();
        alert(`Kamera berhasil ${isEdit ? 'diperbarui' : 'ditambahkan'}!`);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function deleteCamera(cameraId) {
    if (!confirm('Yakin ingin menghapus kamera ini beserta datanya?')) return;
    try {
        const res = await fetch(`/api/cameras/${cameraId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Gagal menghapus');
        await loadCameras();
        if (activeCameraId === cameraId) {
            changeLiveCamera(null);
        }
    } catch (e) {
        alert(e.message);
    }
}

// ==================== IMAGE MODAL ====================
function showImageModal(src) {
    const modal = document.getElementById('modal-image');
    document.getElementById('modal-image-img').src = src;
    modal.classList.remove('hidden');
}

function closeModalImage() {
    document.getElementById('modal-image').classList.add('hidden');
    document.getElementById('modal-image-img').src = '';
}
