// App Client Logic for HR Assist Dashboard
let networkInstance = null; // Vis.js Network instance
let activeCandidate = null; // Stores details of currently selected candidate
let selectedTab = 'mindmap'; // Current tab ('mindmap' or 'aisummary')

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    setupUpload();
    setupTabs();
    setupSplitscreen();
    loadCandidateList();
}

/* 1. Drag and Drop / File Upload */
function setupUpload() {
    const dropzone = document.getElementById('upload-area');
    const fileInput = document.getElementById('resume-file-input');

    if (!dropzone) return;

    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            handleFileUpload(fileInput.files[0]);
        }
    });
}

function handleFileUpload(file) {
    if (!file) return;
    
    // Check file type (PDF, docx, etc.)
    const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!allowedTypes.includes(file.type) && !file.name.endsWith('.pdf') && !file.name.endsWith('.docx')) {
        alert('Please upload a PDF or DOCX file.');
        return;
    }

    showGlobalLoader('Processing Resume with AI...');
    
    const formData = new FormData();
    formData.append('resume', file);

    const csrfToken = getCookie('csrftoken');

    fetch('/api/resume/upload/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        },
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error || 'Server error uploading file') });
        }
        return response.json();
    })
    .then(data => {
        hideGlobalLoader();
        loadCandidateList(data.id); // Reload list and select new candidate
    })
    .catch(error => {
        hideGlobalLoader();
        alert(`Error parsing resume: ${error.message}`);
    });
}

/* 2. Loading Candidate Profile */
function loadCandidateList(selectId = null) {
    const listContainer = document.getElementById('candidate-list');
    if (!listContainer) return;

    fetch('/api/resume/list/')
    .then(res => res.json())
    .then(data => {
        listContainer.innerHTML = '';
        if (data.length === 0) {
            listContainer.innerHTML = '<div class="empty-state-desc" style="padding: 15px; text-align: center; color: var(--text-muted)">No candidates uploaded yet.</div>';
            showEmptyState();
            return;
        }

        data.forEach(candidate => {
            const dateStr = new Date(candidate.uploaded_at).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
            
            const item = document.createElement('div');
            item.className = 'candidate-item';
            item.setAttribute('data-id', candidate.id);
            item.innerHTML = `
                <div class="name">${escapeHtml(candidate.candidate_name || 'Unnamed')}</div>
                <div class="meta">
                    <span>${escapeHtml(candidate.email || 'N/A')}</span>
                    <span>${dateStr}</span>
                </div>
            `;
            
            item.addEventListener('click', () => selectCandidate(candidate.id));
            listContainer.appendChild(item);
        });

        // Auto select first candidate or requested id
        if (selectId) {
            selectCandidate(selectId);
        } else if (data.length > 0) {
            selectCandidate(data[0].id);
        }
    })
    .catch(err => console.error("Error loading candidate list:", err));
}

function selectCandidate(id) {
    // Highlight sidebar active item
    document.querySelectorAll('.candidate-item').forEach(item => {
        if (item.getAttribute('data-id') == id) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    showGlobalLoader('Retrieving candidate details...');

    fetch(`/api/resume/${id}/`)
    .then(res => res.json())
    .then(data => {
        hideGlobalLoader();
        activeCandidate = data;
        renderCandidateProfile();
    })
    .catch(err => {
        hideGlobalLoader();
        console.error("Error retrieving candidate details:", err);
    });
}

function renderCandidateProfile() {
    if (!activeCandidate) return;

    // Remove empty state view
    document.getElementById('empty-state-view').style.display = 'none';
    document.getElementById('active-profile-view').style.display = 'flex';

    // Populate header info
    const nameInitial = activeCandidate.candidate_name ? activeCandidate.candidate_name.charAt(0).toUpperCase() : 'U';
    document.getElementById('candidate-avatar-bubble').innerText = nameInitial;
    document.getElementById('profile-name').innerText = activeCandidate.candidate_name || 'Unknown Candidate';
    
    const emailStr = activeCandidate.email && activeCandidate.email !== 'Unknown' ? activeCandidate.email : 'No email listed';
    const phoneStr = activeCandidate.phone && activeCandidate.phone !== 'Unknown' ? activeCandidate.phone : 'No phone listed';
    
    document.getElementById('profile-contacts').innerHTML = `
        <span><i class="fas fa-envelope"></i> ${escapeHtml(emailStr)}</span>
        <span><i class="fas fa-phone"></i> ${escapeHtml(phoneStr)}</span>
    `;

    // Reset splitscreen right panel if it was open for a different candidate
    closeSplitscreen();

    // Trigger tab rendering
    renderActiveTabContent();
}

/* 3. Tabs Controllers */
function setupTabs() {
    const buttons = document.querySelectorAll('.tab-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetTab = btn.getAttribute('data-tab');
            if (targetTab === selectedTab) return;

            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedTab = targetTab;
            renderActiveTabContent();
        });
    });
}

function renderActiveTabContent() {
    if (!activeCandidate) return;

    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

    if (selectedTab === 'mindmap') {
        document.getElementById('tab-mindmap').classList.add('active');
        setTimeout(() => {
            renderSkillsMindmap();
        }, 100); // Small timeout to ensure container has correct layout size
    } else {
        document.getElementById('tab-aisummary').classList.add('active');
        renderAISummaries();
    }
}

/* 4. Vis.js Mindmap Graph rendering */
function renderSkillsMindmap() {
    const container = document.getElementById('mindmap-container');
    if (!container || !activeCandidate || !activeCandidate.skills_data) return;

    const data = {
        nodes: new vis.DataSet(activeCandidate.skills_data.nodes || []),
        edges: new vis.DataSet(activeCandidate.skills_data.edges || [])
    };

    const options = {
        nodes: {
            shape: 'dot',
            font: {
                color: '#f8fafc',
                size: 14,
                face: 'Outfit'
            },
            borderWidth: 2,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.5)',
                size: 10
            }
        },
        edges: {
            width: 2,
            color: {
                color: 'rgba(255, 255, 255, 0.25)',
                highlight: '#a855f7',
                hover: '#a855f7',
                inherit: 'from'
            },
            smooth: {
                type: 'continuous',
                roundness: 0.5
            }
        },
        physics: {
            stabilization: {
                enabled: true,
                iterations: 150
            },
            barnesHut: {
                gravitationalConstant: -2000,
                centralGravity: 0.1,
                springLength: 95,
                springConstant: 0.04,
                damping: 0.09
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            dragView: true,
            zoomView: true
        }
    };

    if (networkInstance) {
        networkInstance.destroy();
    }

    networkInstance = new vis.Network(container, data, options);

    // Dynamic scale node values
    networkInstance.on("stabilizationIterationsDone", function () {
        networkInstance.setOptions({ physics: { enabled: false } }); // Disable physics after stabilization for smooth manual dragging
    });

    // Add interactivity: Clicking nodes highlights connections
    networkInstance.on("click", function (params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            // Highlight neighbors logic if needed
            // Also, check if it's a category/skill and highlight related items
        }
    });

    // Automatically check github if candidate has repos and add a visual anchor/button
    setupGithubProofTrigger();
}

function setupGithubProofTrigger() {
    const triggerContainer = document.getElementById('github-proof-trigger-container');
    if (!triggerContainer) return;

    if (activeCandidate.github_links && activeCandidate.github_links.length > 0) {
        const linkCount = activeCandidate.github_links.length;
        triggerContainer.innerHTML = `
            <button class="glowing-btn" onclick="openGithubSplitscreen()">
                <i class="fab fa-github"></i> Verify GitHub Project Proofs (${linkCount})
            </button>
        `;
    } else {
        triggerContainer.innerHTML = `
            <div style="font-size: 13px; color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
                <i class="fas fa-exclamation-triangle" style="color: var(--danger)"></i> No GitHub profiles/repos detected in resume.
            </div>
        `;
    }
}

/* 5. AI Summary UI rendering */
function renderAISummaries() {
    const summary = activeCandidate.ai_summary || {};
    
    document.getElementById('summary-text').innerText = summary.summary || "No overview summary provided.";
    
    // Render strengths
    const strengthsList = document.getElementById('strengths-list');
    strengthsList.innerHTML = '';
    const strengths = summary.strengths || [];
    if (strengths.length) {
        strengths.forEach(s => {
            const li = document.createElement('li');
            li.innerText = s;
            strengthsList.appendChild(li);
        });
    } else {
        strengthsList.innerHTML = '<li style="color: var(--text-muted)">No strengths listed.</li>';
    }

    // Render suited roles
    const rolesList = document.getElementById('roles-list');
    rolesList.innerHTML = '';
    const roles = summary.suited_roles || [];
    if (roles.length) {
        roles.forEach(r => {
            const li = document.createElement('li');
            li.innerText = r;
            rolesList.appendChild(li);
        });
    } else {
        rolesList.innerHTML = '<li style="color: var(--text-muted)">No specific roles matched.</li>';
    }

    // Render areas for development (red flags)
    const redFlagsList = document.getElementById('redflags-list');
    redFlagsList.innerHTML = '';
    const redFlags = summary.red_flags || [];
    if (redFlags.length) {
        redFlags.forEach(f => {
            const li = document.createElement('li');
            li.innerText = f;
            redFlagsList.appendChild(li);
        });
    } else {
        redFlagsList.innerHTML = '<li style="color: var(--text-muted)">No issues detected.</li>';
    }
}

/* 6. Split-Screen GitHub Verification Panel */
function setupSplitscreen() {
    const closeBtn = document.getElementById('close-github-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeSplitscreen);
    }
}

function openGithubSplitscreen() {
    const panel = document.getElementById('main-dashboard-content');
    if (!panel) return;

    panel.classList.add('splitscreen-active');
    
    // Load GitHub links list inside the right panel
    const linksContainer = document.getElementById('github-links-list');
    linksContainer.innerHTML = '';

    const repos = activeCandidate.github_links || [];
    repos.forEach((link, idx) => {
        const option = document.createElement('div');
        option.className = `repo-option ${idx === 0 ? 'active' : ''}`;
        option.innerHTML = `
            <div class="repo-option-left">
                <span class="repo-status-dot valid"></span>
                <span class="repo-name">${escapeHtml(truncateUrl(link))}</span>
            </div>
            <i class="fas fa-chevron-right" style="font-size: 11px; color: var(--text-muted)"></i>
        `;
        option.addEventListener('click', () => {
            document.querySelectorAll('.repo-option').forEach(opt => opt.classList.remove('active'));
            option.classList.add('active');
            verifyAndLoadRepo(link);
        });
        linksContainer.appendChild(option);
    });

    // Auto-load first repository
    if (repos.length > 0) {
        verifyAndLoadRepo(repos[0]);
    } else {
        renderEmptyRepoDetails("No repos found.");
    }
}

function verifyAndLoadRepo(url) {
    const detailsContainer = document.getElementById('github-repo-details');
    detailsContainer.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
            <i class="fas fa-circle-notch fa-spin" style="font-size: 30px; margin-bottom: 12px; color: var(--accent-indigo)"></i>
            <p style="font-size: 13px;">Querying GitHub API and parsing code proof...</p>
        </div>
    `;

    fetch(`/api/github/check/?url=${encodeURIComponent(url)}`)
    .then(res => res.json())
    .then(data => {
        if (!data.is_valid) {
            renderInvalidRepo(url, data.message);
            return;
        }

        if (data.is_profile_only) {
            renderProfileOnlyDetails(data);
        } else {
            renderRepoProofDetails(data);
        }
    })
    .catch(err => {
        console.error("Error checking github link:", err);
        renderInvalidRepo(url, "Network connection error while validating URL.");
    });
}

function renderRepoProofDetails(data) {
    const detailsContainer = document.getElementById('github-repo-details');
    
    // Parse language bar details
    const totalLangBytes = Object.values(data.languages || {}).reduce((a, b) => a + b, 0);
    let langBarHtml = '';
    let langListHtml = '';
    
    const colors = ['#f1e05a', '#563d7c', '#e34c26', '#3572A5', '#b07219', '#244776'];
    let idx = 0;
    
    if (totalLangBytes > 0) {
        for (const [lang, bytes] of Object.entries(data.languages)) {
            const pct = ((bytes / totalLangBytes) * 100).toFixed(1);
            const color = colors[idx % colors.length];
            
            langBarHtml += `<div class="lang-bar" style="width: ${pct}%; background-color: ${color}"></div>`;
            langListHtml += `
                <span class="lang-list-item">
                    <span class="lang-color-dot" style="background-color: ${color}"></span>
                    ${escapeHtml(lang)} (${pct}%)
                </span>
            `;
            idx++;
        }
    } else {
        langBarHtml = `<div class="lang-bar" style="width: 100%; background-color: var(--text-muted)"></div>`;
        langListHtml = `<span class="lang-list-item">No language metadata available</span>`;
    }

    // Process markdown README
    let readmeHtml = "No README files provided.";
    if (window.marked && data.readme) {
        try {
            readmeHtml = marked.parse(data.readme);
        } catch (e) {
            readmeHtml = escapeHtml(data.readme);
        }
    } else if (data.readme) {
        readmeHtml = `<pre>${escapeHtml(data.readme)}</pre>`;
    }

    detailsContainer.innerHTML = `
        <div class="proof-card">
            <div class="proof-card-header">
                <img class="owner-avatar" src="${data.avatar_url || 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png'}" alt="Avatar">
                <div class="proof-card-title">
                    <h3>${escapeHtml(data.owner)} / ${escapeHtml(data.repo)}</h3>
                    <p><i class="fas fa-check-circle" style="color: var(--success)"></i> Verified Public Repository Proof</p>
                </div>
            </div>
            
            <p class="repo-desc">${escapeHtml(data.description || 'No repository description set.')}</p>
            
            <div class="repo-stats">
                <span class="stat-item"><i class="fas fa-star"></i> ${data.stars} Stars</span>
                <span class="stat-item"><i class="fas fa-code-branch"></i> ${data.forks} Forks</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: 8px;">
                <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Language Breakdown</span>
                <div class="lang-distribution">
                    ${langBarHtml}
                </div>
                <div class="lang-list">
                    ${langListHtml}
                </div>
            </div>
        </div>

        <div class="readme-container">
            <div class="readme-title"><i class="fas fa-book-open"></i> Project README (Interactive Proof)</div>
            <div class="readme-content">
                ${readmeHtml}
            </div>
        </div>
    `;
}

function renderProfileOnlyDetails(data) {
    const detailsContainer = document.getElementById('github-repo-details');
    detailsContainer.innerHTML = `
        <div class="proof-card">
            <div class="proof-card-header">
                <img class="owner-avatar" src="${data.avatar_url}" alt="Avatar">
                <div class="proof-card-title">
                    <h3>${escapeHtml(data.name || data.owner)}</h3>
                    <p><i class="fab fa-github"></i> Verified User Profile Link</p>
                </div>
            </div>
            <p class="repo-desc">${escapeHtml(data.bio || 'No profile bio provided.')}</p>
            <div class="repo-stats" style="margin-top: 10px;">
                <span class="stat-item"><i class="fas fa-folder"></i> ${data.public_repos} Repositories</span>
                <span class="stat-item"><i class="fas fa-users"></i> ${data.followers} Followers</span>
            </div>
        </div>
        <div style="padding: 20px; border-radius: 12px; border: 1px dashed var(--glass-border); text-align: center; color: var(--text-secondary); font-size: 12px;">
            <i class="fas fa-info-circle" style="color: var(--accent-indigo); margin-bottom: 8px; font-size: 16px; display: block;"></i>
            This URL links directly to the candidate's general GitHub profile rather than a specific project repository.
        </div>
    `;
}

function renderInvalidRepo(url, message) {
    const detailsContainer = document.getElementById('github-repo-details');
    detailsContainer.innerHTML = `
        <div class="proof-card" style="border-color: rgba(239, 68, 68, 0.3); background: rgba(239, 68, 68, 0.03);">
            <div class="proof-card-header">
                <span style="width: 40px; height: 40px; border-radius: 50%; background: rgba(239, 68, 68, 0.1); display: flex; align-items: center; justify-content: center; color: var(--danger);">
                    <i class="fas fa-times-circle" style="font-size: 20px"></i>
                </span>
                <div class="proof-card-title">
                    <h3 style="color: var(--danger)">Verification Failed</h3>
                    <p style="color: var(--text-secondary)">Link: ${escapeHtml(truncateUrl(url))}</p>
                </div>
            </div>
            <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.4;">
                <strong>Error Details:</strong> ${escapeHtml(message)}
            </p>
            <div style="margin-top: 8px; font-size: 11px; color: var(--text-muted)">
                Verify if the repository is private or if the spelling of the URL in the resume is correct.
            </div>
        </div>
    `;
}

function renderEmptyRepoDetails(msg) {
    const detailsContainer = document.getElementById('github-repo-details');
    detailsContainer.innerHTML = `<div class="empty-state-desc" style="text-align: center">${msg}</div>`;
}

function closeSplitscreen() {
    const panel = document.getElementById('main-dashboard-content');
    if (panel) {
        panel.classList.remove('splitscreen-active');
    }
}

/* 7. Global UI Loaders & States */
function showGlobalLoader(text = 'Processing...') {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.querySelector('.loader-text').innerText = text;
        loader.style.display = 'flex';
    }
}

function hideGlobalLoader() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.style.display = 'none';
    }
}

function showEmptyState() {
    document.getElementById('empty-state-view').style.display = 'flex';
    document.getElementById('active-profile-view').style.display = 'none';
}

/* Utilities */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function truncateUrl(url) {
    if (!url) return '';
    return url.replace(/^https?:\/\/(www\.)?/, '');
}
