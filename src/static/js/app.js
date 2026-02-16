// ═══════════════════════════════════════════════════════════════
// MediaLibrary – Spotify-style SPA
// ═══════════════════════════════════════════════════════════════

// ── State ──────────────────────────────────────────────────────
let libraryData = [];
let jobsData = [];
let collectionsData = [];
let podcastsData = [];
let continueWatchingData = [];

let currentMediaId = null;
let currentMediaItem = null;
let progressSaveInterval = null;

// Player
let playbackQueue = [];
let playbackQueueIndex = -1;
let isShuffled = false;
let isRepeat = false;
let playerVolume = 0.7;
let isMuted = false;
let activePlayerEl = null;   // The <audio>/<video> element driving the bottom bar
let isSeeking = false;

// Navigation
let navHistory = [];
let navForwardStack = [];
let currentView = 'home';
let currentViewParams = {};
let sidebarFilter = 'all';

// ── Utilities ──────────────────────────────────────────────────
function escHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}
function escAttr(str) { return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
    return `${m}:${s.toString().padStart(2,'0')}`;
}

function formatDurationLong(seconds) {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

const typeIcons = { video: '🎬', audio: '🎵', image: '🖼️', document: '📄', podcast: '🎙️', other: '📎' };
const typeColors = { video: 'bg-blue-500', audio: 'bg-green-500', image: 'bg-pink-500', document: 'bg-amber-500', podcast: 'bg-purple-500', other: 'bg-gray-500' };

// ── WebSocket ──────────────────────────────────────────────────
const socket = io();
socket.on('connect', () => { const el = document.getElementById('ws-status'); if (el) el.classList.add('hidden'); });
socket.on('disconnect', () => { const el = document.getElementById('ws-status'); if (el) el.classList.remove('hidden'); });
socket.on('rip_progress', (data) => { updateStatusBar(data); });
socket.on('job_update', (data) => {
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') hideStatusBar();
    if (currentView === 'jobs') renderView();
});
socket.on('job_created', () => { if (currentView === 'jobs') renderView(); });
socket.on('library_updated', () => { loadLibrary(); });

// ── Navigation ─────────────────────────────────────────────────
function navigateTo(view, params = {}) {
    if (currentView === view && JSON.stringify(currentViewParams) === JSON.stringify(params)) return;
    navHistory.push({ view: currentView, params: currentViewParams });
    navForwardStack = [];
    currentView = view;
    currentViewParams = params;
    renderView();
    updateSidebarActive();
    document.getElementById('main-content').scrollTo(0, 0);
}

function historyBack() {
    if (navHistory.length === 0) return;
    navForwardStack.push({ view: currentView, params: currentViewParams });
    const prev = navHistory.pop();
    currentView = prev.view;
    currentViewParams = prev.params;
    renderView();
    updateSidebarActive();
}

function historyForward() {
    if (navForwardStack.length === 0) return;
    navHistory.push({ view: currentView, params: currentViewParams });
    const next = navForwardStack.pop();
    currentView = next.view;
    currentViewParams = next.params;
    renderView();
    updateSidebarActive();
}

function updateSidebarActive() {
    document.querySelectorAll('.sidebar-link').forEach(el => el.classList.remove('active'));
    const navEl = document.querySelector(`.sidebar-link[data-nav="${currentView}"]`);
    if (navEl) navEl.classList.add('active');
    const browseEl = document.querySelector(`.sidebar-link[data-browse="${currentViewParams.type}"]`);
    if (currentView === 'browse' && browseEl) browseEl.classList.add('active');
}

function browseType(type) { navigateTo('browse', { type }); }

// ── Search (top bar) ───────────────────────────────────────────
let searchTimeout = null;
function onSearchInput(q) {
    clearTimeout(searchTimeout);
    if (!q.trim()) { if (currentView === 'search') navigateTo('home'); return; }
    searchTimeout = setTimeout(() => {
        navigateTo('search', { q: q.trim() });
    }, 300);
}

// ── View Router ────────────────────────────────────────────────
function renderView() {
    const container = document.getElementById('view-container');
    switch (currentView) {
        case 'home':     renderHome(container); break;
        case 'browse':   renderBrowse(container); break;
        case 'search':   renderSearch(container); break;
        case 'jobs':     renderJobs(container); break;
        case 'add':      renderAddContent(container); break;
        case 'collection': renderCollectionDetail(container); break;
        case 'album':    renderAlbumDetail(container); break;
        case 'artist':   renderArtistDetail(container); break;
        case 'podcast':  renderPodcastDetail(container); break;
        case 'media':    renderMediaDetail(container); break;
        default:         renderHome(container); break;
    }
}

// ── Home View ──────────────────────────────────────────────────
function renderHome(container) {
    let html = '';

    // Type filter pills
    html += `<div class="flex items-center gap-3 mb-6">
        <h1 class="text-2xl font-bold">All Media</h1>
        <div class="flex gap-2">
            ${['All','Movies','Music','Documents','Images'].map(t => {
                const val = t === 'All' ? 'all' : t === 'Movies' ? 'video' : t === 'Music' ? 'audio' : t === 'Documents' ? 'document' : 'image';
                const active = (!currentViewParams.filter && val === 'all') || currentViewParams.filter === val;
                return `<span class="pill ${active ? 'pill-active' : 'pill-inactive'}" onclick="navigateTo('home', {filter:'${val}'})">${t}</span>`;
            }).join('')}
        </div>
    </div>`;

    // Continue watching
    if (continueWatchingData.length > 0 && (!currentViewParams.filter || currentViewParams.filter === 'all')) {
        html += `<div class="mb-8 fade-in">
            <h2 class="text-lg font-bold mb-3">▶️ Continue Watching</h2>
            <div class="flex gap-4 overflow-x-auto pb-3 -mx-1 px-1">
                ${continueWatchingData.map(cw => {
                    const pct = cw.progress_duration > 0 ? Math.round((cw.progress_position / cw.progress_duration) * 100) : 0;
                    return `<div class="flex-shrink-0 w-[180px] media-card p-0 overflow-hidden rounded-lg" onclick="playMediaInBar('${cw.id}')">
                        <div class="relative w-full h-[100px] bg-[#282828] flex items-center justify-center text-3xl overflow-hidden">
                            ${cw.has_poster ? `<img src="/api/poster/${cw.id}" alt="${escHtml(cw.title)}" class="w-full h-full object-cover" loading="lazy">` : typeIcons[cw.media_type || 'video']}
                            <div class="progress-thumb" style="width:${pct}%"></div>
                        </div>
                        <div class="p-2"><div class="text-sm font-medium truncate">${escHtml(cw.title)}</div>
                        <div class="text-xs text-gray-400">${pct}% · ${formatDurationLong(cw.progress_position)} left</div></div>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // Filter items
    let items = libraryData;
    const f = currentViewParams.filter;
    if (f && f !== 'all') items = items.filter(i => (i.media_type || 'video') === f);

    if (items.length === 0) {
        html += `<div class="text-center py-20 fade-in">
            <div class="text-6xl mb-4 opacity-40">📀</div>
            <h2 class="text-xl text-gray-400 mb-2">Nothing here yet</h2>
            <p class="text-gray-500 text-sm">Insert a disc, upload files, or add content to start building your vault</p>
        </div>`;
    } else {
        html += renderMediaGrid(items);
    }

    container.innerHTML = html;
}

// ── Browse View (filtered by type) ─────────────────────────────
function renderBrowse(container) {
    const type = currentViewParams.type || 'audio';
    const labels = { audio: 'Music', video: 'Movies', document: 'Documents', image: 'Images', podcast: 'Podcasts' };
    const label = labels[type] || type;

    if (type === 'podcast') {
        renderPodcastsList(container);
        return;
    }

    const items = libraryData.filter(i => (i.media_type || 'video') === type);

    let html = `<h1 class="section-heading">${label}</h1>`;

    if (type === 'audio') {
        // Group by artist for music
        const albums = groupBy(items, 'collection_name');
        const artists = groupBy(items, 'artist');
        html += `<div class="flex gap-2 mb-6">
            <span class="pill pill-active" onclick="this.parentElement.querySelectorAll('.pill').forEach(p=>p.className='pill pill-inactive');this.className='pill pill-active';document.getElementById('browse-audio-grid').style.display='';document.getElementById('browse-audio-artists').style.display='none';document.getElementById('browse-audio-albums').style.display='none';">All Tracks</span>
            <span class="pill pill-inactive" onclick="this.parentElement.querySelectorAll('.pill').forEach(p=>p.className='pill pill-inactive');this.className='pill pill-active';document.getElementById('browse-audio-grid').style.display='none';document.getElementById('browse-audio-artists').style.display='';document.getElementById('browse-audio-albums').style.display='none';">Artists</span>
            <span class="pill pill-inactive" onclick="this.parentElement.querySelectorAll('.pill').forEach(p=>p.className='pill pill-inactive');this.className='pill pill-active';document.getElementById('browse-audio-grid').style.display='none';document.getElementById('browse-audio-artists').style.display='none';document.getElementById('browse-audio-albums').style.display='';">Albums</span>
        </div>`;
        html += `<div id="browse-audio-grid">${renderTrackList(items)}</div>`;
        html += `<div id="browse-audio-artists" style="display:none">${renderArtistGrid(artists)}</div>`;
        html += `<div id="browse-audio-albums" style="display:none">${renderAlbumGrid(albums)}</div>`;
    } else {
        if (items.length === 0) {
            html += `<div class="text-center py-20 text-gray-500">No ${label.toLowerCase()} yet</div>`;
        } else {
            html += renderMediaGrid(items);
        }
    }

    container.innerHTML = html;
}

// ── Search View ────────────────────────────────────────────────
function renderSearch(container) {
    const q = (currentViewParams.q || '').toLowerCase();
    if (!q) { container.innerHTML = ''; return; }

    const items = libraryData.filter(item =>
        item.title.toLowerCase().includes(q) ||
        (item.artist && item.artist.toLowerCase().includes(q)) ||
        (item.director && item.director.toLowerCase().includes(q)) ||
        (item.cast && item.cast.some(a => a.toLowerCase().includes(q))) ||
        (item.genres && item.genres.some(g => g.toLowerCase().includes(q))) ||
        (item.collection_name && item.collection_name.toLowerCase().includes(q))
    );

    let html = `<h1 class="section-heading">Results for "${escHtml(currentViewParams.q)}"</h1>`;
    if (items.length === 0) {
        html += '<div class="text-gray-500 py-12 text-center">No results found</div>';
    } else {
        // Group results by type
        const groups = {};
        items.forEach(i => { const t = i.media_type || 'video'; if (!groups[t]) groups[t] = []; groups[t].push(i); });
        for (const [type, group] of Object.entries(groups)) {
            const label = { audio: 'Music', video: 'Movies', document: 'Documents', image: 'Images' }[type] || type;
            html += `<h2 class="text-lg font-bold mt-6 mb-3">${label}</h2>`;
            if (type === 'audio') {
                html += renderTrackList(group);
            } else {
                html += renderMediaGrid(group);
            }
        }
    }
    container.innerHTML = html;
}

// ── Collection Detail View (playlist) ──────────────────────────
function renderCollectionDetail(container) {
    const colId = currentViewParams.id;
    const col = collectionsData.find(c => c.id == colId || c.name === colId);
    if (!col) { container.innerHTML = '<div class="text-gray-500 py-12 text-center">Collection not found</div>'; return; }

    const items = col.items || [];
    const posterItem = items.find(i => i.has_poster);
    const totalDur = items.reduce((a, i) => a + (i.duration_seconds || 0), 0);

    let html = `
    <div class="flex gap-6 mb-8 items-end">
        <div class="w-[200px] h-[200px] rounded-lg bg-[#282828] flex items-center justify-center text-5xl overflow-hidden shadow-xl flex-shrink-0">
            ${posterItem ? `<img src="/api/poster/${posterItem.id}" class="w-full h-full object-cover">` : '📁'}
        </div>
        <div class="flex-1 min-w-0">
            <div class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">${col.collection_type === 'playlist' ? 'Playlist' : 'Collection'}</div>
            <h1 class="text-5xl font-black mb-4 truncate">${escHtml(col.name)}</h1>
            <div class="text-sm text-gray-400">${items.length} item${items.length !== 1 ? 's' : ''}${totalDur ? ' · about ' + formatDurationLong(totalDur) : ''}</div>
        </div>
    </div>
    <div class="flex items-center gap-4 mb-6">
        <button onclick="playCollectionFromBar(${col.id}, false)" class="w-12 h-12 rounded-full bg-green-500 hover:bg-green-400 flex items-center justify-center transition hover:scale-105">
            <svg width="20" height="20" fill="black" viewBox="0 0 16 16"><path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"/></svg>
        </button>
        <button onclick="playCollectionFromBar(${col.id}, true)" class="player-btn text-gray-400 hover:text-white" title="Shuffle">
            <svg width="24" height="24" fill="currentColor" viewBox="0 0 16 16"><path d="M13.151.922a.75.75 0 1 0-1.06 1.06L13.109 3H11.16a3.75 3.75 0 0 0-2.873 1.34l-6.173 7.356A2.25 2.25 0 0 1 .39 12.5H0V14h.391a3.75 3.75 0 0 0 2.873-1.34l6.173-7.356A2.25 2.25 0 0 1 11.16 4.5h1.95l-1.018 1.018a.75.75 0 0 0 1.06 1.06l2.06-2.06a.78.78 0 0 0 0-1.06l-2.06-2.06zM9.553 9.96l1.607 1.915A2.25 2.25 0 0 0 12.84 12.5h1.95l-1.017-1.018a.75.75 0 0 1 1.06-1.06l2.06 2.06a.78.78 0 0 1 0 1.06l-2.06 2.06a.75.75 0 1 1-1.06-1.06L14.79 13.5h-1.95a3.75 3.75 0 0 1-2.873-1.34L8.36 10.14l1.192-1.18zM.39 3.5H0V2h.391a3.75 3.75 0 0 1 2.873 1.34L4.89 5.277 3.7 6.457 2.114 4.696A2.25 2.25 0 0 0 .39 3.5z"/></svg>
        </button>
        <button onclick="deleteCollection('${escAttr(col.name)}')" class="player-btn text-gray-400 hover:text-red-400" title="Delete collection">
            <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8z"/><path d="M12 8.5H4v-1h8v1z"/></svg>
        </button>
    </div>`;

    // Track list header
    if (items.length > 0) {
        html += `<div class="track-row text-xs text-gray-400 uppercase font-bold border-b border-[#282828] mb-2 hover:bg-transparent">
            <span>#</span><span>Title</span><span class="hidden sm:block">Type</span><span class="hidden md:block">Added</span><span class="text-right">⏱</span>
        </div>`;
        html += items.map((item, idx) => renderTrackRow(item, idx + 1, col.id)).join('');
    }

    container.innerHTML = html;
}

// ── Album Detail View ──────────────────────────────────────────
function renderAlbumDetail(container) {
    const albumName = currentViewParams.name;
    const items = libraryData.filter(i => i.collection_name === albumName || (i.album && i.album === albumName));
    if (items.length === 0) { container.innerHTML = '<div class="text-gray-500 py-12 text-center">Album not found</div>'; return; }

    const first = items[0];
    const artist = first.artist || 'Unknown Artist';
    const year = first.year || '';
    const totalDur = items.reduce((a, i) => a + (i.duration_seconds || 0), 0);

    let html = `
    <div class="flex gap-6 mb-8 items-end">
        <div class="w-[200px] h-[200px] rounded-lg bg-[#282828] flex items-center justify-center text-5xl overflow-hidden shadow-xl flex-shrink-0">
            ${first.has_poster ? `<img src="/api/poster/${first.id}" class="w-full h-full object-cover">` : '💿'}
        </div>
        <div class="flex-1 min-w-0">
            <div class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Album</div>
            <h1 class="text-4xl font-black mb-2 truncate">${escHtml(albumName)}</h1>
            <div class="text-sm text-gray-400">
                <span class="text-white font-semibold cursor-pointer hover:underline" onclick="navigateTo('artist',{name:'${escAttr(artist)}'})">${escHtml(artist)}</span>
                ${year ? ` · ${year}` : ''} · ${items.length} song${items.length !== 1 ? 's' : ''}${totalDur ? ', ' + formatDurationLong(totalDur) : ''}
            </div>
        </div>
    </div>
    <div class="flex items-center gap-4 mb-6">
        <button onclick="playItemsInBar(${JSON.stringify(items.map(i=>i.id)).replace(/"/g,'&quot;')}, false)" class="w-12 h-12 rounded-full bg-green-500 hover:bg-green-400 flex items-center justify-center transition hover:scale-105">
            <svg width="20" height="20" fill="black" viewBox="0 0 16 16"><path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"/></svg>
        </button>
    </div>`;

    html += `<div class="track-row text-xs text-gray-400 uppercase font-bold border-b border-[#282828] mb-2 hover:bg-transparent">
        <span>#</span><span>Title</span><span class="hidden sm:block">Artist</span><span class="hidden md:block"></span><span class="text-right">⏱</span>
    </div>`;
    html += items.map((item, idx) => renderTrackRow(item, idx + 1)).join('');

    container.innerHTML = html;
}

// ── Artist Detail View ─────────────────────────────────────────
function renderArtistDetail(container) {
    const artistName = currentViewParams.name;
    const items = libraryData.filter(i => i.artist === artistName);
    if (items.length === 0) { container.innerHTML = '<div class="text-gray-500 py-12 text-center">Artist not found</div>'; return; }

    // Group by album
    const albums = groupBy(items, 'collection_name');
    const first = items.find(i => i.has_poster) || items[0];

    let html = `
    <div class="flex gap-6 mb-8 items-end">
        <div class="w-[200px] h-[200px] rounded-full bg-[#282828] flex items-center justify-center text-5xl overflow-hidden shadow-xl flex-shrink-0">
            ${first.has_poster ? `<img src="/api/poster/${first.id}" class="w-full h-full object-cover">` : '🎤'}
        </div>
        <div class="flex-1 min-w-0">
            <div class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Artist</div>
            <h1 class="text-5xl font-black mb-2 truncate">${escHtml(artistName)}</h1>
            <div class="text-sm text-gray-400">${items.length} track${items.length !== 1 ? 's' : ''}</div>
        </div>
    </div>
    <div class="flex items-center gap-4 mb-6">
        <button onclick="playItemsInBar(${JSON.stringify(items.map(i=>i.id)).replace(/"/g,'&quot;')}, false)" class="w-12 h-12 rounded-full bg-green-500 hover:bg-green-400 flex items-center justify-center transition hover:scale-105">
            <svg width="20" height="20" fill="black" viewBox="0 0 16 16"><path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"/></svg>
        </button>
    </div>`;

    // Show albums
    const albumNames = Object.keys(albums).filter(n => n);
    if (albumNames.length > 0) {
        html += `<h2 class="text-xl font-bold mb-4">Albums</h2>`;
        html += renderAlbumGrid(albums);
    }

    // All tracks
    html += `<h2 class="text-xl font-bold mt-8 mb-4">All Tracks</h2>`;
    html += renderTrackList(items);

    container.innerHTML = html;
}

// ── Podcast List View ──────────────────────────────────────────
function renderPodcastsList(container) {
    let html = `<div class="flex justify-between items-center mb-6">
        <h1 class="section-heading mb-0">Podcasts</h1>
        <button onclick="showSubscribeModal()" class="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-full transition text-sm font-medium">+ Subscribe</button>
    </div>`;

    if (podcastsData.length === 0) {
        html += `<div class="text-center py-20 text-gray-500"><div class="text-5xl mb-4">🎙️</div><p>No podcasts yet. Subscribe to add one.</p></div>`;
    } else {
        html += `<div class="card-grid">`;
        html += podcastsData.map(pod => `
            <div class="media-card rounded-lg" onclick="navigateTo('podcast',{id:'${pod.id}'})">
                <div class="w-full aspect-square rounded-lg bg-[#282828] flex items-center justify-center text-4xl overflow-hidden mb-3">
                    ${pod.artwork_path ? `<img src="/api/poster/${pod.id}" class="w-full h-full object-cover" onerror="this.outerHTML='🎙️'" loading="lazy">` : '🎙️'}
                </div>
                <div class="font-medium text-sm truncate">${escHtml(pod.title || pod.feed_url)}</div>
                <div class="text-xs text-gray-400 truncate">${escHtml(pod.author || '')}</div>
            </div>
        `).join('');
        html += `</div>`;
    }
    container.innerHTML = html;
}

// ── Podcast Detail View ────────────────────────────────────────
async function renderPodcastDetail(container) {
    const podId = currentViewParams.id;
    const pod = podcastsData.find(p => p.id === podId);
    if (!pod) { container.innerHTML = '<div class="text-gray-500 py-12 text-center">Podcast not found</div>'; return; }

    container.innerHTML = `<div class="flex gap-6 mb-8 items-end">
        <div class="w-[200px] h-[200px] rounded-lg bg-[#282828] flex items-center justify-center text-5xl overflow-hidden shadow-xl flex-shrink-0">
            ${pod.artwork_path ? `<img src="/api/poster/${pod.id}" class="w-full h-full object-cover">` : '🎙️'}
        </div>
        <div class="flex-1 min-w-0">
            <div class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Podcast</div>
            <h1 class="text-4xl font-black mb-2 truncate">${escHtml(pod.title || pod.feed_url)}</h1>
            <div class="text-sm text-gray-400">${escHtml(pod.author || '')}</div>
            <p class="text-sm text-gray-500 mt-2 line-clamp-3">${escHtml((pod.description || '').substring(0, 300))}</p>
        </div>
    </div>
    <div class="flex gap-3 mb-6">
        <button onclick="unsubscribePodcast('${pod.id}')" class="px-4 py-2 bg-red-900/40 hover:bg-red-900/60 rounded-lg text-sm text-red-300 transition">Unsubscribe</button>
    </div>
    <div id="episodes-list"><div class="text-gray-500 py-4">Loading episodes...</div></div>`;

    // Load episodes
    try {
        const res = await fetch(`/api/podcasts/${podId}/episodes`);
        const data = await res.json();
        const epContainer = document.getElementById('episodes-list');
        if (!epContainer) return;
        if (data.episodes.length === 0) {
            epContainer.innerHTML = '<div class="text-gray-500 py-8 text-center">No episodes found.</div>';
        } else {
            epContainer.innerHTML = data.episodes.map((ep, idx) => `
                <div class="track-row text-sm" style="grid-template-columns: 2rem 1fr auto auto;">
                    <span class="text-gray-500">${idx + 1}</span>
                    <div class="min-w-0">
                        <div class="font-medium truncate">${escHtml(ep.title)}</div>
                        <div class="text-xs text-gray-500">${ep.published_at ? new Date(ep.published_at).toLocaleDateString() : ''}${ep.is_downloaded ? ' · ✅ Downloaded' : ''}</div>
                    </div>
                    <span class="text-xs text-gray-500">${ep.duration_seconds ? formatDuration(ep.duration_seconds) : ''}</span>
                    ${ep.is_downloaded && ep.file_path ? `<button onclick="event.stopPropagation(); playEpisodeInBar('${ep.id}', '${escAttr(ep.title)}')" class="text-green-500 hover:text-green-400 text-sm font-medium">▶</button>` : '<span></span>'}
                </div>
            `).join('');
        }
    } catch (e) {
        const epContainer = document.getElementById('episodes-list');
        if (epContainer) epContainer.innerHTML = '<div class="text-red-400 py-4">Error loading episodes</div>';
    }
}

// ── Media Detail View (inline, not modal) ──────────────────────
function renderMediaDetail(container) {
    const id = currentViewParams.id;
    const item = libraryData.find(i => i.id === id) || currentMediaItem;
    if (!item) {
        // Fetch it
        fetch(`/api/media/${id}`).then(r => r.json()).then(data => {
            if (!data.error) { currentMediaItem = data; renderMediaDetail(container); }
        });
        container.innerHTML = '<div class="text-gray-500 py-12 text-center">Loading...</div>';
        return;
    }
    currentMediaItem = item;
    const mt = item.media_type || 'video';

    let html = `
    <div class="flex gap-6 mb-8 items-end">
        <div class="w-[200px] h-[200px] rounded-lg bg-[#282828] flex items-center justify-center text-5xl overflow-hidden shadow-xl flex-shrink-0">
            ${item.has_poster ? `<img src="/api/poster/${item.id}" class="w-full h-full object-cover">` : typeIcons[mt]}
        </div>
        <div class="flex-1 min-w-0">
            <div class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">${mt}</div>
            <h1 class="text-4xl font-black mb-2">${escHtml(item.title)} ${item.year ? `<span class="font-normal opacity-60">(${item.year})</span>` : ''}</h1>
            ${item.artist ? `<div class="text-sm text-gray-400 cursor-pointer hover:underline" onclick="navigateTo('artist',{name:'${escAttr(item.artist)}'})">${escHtml(item.artist)}</div>` : ''}
            ${item.director ? `<div class="text-sm text-gray-400">Directed by ${escHtml(item.director)}</div>` : ''}
            ${item.rating ? `<div class="text-yellow-400 text-sm mt-1">⭐ ${item.rating}/10</div>` : ''}
            <div class="text-xs text-gray-500 mt-2">${item.size_formatted || ''} ${item.duration_seconds ? ' · ' + formatDurationLong(item.duration_seconds) : ''}</div>
        </div>
    </div>
    <div class="flex items-center gap-3 mb-6">
        <button onclick="playMediaInBar('${item.id}')" class="w-12 h-12 rounded-full bg-green-500 hover:bg-green-400 flex items-center justify-center transition hover:scale-105">
            <svg width="20" height="20" fill="black" viewBox="0 0 16 16"><path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"/></svg>
        </button>
        <button onclick="openEditModal(); currentMediaId='${item.id}'" class="player-btn text-gray-400 hover:text-white" title="Edit"><svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25a1.75 1.75 0 0 1 .445-.758l8.61-8.61zm1.414 1.06a.25.25 0 0 0-.354 0L3.463 11.098a.25.25 0 0 0-.064.108l-.631 2.208 2.208-.63a.25.25 0 0 0 .108-.064l8.609-8.61a.25.25 0 0 0 0-.353l-1.086-1.086-.18.18.18-.18z"/></svg></button>
        <button onclick="addToCollectionFor('${item.id}')" class="player-btn text-gray-400 hover:text-white" title="Add to collection"><svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M15.25 8a.75.75 0 0 1-.75.75H8.75v5.75a.75.75 0 0 1-1.5 0V8.75H1.5a.75.75 0 0 1 0-1.5h5.75V1.5a.75.75 0 0 1 1.5 0v5.75h5.75a.75.75 0 0 1 .75.75z"/></svg></button>
        <button onclick="downloadMediaById('${item.id}')" class="player-btn text-gray-400 hover:text-white" title="Download"><svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M2.5 13.5A.5.5 0 0 1 3 13h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5zM7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg></button>
    </div>`;

    // Metadata details
    if (item.genres && item.genres.length) html += `<div class="flex gap-2 mb-3 flex-wrap">${item.genres.map(g => `<span class="pill pill-inactive text-xs">${escHtml(g)}</span>`).join('')}</div>`;
    if (item.cast && item.cast.length) html += `<div class="text-sm text-gray-400 mb-3"><span class="font-semibold">Cast:</span> ${item.cast.slice(0,8).map(escHtml).join(', ')}</div>`;
    if (item.overview) html += `<p class="text-sm text-gray-300 leading-relaxed mb-4">${escHtml(item.overview)}</p>`;
    if (item.source_url) html += `<p class="text-sm text-gray-500 mb-2">Source: <a href="${escHtml(item.source_url)}" target="_blank" class="text-green-400 hover:underline">${escHtml(item.source_url.substring(0,60))}${item.source_url.length > 60 ? '...' : ''}</a></p>`;

    container.innerHTML = html;
}

// ── Jobs View ──────────────────────────────────────────────────
async function renderJobs(container) {
    try {
        const res = await fetch('/api/jobs');
        const data = await res.json();
        jobsData = data.jobs;
    } catch (e) {}

    let html = `<div class="flex justify-between items-center mb-6">
        <h1 class="section-heading mb-0">Jobs</h1>
        <div class="flex gap-2">
            <button onclick="rescanLibrary()" class="px-4 py-2 bg-[#282828] hover:bg-[#3a3a3a] rounded-lg transition text-sm">🔄 Rescan Library</button>
            <button onclick="showRipForm()" class="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg transition text-sm font-medium">+ Rip a Disc</button>
        </div>
    </div>`;

    if (jobsData.length === 0) {
        html += '<div class="text-center py-12 text-gray-500">No rip jobs yet.</div>';
    } else {
        html += `<div class="bg-[#181818] rounded-xl overflow-hidden">
            <table class="w-full text-left text-sm">
                <thead class="text-xs uppercase text-gray-500 border-b border-[#282828]">
                    <tr><th class="p-3">Title</th><th class="p-3">Status</th><th class="p-3">Progress</th><th class="p-3">Created</th><th class="p-3">Actions</th></tr>
                </thead>
                <tbody>${jobsData.map(job => `
                    <tr class="border-t border-[#282828]/50" id="job-${job.id}">
                        <td class="p-3 font-medium">${escHtml(job.title)}</td>
                        <td class="p-3">${statusBadge(job.status)}</td>
                        <td class="p-3 w-40">
                            ${job.status === 'encoding' ? `<div class="flex items-center gap-2"><div class="flex-1 bg-[#282828] rounded-full h-1.5"><div class="bg-green-500 rounded-full h-1.5 transition-all progress-fill" style="width:${job.progress||0}%"></div></div><span class="text-xs font-mono progress-text">${(job.progress||0).toFixed(1)}%</span></div>` :
                             job.status === 'completed' ? '<span class="text-green-500 text-xs">Done</span>' : '<span class="opacity-30 text-xs">—</span>'}
                        </td>
                        <td class="p-3 text-xs text-gray-500">${job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</td>
                        <td class="p-3">
                            ${['queued','encoding'].includes(job.status) ? `<button onclick="cancelJob('${job.id}')" class="text-red-400 hover:text-red-300 text-xs font-medium">Cancel</button>` : ''}
                            ${['failed','cancelled'].includes(job.status) ? `<button onclick="retryJob('${job.id}')" class="text-green-400 hover:text-green-300 text-xs font-medium">Retry</button>` : ''}
                        </td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }
    container.innerHTML = html;
}

// ── Add Content View ───────────────────────────────────────────
function renderAddContent(container) {
    container.innerHTML = `
        <h1 class="section-heading">Add Content</h1>

        <!-- Upload -->
        <div class="bg-[#181818] rounded-xl p-6 mb-4">
            <h3 class="font-semibold mb-3">📤 Upload Files</h3>
            <div id="drop-zone" class="drop-zone rounded-xl p-10 text-center bg-[#282828]/50 cursor-pointer" onclick="document.getElementById('file-input').click()">
                <div class="text-4xl mb-2">📁</div>
                <p class="font-medium mb-1 text-sm">Drag & drop files here</p>
                <p class="text-xs text-gray-500">or click to browse</p>
                <input id="file-input" type="file" multiple class="hidden" onchange="handleFileSelect(event)">
            </div>
            <div id="upload-progress" class="hidden mt-3">
                <div class="flex items-center gap-3"><div class="flex-1 bg-[#282828] rounded-full h-1.5"><div id="upload-bar" class="bg-green-500 rounded-full h-1.5 transition-all" style="width:0%"></div></div><span id="upload-status" class="text-xs text-gray-400">Uploading...</span></div>
            </div>
        </div>

        <!-- Download Video -->
        <div class="bg-[#181818] rounded-xl p-6 mb-4">
            <h3 class="font-semibold mb-2">🎥 Download Video</h3>
            <p class="text-xs text-gray-500 mb-3">YouTube, Vimeo, or any yt-dlp supported URL</p>
            <div class="flex gap-2"><input id="video-url" placeholder="https://youtube.com/watch?v=..." class="flex-1 p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none"><button onclick="submitVideoDownload()" class="px-5 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-lg transition text-sm font-medium">Download</button></div>
        </div>

        <!-- Archive Article -->
        <div class="bg-[#181818] rounded-xl p-6 mb-4">
            <h3 class="font-semibold mb-2">📰 Archive Article</h3>
            <p class="text-xs text-gray-500 mb-3">Save a web article for permanent offline reading</p>
            <div class="flex gap-2"><input id="article-url" placeholder="https://example.com/article" class="flex-1 p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none"><button onclick="submitArticle()" class="px-5 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-lg transition text-sm font-medium">Archive</button></div>
        </div>

        <!-- Book -->
        <div class="bg-[#181818] rounded-xl p-6 mb-4">
            <h3 class="font-semibold mb-3">📖 Catalogue a Book</h3>
            <div class="grid grid-cols-2 gap-3">
                <input id="book-title" placeholder="Book title *" class="col-span-2 p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none">
                <input id="book-author" placeholder="Author" class="p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none">
                <input id="book-year" placeholder="Year" class="p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none">
                <textarea id="book-desc" placeholder="Description (optional)" rows="2" class="col-span-2 p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm resize-none focus:ring-2 focus:ring-green-500 focus:outline-none"></textarea>
            </div>
            <div class="flex justify-end mt-3"><button onclick="submitBook()" class="px-5 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-lg transition text-sm font-medium">Add Book</button></div>
        </div>

        <!-- Playlist Import -->
        <div class="bg-[#181818] rounded-xl p-6 mb-4">
            <h3 class="font-semibold mb-2">🎵 Import Playlist</h3>
            <p class="text-xs text-gray-500 mb-3">YouTube or Spotify playlist URL</p>
            <div class="flex gap-2"><input id="playlist-url" placeholder="https://open.spotify.com/playlist/..." class="flex-1 p-2.5 rounded-lg bg-[#282828] border-none text-white text-sm focus:ring-2 focus:ring-green-500 focus:outline-none"><button onclick="submitPlaylist()" class="px-5 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-lg transition text-sm font-medium">Import</button></div>
        </div>`;

    // Re-init drop zone
    setTimeout(initDropZone, 50);
}

// ── Render Helpers ─────────────────────────────────────────────
function renderMediaGrid(items) {
    return `<div class="card-grid">${items.map(item => {
        const mt = item.media_type || 'video';
        return `<div class="media-card rounded-lg fade-in" onclick="navigateTo('media',{id:'${item.id}'})">
            <div class="relative w-full aspect-square rounded-md bg-[#282828] flex items-center justify-center text-5xl overflow-hidden mb-3 shadow-lg group">
                ${item.has_poster ? `<img src="/api/poster/${item.id}" alt="${escHtml(item.title)}" class="w-full h-full object-cover" loading="lazy">` : typeIcons[mt]}
                <span class="absolute top-2 right-2 type-badge px-1.5 py-0.5 rounded text-white font-bold uppercase ${typeColors[mt] || 'bg-gray-500'}">${mt}</span>
                <button onclick="event.stopPropagation(); playMediaInBar('${item.id}')" class="absolute bottom-2 right-2 w-10 h-10 rounded-full bg-green-500 text-black flex items-center justify-center opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all shadow-xl hover:scale-105 hover:bg-green-400">
                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"/></svg>
                </button>
            </div>
            <div class="font-medium text-sm truncate">${escHtml(item.title)}</div>
            <div class="text-xs text-gray-400 truncate">${item.year || ''}${item.artist ? ' · ' + escHtml(item.artist) : ''}${item.size_formatted ? ' · ' + item.size_formatted : ''}</div>
        </div>`;
    }).join('')}</div>`;
}

function renderTrackList(items) {
    if (items.length === 0) return '<div class="text-gray-500 py-8 text-center">No tracks</div>';
    let html = `<div class="track-row text-xs text-gray-400 uppercase font-bold border-b border-[#282828] mb-1" style="background:transparent !important">
        <span>#</span><span>Title</span><span class="hidden sm:block">Album</span><span class="hidden md:block">Date added</span><span class="text-right">⏱</span>
    </div>`;
    html += items.map((item, idx) => renderTrackRow(item, idx + 1)).join('');
    return html;
}

function renderTrackRow(item, num, colId) {
    const mt = item.media_type || 'video';
    return `<div class="track-row cursor-pointer" onclick="playMediaInBar('${item.id}')">
        <span>
            <span class="track-num text-gray-500 text-sm">${num}</span>
            <span class="track-play text-white">▶</span>
        </span>
        <div class="flex items-center gap-3 min-w-0">
            <div class="w-10 h-10 rounded bg-[#282828] flex items-center justify-center flex-shrink-0 overflow-hidden text-lg">
                ${item.has_poster ? `<img src="/api/poster/${item.id}" class="w-full h-full object-cover" loading="lazy">` : typeIcons[mt]}
            </div>
            <div class="min-w-0">
                <div class="font-medium truncate text-white text-sm">${escHtml(item.title)}</div>
                <div class="text-xs text-gray-400 truncate">${escHtml(item.artist || item.director || '')}</div>
            </div>
        </div>
        <span class="text-gray-400 truncate text-sm hidden sm:block">${escHtml(item.collection_name || item.album || '')}</span>
        <span class="text-gray-500 text-xs hidden md:block">${item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}</span>
        <span class="text-gray-400 text-sm text-right">${item.duration_seconds ? formatDuration(item.duration_seconds) : ''}</span>
    </div>`;
}

function renderAlbumGrid(albumGroups) {
    const names = Object.keys(albumGroups).filter(n => n);
    if (names.length === 0) return '';
    return `<div class="card-grid">${names.map(name => {
        const items = albumGroups[name];
        const first = items.find(i => i.has_poster) || items[0];
        const artist = items[0]?.artist || '';
        return `<div class="media-card rounded-lg" onclick="navigateTo('album',{name:'${escAttr(name)}'})">
            <div class="w-full aspect-square rounded-md bg-[#282828] flex items-center justify-center text-4xl overflow-hidden mb-3 shadow-lg">
                ${first.has_poster ? `<img src="/api/poster/${first.id}" class="w-full h-full object-cover" loading="lazy">` : '💿'}
            </div>
            <div class="font-medium text-sm truncate">${escHtml(name)}</div>
            <div class="text-xs text-gray-400 truncate">${escHtml(artist)} · ${items.length} track${items.length !== 1 ? 's' : ''}</div>
        </div>`;
    }).join('')}</div>`;
}

function renderArtistGrid(artistGroups) {
    const names = Object.keys(artistGroups).filter(n => n);
    if (names.length === 0) return '';
    return `<div class="card-grid">${names.map(name => {
        const items = artistGroups[name];
        const first = items.find(i => i.has_poster) || items[0];
        return `<div class="media-card rounded-lg" onclick="navigateTo('artist',{name:'${escAttr(name)}'})">
            <div class="w-full aspect-square rounded-full bg-[#282828] flex items-center justify-center text-4xl overflow-hidden mb-3 shadow-lg mx-auto" style="max-width:160px">
                ${first.has_poster ? `<img src="/api/poster/${first.id}" class="w-full h-full object-cover" loading="lazy">` : '🎤'}
            </div>
            <div class="font-medium text-sm truncate text-center">${escHtml(name)}</div>
            <div class="text-xs text-gray-400 text-center">${items.length} track${items.length !== 1 ? 's' : ''}</div>
        </div>`;
    }).join('')}</div>`;
}

function groupBy(items, key) {
    const groups = {};
    items.forEach(i => {
        const val = i[key] || '';
        if (!groups[val]) groups[val] = [];
        groups[val].push(i);
    });
    return groups;
}

function statusBadge(status) {
    const styles = {
        queued: 'bg-yellow-900/40 text-yellow-300', encoding: 'bg-blue-900/40 text-blue-300',
        completed: 'bg-green-900/40 text-green-300', failed: 'bg-red-900/40 text-red-300',
        cancelled: 'bg-gray-700 text-gray-400'
    };
    return `<span class="px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || ''}">${status}</span>`;
}

// ── Sidebar Library ────────────────────────────────────────────
function filterSidebar(filter) {
    sidebarFilter = filter;
    document.querySelectorAll('#lib-pills .pill').forEach(p => {
        p.className = 'pill ' + (p.dataset.libFilter === filter ? 'pill-active' : 'pill-inactive');
    });
    renderSidebarLibrary();
}

function renderSidebarLibrary() {
    const container = document.getElementById('sidebar-library');
    let items = [];

    if (sidebarFilter === 'all' || sidebarFilter === 'albums') {
        // Show collections + albums
        const seen = new Set();
        collectionsData.forEach(c => {
            items.push({ type: 'collection', id: c.id, name: c.name, count: c.items.length, poster: c.items.find(i => i.has_poster), colType: c.collection_type });
            seen.add(c.name);
        });
        if (sidebarFilter === 'all' || sidebarFilter === 'albums') {
            const albums = groupBy(libraryData.filter(i => (i.media_type || 'video') === 'audio' && i.collection_name), 'collection_name');
            Object.entries(albums).forEach(([name, tracks]) => {
                if (!seen.has(name)) {
                    items.push({ type: 'album', name, count: tracks.length, poster: tracks.find(t => t.has_poster) });
                }
            });
        }
    }
    if (sidebarFilter === 'artists') {
        const artists = groupBy(libraryData.filter(i => (i.media_type || 'video') === 'audio' && i.artist), 'artist');
        Object.entries(artists).forEach(([name, tracks]) => {
            items.push({ type: 'artist', name, count: tracks.length, poster: tracks.find(t => t.has_poster) });
        });
    }
    if (sidebarFilter === 'movies') {
        libraryData.filter(i => (i.media_type || 'video') === 'video').forEach(i => {
            items.push({ type: 'media', id: i.id, name: i.title, poster: i.has_poster ? i : null, year: i.year });
        });
    }
    if (sidebarFilter === 'podcasts') {
        podcastsData.forEach(p => {
            items.push({ type: 'podcast', id: p.id, name: p.title || p.feed_url, poster: p.artwork_path ? p : null, author: p.author });
        });
    }

    if (items.length === 0) {
        container.innerHTML = '<div class="text-sm text-gray-500 px-2 py-4">Nothing here yet</div>';
        return;
    }

    container.innerHTML = items.map(item => {
        const posterId = item.poster?.id || item.poster?.id;
        const isRound = item.type === 'artist';
        const icon = item.type === 'collection' ? '📁' : item.type === 'album' ? '💿' : item.type === 'artist' ? '🎤' : item.type === 'podcast' ? '🎙️' : '🎬';
        const subtitle = item.type === 'collection' ? `${item.colType || 'Collection'} · ${item.count} items` :
                         item.type === 'album' ? `Album · ${item.count} tracks` :
                         item.type === 'artist' ? `Artist · ${item.count} tracks` :
                         item.type === 'podcast' ? (item.author || 'Podcast') :
                         item.year || '';
        const onclick = item.type === 'collection' ? `navigateTo('collection',{id:${item.id}})` :
                       item.type === 'album' ? `navigateTo('album',{name:'${escAttr(item.name)}'})` :
                       item.type === 'artist' ? `navigateTo('artist',{name:'${escAttr(item.name)}'})` :
                       item.type === 'podcast' ? `navigateTo('podcast',{id:'${item.id}'})` :
                       `navigateTo('media',{id:'${item.id}'})`;
        return `<div class="lib-item" onclick="${onclick}">
            <div class="w-10 h-10 ${isRound ? 'rounded-full' : 'rounded'} bg-[#282828] flex items-center justify-center overflow-hidden flex-shrink-0 text-lg">
                ${posterId ? `<img src="/api/poster/${posterId}" class="w-full h-full object-cover" loading="lazy">` : icon}
            </div>
            <div class="min-w-0">
                <div class="text-sm font-medium truncate">${escHtml(item.name)}</div>
                <div class="text-xs text-gray-500 truncate">${subtitle}</div>
            </div>
        </div>`;
    }).join('');
}

// ── Bottom Player Bar ──────────────────────────────────────────
function playMediaInBar(id) {
    const item = libraryData.find(i => i.id === id);
    if (!item) {
        // Fetch it
        fetch(`/api/media/${id}`).then(r => r.json()).then(data => {
            if (!data.error) { libraryData.push(data); playMediaInBar(id); }
        });
        return;
    }

    currentMediaId = id;
    currentMediaItem = item;
    const mt = item.media_type || 'video';

    // If it's a video, open in modal instead
    if (mt === 'video') {
        showMediaModal(id);
        return;
    }

    // Audio/document: play in bottom bar
    stopActivePlayer();

    const audio = document.getElementById('modal-audio');
    audio.src = `/api/stream/${id}`;
    audio.volume = isMuted ? 0 : playerVolume;
    activePlayerEl = audio;

    // Update player bar UI
    updatePlayerBarInfo(item);

    // Load saved progress
    fetch(`/api/media/${id}/progress`).then(r => r.json()).then(prog => {
        if (prog && prog.position_seconds > 5 && !prog.finished) {
            audio.addEventListener('loadedmetadata', function onLoad() {
                audio.removeEventListener('loadedmetadata', onLoad);
                audio.currentTime = prog.position_seconds;
                audio.play().catch(() => {});
            });
        } else {
            audio.play().catch(() => {});
        }
    }).catch(() => { audio.play().catch(() => {}); });

    setupBarProgressTracking(audio, id);
}

function playItemsInBar(ids, shuffle) {
    playbackQueue = [...ids];
    if (shuffle) {
        for (let i = playbackQueue.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [playbackQueue[i], playbackQueue[j]] = [playbackQueue[j], playbackQueue[i]];
        }
        isShuffled = true;
        document.getElementById('btn-shuffle')?.classList.add('active-green');
    } else {
        isShuffled = false;
        document.getElementById('btn-shuffle')?.classList.remove('active-green');
    }
    playbackQueueIndex = 0;
    playMediaInBar(playbackQueue[0]);
}

function playCollectionFromBar(colId, shuffle) {
    const col = collectionsData.find(c => c.id === colId);
    if (!col || !col.items.length) return;
    playItemsInBar(col.items.map(i => i.id), shuffle);
}

function showMediaModal(id) {
    // For video playback, use the modal
    fetch(`/api/media/${id}`).then(r => r.json()).then(async item => {
        if (item.error) return;
        currentMediaId = id;
        currentMediaItem = item;

        const video = document.getElementById('modal-video');
        const audio = document.getElementById('modal-audio');
        const mt = item.media_type || 'video';

        let savedProgress = null;
        try { const pRes = await fetch(`/api/media/${id}/progress`); savedProgress = await pRes.json(); } catch (e) {}

        const restartBtn = document.getElementById('btn-restart');

        if (mt === 'video') {
            audio.classList.add('hidden'); audio.src = '';
            video.classList.remove('hidden');
            video.src = `/api/stream/${id}`;
            video.volume = isMuted ? 0 : playerVolume;
            activePlayerEl = video;
            setupBarProgressTracking(video, id);
            updatePlayerBarInfo(item);
            if (savedProgress && savedProgress.position_seconds > 5 && !savedProgress.finished) {
                video.addEventListener('loadedmetadata', function onLoaded() {
                    video.removeEventListener('loadedmetadata', onLoaded);
                    if (confirm(`Continue from ${formatDuration(savedProgress.position_seconds)}?`)) video.currentTime = savedProgress.position_seconds;
                    video.play().catch(() => {});
                });
                restartBtn.classList.remove('hidden');
            } else {
                restartBtn.classList.add('hidden');
            }
        } else {
            video.classList.add('hidden'); video.src = '';
            audio.classList.remove('hidden');
            audio.src = `/api/stream/${id}`;
            audio.volume = isMuted ? 0 : playerVolume;
            activePlayerEl = audio;
            setupBarProgressTracking(audio, id);
            updatePlayerBarInfo(item);
            if (savedProgress && savedProgress.position_seconds > 5 && !savedProgress.finished) {
                audio.addEventListener('loadedmetadata', function onLoaded() {
                    audio.removeEventListener('loadedmetadata', onLoaded);
                    if (confirm(`Continue from ${formatDuration(savedProgress.position_seconds)}?`)) audio.currentTime = savedProgress.position_seconds;
                    audio.play().catch(() => {});
                });
                restartBtn.classList.remove('hidden');
            } else {
                restartBtn.classList.add('hidden');
                audio.play().catch(() => {});
            }
        }

        document.getElementById('modal-info').innerHTML = `
            <h2 class="text-2xl font-bold mb-3">${escHtml(item.title)} ${item.year ? `<span class="font-normal opacity-60">(${item.year})</span>` : ''}</h2>
            ${item.rating ? `<p class="text-yellow-500 mb-3">⭐ ${item.rating}/10</p>` : ''}
            ${item.artist ? `<p class="mb-1"><span class="font-semibold opacity-60">Artist:</span> ${escHtml(item.artist)}</p>` : ''}
            ${item.director ? `<p class="mb-1"><span class="font-semibold opacity-60">Director:</span> ${escHtml(item.director)}</p>` : ''}
            ${item.cast?.length ? `<p class="mb-1"><span class="font-semibold opacity-60">Cast:</span> ${item.cast.slice(0,5).map(escHtml).join(', ')}</p>` : ''}
            ${item.genres?.length ? `<p class="mb-1"><span class="font-semibold opacity-60">Genres:</span> ${item.genres.map(escHtml).join(', ')}</p>` : ''}
            ${item.overview ? `<p class="mt-4 opacity-80 leading-relaxed">${escHtml(item.overview)}</p>` : ''}
            <p class="mt-4 text-sm opacity-40"><span class="uppercase font-semibold">${mt}</span> · ${escHtml(item.filename || '')} · ${item.size_formatted || ''}</p>`;

        document.getElementById('modal').classList.remove('hidden');
    });
}

function updatePlayerBarInfo(item) {
    document.getElementById('player-title').textContent = item.title || 'Unknown';
    document.getElementById('player-artist').textContent = item.artist || item.director || '';
    const artEl = document.getElementById('player-art');
    if (item.has_poster) {
        artEl.innerHTML = `<img src="/api/poster/${item.id}" class="w-full h-full object-cover">`;
    } else {
        artEl.innerHTML = `<span class="text-gray-500 text-2xl">${typeIcons[item.media_type || 'video']}</span>`;
    }
}

function setupBarProgressTracking(playerEl, mediaId) {
    if (progressSaveInterval) clearInterval(progressSaveInterval);

    // Update bottom bar progress
    playerEl.ontimeupdate = () => {
        if (isSeeking) return;
        const dur = playerEl.duration || 0;
        const cur = playerEl.currentTime || 0;
        if (dur > 0) {
            document.getElementById('player-progress-fill').style.width = ((cur / dur) * 100) + '%';
        }
        document.getElementById('player-time-current').textContent = formatDuration(cur);
        document.getElementById('player-time-total').textContent = formatDuration(dur);

        // Play/pause icon
        updatePlayPauseIcon(!playerEl.paused);
    };

    playerEl.onplay = () => updatePlayPauseIcon(true);
    playerEl.onpause = () => {
        updatePlayPauseIcon(false);
        if (playerEl.currentTime > 0) saveProgress(mediaId, playerEl.currentTime, playerEl.duration || 0);
    };

    playerEl.onended = () => {
        saveProgress(mediaId, playerEl.duration, playerEl.duration || 0);
        updatePlayPauseIcon(false);
        if (playbackQueue.length > 1 && playbackQueueIndex < playbackQueue.length - 1) {
            playerNext();
        } else if (isRepeat && playbackQueue.length > 0) {
            playbackQueueIndex = 0;
            playMediaInBar(playbackQueue[0]);
        }
    };

    // Save progress every 10s
    progressSaveInterval = setInterval(() => {
        if (!playerEl.paused && playerEl.currentTime > 0) {
            saveProgress(mediaId, playerEl.currentTime, playerEl.duration || 0);
        }
    }, 10000);
}

function updatePlayPauseIcon(isPlaying) {
    document.getElementById('icon-play').classList.toggle('hidden', isPlaying);
    document.getElementById('icon-pause').classList.toggle('hidden', !isPlaying);
}

function stopActivePlayer() {
    if (progressSaveInterval) { clearInterval(progressSaveInterval); progressSaveInterval = null; }
    const video = document.getElementById('modal-video');
    const audio = document.getElementById('modal-audio');
    if (video) { video.pause(); video.src = ''; }
    if (audio) { audio.pause(); audio.src = ''; }
    activePlayerEl = null;
}

// Player controls
function playerToggle() {
    if (!activePlayerEl) return;
    if (activePlayerEl.paused) activePlayerEl.play().catch(() => {});
    else activePlayerEl.pause();
}

function playerNext() {
    if (playbackQueue.length > 1 && playbackQueueIndex < playbackQueue.length - 1) {
        playbackQueueIndex++;
        playMediaInBar(playbackQueue[playbackQueueIndex]);
    }
}

function playerPrev() {
    if (activePlayerEl && activePlayerEl.currentTime > 3) {
        activePlayerEl.currentTime = 0;
        return;
    }
    if (playbackQueue.length > 1 && playbackQueueIndex > 0) {
        playbackQueueIndex--;
        playMediaInBar(playbackQueue[playbackQueueIndex]);
    }
}

function toggleShuffle() {
    isShuffled = !isShuffled;
    document.getElementById('btn-shuffle').classList.toggle('active-green', isShuffled);
    if (isShuffled && playbackQueue.length > 1) {
        const current = playbackQueue[playbackQueueIndex];
        for (let i = playbackQueue.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [playbackQueue[i], playbackQueue[j]] = [playbackQueue[j], playbackQueue[i]];
        }
        playbackQueueIndex = playbackQueue.indexOf(current);
    }
}

function toggleRepeat() {
    isRepeat = !isRepeat;
    document.getElementById('btn-repeat').classList.toggle('active-green', isRepeat);
}

function seekPlayer(e) {
    if (!activePlayerEl || !activePlayerEl.duration) return;
    const bar = document.getElementById('player-progress');
    const rect = bar.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    activePlayerEl.currentTime = pct * activePlayerEl.duration;
}

function setVolume(e) {
    const bar = document.getElementById('vol-bar');
    const rect = bar.getBoundingClientRect();
    playerVolume = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    isMuted = false;
    if (activePlayerEl) activePlayerEl.volume = playerVolume;
    document.getElementById('vol-fill').style.width = (playerVolume * 100) + '%';
}

function toggleMute() {
    isMuted = !isMuted;
    if (activePlayerEl) activePlayerEl.volume = isMuted ? 0 : playerVolume;
    document.getElementById('vol-fill').style.width = isMuted ? '0%' : (playerVolume * 100) + '%';
}

function toggleQueuePanel() {
    // Show queue in a simple view
    if (playbackQueue.length === 0) return;
    let queueInfo = 'Queue:\n';
    playbackQueue.forEach((id, idx) => {
        const item = libraryData.find(i => i.id === id);
        const marker = idx === playbackQueueIndex ? '► ' : '  ';
        queueInfo += `${marker}${idx + 1}. ${item ? item.title : id}\n`;
    });
    alert(queueInfo);
}

function scrollToNowPlaying() {
    if (currentMediaId) navigateTo('media', { id: currentMediaId });
}

// ── Modal Functions ────────────────────────────────────────────
function closeModal() {
    const video = document.getElementById('modal-video');
    const audio = document.getElementById('modal-audio');
    if (video && !video.classList.contains('hidden') && video.currentTime > 0 && currentMediaId) {
        saveProgress(currentMediaId, video.currentTime, video.duration || 0);
    }
    if (video) { video.pause(); video.src = ''; video.classList.remove('hidden'); }
    if (audio) { audio.classList.add('hidden'); }
    document.getElementById('modal').classList.add('hidden');
    loadLibrary();
}

function restartMedia() {
    if (activePlayerEl) { activePlayerEl.currentTime = 0; activePlayerEl.play().catch(() => {}); }
}

function downloadMedia() {
    if (currentMediaId) window.location.href = `/api/download/${currentMediaId}`;
}

function downloadMediaById(id) {
    window.location.href = `/api/download/${id}`;
}

function deleteMedia() {
    // Not implemented in API yet, but placeholder
    alert('Delete not available yet');
}

// ── Edit Metadata ──────────────────────────────────────────────
async function openEditModal() {
    if (!currentMediaId) return;
    const res = await fetch(`/api/media/${currentMediaId}`);
    const item = await res.json();
    document.getElementById('edit-title').value = item.title || '';
    document.getElementById('edit-year').value = item.year || '';
    document.getElementById('edit-director').value = item.director || '';
    document.getElementById('edit-rating').value = item.rating || '';
    document.getElementById('edit-artist').value = item.artist || '';
    document.getElementById('edit-album').value = item.collection_name || '';
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
        artist: document.getElementById('edit-artist').value,
        collection_name: document.getElementById('edit-album').value,
        genres: document.getElementById('edit-genres').value.split(',').map(s => s.trim()).filter(Boolean),
        cast_members: document.getElementById('edit-cast').value.split(',').map(s => s.trim()).filter(Boolean),
        overview: document.getElementById('edit-overview').value
    };
    await fetch(`/api/media/${currentMediaId}/metadata`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
    });
    closeEditModal();
    loadLibrary();
    if (currentView === 'media') renderView();
}

function closeEditModal() { document.getElementById('edit-modal').classList.add('hidden'); }

// ── Collection Management ──────────────────────────────────────
async function addToCollection() {
    if (!currentMediaId) return;
    await addToCollectionFor(currentMediaId);
}

async function addToCollectionFor(mediaId) {
    const name = prompt('Enter collection name:');
    if (!name?.trim()) return;
    const cleanName = name.trim();

    let existingIds = [];
    try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        const existing = data.collections.find(c => c.name === cleanName);
        if (existing) existingIds = existing.items.map(i => i.id);
    } catch (e) {}

    if (existingIds.includes(mediaId)) { alert('Already in this collection'); return; }
    existingIds.push(mediaId);

    await fetch(`/api/collections/${encodeURIComponent(cleanName)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ media_ids: existingIds })
    });
    alert(`Added to "${cleanName}"`);
    loadCollections();
}

async function deleteCollection(name) {
    if (!confirm(`Delete collection "${name}"?`)) return;
    await fetch(`/api/collections/${encodeURIComponent(name)}`, { method: 'DELETE' });
    loadCollections();
    navigateTo('home');
}

// ── Progress ───────────────────────────────────────────────────
function saveProgress(mediaId, position, duration) {
    fetch(`/api/media/${mediaId}/progress`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position, duration })
    }).catch(() => {});
}

// ── Jobs ───────────────────────────────────────────────────────
async function cancelJob(id) { await fetch(`/api/jobs/${id}`, { method: 'DELETE' }); renderView(); }
async function retryJob(id) { await fetch(`/api/jobs/${id}/retry`, { method: 'POST' }); renderView(); }

function showRipForm() {
    document.getElementById('rip-source').value = '';
    document.getElementById('rip-title').value = '';
    document.getElementById('rip-title-num').value = '1';
    document.getElementById('rip-modal').classList.remove('hidden');
}
function closeRipModal() { document.getElementById('rip-modal').classList.add('hidden'); }

async function submitRipJob() {
    const source = document.getElementById('rip-source').value.trim();
    const title = document.getElementById('rip-title').value.trim();
    const titleNum = parseInt(document.getElementById('rip-title-num').value) || 1;
    if (!source) { alert('Source path is required'); return; }
    await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: source, title: title || undefined, title_number: titleNum }) });
    closeRipModal();
    navigateTo('jobs');
}

async function rescanLibrary() {
    try { await fetch('/api/scan', { method: 'POST' }); loadLibrary(); } catch (e) {}
}

// ── Status Bar ─────────────────────────────────────────────────
function updateStatusBar(data) {
    const bar = document.getElementById('status-bar');
    bar.classList.remove('hidden');
    document.getElementById('status-title').textContent = data.title || 'Encoding...';
    document.getElementById('status-percent').textContent = `${(data.progress||0).toFixed(1)}%`;
    document.getElementById('status-eta').textContent = data.eta ? `ETA: ${data.eta}` : '';
    document.getElementById('status-progress-bar').style.width = `${data.progress||0}%`;
}
function hideStatusBar() { document.getElementById('status-bar').classList.add('hidden'); }

// ── Content Submission ─────────────────────────────────────────
async function submitVideoDownload() {
    const url = document.getElementById('video-url').value.trim();
    if (!url) return alert('Please enter a URL');
    try {
        const res = await fetch('/api/downloads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
        if (res.ok) { document.getElementById('video-url').value = ''; alert('Download queued!'); navigateTo('jobs'); }
        else { const d = await res.json(); alert(d.error || 'Failed'); }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitArticle() {
    const url = document.getElementById('article-url').value.trim();
    if (!url) return alert('Please enter a URL');
    try {
        const res = await fetch('/api/articles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
        if (res.ok) { document.getElementById('article-url').value = ''; alert('Article archiving queued!'); navigateTo('jobs'); }
        else { const d = await res.json(); alert(d.error || 'Failed'); }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitBook() {
    const title = document.getElementById('book-title').value.trim();
    if (!title) return alert('Book title is required');
    try {
        const res = await fetch('/api/books', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, author: document.getElementById('book-author').value.trim() || undefined,
                year: document.getElementById('book-year').value.trim() || undefined,
                description: document.getElementById('book-desc').value.trim() || undefined }) });
        if (res.ok) { ['book-title','book-author','book-year','book-desc'].forEach(id => document.getElementById(id).value = ''); alert('Book added!'); loadLibrary(); }
    } catch (e) { alert('Error: ' + e.message); }
}

async function submitPlaylist() {
    const url = document.getElementById('playlist-url').value.trim();
    if (!url) return alert('Please enter a playlist URL');
    const name = prompt('Name for this playlist:', 'Imported Playlist');
    if (!name) return;
    try {
        const res = await fetch('/api/import/playlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, name }) });
        if (res.ok) { document.getElementById('playlist-url').value = ''; alert('Playlist import queued!'); navigateTo('jobs'); }
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Podcasts ───────────────────────────────────────────────────
function showSubscribeModal() {
    document.getElementById('podcast-feed-url').value = '';
    document.getElementById('podcast-title').value = '';
    document.getElementById('subscribe-modal').classList.remove('hidden');
}
function closeSubscribeModal() { document.getElementById('subscribe-modal').classList.add('hidden'); }

async function submitPodcastSubscription() {
    const feedUrl = document.getElementById('podcast-feed-url').value.trim();
    if (!feedUrl) return alert('Feed URL is required');
    const title = document.getElementById('podcast-title').value.trim();
    try {
        const res = await fetch('/api/podcasts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feed_url: feedUrl, title: title || undefined }) });
        if (res.ok) { closeSubscribeModal(); loadPodcasts(); }
        else { const d = await res.json(); alert(d.error || 'Failed to subscribe'); }
    } catch (e) { alert('Error: ' + e.message); }
}

async function unsubscribePodcast(podId) {
    if (!confirm('Unsubscribe from this podcast?')) return;
    await fetch(`/api/podcasts/${podId}`, { method: 'DELETE' });
    loadPodcasts();
    navigateTo('home');
}

function playEpisodeInBar(epId, title) {
    // TODO: play podcast episode in bottom bar
    alert('Podcast episode playback coming soon!');
}

// ── Upload / Drag-and-Drop ─────────────────────────────────────
function initDropZone() {
    const dz = document.getElementById('drop-zone');
    if (!dz) return;
    ['dragenter','dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('dragover'); }));
    ['dragleave','drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('dragover'); }));
    dz.addEventListener('drop', e => { if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); });
}

function handleFileSelect(e) { if (e.target.files.length) uploadFiles(e.target.files); }

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
        xhr.upload.onprogress = e => { if (e.lengthComputable) { const pct = Math.round((e.loaded/e.total)*100); bar.style.width = pct+'%'; status.textContent = `Uploading... ${pct}%`; } };
        xhr.onload = () => {
            if (xhr.status === 201) { const data = JSON.parse(xhr.responseText); status.textContent = `✅ ${data.uploaded.length} file${data.uploaded.length > 1 ? 's' : ''} uploaded`; bar.style.width = '100%'; loadLibrary(); }
            else status.textContent = '❌ Upload failed';
            setTimeout(() => prog.classList.add('hidden'), 3000);
        };
        xhr.onerror = () => { status.textContent = '❌ Upload failed'; setTimeout(() => prog.classList.add('hidden'), 3000); };
        xhr.send(form);
    } catch (e) { status.textContent = '❌ Upload failed'; setTimeout(() => prog.classList.add('hidden'), 3000); }
}

// ── Data Loading ───────────────────────────────────────────────
async function loadLibrary() {
    try {
        const res = await fetch('/api/library');
        const data = await res.json();
        libraryData = data.items;
        try { const cwRes = await fetch('/api/continue-watching'); const cwData = await cwRes.json(); continueWatchingData = cwData.items || []; } catch (e) { continueWatchingData = []; }
        renderView();
        renderSidebarLibrary();
    } catch (e) {
        console.error('Library load error:', e);
    }
}

async function loadCollections() {
    try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        collectionsData = data.collections;
        renderSidebarLibrary();
    } catch (e) { console.error('Collections load error:', e); }
}

async function loadPodcasts() {
    try {
        const res = await fetch('/api/podcasts');
        const data = await res.json();
        podcastsData = data.podcasts;
        renderSidebarLibrary();
        if (currentView === 'browse' && currentViewParams.type === 'podcast') renderView();
    } catch (e) { console.error('Podcasts load error:', e); }
}

// ── Init ───────────────────────────────────────────────────────
document.documentElement.classList.add('dark'); // Always dark for Spotify look
loadLibrary();
loadCollections();
loadPodcasts();
renderView();
