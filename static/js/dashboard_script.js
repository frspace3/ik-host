    window.shownHackAlerts = new Set();

    // Copy / Move state
    let moveCopyAction = '';
    let moveCopySourcePath = '';
    let moveCopyFiles = [];
    let moveCopyCurrentPath = '';

    // Global fetch interceptor to detect hack block responses automatically
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const response = await originalFetch.apply(this, args);
            const clonedResponse = response.clone();
            clonedResponse.json().then(data => {
                if (data && (data.msg === "you cant hack anything from here . so you should go and fuck your self \ud83e\udd23" || (data.log && data.log.includes("you cant hack anything from here")))) {
                    const fld = currentServer ? currentServer.folder : 'global';
                    if (!window.shownHackAlerts.has(fld)) {
                        window.shownHackAlerts.add(fld);
                        Swal.fire({
                            title: "Error",
                            text: "you cant hack anything from here . so you should go and fuck your self \ud83e\udd23",
                            icon: "error"
                        });
                    }
                }
            }).catch(() => {
                clonedResponse.text().then(text => {
                    if (text && text.includes("you cant hack anything from here")) {
                        const fld = currentServer ? currentServer.folder : 'global';
                        if (!window.shownHackAlerts.has(fld)) {
                            window.shownHackAlerts.add(fld);
                            Swal.fire({
                                title: "Error",
                                text: "you cant hack anything from here . so you should go and fuck your self \ud83e\udd23",
                                icon: "error"
                            });
                        }
                    }
                }).catch(() => {});
            });
            return response;
        } catch (error) {
            throw error;
        }
    };

    // Intercept Swal.fire to show warning GIF for hacking attempts
    // Safely wrap in a check — if SweetAlert2 CDN hasn't loaded yet, retry until available
    function _patchSwal() {
        if (typeof Swal === 'undefined' || !Swal.fire) {
            setTimeout(_patchSwal, 200);
            return;
        }
        const originalSwalFire = Swal.fire.bind(Swal);
        Swal.fire = function(...args) {
            if (args.length > 0) {
                let opt = args[0];
                if (typeof opt === 'object' && opt !== null) {
                    let text = opt.text || opt.html || '';
                    let title = opt.title || '';
                    if (String(text).includes("you cant hack anything from here") || String(title).includes("you cant hack anything from here")) {
                        opt.icon = 'error';
                        opt.html = `<div style="font-size: 1.1rem; line-height: 1.5; margin-bottom: 15px;">${text}</div><div><img src="/static/hack_blocked.gif" style="max-width: 100%; height: auto; border-radius: 12px; border: 1px solid rgba(255, 51, 51, 0.4); box-shadow: 0 4px 15px rgba(255, 51, 51, 0.2);" alt="Hacking Blocked" /></div>`;
                        delete opt.text;
                        opt.background = '#0b0b0b';
                        opt.color = '#e2e2e2';
                    }
                } else if (typeof opt === 'string') {
                    if (opt.includes("you cant hack anything from here") || (args[1] && String(args[1]).includes("you cant hack anything from here"))) {
                        let title = args[0];
                        let text = args[1] || '';
                        let icon = args[2] || 'error';
                        return originalSwalFire({
                            title: title,
                            html: `<div style="font-size: 1.1rem; line-height: 1.5; margin-bottom: 15px;">${text}</div><div><img src="/static/hack_blocked.gif" style="max-width: 100%; height: auto; border-radius: 12px; border: 1px solid rgba(255, 51, 51, 0.4); box-shadow: 0 4px 15px rgba(255, 51, 51, 0.2);" alt="Hacking Blocked" /></div>`,
                            icon: icon,
                            background: '#0b0b0b',
                            color: '#e2e2e2'
                        });
                    }
                }
            }
            return originalSwalFire.apply(this, args);
        };
    }
    _patchSwal();

    let currentServer  = null;
    let logInterval    = null;
    let currentPath    = '';
    let editor         = null;
    let cmdHistory     = [];
    let cmdHistIdx     = -1;
    let consoleExpanded = false;
    let showDateTime   = true;
    let consoleFontSize = 11;  // px, default
    let selectedServers = new Set();

    // ─── Change detection for console log ───────
    let _lastLogContent = '';

    // ─── Helpers ────────────────────────────────
    function h(s) {
        return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    function ea(s) { return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

    function toast(icon, title, text='') {
        Swal.fire({
            icon, title, text,
            toast:true, position:'top-end', timer:2000, showConfirmButton:false,
            background:'#0b0b0b', color:'#e2e2e2',
            customClass: { popup: 'toast-popup' }
        });
    }

    // ─── HOME VIEW ──────────────────────────────
    async function loadServers() {
        const res  = await fetch('/api/v1/servers');
        const data = await res.json();
        if (data.servers) {
            const hackedServer = data.servers.find(s => s.is_hacked);
            if (hackedServer && !window.shownHackAlerts.has(hackedServer.folder)) {
                window.shownHackAlerts.add(hackedServer.folder);
                Swal.fire({
                    title: "Error",
                    text: "you cant hack anything from here . so you should go and fuck your self \ud83e\udd23",
                    icon: "error"
                });
            }
        }
        const topRamEl = document.getElementById('topRamUsage');
        if (topRamEl) {
            const sysRam = typeof data.sys_ram_mb !== 'undefined' ? Number(data.sys_ram_mb).toFixed(1) : (data.total_ram_mb || 0).toFixed(1);
            const instRam = typeof data.total_ram_mb !== 'undefined' ? Number(data.total_ram_mb).toFixed(1) : '0.0';
            topRamEl.textContent = `RAM: ${sysRam} MB / 1024 MB (Instances: ${instRam} MB)`;
        }
        const list = document.getElementById('serverList');
        if (!data.servers || !data.servers.length) {
            list.innerHTML = `<div class="empty-state">No instances yet. Click <strong>+ Create</strong> to get started.</div>`;
            selectedServers.clear();
            updateBulkActionButtons();
            return;
        }

        // Clean up selectedServers Set to remove folders that no longer exist
        const currentFolders = new Set(data.servers.map(s => s.folder));
        selectedServers.forEach(fld => {
            if (!currentFolders.has(fld)) {
                selectedServers.delete(fld);
            }
        });

        // Apply saved custom drag order if present
        try {
            const savedOrder = JSON.parse(localStorage.getItem('ik_instance_order') || '[]');
            if (savedOrder && savedOrder.length) {
                const orderMap = new Map(savedOrder.map((folder, index) => [folder, index]));
                data.servers.sort((a, b) => {
                    const idxA = orderMap.has(a.folder) ? orderMap.get(a.folder) : 9999;
                    const idxB = orderMap.has(b.folder) ? orderMap.get(b.folder) : 9999;
                    return idxA - idxB;
                });
            }
        } catch (err) {}

        list.innerHTML = data.servers.map(s => {
            const running   = s.online;
            const suspended = s.status === 'suspended';
            const runner    = s.runner_status || 'Offline';
            const health    = s.health_status || 'Unknown';
            const projType  = s.project_type || 'script';
            const cardClass = suspended ? 'suspended' : (running ? 'running' : '');
            
            const isSelected = selectedServers.has(s.folder) ? 'checked' : '';

            // Determine primary status badge
            let statusBadge = '';
            if (suspended) {
                statusBadge = `<span class="badge badge-suspended">SUSPENDED</span>`;
            } else if (runner === 'Deploying') {
                statusBadge = `<span class="badge badge-deploying"><i class="fas fa-spinner fa-spin"></i> DEPLOYING</span>`;
            } else if (runner === 'Installing') {
                statusBadge = `<span class="badge badge-installing"><i class="fas fa-cog fa-spin"></i> INSTALLING</span>`;
            } else if (runner === 'Crashed') {
                statusBadge = `<span class="badge badge-crashed">CRASHED</span>`;
            } else if (running) {
                statusBadge = `<span class="badge badge-running">● RUNNING</span>`;
            } else {
                statusBadge = `<span class="badge badge-offline">STOPPED</span>`;
            }

            // Determine health badge (only for web apps when running)
            let healthBadge = '';
            if (running && projType !== 'script') {
                if (health === 'Healthy') {
                    healthBadge = `<span class="badge badge-healthy"><i class="fas fa-check-circle"></i> HEALTHY</span>`;
                } else if (health === 'Unhealthy') {
                    healthBadge = `<span class="badge badge-unhealthy"><i class="fas fa-exclamation-triangle"></i> UNHEALTHY</span>`;
                } else {
                    healthBadge = `<span class="badge badge-unknown">UNKNOWN</span>`;
                }
            } else if (running) {
                healthBadge = `<span class="badge badge-offline">N/A</span>`;
            }

            // Project Type Badge
            let typeBadge = `<span class="badge badge-type" style="margin-left: 6px;">${projType}</span>`;

            const actionBtn = suspended
                ? `<button class="card-action-btn disabled" title="Suspended"><i class="fas fa-ban"></i></button>`
                : running
                    ? `<button class="card-action-btn stop" onclick="quickStop(event,'${ea(s.folder)}')" title="Stop"><i class="fas fa-stop"></i></button>`
                    : `<button class="card-action-btn play" onclick="quickStart(event,'${ea(s.folder)}')" title="Start"><i class="fas fa-play"></i></button>`;

            // Uptime and Restart info
            const uptimeRow = running ? `Uptime: ${s.uptime}` : 'Offline';
            const restartRow = s.restart_count > 0 ? `Restarts: ${s.restart_count}` : '';

            // Metadata info grid on the card
            let metaHtml = '';
            if (projType !== 'script') {
                metaHtml = `
                <div class="srv-meta-grid" style="display:grid; grid-template-columns: auto 1fr; gap:2px 8px; margin-top:6px; font-size:10px; color:#777; font-family:var(--mono);">
                    <span>PORT:</span> <span style="color:#aaa;">${s.assigned_port || ''}</span>
                    <span>STARTUP:</span> <span style="color:#aaa;">${h(s.startup)}</span>
                    <span>URL:</span> <span><a href="${s.public_url}" target="_blank" onclick="event.stopPropagation();" style="color:var(--blue); text-decoration:none;">${s.public_url}</a></span>
                </div>`;
            } else {
                metaHtml = `
                <div class="srv-meta-grid" style="display:grid; grid-template-columns: auto 1fr; gap:2px 8px; margin-top:6px; font-size:10px; color:#777; font-family:var(--mono);">
                    <span>STARTUP:</span> <span style="color:#aaa;">${h(s.startup)}</span>
                </div>`;
            }

            return `
            <div class="srv-card ${cardClass}" draggable="true" data-folder="${ea(s.folder)}" onclick="openServer('${ea(s.folder)}','${ea(s.name)}','${s.status}','${ea(s.startup||'main.py')}')">
                <i class="fas fa-grip-vertical drag-handle" title="Drag to move instance position" onclick="event.stopPropagation();"></i>
                <input type="checkbox" class="srv-select-checkbox" data-folder="${ea(s.folder)}" onclick="toggleServerSelection(event, '${ea(s.folder)}')" ${isSelected} style="margin-right:12px; cursor:pointer; transform:scale(1.2);">
                <div class="srv-info">
                    <div style="display:flex; align-items:center;">
                        <span class="srv-name">${h(s.name)}</span>
                        ${typeBadge}
                    </div>
                    <div class="srv-folder">${h(s.folder)}</div>
                    ${metaHtml}
                </div>
                <div class="srv-right">
                    <div class="srv-stats" style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                        <div style="display:flex; gap:4px;">
                            ${statusBadge}
                            ${healthBadge}
                        </div>
                        <div class="srv-stats-row">${h(s.cpu)} &nbsp;${h(s.ram)}</div>
                        <div style="font-size:9px; color:#555; font-family:var(--mono); text-align:right; margin-top:2px;">
                            <div>${uptimeRow}</div>
                            ${restartRow ? `<div>${restartRow}</div>` : ''}
                        </div>
                    </div>
                    ${actionBtn}
                    <button class="card-action-btn" onclick="quickRename(event,'${ea(s.folder)}','${ea(s.name)}')" title="Rename Instance" style="color:var(--dim);">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="card-del-btn" onclick="quickDelete(event,'${ea(s.folder)}','${ea(s.name)}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`;
        }).join('');
        updateBulkActionButtons();
        initDragAndDrop();
    }

    // ─── INSTANCE DRAG AND DROP REORDERING ─────────────────────
    function initDragAndDrop() {
        const list = document.getElementById('serverList');
        if (!list || list.dataset.dragInitialized) return;
        list.dataset.dragInitialized = 'true';

        let draggedCard = null;

        list.addEventListener('dragstart', (e) => {
            const card = e.target.closest('.srv-card');
            if (!card) return;
            draggedCard = card;
            card.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', card.dataset.folder);
        });

        list.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!draggedCard) return;
            const afterElement = getDragAfterElement(list, e.clientY);
            if (afterElement == null) {
                list.appendChild(draggedCard);
            } else {
                list.insertBefore(draggedCard, afterElement);
            }
        });

        list.addEventListener('dragend', (e) => {
            const card = e.target.closest('.srv-card');
            if (card) card.classList.remove('dragging');
            draggedCard = null;
            saveInstanceOrder();
        });
    }

    function getDragAfterElement(container, y) {
        const draggableElements = [...container.querySelectorAll('.srv-card:not(.dragging)')];
        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
    }

    function saveInstanceOrder() {
        const list = document.getElementById('serverList');
        if (!list) return;
        const cards = [...list.querySelectorAll('.srv-card')];
        const orderedFolders = cards.map(c => c.dataset.folder).filter(Boolean);
        localStorage.setItem('ik_instance_order', JSON.stringify(orderedFolders));
    }

    const activeActions = new Set();

    async function quickStart(e, folder) {
        if (e) e.stopPropagation();
        if (activeActions.has(folder)) return;
        activeActions.add(folder);
        try {
            await fetch(`/api/v1/servers/${folder}/action/start`, { method:'POST' });
        } finally {
            activeActions.delete(folder);
            loadServers();
        }
    }
    async function quickStop(e, folder) {
        if (e) e.stopPropagation();
        if (activeActions.has(folder)) return;
        activeActions.add(folder);
        try {
            await fetch(`/api/v1/servers/${folder}/action/stop`, { method:'POST' });
        } finally {
            activeActions.delete(folder);
            loadServers();
        }
    }
    async function bulkAction(act) {
        const res  = await fetch('/api/v1/servers');
        const data = await res.json();
        if (!data.servers || !data.servers.length) return;
        
        Swal.fire({
            title: 'Processing...',
            text: `Applying ${act} to all instances...`,
            background: '#0b0b0b', color: '#e2e2e2',
            allowOutsideClick: false, showConfirmButton: false,
            didOpen: () => { Swal.showLoading(); }
        });

        await Promise.all(data.servers.filter(s => s.status !== 'suspended').map(s =>
            fetch(`/api/v1/servers/${s.folder}/action/${act}`, { method:'POST' })
        ));
        
        Swal.close();
        loadServers();
    }

    function toggleServerSelection(e, folder) {
        e.stopPropagation();
        if (e.target.checked) {
            selectedServers.add(folder);
        } else {
            selectedServers.delete(folder);
        }
        updateBulkActionButtons();
    }

    function toggleSelectAllServers(checked) {
        const checkboxes = document.querySelectorAll('.srv-select-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = checked;
            const folder = cb.dataset.folder;
            if (checked) {
                selectedServers.add(folder);
            } else {
                selectedServers.delete(folder);
            }
        });
        updateBulkActionButtons();
    }

    function updateBulkActionButtons() {
        const count = selectedServers.size;
        const bar = document.getElementById('selectedActionsBar');
        const labelCount = document.getElementById('selectedCount');
        if (bar && labelCount) {
            if (count > 0) {
                bar.style.display = 'flex';
                labelCount.textContent = count;
            } else {
                bar.style.display = 'none';
            }
        }
        
        const selectAllCheckbox = document.getElementById('selectAllServers');
        if (selectAllCheckbox) {
            const checkboxes = document.querySelectorAll('.srv-select-checkbox');
            if (checkboxes.length > 0) {
                const allChecked = Array.from(checkboxes).every(cb => cb.checked);
                selectAllCheckbox.checked = allChecked;
            } else {
                selectAllCheckbox.checked = false;
            }
        }
    }

    async function bulkActionSelected(act) {
        if (!selectedServers.size) return;
        const folders = Array.from(selectedServers);
        Swal.fire({
            title: 'Processing...',
            text: `Applying ${act} to selected instances...`,
            background: '#0b0b0b', color: '#e2e2e2',
            allowOutsideClick: false, showConfirmButton: false,
            didOpen: () => { Swal.showLoading(); }
        });

        await Promise.all(folders.map(async folder => {
            try {
                await fetch(`/api/v1/servers/${folder}/action/${act}`, { method: 'POST' });
            } catch(e) { console.error(e); }
        }));

        Swal.close();
        loadServers();
    }

    async function bulkDeleteServersSelected() {
        if (!selectedServers.size) return;
        const folders = Array.from(selectedServers);
        const c = await Swal.fire({
            title: `Delete ${folders.length} Selected Instances?`,
            text: 'All files for these instances will be permanently deleted.',
            icon: 'warning',
            background: '#0b0b0b', color: '#e2e2e2',
            showCancelButton: true,
            confirmButtonColor: '#ff3333',
            confirmButtonText: 'Delete'
        });
        if (!c.isConfirmed) return;

        Swal.fire({
            title: 'Deleting...',
            text: 'Removing selected instances...',
            background: '#0b0b0b', color: '#e2e2e2',
            allowOutsideClick: false, showConfirmButton: false,
            didOpen: () => { Swal.showLoading(); }
        });

        await Promise.all(folders.map(async folder => {
            try {
                const res = await fetch(`/api/v1/servers/${folder}/delete`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'deleted' || data.status === 'success') {
                    selectedServers.delete(folder);
                }
            } catch (err) {
                console.error('Delete error for ' + folder, err);
            }
        }));

        Swal.close();
        loadServers();
        toast('success', 'Selected instances deleted');
    }

    async function bulkDownloadSelected() {
        if (!selectedServers.size) return;
        const folders = Array.from(selectedServers);
        toast('info', 'Downloading...', `Downloading ${folders.length} instances...`);
        
        for (let i = 0; i < folders.length; i++) {
            const folder = folders[i];
            setTimeout(() => {
                const link = document.createElement('a');
                link.href = `/api/v1/servers/${folder}/download-zip`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }, i * 600);
        }
    }

    function openZipDeploy() { document.getElementById('zipDeployInput').click(); }

    // ─── Auto-Run Toggle ────────────────────────
    let autoRun = true;
    function toggleAutoRun() {
        autoRun = !autoRun;
        const btn   = document.getElementById('autoRunToggle');
        const track = document.getElementById('autoRunTrack');
        btn.className   = autoRun ? 'toggle-btn on' : 'toggle-btn off';
        track.className = autoRun ? 'toggle-track on' : 'toggle-track';
        btn.title = autoRun ? 'Auto-Run ON: ZIPs auto-start after deploy' : 'Auto-Run OFF';
    }

    // ─── ZIP Deploy ─────────────────────────────
    async function deployZips(input) {
        const files = Array.from(input.files);
        if (!files.length) return;
        const doAutoRun = autoRun;

        await Swal.fire({
            title: '🚀 Deploying...',
            html: `<div id="deployStatus" style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:11px;color:#aaa;max-height:250px;overflow-y:auto;background:#000;padding:10px;border-radius:6px;"></div>`,
            background:'#0b0b0b', color:'#e2e2e2',
            allowOutsideClick:false, showConfirmButton:false,
            didOpen: async () => {
                const log = document.getElementById('deployStatus');
                function addLog(msg, color='#aaa') {
                    log.innerHTML += `<div style="color:${color};margin-bottom:3px;">${msg}</div>`;
                    log.scrollTop = log.scrollHeight;
                }
                let anyFailed = false;

                for (const file of files) {
                    const isZip = file.name.toLowerCase().endsWith('.zip');
                    const isPy = file.name.toLowerCase().endsWith('.py');
                    if (!isZip && !isPy) {
                        addLog(`✗ Unsupported file type: ${file.name}`, '#ff3333');
                        anyFailed = true;
                        continue;
                    }

                    addLog(`📦 Deploying: <strong style="color:#fff">${file.name}</strong>`);
                    addLog('  ① Creating server...','#444');
                    const name = file.name.replace(/\.(zip|py)$/i,'');
                    let addData;
                    try {
                        const r = await fetch('/api/v1/servers', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ name }) });
                        addData = await r.json();
                    } catch(e) { addLog('  ✗ Network error','#ff3333'); anyFailed=true; continue; }
                    if (addData.status !== 'success') { addLog('  ✗ '+(addData.msg||'Failed'),'#ff3333'); anyFailed=true; continue; }
                    const folder = addData.folder;
                    addLog('  ✓ Created: '+folder,'#00ff66');

                    addLog(`  ② Uploading file...`,'#444');
                    let uploadedFilename = file.name;
                    try {
                        const fd = new FormData(); fd.append('file',file); fd.append('path','');
                        const r = await fetch(`/api/v1/files/${folder}/upload`,{method:'POST',body:fd});
                        if(!r.ok) throw new Error('HTTP '+r.status);
                        const ud = await r.json();
                        if(ud.status!=='success') throw new Error(ud.msg||'Upload failed');
                        if(ud.filename) uploadedFilename=ud.filename;
                        addLog('  ✓ Uploaded: '+uploadedFilename,'#00ff66');
                    } catch(e) { addLog('  ✗ Upload failed: '+e.message,'#ff3333'); anyFailed=true; continue; }

                    addLog('  ③ Running deployment pipeline...','#444');
                    try {
                        const r = await fetch(`/api/v1/servers/${folder}/deploy-pipeline`, { method:'POST' });
                        const deployRes = await r.json();
                        if (deployRes.status !== 'success') {
                            throw new Error(deployRes.msg || 'Pipeline failed');
                        }
                        addLog(`  ✓ Pipeline complete: detected ${deployRes.project_type.toUpperCase()}`, '#00ff66');
                        if (deployRes.assigned_port) {
                            addLog(`    - Assigned Port: ${deployRes.assigned_port}`, '#aaa');
                            addLog(`    - Public URL: ${deployRes.public_url}`, '#aaa');
                        }
                    } catch(e) { addLog('  ✗ Pipeline failed: '+e.message,'#ff3333'); anyFailed=true; continue; }

                    if (doAutoRun) {
                        addLog(`  ④ Starting server...`,'#444');
                        try {
                            const r = await fetch(`/api/v1/servers/${folder}/action/start`,{method:'POST'});
                            const d = await r.json();
                            if(d.status==='error') { addLog('  ✗ Start failed: '+d.msg,'#ff3333'); anyFailed=true; }
                            else addLog('  ✓ Server started!','#00ff66');
                        } catch(e) { addLog('  ✗ Start error: '+e.message,'#ff3333'); }
                    } else { addLog('  — Auto-Run OFF, skipping start','#333'); }

                    addLog('');
                }
                addLog(anyFailed ? '⚠ Done with some errors' : '✅ All done!', anyFailed ? '#ffaa00' : '#00ff66');
                Swal.update({ showConfirmButton:true, confirmButtonText:'Close' });
                if (input && 'value' in input) input.value='';
                loadServers();
                if (!anyFailed) {
                    setTimeout(() => {
                        Swal.close();
                    }, 1500);
                }
            }
        });
    }

    async function renameServerUI() {
        if (!currentServer) return;
        const { value: newName } = await Swal.fire({
            title: 'Rename Instance',
            input: 'text',
            inputValue: currentServer.name,
            background: '#0b0b0b',
            color: '#e2e2e2',
            inputValidator: v => !v && 'Name cannot be empty'
        });
        if (newName && newName !== currentServer.name) {
            try {
                const res = await fetch(`/api/v1/servers/${currentServer.folder}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    currentServer.name = newName;
                    document.getElementById('manageServerName').textContent = newName;
                    document.getElementById('consoleSrvName').textContent = newName;
                    toast('success', 'Instance renamed');
                } else {
                    Swal.fire({ icon: 'error', title: 'Error', text: data.msg, background: '#0b0b0b', color: '#e2e2e2' });
                }
            } catch(e) {
                toast('error', 'Network error');
            }
        }
    }

    async function quickRename(e, folder, oldName) {
        if (e && e.stopPropagation) e.stopPropagation();
        const { value: newName } = await Swal.fire({
            title: 'Rename Instance',
            input: 'text',
            inputValue: oldName,
            background: '#0b0b0b',
            color: '#e2e2e2',
            showCancelButton: true,
            confirmButtonText: 'Save',
            confirmButtonColor: 'var(--accent)',
            cancelButtonColor: '#333'
        });
        if (!newName || newName.trim() === '' || newName === oldName) return;
        try {
            const res = await fetch(`/api/v1/servers/${folder}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName.trim() })
            });
            const data = await res.json();
            if (data.status === 'success') {
                toast('success', 'Instance renamed');
                loadServers();
            } else {
                Swal.fire({ icon: 'error', title: 'Error', text: data.msg || 'Rename failed', background: '#0b0b0b', color: '#e2e2e2' });
            }
        } catch(e) {
            toast('error', 'Network error');
        }
    }

    async function editStartupCommand() {
        if (!currentServer) return;
        const { value: newCmd } = await Swal.fire({
            title: 'Override Startup Command',
            input: 'text',
            inputValue: document.getElementById('detailStartup').textContent,
            background: '#0b0b0b',
            color: '#e2e2e2',
            showCancelButton: true,
            confirmButtonText: 'Save',
            confirmButtonColor: 'var(--accent)',
            cancelButtonColor: '#333'
        });
        if (newCmd === undefined) return;
        try {
            const res = await fetch(`/api/v1/servers/${currentServer.folder}/set-startup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: newCmd })
            });
            const data = await res.json();
            if (data.status === 'success') {
                toast('success', 'Startup command updated');
                document.getElementById('detailStartup').textContent = newCmd;
                currentServer.startup = newCmd;
                loadServers();
            } else {
                Swal.fire({ icon: 'error', title: 'Error', text: data.msg || 'Failed to update startup command', background: '#0b0b0b', color: '#e2e2e2' });
            }
        } catch(e) {
            toast('error', 'Network error');
        }
    }

    function copyPublicUrl() {
        const urlLink = document.getElementById('detailPublicUrl');
        if (!urlLink || !urlLink.textContent || urlLink.textContent === '—') return;
        navigator.clipboard.writeText(urlLink.textContent).then(() => {
            toast('success', 'URL Copied');
        }).catch(err => {
            toast('error', 'Copy failed');
        });
    }

    function openPublicUrl() {
        const urlLink = document.getElementById('detailPublicUrl');
        if (!urlLink || !urlLink.href) return;
        window.open(urlLink.href, '_blank');
    }

    async function quickDelete(e, folder, name) {
        e.stopPropagation();
        const c = await Swal.fire({ title:`Delete "${name}"?`, text:'All files will be permanently deleted.', icon:'warning', background:'#0b0b0b', color:'#e2e2e2', showCancelButton:true, confirmButtonColor:'#ff3333', confirmButtonText:'Delete' });
        if (!c.isConfirmed) return;
        const res  = await fetch(`/api/v1/servers/${folder}/delete`,{method:'POST'});
        const data = await res.json();
        if(data.status==='deleted' || data.status==='success') { loadServers(); toast('success','Deleted'); }
        else Swal.fire({ icon:'error', title:'Error', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
    }

    async function createServer() {
        const { value: name } = await Swal.fire({ title:'New Instance', input:'text', inputPlaceholder:'my-bot', background:'#0b0b0b', color:'#e2e2e2', inputValidator: v => !v && 'Name cannot be empty' });
        if (!name) return;
        const res  = await fetch('/api/v1/servers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
        const data = await res.json();
        if(data.status==='success') loadServers();
        else Swal.fire({ icon:'error', title:'Error', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
    }

    // ─── MANAGE VIEW ────────────────────────────
    function openServer(folder, name, status, startup) {
        currentServer = { folder, name, status, startup };
        currentPath   = '';
        document.getElementById('homeView').style.display   = 'none';
        document.getElementById('manageView').style.display = 'block';
        document.getElementById('manageServerName').textContent = name;
        document.getElementById('consoleSrvName').textContent   = name;
        const susp = status === 'suspended';
        document.getElementById('suspWarn').style.display = susp ? 'block' : 'none';
        // reset console expand
        consoleExpanded = false;
        document.getElementById('console').classList.remove('expanded');
        // reset file manager open
        document.getElementById('fmBody').classList.remove('hidden');
        document.getElementById('fmToggleHeader').classList.add('open');
        // reset log change detection
        _lastLogContent = '';
        updateStatusUI(null);
        loadFiles();
        startLogPolling();
    }

    function backToHome() {
        clearInterval(logInterval); logInterval = null;
        document.getElementById('manageView').style.display = 'none';
        document.getElementById('homeView').style.display   = 'block';
        loadServers();
    }

    function updateStatusUI(srv) {
        const pill   = document.getElementById('statusPill');
        const uptime = document.getElementById('uptimeText');
        if (!srv) {
            pill.className   = 'status-pill offline';
            pill.textContent = 'OFFLINE';
            uptime.textContent = '';
            document.getElementById('instanceDetailsPanel').style.display = 'none';
            return;
        }
        currentServer.status = srv.status;
        
        // Show details panel
        document.getElementById('instanceDetailsPanel').style.display = 'block';
        
        // Update details panel fields
        document.getElementById('detailProjType').textContent = srv.project_type || 'script';
        document.getElementById('detailPort').textContent = srv.assigned_port ? srv.assigned_port : 'None (Script Runner)';
        document.getElementById('detailStartup').textContent = srv.startup || 'main.py';

        // Auto Restart BDT display
        const arEnabled = srv.auto_restart_enabled || 0;
        const arTime = srv.auto_restart_time || '';
        const autoRestartText = document.getElementById('detailAutoRestart');
        if (autoRestartText) {
            if (arEnabled && arTime) {
                autoRestartText.textContent = formatTime12h(arTime);
                autoRestartText.style.color = '#5cb85c';
            } else {
                autoRestartText.textContent = 'Off';
                autoRestartText.style.color = 'var(--dim)';
            }
        }
        
        // Health badge
        const health = srv.health_status || 'Unknown';
        const isWebApp = (srv.project_type && srv.project_type !== 'script');
        let healthHtml = '';
        if (srv.online && isWebApp) {
            if (health === 'Healthy') {
                healthHtml = '<span class="badge badge-healthy"><i class="fas fa-check-circle"></i> HEALTHY</span>';
            } else if (health === 'Unhealthy') {
                healthHtml = '<span class="badge badge-unhealthy"><i class="fas fa-exclamation-triangle"></i> UNHEALTHY</span>';
            } else {
                healthHtml = '<span class="badge badge-unknown">UNKNOWN</span>';
            }
        } else {
            healthHtml = '<span class="badge badge-offline">N/A</span>';
        }
        document.getElementById('detailHealth').innerHTML = healthHtml;
        
        // Uptime and Restarts
        const upStr = srv.online ? (srv.uptime || 'Online') : 'Offline';
        const rCount = srv.restart_count || 0;
        document.getElementById('detailUptimeRestarts').textContent = `${upStr} ${rCount > 0 ? `(${rCount} restarts)` : ''}`;
        
        // Public URL Container
        const urlContainer = document.getElementById('detailUrlContainer');
        const endpointsContainer = document.getElementById('detailEndpointsContainer');
        const endpointsList = document.getElementById('detailEndpointsList');
        if (isWebApp && srv.public_url) {
            urlContainer.style.display = 'flex';
            const link = document.getElementById('detailPublicUrl');
            link.href = srv.public_url;
            link.textContent = srv.public_url;

            // Fetch and show auto-detected endpoints
            fetch(`/api/v1/servers/${srv.folder}/endpoints`)
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success' && data.endpoints && data.endpoints.length > 0) {
                        endpointsContainer.style.display = 'block';
                        endpointsList.innerHTML = data.endpoints.map(ep => `
                            <div style="background:#151515; padding:6px 10px; border-radius:6px; border:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom: 2px;">
                                <div style="min-width:0; flex:1; font-family:var(--mono); font-size:11px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                    <span style="color:var(--green); font-weight:bold; margin-right:6px;">GET</span>
                                    <a href="${ep.url}" target="_blank" style="color:var(--blue); text-decoration:none;">${ep.url}</a>
                                </div>
                                <button class="sm-btn" onclick="navigator.clipboard.writeText('${ep.url}').then(() => toast('success', 'Copied!'))" style="padding:2px 6px; font-size:9px;">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                        `).join('');
                    } else {
                        endpointsContainer.style.display = 'none';
                    }
                })
                .catch(() => {
                    endpointsContainer.style.display = 'none';
                });
        } else {
            urlContainer.style.display = 'none';
            endpointsContainer.style.display = 'none';
        }

        // Pill / Top Bar status
        const runner = srv.runner_status || 'Offline';
        if (srv.status === 'suspended') {
            pill.className   = 'status-pill suspended';
            pill.textContent = 'SUSPENDED';
            uptime.textContent = '';
            document.getElementById('suspWarn').style.display = 'block';
        } else if (runner === 'Deploying') {
            pill.className   = 'status-pill badge-deploying';
            pill.textContent = 'DEPLOYING';
            uptime.textContent = '';
            document.getElementById('suspWarn').style.display = 'none';
        } else if (runner === 'Installing') {
            pill.className   = 'status-pill badge-installing';
            pill.textContent = 'INSTALLING';
            uptime.textContent = '';
            document.getElementById('suspWarn').style.display = 'none';
        } else if (runner === 'Crashed') {
            pill.className   = 'status-pill badge-crashed';
            pill.textContent = 'CRASHED';
            uptime.textContent = '';
            document.getElementById('suspWarn').style.display = 'none';
        } else if (srv.online) {
            pill.className   = 'status-pill running';
            pill.textContent = '● RUNNING';
            uptime.textContent = srv.uptime ? `${srv.uptime}` : '';
            document.getElementById('suspWarn').style.display = 'none';
        } else {
            pill.className   = 'status-pill offline';
            pill.textContent = 'OFFLINE';
            uptime.textContent = '';
            document.getElementById('suspWarn').style.display = 'none';
        }
    }

    // ─── Server Actions ──────────────────────────
    async function serverAction(act) {
        const res  = await fetch(`/api/v1/servers/${currentServer.folder}/action/${act}`,{method:'POST'});
        const data = await res.json();
        if(data.status==='error') Swal.fire({ icon:'error', title:'Error', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
        else toast('success', act.charAt(0).toUpperCase()+act.slice(1)+'ed');
    }

    function formatTime12h(timeStr) {
        if (!timeStr) return 'Off';
        const parts = timeStr.split(':');
        if (parts.length !== 2) return 'Off';
        let h = parseInt(parts[0], 10);
        const m = parts[1];
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        if (h === 0) h = 12;
        return `${String(h).padStart(2, '0')}:${m} ${ampm}`;
    }

    async function configureAutoRestart() {
        if (!currentServer || !currentServer.folder) return;
        
        // Find current settings
        const res = await fetch('/api/v1/servers');
        const data = await res.json();
        const srv = data.servers ? data.servers.find(s => s.folder === currentServer.folder) : null;
        
        const enabled = srv ? (srv.auto_restart_enabled || 0) : 0;
        const timeVal = srv ? (srv.auto_restart_time || '03:00') : '03:00';
        
        const { value: formValues } = await Swal.fire({
            title: 'Configure Auto Restart (BDT)',
            html: `
                <div style="text-align: left; font-size: 13px; color: #ccc;">
                    <p style="margin-bottom: 12px; color: #888;">Daily automatic clean restart at your specified Bangladesh Time (BDT, UTC+6).</p>
                    <div style="margin-bottom: 15px; display: flex; align-items: center; gap: 10px;">
                        <label style="font-weight: bold; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                            <input type="checkbox" id="swal-ar-enabled" ${enabled ? 'checked' : ''} style="transform: scale(1.2); cursor: pointer;">
                            Enable Daily Auto-Restart
                        </label>
                    </div>
                    <div id="swal-ar-time-container" style="display: ${enabled ? 'block' : 'none'};">
                        <label style="display: block; font-weight: bold; margin-bottom: 6px;">Restart Time (BDT):</label>
                        <input type="time" id="swal-ar-time" value="${timeVal}" class="swal2-input" style="margin: 0; width: 100%; box-sizing: border-box; background: #1c1c1c; color: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 8px;">
                        <div style="font-size: 11px; color: var(--blue); margin-top: 4px;" id="swal-ar-12h-preview">
                            Preview: ${formatTime12h(timeVal)}
                        </div>
                    </div>
                </div>
            `,
            background: '#0b0b0b',
            color: '#e2e2e2',
            showCancelButton: true,
            confirmButtonText: 'Save',
            confirmButtonColor: 'var(--blue)',
            didOpen: () => {
                const cb = document.getElementById('swal-ar-enabled');
                const timeContainer = document.getElementById('swal-ar-time-container');
                const timeInput = document.getElementById('swal-ar-time');
                const preview = document.getElementById('swal-ar-12h-preview');
                
                cb.addEventListener('change', (e) => {
                    timeContainer.style.display = e.target.checked ? 'block' : 'none';
                });
                
                timeInput.addEventListener('input', (e) => {
                    preview.textContent = 'Preview: ' + formatTime12h(e.target.value);
                });
            },
            preConfirm: () => {
                const arEnabled = document.getElementById('swal-ar-enabled').checked;
                const arTime = document.getElementById('swal-ar-time').value;
                
                if (arEnabled && !arTime) {
                    Swal.showValidationMessage('Please select a restart time.');
                    return false;
                }
                return { enabled: arEnabled, time: arTime };
            }
        });
        
        if (formValues) {
            Swal.fire({
                title: 'Saving...',
                allowOutsideClick: false,
                showConfirmButton: false,
                background: '#0b0b0b',
                color: '#e2e2e2',
                didOpen: () => { Swal.showLoading(); }
            });
            
            try {
                const response = await fetch(`/api/v1/servers/${currentServer.folder}/set-auto-restart`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formValues)
                });
                const resData = await response.json();
                Swal.close();
                if (resData.status === 'success') {
                    toast('success', 'Auto-restart updated');
                    const sr = await fetch('/api/v1/servers');
                    const sd = await sr.json();
                    const srv = sd.servers ? sd.servers.find(s => s.folder === currentServer.folder) : null;
                    if (srv) updateStatusUI(srv);
                } else {
                    Swal.fire({ icon: 'error', title: 'Error', text: resData.msg, background: '#0b0b0b', color: '#e2e2e2' });
                }
            } catch (err) {
                Swal.close();
                Swal.fire({ icon: 'error', title: 'Error', text: 'Network connection failed.', background: '#0b0b0b', color: '#e2e2e2' });
            }
        }
    }

    async function installPackages() {
        const res  = await fetch(`/api/v1/servers/${currentServer.folder}/action/install`,{method:'POST'});
        const data = await res.json();
        if(data.status==='installing' || data.status==='success') toast('info','Installing...','Check console for progress.');
        else Swal.fire({ icon:'error', title:'Error', text:data.msg||'Could not install', background:'#0b0b0b', color:'#e2e2e2' });
    }

    async function deleteServer() {
        const c = await Swal.fire({ title:'Delete server?', text:'All files will be permanently deleted.', icon:'warning', background:'#0b0b0b', color:'#e2e2e2', showCancelButton:true, confirmButtonColor:'#ff3333', confirmButtonText:'Delete' });
        if (!c.isConfirmed) return;
        const res  = await fetch(`/api/v1/servers/${currentServer.folder}/delete`,{method:'POST'});
        const data = await res.json();
        if(data.status==='deleted' || data.status==='success') { backToHome(); toast('success','Deleted'); }
        else Swal.fire({ icon:'error', title:'Error', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
    }

    // ─── Console ─────────────────────────────────
    function toggleConsoleExpand() {
        consoleExpanded = !consoleExpanded;
        const con  = document.getElementById('console');
        const icon = document.getElementById('consoleExpandIcon');
        con.classList.toggle('expanded', consoleExpanded);
        icon.className = consoleExpanded ? 'fas fa-compress-alt' : 'fas fa-expand-alt';
    }

    function toggleDateTime() {
        showDateTime = !showDateTime;
        const btn = document.getElementById('dtToggleBtn');
        if (showDateTime) {
            btn.classList.add('on');
        } else {
            btn.classList.remove('on');
        }
        // Force re-render by clearing cache
        _lastLogContent = '';
        pollLog();
    }

    function adjustFontSize(delta) {
        consoleFontSize = Math.min(10, Math.max(3, consoleFontSize + delta));
        document.getElementById('console').style.fontSize = consoleFontSize + 'px';
        document.getElementById('fsLabel').textContent = consoleFontSize;
    }

    async function copyConsole() {
        const con = document.getElementById('console');
        // Extract plain text from each line div, preserving datetime spans
        const lines = Array.from(con.querySelectorAll('div')).map(div => div.textContent).join('\n');
        try {
            await navigator.clipboard.writeText(lines);
            const btn = document.getElementById('copyLogBtn');
            const orig = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> Copied';
            btn.classList.add('on');
            setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('on'); }, 1500);
        } catch(e) {
            toast('error', 'Copy failed', 'Clipboard access denied');
        }
    }

    function startLogPolling() {
        if (logInterval) clearInterval(logInterval);
        _lastLogContent = '';
        pollLog();
        logInterval = setInterval(pollLog, 5000);
    }

    async function pollLog() {
        try {
            const res  = await fetch(`/api/v1/servers/${currentServer.folder}/log`);
            const data = await res.json();

            // Change detection: only update DOM if log content changed
            if (data.log === _lastLogContent) return;
            _lastLogContent = data.log;

            const con  = document.getElementById('console');
            const atBottom = con.scrollHeight - con.scrollTop - con.clientHeight < 60;

            const now = new Date();
            const pad = n => String(n).padStart(2,'0');
            const dtStr = `[${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}]`;
            const dtSpan = `<span style="color:#333;user-select:none;">${h(dtStr)}</span> `;

            con.innerHTML = data.log.split('\n').map(l => {
                if (!l.trim()) return `<div style="height:3px;"></div>`;
                const cls = (l.includes('ERROR') || l.includes('✗') || l.includes('Traceback') || l.toLowerCase().includes('error')) ? 'err-line' : '';
                // Lines that already have a backend timestamp like [2026-04-21 ...] — don't double-stamp
                const hasTs = /^\[2\d{3}-\d{2}-\d{2}/.test(l.trim());
                const prefix = (showDateTime && !hasTs) ? dtSpan : '';
                return `<div class="${cls}">${prefix}${h(l)}</div>`;
            }).join('');

            if (atBottom) con.scrollTop = con.scrollHeight;

            // Update server status from the servers list
            const sr = await fetch('/api/v1/servers');
            const sd = await sr.json();
            const srv = sd.servers ? sd.servers.find(s => s.folder === currentServer.folder) : null;
            if (srv) updateStatusUI(srv);
        } catch(e) {}
    }

    async function sendCommand() {
        const input = document.getElementById('cmdInput');
        const cmd   = input.value.trim();
        if (!cmd) return;
        cmdHistory.unshift(cmd); if(cmdHistory.length>50) cmdHistory.pop(); cmdHistIdx=-1;
        input.value=''; input.disabled=true;
        try {
            const res  = await fetch(`/api/v1/servers/${currentServer.folder}/command`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:cmd}) });
            const data = await res.json();
            if(data.status==='error') toast('error','Command Error',data.msg);
            _lastLogContent = '';  // Force refresh after command
            await pollLog();
        } catch(e) { toast('error','Network error'); }
        finally { input.disabled=false; input.focus(); }
    }

    async function clearConsole() {
        await fetch(`/api/v1/files/${currentServer.folder}/save`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:'console.log',path:'',content:''}) });
        document.getElementById('console').innerHTML='';
        _lastLogContent = '';
        toast('success','Console cleared');
    }

    // ─── File Manager Toggle ─────────────────────
    function toggleFileManager() {
        const body   = document.getElementById('fmBody');
        const header = document.getElementById('fmToggleHeader');
        const con    = document.getElementById('console');
        const isOpen = !body.classList.contains('hidden');

        if (isOpen) {
            body.classList.add('hidden');
            header.classList.remove('open');
            // expand console when FM is collapsed
            con.classList.add('expanded');
            consoleExpanded = true;
            document.getElementById('consoleExpandIcon').className = 'fas fa-compress-alt';
        } else {
            body.classList.remove('hidden');
            header.classList.add('open');
            con.classList.remove('expanded');
            consoleExpanded = false;
            document.getElementById('consoleExpandIcon').className = 'fas fa-expand-alt';
        }
    }

    // ─── File Manager ─────────────────────────────
    function updateBreadcrumb() {
        const parts = currentPath ? currentPath.split('/') : [];
        let html = `<span class="crumb" onclick="navigateTo('')"><i class="fas fa-home"></i> root</span>`;
        let built = '';
        for (const p of parts) {
            built = built ? built+'/'+p : p;
            const snap = built;
            html += `<span class="sep"> / </span><span class="crumb" onclick="navigateTo('${ea(snap)}')">${h(p)}</span>`;
        }
        document.getElementById('breadcrumb').innerHTML = html;
    }

    function navigateTo(path) { currentPath=path; loadFiles(); }

    function toggleSelectAll(checked) {
        document.querySelectorAll('.f-check').forEach(cb => cb.checked=checked);
    }

    function getSelectedNames() {
        return Array.from(document.querySelectorAll('.f-check:checked')).map(cb => cb.dataset.name);
    }

    async function loadFiles() {
        updateBreadcrumb();
        document.getElementById('selectAll').checked = false;
        const res   = await fetch(`/api/v1/files/${currentServer.folder}/list?path=${encodeURIComponent(currentPath)}`);
        const files = await res.json();
        if (!files.length) {
            document.getElementById('fileList').innerHTML = '<div class="empty-folder">Empty folder</div>';
            return;
        }
        document.getElementById('fileList').innerHTML = files.map(f => `
            <div class="file-item">
                <input type="checkbox" class="f-check" data-name="${h(f.name)}" onchange="updateSelectAllState()">
                <i class="file-icon ${f.is_dir?'folder fas fa-folder':'file fas fa-file-code'}"></i>
                <span class="file-name-txt" onclick="${f.is_dir?`enterFolder('${ea(f.name)}')`:`editFile('${ea(f.name)}')`}">${h(f.name)}</span>
                <span class="file-actions-row">
                    ${!f.is_dir?`<i class="fas fa-edit fa-icon blue" title="Edit" onclick="editFile('${ea(f.name)}')"></i>`:''}
                    <i class="fas fa-pencil-alt fa-icon" title="Rename" onclick="renameFile('${ea(f.name)}')"></i>
                    ${!f.is_dir?`<i class="fas fa-download fa-icon blue" title="Download" onclick="downloadFile('${ea(f.name)}')"></i>`:''}
                    ${f.is_zip?`<i class="fas fa-file-archive fa-icon" title="Unzip" onclick="unzipFile('${ea(f.name)}')"></i>`:''}
                    <i class="fas fa-trash fa-icon red" title="Delete" onclick="deleteFile('${ea(f.name)}')"></i>
                </span>
            </div>`).join('');
    }

    function updateSelectAllState() {
        const all     = document.querySelectorAll('.f-check');
        const checked = document.querySelectorAll('.f-check:checked');
        const sa = document.getElementById('selectAll');
        sa.checked       = all.length===checked.length && all.length>0;
        sa.indeterminate = checked.length>0 && checked.length<all.length;
    }

    function enterFolder(name) { currentPath = currentPath ? currentPath+'/'+name : name; loadFiles(); }

    async function bulkDeleteSelected() {
        const names = getSelectedNames();
        if (!names.length) { toast('warning','No files selected'); return; }
        const c = await Swal.fire({ title:`Delete ${names.length} item(s)?`, icon:'warning', background:'#0b0b0b', color:'#e2e2e2', showCancelButton:true, confirmButtonColor:'#ff3333' });
        if (!c.isConfirmed) return;
        await fetch(`/api/v1/files/${currentServer.folder}/delete-bulk`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names,path:currentPath}) });
        loadFiles();
    }

    async function bulkDownloadFilesSelected() {
        const names = getSelectedNames();
        if (!names.length) { toast('warning','No files selected'); return; }
        const res  = await fetch(`/api/v1/files/${currentServer.folder}/zip-bulk`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names,path:currentPath}) });
        const data = await res.json();
        if(data.status==='success') window.location.href=`/api/v1/files/${currentServer.folder}/download/${encodeURIComponent(data.zip)}?path=${encodeURIComponent(currentPath)}`;
    }

    async function bulkZipSelected() {
        const names = getSelectedNames();
        if (!names.length) { toast('warning','No files selected'); return; }
        const res  = await fetch(`/api/v1/files/${currentServer.folder}/zip-bulk`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names,path:currentPath}) });
        const data = await res.json();
        if(data.status==='success') { loadFiles(); toast('success','Zipped!',data.zip); }
    }

    async function editFile(name) {
        const res  = await fetch(`/api/v1/files/${currentServer.folder}/read?name=${encodeURIComponent(name)}&path=${encodeURIComponent(currentPath)}`);
        const data = await res.json();
        document.getElementById('editingFilename').textContent = name;
        document.getElementById('editorOverlay').style.display = 'flex';
        if (!editor) {
            editor = CodeMirror.fromTextArea(document.getElementById('editorTextarea'),{
                mode:'python', theme:'dracula', lineNumbers:true, lineWrapping:true
            });
        }
        editor.setValue(data.content||'');
        setTimeout(()=>editor.refresh(),60);
    }
    function closeEditor() { document.getElementById('editorOverlay').style.display='none'; }
    async function saveFile() {
        const name = document.getElementById('editingFilename').textContent;
        const res  = await fetch(`/api/v1/files/${currentServer.folder}/save`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name,content:editor.getValue(),path:currentPath}) });
        const data = await res.json();
        closeEditor();
        (data.status==='saved' || data.status==='success') ? toast('success','Saved!') : Swal.fire({ icon:'error', title:'Save failed', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
    }

    async function deleteFile(name) {
        const c = await Swal.fire({ title:'Delete?', text:name, icon:'warning', background:'#0b0b0b', color:'#e2e2e2', showCancelButton:true, confirmButtonColor:'#ff3333' });
        if(c.isConfirmed) {
            await fetch(`/api/v1/files/${currentServer.folder}/delete-bulk`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names:[name],path:currentPath}) });
            loadFiles();
        }
    }

    async function renameFile(oldName) {
        const { value: newName } = await Swal.fire({ title:'Rename', input:'text', inputValue:oldName, background:'#0b0b0b', color:'#e2e2e2', inputValidator: v=>!v&&'Name cannot be empty' });
        if(newName && newName!==oldName) {
            await fetch(`/api/v1/files/${currentServer.folder}/rename`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({old:oldName,new:newName,path:currentPath}) });
            loadFiles();
        }
    }

    function downloadFile(name) {
        window.location.href=`/api/v1/files/${currentServer.folder}/download/${encodeURIComponent(name)}?path=${encodeURIComponent(currentPath)}`;
    }

    async function unzipFile(name) {
        Swal.fire({ title:'Extracting...', allowOutsideClick:false, background:'#0b0b0b', color:'#e2e2e2', didOpen:()=>Swal.showLoading() });
        const res  = await fetch(`/api/v1/files/${currentServer.folder}/unzip`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name,path:currentPath}) });
        const data = await res.json();
        Swal.close();
        data.status==='success' ? (loadFiles(), toast('success','Extracted!')) : Swal.fire({ icon:'error', title:'Failed', text:data.msg, background:'#0b0b0b', color:'#e2e2e2' });
    }

    async function createNewItem(type) {
        const { value: name } = await Swal.fire({ title:`New ${type}`, input:'text', inputPlaceholder:type==='file'?'script.py':'my_folder', background:'#0b0b0b', color:'#e2e2e2', inputValidator:v=>!v&&'Name cannot be empty' });
        if (!name) return;
        const ep = type==='file' ? `/api/v1/files/${currentServer.folder}/create-file` : `/api/v1/files/${currentServer.folder}/create-folder`;
        await fetch(ep,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name,path:currentPath}) });
        loadFiles();
    }

    // ─── FILE COPY/MOVE MODAL FUNCTIONS ─────────
    function openMoveCopyModal(action) {
        const names = getSelectedNames();
        if (!names.length) {
            Swal.fire({
                title: 'No items selected',
                text: `Please select at least one file or folder to ${action}.`,
                icon: 'warning',
                background: '#0b0b0b',
                color: '#e2e2e2'
            });
            return;
        }
        
        moveCopyAction = action;
        moveCopySourcePath = currentPath;
        moveCopyFiles = names;
        moveCopyCurrentPath = '';
        
        document.getElementById('fileMoveTitle').textContent = action === 'copy' ? 'Copy Files' : 'Move Files';
        document.getElementById('fileMovePasteBtn').textContent = action === 'copy' ? 'Paste Here' : 'Move Here';
        document.getElementById('fileMoveOverlay').style.display = 'flex';
        
        loadMoveCopyFolders();
    }

    function closeMoveCopyModal() {
        document.getElementById('fileMoveOverlay').style.display = 'none';
    }

    async function loadMoveCopyFolders() {
        const res = await fetch(`/api/v1/files/${currentServer.folder}/list?path=${encodeURIComponent(moveCopyCurrentPath)}`);
        const items = await res.json();
        
        const body = document.getElementById('fileMoveBody');
        const pathEl = document.getElementById('fileMovePath');
        pathEl.innerHTML = `<i class="fas fa-folder-open"></i> root/${moveCopyCurrentPath}`;
        
        let html = '';
        
        // Add Go Up item if not at root
        if (moveCopyCurrentPath !== '') {
            html += `
                <div class="file-move-item" onclick="navigateMoveCopyUp()">
                    <i class="fas fa-level-up-alt" style="transform: rotate(-90deg)"></i>
                    <span>.. (Go Up)</span>
                </div>
            `;
        }
        
        // Filter and add directories
        const dirs = items.filter(item => item.is_dir);
        if (dirs.length === 0) {
            html += `<div class="empty-folder">No subfolders here.</div>`;
        } else {
            dirs.forEach(dir => {
                html += `
                    <div class="file-move-item" onclick="navigateMoveCopyInto('${dir.name}')">
                        <i class="fas fa-folder"></i>
                        <span>${dir.name}</span>
                    </div>
                `;
            });
        }
        
        body.innerHTML = html;
    }

    function navigateMoveCopyInto(dirName) {
        if (moveCopyCurrentPath === '') {
            moveCopyCurrentPath = dirName;
        } else {
            moveCopyCurrentPath = moveCopyCurrentPath + '/' + dirName;
        }
        loadMoveCopyFolders();
    }

    function navigateMoveCopyUp() {
        if (moveCopyCurrentPath === '') return;
        const parts = moveCopyCurrentPath.split('/');
        parts.pop();
        moveCopyCurrentPath = parts.join('/');
        loadMoveCopyFolders();
    }

    async function executeMoveCopy() {
        const url = `/api/v1/files/${currentServer.folder}/${moveCopyAction}-bulk`;
        const payload = {
            path: moveCopySourcePath,
            names: moveCopyFiles,
            target_path: moveCopyCurrentPath
        };
        
        try {
            Swal.fire({
                title: `${moveCopyAction === 'copy' ? 'Copying' : 'Moving'}...`,
                allowOutsideClick: false,
                background: '#0b0b0b',
                color: '#e2e2e2',
                didOpen: () => Swal.showLoading()
            });
            
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            Swal.close();
            
            if (data.status === 'success') {
                closeMoveCopyModal();
                loadFiles();
                Swal.fire({
                    title: 'Success',
                    text: `Successfully ${moveCopyAction === 'copy' ? 'copied' : 'moved'} ${data.copied_count || data.moved_count || moveCopyFiles.length} item(s).`,
                    icon: 'success',
                    timer: 2000,
                    showConfirmButton: false,
                    background: '#0b0b0b',
                    color: '#e2e2e2'
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Failed',
                    text: data.msg || 'Operation failed',
                    background: '#0b0b0b',
                    color: '#e2e2e2'
                });
            }
        } catch (err) {
            Swal.close();
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: `Network error: ${err.message}`,
                background: '#0b0b0b',
                color: '#e2e2e2'
            });
        }
    }

    async function uploadFile(input) {
        const file = input.files[0];
        if (!file) return;
        const fd = new FormData(); fd.append('file',file); fd.append('path',currentPath);
        await fetch(`/api/v1/files/${currentServer.folder}/upload`,{method:'POST',body:fd});
        loadFiles(); input.value=''; toast('success','Uploaded!');
    }

    // ─── CMD history ─────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('cmdInput').addEventListener('keydown', e => {
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                if(cmdHistIdx < cmdHistory.length-1) { cmdHistIdx++; e.target.value=cmdHistory[cmdHistIdx]; }
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if(cmdHistIdx>0) { cmdHistIdx--; e.target.value=cmdHistory[cmdHistIdx]; }
                else { cmdHistIdx=-1; e.target.value=''; }
            }
        });

        // Drag and Drop for Deploy Zone (Home View)
        const deployZone = document.getElementById('deployZone');
        if (deployZone) {
            ['dragenter', 'dragover'].forEach(eventName => {
                deployZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    deployZone.classList.add('dragover');
                }, false);
            });
            ['dragleave', 'drop'].forEach(eventName => {
                deployZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    deployZone.classList.remove('dragover');
                }, false);
            });
            deployZone.addEventListener('drop', (e) => {
                const dt = e.dataTransfer;
                const files = dt.files;
                if (files && files.length) {
                    deployZips({ files: files, value: '' });
                }
            }, false);
        }

        // Drag and Drop for File Manager (Manage View)
        const fmListWrap = document.getElementById('fileListWrap');
        if (fmListWrap) {
            ['dragenter', 'dragover'].forEach(eventName => {
                fmListWrap.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    fmListWrap.classList.add('dragover');
                }, false);
            });
            ['dragleave', 'drop'].forEach(eventName => {
                fmListWrap.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    fmListWrap.classList.remove('dragover');
                }, false);
            });
            fmListWrap.addEventListener('drop', async (e) => {
                const dt = e.dataTransfer;
                const files = dt.files;
                if (files && files.length && currentServer) {
                    for (const file of files) {
                        const fd = new FormData();
                        fd.append('file', file);
                        fd.append('path', currentPath);
                        try {
                            await fetch(`/api/v1/files/${currentServer.folder}/upload`, { method: 'POST', body: fd });
                        } catch(err) {
                            console.error('Upload error:', err);
                        }
                    }
                    loadFiles();
                    toast('success', 'File(s) uploaded via drag & drop');
                }
            }, false);
        }
    });

    // ─── Init ────────────────────────────────────
    loadServers();
    setInterval(()=>{
        if(document.getElementById('homeView').style.display!=='none') loadServers();
    }, 15000);
