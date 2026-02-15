// ═══════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════
let libraryData = [];
let jobsData = [];
let collectionsData = [];
let podcastsData = [];
let currentTab = 'library';
let currentMediaId = null;
let currentMediaItem = null;
let progressSaveInterval = null;
let continueWatchingData = [];
let playbackQueue = [];
let playbackQueueIndex = -1;
let isShuffled = false;

// ═══════════════════════════════════════════════════════════════
// WebSocket (Socket.IO)
// ═══════════════════════════════════════════════════════════════
const socket = io();

socket.on('connect', () => {
    console.log('WebSocket connected');
    const el = document.getElementById('ws-status');
    if (el) el.classList.add('hidden');
});

socket.on('disconnect', () => {
    console.log('WebSocket disconnected');
    const el = document.getElementById('ws-status');
    if (el) el.classList.remove('hidden');
});

socket.on('rip_progress', (data) => {
    updateStatusBar(data);
    updateJobProgress(data);
});

socket.on('job_update', (data) => {
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        hideStatusBar();
    }
    if (currentTab === 'jobs') loadJobs();
});

socket.on('job_created', (data) => {
    if (currentTab === 'jobs') loadJobs();
});

socket.on('library_updated', () => {
    loadLibrary();
});

// ═══════════════════════════════════════════════════════════════
// Tab Navigation
// ═══════════════════════════════════════════════════════════════
function showTab(tab) {
    currentTab = tab;
    ['library', 'jobs', 'collections', 'podcasts', 'add'].forEach(t => {
        document.getElementById(`tab-${t}`).classList.toggle('hidden', t !== tab);
        const btn = document.getElementById(`btn-${t}`);
        if (btn) btn.classList.toggle('bg-white/20', t === tab);
        if (t !== tab && btn) btn.classList.remove('bg-white/20');
    });
    document.getElementById('search-container').classList.toggle('hidden', tab !== 'library');

    if (tab === 'jobs') loadJobs();
    if (tab === 'collections') loadCollections();
    if (tab === 'podcasts') loadPodcasts();
}

// ═══════════════════════════════════════════════════════════════
// Library
// ═══════════════════════════════════════════════════════════════
async function loadLibrary() {
    try {
        const res = await fetch('/api/library');
        const data = await res.json();
        libraryData = data.items;
        // Also load continue watching
        try {
            const cwRes = await fetch('/api/continue-watching');
            const cwData = await cwRes.json();
            continueWatchingData = cwData.items || [];
        } catch (e) { continueWatchingData = []; }
        displayLibrary(libraryData);
        document.getElementById('library-count').textContent =
            `${data.count} item${data.count !== 1 ? 's' : ''} in your vault`;
    } catch (e) {
        document.getElementById('media-grid').innerHTML =
            '<div class="text-center py-24 col-span-full opacity-50">Error loading library</div>';
    }
}

function displayLibrary(items) {
    const grid = document.getElementById('media-grid');
    if (items.length === 0) {
        grid.innerHTML = `
            <div class="text-center py-24 col-span-full fade-in">
                <div class="text-6xl mb-4">📀</div>
                <h2 class="text-xl opacity-50 mb-2">No media found</h2>
                <p class="text-gray-400 dark:text-gray-500">Insert a disc, upload files, or add content to start building your vault</p>
            </div>`;
        return;
    }

    const typeIcons = { video: '🎬', audio: '🎵', image: '🖼️', document: '📄', other: '📎' };
    const typeColors = {
        video: 'bg-blue-500', audio: 'bg-green-500', image: 'bg-pink-500',
        document: 'bg-amber-500', other: 'bg-gray-500'
    };

    // Build continue-watching section
    let cwHtml = '';
    if (continueWatchingData.length > 0 && items === libraryData) {
        cwHtml = `
        <div class="col-span-full mb-6 fade-in">
            <h3 class="text-lg font-bold mb-3 flex items-center gap-2">▶️ Continue Watching</h3>
            <div class="flex gap-4 overflow-x-auto pb-3 -mx-1 px-1">
                ${continueWatchingData.map(cw => {
                    const pct = cw.progress_duration > 0 ? Math.round((cw.progress_position / cw.progress_duration) * 100) : 0;
                    const mt = cw.media_type || 'video';
                    return `
                    <div class="flex-shrink-0 w-[180px] bg-white dark:bg-gray-800 rounded-xl overflow-hidden cursor-pointer
                                transition-all duration-200 hover:-translate-y-1 hover:shadow-lg group"
                         onclick="showMedia('${cw.id}')">
                        <div class="relative w-full h-[110px] bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-4xl overflow-hidden">
                            ${cw.has_poster ?
                                `<img src="/api/poster/${cw.id}" alt="${escHtml(cw.title)}" class="w-full h-full object-cover" loading="lazy">` :
                                typeIcons[mt] || '📎'}
                            <div class="progress-thumb" style="width:${pct}%"></div>
                        </div>
                        <div class="p-2">
                            <div class="text-sm font-medium truncate">${escHtml(cw.title)}</div>
                            <div class="text-xs opacity-50">${pct}% · ${formatDuration(cw.progress_position)} left</div>
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // Build progress lookup for cards
    const progressMap = {};
    continueWatchingData.forEach(cw => {
        if (cw.progress_duration > 0) {
            progressMap[cw.id] = Math.round((cw.progress_position / cw.progress_duration) * 100);
        }
    });

    grid.innerHTML = cwHtml + items.map(item => {
        const mt = item.media_type || 'video';
        const pct = progressMap[item.id] || 0;
        return `
        <div class="bg-white dark:bg-gray-800 rounded-xl overflow-hidden cursor-pointer
                    transition-all duration-200 hover:-translate-y-1 hover:shadow-lg
                    hover:shadow-indigo-500/20 group fade-in"
             onclick="showMedia('${item.id}')">
            <div class="relative w-full h-[300px] bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-6xl overflow-hidden">
                ${item.has_poster ?
                    `<img src="/api/poster/${item.id}" alt="${escHtml(item.title)}"
                          class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                          loading="lazy">` :
                    typeIcons[mt] || '📎'}
                <span class="absolute top-2 right-2 type-badge px-1.5 py-0.5 rounded text-white font-bold uppercase ${typeColors[mt] || 'bg-gray-500'}">${mt}</span>
                ${pct > 0 ? `<div class="progress-thumb" style="width:${pct}%"></div>` : ''}
            </div>
            <div class="p-4">
                <div class="font-semibold mb-1 truncate">${escHtml(item.title)}</div>
                <div class="text-sm text-gray-500 dark:text-gray-400">
                    ${item.year || ''} ${item.artist ? '• ' + escHtml(item.artist) : ''}
                    ${item.size_formatted ? '• ' + item.size_formatted : ''}
                </div>
            </div>
        </div>`;
    }).join('');
}

function searchLibrary() {
    const q = document.getElementById('search').value.toLowerCase();
    if (!q) { displayLibrary(libraryData); return; }
    const filtered = libraryData.filter(item =>
        item.title.toLowerCase().includes(q) ||
        (item.director && item.director.toLowerCase().includes(q)) ||
        (item.cast && item.cast.some(a => a.toLowerCase().includes(q))) ||
        (item.genres && item.genres.some(g => g.toLowerCase().includes(q)))
    );
    displayLibrary(filtered);
}

async function rescanLibrary() {
    try {
        await fetch('/api/scan', { method: 'POST' });
        loadLibrary();
    } catch (e) {
        console.error('Rescan failed:', e);
    }
}

// ═══════════════════════════════════════════════════════════════
// Media Detail Modal
// ═══════════════════════════════════════════════════════════════
async function showMedia(id) {
    try {
        const res = await fetch(`/api/media/${id}`);
        const item = await res.json();
        if (item.error) return;
        currentMediaId = id;
        currentMediaItem = item;

        const video = document.getElementById('modal-video');
        const audio = document.getElementById('modal-audio');
        const mt = item.media_type || 'video';

        // Fetch saved progress
        let savedProgress = null;
        try {
            const pRes = await fetch(`/api/media/${id}/progress`);
            savedProgress = await pRes.json();
        } catch (e) {}

        const restartBtn = document.getElementById('btn-restart');

        if (mt === 'audio') {
            video.classList.add('hidden');
            video.src = '';
            audio.classList.remove('hidden');
            audio.src = `/api/stream/${id}`;
            setupProgressTracking(audio, id);
            if (savedProgress && savedProgress.position_seconds > 5 && !savedProgress.finished) {
                audio.addEventListener('loadedmetadata', function onLoaded() {
                    audio.removeEventListener('loadedmetadata', onLoaded);
                    if (confirm(`Continue from ${formatDuration(savedProgress.position_seconds)}?`)) {
                        audio.currentTime = savedProgress.position_seconds;
                    }
                    audio.play().catch(() => {});
                });
                restartBtn.classList.remove('hidden');
            } else {
                restartBtn.classList.add('hidden');
            }
        } else if (mt === 'video') {
            audio.classList.add('hidden');
            audio.src = '';
            video.classList.remove('hidden');
            video.src = `/api/stream/${id}`;
            setupProgressTracking(video, id);
            if (savedProgress && savedProgress.position_seconds > 5 && !savedProgress.finished) {
                video.addEventListener('loadedmetadata', function onLoaded() {
                    video.removeEventListener('loadedmetadata', onLoaded);
                    if (confirm(`Continue from ${formatDuration(savedProgress.position_seconds)}?`)) {
                        video.currentTime = savedProgress.position_seconds;
                    }
                    video.play().catch(() => {});
                });
                restartBtn.classList.remove('hidden');
            } else {
                restartBtn.classList.add('hidden');
            }
        } else {
            video.classList.add('hidden');
            video.src = '';
            audio.classList.add('hidden');
            audio.src = '';
            restartBtn.classList.add('hidden');
        }

        // Show queue navigation if playing from a collection
        const queueNav = document.getElementById('queue-nav');
        if (playbackQueue.length > 1) {
            queueNav.classList.remove('hidden');
            document.getElementById('queue-position').textContent =
                `${playbackQueueIndex + 1} of ${playbackQueue.length}`;
        } else {
            queueNav.classList.add('hidden');
        }

        document.getElementById('modal-info').innerHTML = `
            <h2 class="text-2xl font-bold mb-3">${escHtml(item.title)} ${item.year ? `<span class="font-normal opacity-60">(${item.year})</span>` : ''}</h2>
            ${item.rating ? `<p class="text-yellow-500 mb-3">⭐ ${item.rating}/10</p>` : ''}
            ${item.artist ? `<p class="mb-1"><span class="font-semibold opacity-60">Artist/Author:</span> ${escHtml(item.artist)}</p>` : ''}
            ${item.director ? `<p class="mb-1"><span class="font-semibold opacity-60">Director:</span> ${escHtml(item.director)}</p>` : ''}
            ${item.cast && item.cast.length ? `<p class="mb-1"><span class="font-semibold opacity-60">Cast:</span> ${item.cast.slice(0,5).map(escHtml).join(', ')}</p>` : ''}
            ${item.genres && item.genres.length ? `<p class="mb-1"><span class="font-semibold opacity-60">Genres:</span> ${item.genres.map(escHtml).join(', ')}</p>` : ''}
            ${item.source_url ? `<p class="mb-1"><span class="font-semibold opacity-60">Source:</span> <a href="${escHtml(item.source_url)}" target="_blank" class="text-indigo-400 hover:underline">${escHtml(item.source_url.substring(0,60))}${item.source_url.length > 60 ? '...' : ''}</a></p>` : ''}
            ${item.overview ? `<p class="mt-4 opacity-80 leading-relaxed">${escHtml(item.overview)}</p>` : ''}
            <p class="mt-4 text-sm opacity-40">
                <span class="uppercase font-semibold">${mt}</span> &bull;
                ${escHtml(item.filename || '')} &bull; ${item.size_formatted || ''}
            </p>
        `;

        document.getElementById('modal').classList.remove('hidden');
    } catch (e) {
        console.error('Error loading media:', e);
    }
}

function closeModal() {
    const video = document.getElementById('modal-video');
    const audio = document.getElementById('modal-audio');
    // Save progress before closing
    const activePlayer = !video.classList.contains('hidden') ? video :
                         !audio.classList.contains('hidden') ? audio : null;
    if (activePlayer && currentMediaId && activePlayer.currentTime > 0) {
        saveProgress(currentMediaId, activePlayer.currentTime, activePlayer.duration || 0);
    }
    if (progressSaveInterval) { clearInterval(progressSaveInterval); progressSaveInterval = null; }
    video.pause(); video.src = '';
    audio.pause(); audio.src = '';
    document.getElementById('modal').classList.add('hidden');
    document.getElementById('queue-nav').classList.add('hidden');
    currentMediaId = null;
    currentMediaItem = null;
    // Refresh continue-watching data
    loadLibrary();
}

// ═══════════════════════════════════════════════════════════════
// Edit Metadata
// ═══════════════════════════════════════════════════════════════
async function openEditModal() {
    if (!currentMediaId) return;
    const res = await fetch(`/api/media/${currentMediaId}`);
    const item = await res.json();

    document.getElementById('edit-title').value = item.title || '';
    document.getElementById('edit-year').value = item.year || '';
    document.getElementById('edit-director').value = item.director || '';
    document.getElementById('edit-rating').value = item.rating || '';
    document.getElementById('edit-genres').value = (item.genres || []).join(', ');
    document.getElementById('edit-cast').value = (item.cast || []).join(', ');
    document.getElementById('edit-overview').value = item.overview || '';

    document.getElementById('edit-modal').classList.remove('hidden');
}

async function saveMetadata() {
    if (!currentMediaId) return;
    const data = {
        title: document.getElementById('edit-title').value,
        year: document.getElementById('edit-year').value,
        director: document.getElementById('edit-director').value,
        rating: parseFloat(document.getElementById('edit-rating').value) || null,
        genres: document.getElementById('edit-genres').value.split(',').map(s => s.trim()).filter(Boolean),
        cast_members: document.getElementById('edit-cast').value.split(',').map(s => s.trim()).filter(Boolean),
        overview: document.getElementById('edit-overview').value
    };

    await fetch(`/api/media/${currentMediaId}/metadata`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    closeEditModal();
    loadLibrary();
    showMedia(currentMediaId);
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════
// Playback Progress Tracking
// ═══════════════════════════════════════════════════════════════
function setupProgressTracking(playerEl, mediaId) {
    // Clear any existing interval
    if (progressSaveInterval) clearInterval(progressSaveInterval);
    // Save every 10 seconds while playing
    progressSaveInterval = setInterval(() => {
        if (!playerEl.paused && playerEl.currentTime > 0) {
            saveProgress(mediaId, playerEl.currentTime, playerEl.duration || 0);
        }
    }, 10000);
    // Also save on pause
    playerEl.onpause = () => {
        if (playerEl.currentTime > 0) {
            saveProgress(mediaId, playerEl.currentTime, playerEl.duration || 0);
        }
    };
    // Auto-advance queue when track ends
    playerEl.onended = () => {
        saveProgress(mediaId, playerEl.duration, playerEl.duration || 0);
        if (playbackQueue.length > 1 && playbackQueueIndex < playbackQueue.length - 1) {
            queueNext();
        }
    };
}

function saveProgress(mediaId, position, duration) {
    fetch(`/api/media/${mediaId}/progress`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position, duration })
    }).catch(() => {});
}

function restartMedia() {
    const video = document.getElementById('modal-video');
    const audio = document.getElementById('modal-audio');
    const player = !video.classList.contains('hidden') ? video : audio;
    player.currentTime = 0;
    player.play().catch(() => {});
}

// ═══════════════════════════════════════════════════════════════
// Collection Queue Playback + Shuffle
// ═══════════════════════════════════════════════════════════════
function playCollection(colId, shuffle) {
    // Find collection in loaded data
    const col = collectionsData.find(c => c.id === colId);
    if (!col || !col.items.length) return;

    playbackQueue = col.items.map(i => i.id);
    if (shuffle) {
        // Fisher-Yates shuffle
        for (let i = playbackQueue.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [playbackQueue[i], playbackQueue[j]] = [playbackQueue[j], playbackQueue[i]];
        }
        isShuffled = true;
    } else {
        isShuffled = false;
    }
    playbackQueueIndex = 0;
    showMedia(playbackQueue[0]);
}

function queueNext() {
    if (playbackQueueIndex < playbackQueue.length - 1) {
        playbackQueueIndex++;
        showMedia(playbackQueue[playbackQueueIndex]);
    }
}

function queuePrev() {
    if (playbackQueueIndex > 0) {
        playbackQueueIndex--;
        showMedia(playbackQueue[playbackQueueIndex]);
    }
}

// ═══════════════════════════════════════════════════════════════
// Download
// ═══════════════════════════════════════════════════════════════
function downloadMedia() {
    if (currentMediaId) {
        window.location.href = `/api/download/${currentMediaId}`;
    }
}

// ═══════════════════════════════════════════════════════════════
// Jobs
// ═══════════════════════════════════════════════════════════════
async function loadJobs() {
    try {
        const res = await fetch('/api/jobs');
        const data = await res.json();
        jobsData = data.jobs;
        displayJobs(jobsData);
    } catch (e) {
        console.error('Error loading jobs:', e);
    }
}

function displayJobs(jobs) {
    const container = document.getElementById('jobs-list');
    if (jobs.length === 0) {
        container.innerHTML = '<p class="text-center py-12 opacity-50">No rip jobs yet. Insert a disc or click "Rip a Disc" to start.</p>';
        return;
    }
    container.innerHTML = `
        <div class="overflow-x-auto">
            <table class="w-full text-left">
                <thead class="text-xs uppercase opacity-50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                        <th class="p-3">Title</th>
                        <th class="p-3">Status</th>
                        <th class="p-3">Progress</th>
                        <th class="p-3">Created</th>
                        <th class="p-3">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${jobs.map(job => `
                        <tr class="border-t border-gray-100 dark:border-gray-700/50" id="job-${job.id}">
                            <td class="p-3 font-medium">${escHtml(job.title)}</td>
                            <td class="p-3">${statusBadge(job.status)}</td>
                            <td class="p-3 w-48">
                                ${job.status === 'encoding' ? `
                                    <div class="flex items-center gap-2">
                                        <div class="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                            <div class="bg-indigo-500 rounded-full h-2 transition-all duration-300 progress-fill"
                                                 style="width:${job.progress || 0}%"></div>
                                        </div>
                                        <span class="text-xs font-mono progress-text">${(job.progress || 0).toFixed(1)}%</span>
                                    </div>
                                ` : job.status === 'completed' ? '<span class="text-green-500">100%</span>' : '<span class="opacity-30">—</span>'}
                            </td>
                            <td class="p-3 text-sm opacity-60">
                                ${job.created_at ? new Date(job.created_at).toLocaleString() : '—'}
                            </td>
                            <td class="p-3">
                                ${['queued', 'encoding'].includes(job.status) ?
                                    `<button onclick="cancelJob('${job.id}')"
                                        class="text-red-500 hover:text-red-400 text-sm font-medium">Cancel</button>` : ''}
                                ${['failed', 'cancelled'].includes(job.status) ?
                                    `<button onclick="retryJob('${job.id}')"
                                        class="text-indigo-500 hover:text-indigo-400 text-sm font-medium">Retry</button>` : ''}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function statusBadge(status) {
    const styles = {
        queued:    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
        encoding:  'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
        completed: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        failed:    'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
    };
    return `<span class="px-2.5 py-1 rounded-full text-xs font-medium ${styles[status] || ''}">${status}</span>`;
}

function updateJobProgress(data) {
    const row = document.getElementById(`job-${data.id}`);
    if (row) {
        const bar = row.querySelector('.progress-fill');
        const text = row.querySelector('.progress-text');
        if (bar) bar.style.width = `${data.progress}%`;
        if (text) text.textContent = `${data.progress.toFixed(1)}%`;
    }
}

async function cancelJob(id) {
    await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
    loadJobs();
}

async function retryJob(id) {
    await fetch(`/api/jobs/${id}/retry`, { method: 'POST' });
    loadJobs();
}

function showRipForm() {
    document.getElementById('rip-source').value = '';
    document.getElementById('rip-title').value = '';
    document.getElementById('rip-title-num').value = '1';
    document.getElementById('rip-modal').classList.remove('hidden');
}

function closeRipModal() {
    document.getElementById('rip-modal').classList.add('hidden');
}

async function submitRipJob() {
    const source = document.getElementById('rip-source').value.trim();
    const title = document.getElementById('rip-title').value.trim();
    const titleNum = parseInt(document.getElementById('rip-title-num').value) || 1;

    if (!source) { alert('Source path is required'); return; }

    await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source_path: source,
            title: title || undefined,
            title_number: titleNum
        })
    });

    closeRipModal();
    showTab('jobs');
}

// ═══════════════════════════════════════════════════════════════
// Status Bar
// ═══════════════════════════════════════════════════════════════
function updateStatusBar(data) {
    const bar = document.getElementById('status-bar');
    bar.classList.remove('hidden');
    document.getElementById('status-title').textContent = data.title || 'Encoding...';
    document.getElementById('status-percent').textContent = `${(data.progress || 0).toFixed(1)}%`;
    document.getElementById('status-eta').textContent = data.eta ? `ETA: ${data.eta}` : '';
    document.getElementById('status-progress-bar').style.width = `${data.progress || 0}%`;
}

function hideStatusBar() {
    document.getElementById('status-bar').classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════
// Collections
// ═══════════════════════════════════════════════════════════════
async function loadCollections() {
    try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        collectionsData = data.collections;
        displayCollections(collectionsData);
    } catch (e) {
        console.error('Error loading collections:', e);
    }
}

function displayCollections(collections) {
    const container = document.getElementById('collections-list');
    if (collections.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 opacity-50">
                <div class="text-5xl mb-4">📁</div>
                <p>No collections yet. Add movies to collections from the media detail view.</p>
            </div>`;
        return;
    }
    container.innerHTML = collections.map(col => `
        <div class="mb-8 fade-in">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold">${escHtml(col.name)}
                    <span class="text-sm font-normal opacity-50 ml-2">${col.items.length} items</span>
                    ${col.collection_type === 'playlist' ? '<span class="text-xs ml-2 px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">playlist</span>' : ''}
                </h3>
                <div class="flex gap-2">
                    ${col.items.length > 0 ? `
                    <button onclick="playCollection(${col.id}, false)"
                        class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition text-sm font-medium">
                        ▶ Play
                    </button>
                    <button onclick="playCollection(${col.id}, true)"
                        class="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-700 text-white rounded-lg transition text-sm font-medium"
                        title="Shuffle play">
                        🔀 Shuffle
                    </button>` : ''}
                    <button onclick="deleteCollection('${escAttr(col.name)}')"
                        class="text-red-500 hover:text-red-400 text-sm">Delete</button>
                </div>
            </div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-4">
                ${col.items.map(item => `
                    <div class="bg-white dark:bg-gray-800 rounded-lg overflow-hidden cursor-pointer
                                hover:-translate-y-1 transition-transform shadow-sm"
                         onclick="showMedia('${item.id}')">
                        <div class="h-[200px] bg-gray-200 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                            ${item.has_poster ?
                                `<img src="/api/poster/${item.id}" class="w-full h-full object-cover" loading="lazy">` :
                                '<span class="text-4xl">🎬</span>'}
                        </div>
                        <div class="p-2 text-sm truncate">${escHtml(item.title)}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

async function deleteCollection(name) {
    if (!confirm(`Delete collection "${name}"?`)) return;
    await fetch(`/api/collections/${encodeURIComponent(name)}`, { method: 'DELETE' });
    loadCollections();
}

async function addToCollection() {
    if (!currentMediaId) return;
    const name = prompt('Enter collection name:');
    if (!name || !name.trim()) return;
    const cleanName = name.trim();

    // Get existing items in collection (if any)
    let existingIds = [];
    try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        const existing = data.collections.find(c => c.name === cleanName);
        if (existing) existingIds = existing.items.map(i => i.id);
    } catch (e) {}

    if (existingIds.includes(currentMediaId)) {
        alert('Already in this collection');
        return;
    }
    existingIds.push(currentMediaId);

    await fetch(`/api/collections/${encodeURIComponent(cleanName)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_ids: existingIds })
    });

    alert(`Added to "${cleanName}"`);
}

// ═══════════════════════════════════════════════════════════════
// Dark Mode
// ═══════════════════════════════════════════════════════════════
function initDarkMode() {
    const saved = localStorage.getItem('darkMode');
    if (saved === 'false') {
        document.documentElement.classList.remove('dark');
    }
    updateDarkModeIcon();
}

function toggleDarkMode() {
    document.documentElement.classList.toggle('dark');
    const isDark = document.documentElement.classList.contains('dark');
    localStorage.setItem('darkMode', String(isDark));
    updateDarkModeIcon();
}

function updateDarkModeIcon() {
    const isDark = document.documentElement.classList.contains('dark');
    const el = document.getElementById('dark-mode-icon');
    if (el) el.textContent = isDark ? '☀️' : '🌙';
}

// ═══════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════
function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ═══════════════════════════════════════════════════════════════
// Upload / Drag-and-Drop
// ═══════════════════════════════════════════════════════════════
function initDropZone() {
    const dz = document.getElementById('drop-zone');
    if (!dz) return;

    ['dragenter', 'dragover'].forEach(ev =>
        dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach(ev =>
        dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('dragover'); }));

    dz.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files.length) uploadFiles(files);
    });
}

function handleFileSelect(e) {
    if (e.target.files.length) uploadFiles(e.target.files);
}

async function uploadFiles(files) {
    const form = new FormData();
    for (const f of files) form.append('files', f);

    const prog = document.getElementById('upload-progress');
    const bar = document.getElementById('upload-bar');
    const status = document.getElementById('upload-status');
    prog.classList.remove('hidden');
    bar.style.width = '0%';
    status.textContent = `Uploading ${files.length} file${files.length > 1 ? 's' : ''}...`;

    try {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        xhr.upload.onprogress = e => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                bar.style.width = pct + '%';
                status.textContent = `Uploading... ${pct}%`;
            }
        };
        xhr.onload = () => {
            if (xhr.status === 201) {
                const data = JSON.parse(xhr.responseText);
                status.textContent = `✅ ${data.uploaded.length} file${data.uploaded.length > 1 ? 's' : ''} uploaded`;
                bar.style.width = '100%';
                loadLibrary();
            } else {
                status.textContent = '❌ Upload failed';
            }
            setTimeout(() => prog.classList.add('hidden'), 3000);
        };
        xhr.onerror = () => {
            status.textContent = '❌ Upload failed';
            setTimeout(() => prog.classList.add('hidden'), 3000);
        };
        xhr.send(form);
    } catch (e) {
        status.textContent = '❌ Upload failed';
        setTimeout(() => prog.classList.add('hidden'), 3000);
    }
}

// ═══════════════════════════════════════════════════════════════
// Content Submission
// ═══════════════════════════════════════════════════════════════
async function submitVideoDownload() {
    const url = document.getElementById('video-url').value.trim();
    if (!url) return alert('Please enter a URL');
    try {
        const res = await fetch('/api/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('video-url').value = '';
            alert('Download queued! Check Jobs tab for progress.');
            showTab('jobs');
        } else {
            alert(data.error || 'Failed');
        }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitArticle() {
    const url = document.getElementById('article-url').value.trim();
    if (!url) return alert('Please enter a URL');
    try {
        const res = await fetch('/api/articles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('article-url').value = '';
            alert('Article archiving queued!');
            showTab('jobs');
        } else {
            alert(data.error || 'Failed');
        }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitBook() {
    const title = document.getElementById('book-title').value.trim();
    if (!title) return alert('Book title is required');
    const body = {
        title,
        author: document.getElementById('book-author').value.trim() || undefined,
        year: document.getElementById('book-year').value.trim() || undefined,
        description: document.getElementById('book-desc').value.trim() || undefined,
    };
    try {
        const res = await fetch('/api/books', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.ok) {
            ['book-title', 'book-author', 'book-year', 'book-desc'].forEach(
                id => document.getElementById(id).value = '');
            alert('Book added to library!');
            loadLibrary();
        }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitPlaylist() {
    const url = document.getElementById('playlist-url').value.trim();
    if (!url) return alert('Please enter a playlist URL');
    const name = prompt('Name for this playlist:', 'Imported Playlist');
    if (!name) return;
    try {
        const res = await fetch('/api/import/playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, name })
        });
        if (res.ok) {
            document.getElementById('playlist-url').value = '';
            alert('Playlist import queued!');
            showTab('jobs');
        }
    } catch (e) { alert('Error: ' + e.message); }
}

// ═══════════════════════════════════════════════════════════════
// Podcasts
// ═══════════════════════════════════════════════════════════════
async function loadPodcasts() {
    try {
        const res = await fetch('/api/podcasts');
        const data = await res.json();
        podcastsData = data.podcasts;
        displayPodcasts(podcastsData);
    } catch (e) {
        console.error('Error loading podcasts:', e);
    }
}

function displayPodcasts(pods) {
    const container = document.getElementById('podcasts-list');
    if (pods.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 opacity-50 fade-in">
                <div class="text-5xl mb-4">🎙️</div>
                <p>No podcasts yet. Click "+ Subscribe" to add one.</p>
            </div>`;
        return;
    }
    container.innerHTML = pods.map(pod => `
        <div class="bg-white dark:bg-gray-800 rounded-xl p-5 mb-4 flex gap-5 items-start shadow-sm fade-in">
            <div class="w-20 h-20 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-3xl flex-shrink-0 overflow-hidden">
                ${pod.artwork_path ?
                    `<img src="/api/poster/${pod.id}" class="w-full h-full object-cover" onerror="this.outerHTML='🎙️'">` :
                    '🎙️'}
            </div>
            <div class="flex-1 min-w-0">
                <h3 class="font-semibold text-lg truncate">${escHtml(pod.title || pod.feed_url)}</h3>
                <p class="text-sm opacity-60 truncate">${escHtml(pod.author || '')}</p>
                <p class="text-sm opacity-40 mt-1 line-clamp-2">${escHtml(pod.description || '').substring(0, 150)}</p>
                <div class="flex gap-3 mt-3">
                    <button onclick="viewEpisodes('${pod.id}')"
                        class="text-sm text-indigo-500 hover:text-indigo-400 font-medium">
                        View Episodes
                    </button>
                    <button onclick="unsubscribePodcast('${pod.id}')"
                        class="text-sm text-red-500 hover:text-red-400 font-medium">
                        Unsubscribe
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

async function viewEpisodes(podId) {
    try {
        const res = await fetch(`/api/podcasts/${podId}/episodes`);
        const data = await res.json();
        const pod = podcastsData.find(p => p.id === podId);
        const container = document.getElementById('podcasts-list');

        container.innerHTML = `
            <div class="mb-4">
                <button onclick="loadPodcasts()" class="text-indigo-500 hover:text-indigo-400 text-sm font-medium">&larr; Back to Podcasts</button>
            </div>
            <h3 class="text-xl font-bold mb-4">${escHtml(pod?.title || 'Episodes')}</h3>
            ${data.episodes.length === 0 ?
                '<p class="opacity-50 py-8 text-center">No episodes found.</p>' :
                data.episodes.map(ep => `
                    <div class="bg-white dark:bg-gray-800 rounded-lg p-4 mb-2 shadow-sm">
                        <div class="flex justify-between items-start">
                            <div class="flex-1 min-w-0">
                                <div class="font-medium truncate">${escHtml(ep.title)}</div>
                                <div class="text-sm opacity-50 mt-1">
                                    ${ep.published_at ? new Date(ep.published_at).toLocaleDateString() : ''}
                                    ${ep.duration_seconds ? ' • ' + formatDuration(ep.duration_seconds) : ''}
                                    ${ep.is_downloaded ? ' • ✅ Downloaded' : ''}
                                </div>
                            </div>
                            ${ep.is_downloaded && ep.file_path ?
                                `<button onclick="playEpisodeAudio('${ep.id}', '${escAttr(ep.title)}')" class="text-indigo-500 hover:text-indigo-400 text-sm font-medium ml-2 whitespace-nowrap">▶ Play</button>` :
                                ''}
                        </div>
                    </div>
                `).join('')}
        `;
    } catch (e) {
        console.error('Error loading episodes:', e);
    }
}

function formatDuration(seconds) {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${s}s`;
}

function playEpisodeAudio(epId, title) {
    // Simple inline player
    alert('Audio playback coming in next update!');
}

async function unsubscribePodcast(podId) {
    if (!confirm('Unsubscribe from this podcast?')) return;
    await fetch(`/api/podcasts/${podId}`, { method: 'DELETE' });
    loadPodcasts();
}

function showSubscribeModal() {
    document.getElementById('podcast-feed-url').value = '';
    document.getElementById('podcast-title').value = '';
    document.getElementById('subscribe-modal').classList.remove('hidden');
}

function closeSubscribeModal() {
    document.getElementById('subscribe-modal').classList.add('hidden');
}

async function submitPodcastSubscription() {
    const feedUrl = document.getElementById('podcast-feed-url').value.trim();
    if (!feedUrl) return alert('Feed URL is required');
    const title = document.getElementById('podcast-title').value.trim();

    try {
        const res = await fetch('/api/podcasts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feed_url: feedUrl, title: title || undefined })
        });
        const data = await res.json();
        if (res.ok) {
            closeSubscribeModal();
            loadPodcasts();
        } else {
            alert(data.error || 'Failed to subscribe');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════
initDarkMode();
initDropZone();
loadLibrary();
