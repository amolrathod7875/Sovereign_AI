document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const folderInput = document.getElementById('folder-input');
    const btnSelectFiles = document.getElementById('btn-select-files');
    const btnSelectFolder = document.getElementById('btn-select-folder');
    
    const selectionArea = document.getElementById('selection-area');
    const selectedFilesList = document.getElementById('selected-files-list');
    const btnStartIngestion = document.getElementById('btn-start-ingestion');
    
    const loadingArea = document.getElementById('loading-area');
    const resultsArea = document.getElementById('results-area');
    const btnReset = document.getElementById('btn-reset');
    
    let selectedFiles = [];

    // Fetch supported formats
    fetch('/api/formats')
        .then(res => res.json())
        .then(data => {
            const formats = data.supported.map(f => f.replace('.', '').toUpperCase()).join(' &bull; ');
            document.getElementById('formats-list').innerHTML = formats;
        })
        .catch(err => {
            console.error('Failed to load formats', err);
            document.getElementById('formats-list').innerText = 'ERROR LOADING FORMATS';
        });

    // Event Listeners for file selection
    btnSelectFiles.addEventListener('click', () => fileInput.click());
    btnSelectFolder.addEventListener('click', () => folderInput.click());

    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
    folderInput.addEventListener('change', (e) => handleFiles(e.target.files));

    // Drag and Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
    });

    dropzone.addEventListener('drop', (e) => {
        // Drag and drop folders is complex in browser without using File System Access API or DataTransferItem.webkitGetAsEntry
        // To keep it simple and robust, we process dataTransfer.files
        // Note: dataTransfer.files on folders only contains the first level files in some browsers, but we use webkitGetAsEntry if needed
        handleDroppedItems(e.dataTransfer.items);
    });

    function handleDroppedItems(items) {
        let promises = [];
        for (let i = 0; i < items.length; i++) {
            let item = items[i].webkitGetAsEntry();
            if (item) {
                promises.push(traverseFileTree(item));
            }
        }
        
        Promise.all(promises).then(filesArrays => {
            const allFiles = filesArrays.flat();
            handleFiles(allFiles);
        });
    }

    function traverseFileTree(item, path = '') {
        return new Promise((resolve) => {
            if (item.isFile) {
                item.file(file => {
                    // Custom property to hold the relative path
                    file.customPath = path + file.name;
                    resolve([file]);
                });
            } else if (item.isDirectory) {
                let dirReader = item.createReader();
                let files = [];
                
                const readEntries = () => {
                    dirReader.readEntries(entries => {
                        if (entries.length === 0) {
                            resolve(files);
                        } else {
                            let promises = [];
                            for (let i = 0; i < entries.length; i++) {
                                promises.push(traverseFileTree(entries[i], path + item.name + "/"));
                            }
                            Promise.all(promises).then(results => {
                                files = files.concat(results.flat());
                                readEntries(); // Read next batch
                            });
                        }
                    });
                };
                readEntries();
            }
        });
    }

    function handleFiles(files) {
        if (!files || files.length === 0) return;
        
        selectedFiles = Array.from(files);
        
        selectedFilesList.innerHTML = '';
        selectedFiles.forEach(file => {
            const li = document.createElement('li');
            const path = file.customPath || file.webkitRelativePath || file.name;
            li.textContent = path;
            selectedFilesList.appendChild(li);
        });

        dropzone.style.display = 'none';
        selectionArea.style.display = 'block';
    }

    btnStartIngestion.addEventListener('click', async () => {
        if (selectedFiles.length === 0) return;

        selectionArea.style.display = 'none';
        loadingArea.style.display = 'block';

        const formData = new FormData();

        selectedFiles.forEach(file => {
            const path = file.customPath || file.webkitRelativePath || file.name;
            formData.append('files', file);
            formData.append('paths', path);
        });

        try {
            const response = await fetch('/api/ingest', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const result = await response.json();
            
            loadingArea.style.display = 'none';
            resultsArea.style.display = 'block';

            document.getElementById('res-project-id').textContent = result.project_id || 'N/A';
            document.getElementById('res-discovered').textContent = result.discovered;
            document.getElementById('res-processed').textContent = result.processed;
            document.getElementById('res-duplicates').textContent = result.duplicates;
            document.getElementById('res-failed').textContent = result.failed;
            
            const detailedResults = document.getElementById('detailed-results');
            detailedResults.innerHTML = '';
            
            if (result.files && result.files.length > 0) {
                result.files.forEach(f => {
                    const el = document.createElement('div');
                    el.className = `file-result status-${f.status}`;
                    
                    let icon = '';
                    let statusText = '';
                    let detailsHTML = '';
                    
                    if (f.status === 'processed') {
                        icon = '✓';
                        statusText = 'Processed';
                        detailsHTML = `Document ID: <span class="file-result-id">${f.document_id}</span>`;
                    } else if (f.status === 'duplicate') {
                        icon = '↻';
                        statusText = 'Duplicate';
                        detailsHTML = `This file is identical to an existing document. No new canonical copy was stored.<br>Existing document: <span class="file-result-id">${f.document_id}</span>`;
                    } else if (f.status === 'failed') {
                        icon = '✗';
                        statusText = 'Failed';
                        detailsHTML = `The file could not be processed. No processed document was created.<br>Error: ${f.error || 'Unknown error'}`;
                    }
                    
                    el.innerHTML = `
                        <div class="file-result-header">
                            <span class="file-result-icon">${icon}</span>
                            <span class="file-result-name">${f.filename}</span>
                        </div>
                        <div class="file-result-details">
                            <strong>${statusText}</strong><br>
                            ${detailsHTML}
                        </div>
                    `;
                    detailedResults.appendChild(el);
                });
            }
            
        } catch (error) {
            console.error('Upload failed:', error);
            alert('Ingestion failed. See console for details.');
            loadingArea.style.display = 'none';
            selectionArea.style.display = 'block';
        }
    });

    btnReset.addEventListener('click', () => {
        selectedFiles = [];
        fileInput.value = '';
        folderInput.value = '';
        
        resultsArea.style.display = 'none';
        selectionArea.style.display = 'none';
        dropzone.style.display = 'block';
    });
});

    // --- TAB LOGIC ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');

            if (btn.dataset.tab === 'sources-tab') {
                loadSources();
            }
        });
    });

    // --- SOURCES LOGIC ---
    const btnAddSource = document.getElementById('btn-add-source');
    const sourcesList = document.getElementById('sources-list');

    async function loadSources() {
        try {
            const res = await fetch('/api/sources');
            const sources = await res.json();
            
            sourcesList.innerHTML = '';
            sources.forEach(source => {
                const card = document.createElement('div');
                card.className = 'source-card';
                card.innerHTML = `
                    <div class="source-info">
                        <h4>${source.name}</h4>
                        <p class="source-path">${source.path}</p>
                        <div class="source-meta">
                            <span>Status: ${source.status}</span>
                            <span>Last scan: ${source.last_scan || 'Never'}</span>
                            <span>Files: ${source.files_count || 0}</span>
                        </div>
                    </div>
                    <div class="source-actions">
                        <button class="btn secondary" onclick="scanSource('${source.id}')">Scan Now</button>
                        <button class="btn secondary" onclick="removeSource('${source.id}')">Remove</button>
                    </div>
                `;
                sourcesList.appendChild(card);
            });
        } catch (e) {
            console.error(e);
        }
    }

    btnAddSource.addEventListener('click', async () => {
        const name = document.getElementById('new-source-name').value;
        const path = document.getElementById('new-source-path').value;
        if (!name || !path) return alert('Name and Path required');

        try {
            await fetch('/api/sources', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, path })
            });
            document.getElementById('new-source-name').value = '';
            document.getElementById('new-source-path').value = '';
            loadSources();
        } catch (e) {
            console.error(e);
            alert('Failed to add source');
        }
    });

    window.removeSource = async (id) => {
        try {
            await fetch(`/api/sources/${id}`, { method: 'DELETE' });
            loadSources();
        } catch (e) {
            console.error(e);
        }
    };

    window.scanSource = async (id) => {
        document.getElementById('sync-overlay').style.display = 'flex';
        document.getElementById('sync-loading').style.display = 'block';
        document.getElementById('sync-results').style.display = 'none';

        try {
            const res = await fetch(`/api/sources/${id}/scan`, { method: 'POST' });
            const data = await res.json();
            
            document.getElementById('sync-loading').style.display = 'none';
            
            if (!res.ok) {
                alert('Scan failed: ' + (data.detail || 'Unknown error'));
                document.getElementById('sync-overlay').style.display = 'none';
                return;
            }

            document.getElementById('sync-results').style.display = 'block';
            document.getElementById('sync-new').textContent = data.stats.new;
            document.getElementById('sync-modified').textContent = data.stats.modified;
            document.getElementById('sync-unchanged').textContent = data.stats.unchanged;
            document.getElementById('sync-deleted').textContent = data.stats.deleted;
            document.getElementById('sync-failed').textContent = data.stats.failed;
            
            loadSources(); // Refresh last scan time
        } catch (e) {
            console.error(e);
            alert('Scan failed');
            document.getElementById('sync-overlay').style.display = 'none';
        }
    };

    document.getElementById('btn-close-sync').addEventListener('click', () => {
        document.getElementById('sync-overlay').style.display = 'none';
    });
