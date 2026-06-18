// Keyword News Scraper Front-end Application logic

const API_BASE = window.location.origin;

// State Management
const appState = {
  currentTab: 'dashboard-view',
  activeSearchId: null,
  activeSearchPollingId: null,
  searchResults: [], // Store current search crawled URLs
  historyList: [],
  scheduleList: [],
  filters: {
    searchQuery: '',
    status: '',
    excludeDuplicates: true,
    minRelevance: 0,
    page: 1,
    limit: 50,
    sortBy: 'relevance', // 'relevance' or 'occurrences'
    sortDesc: true
  }
};

// Initial Setup on Document Load
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initForms();
  initAccordion();
  initResultsToolbar();
  initHistoryActions();
  initSchedules();
  initModal();
  startLiveClock();
  
  // Load initial dashboard metrics and history
  loadDashboardData();
  checkApiConnection();
});

// 1. Navigation / View Controller
function initNavigation() {
  const menuItems = document.querySelectorAll('.menu-item');
  const viewSections = document.querySelectorAll('.view-section');
  const pageTitle = document.getElementById('page-title-text');
  const pageSubtitle = document.getElementById('page-subtitle-text');

  menuItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      
      // Toggle sidebar button active state
      menuItems.forEach(btn => btn.classList.remove('active'));
      item.classList.add('active');

      // Toggle content section active state
      viewSections.forEach(sec => sec.classList.remove('active'));
      document.getElementById(targetTab).classList.add('active');
      
      appState.currentTab = targetTab;

      // Update header labels
      if (targetTab === 'dashboard-view') {
        pageTitle.innerText = 'Dashboard Overview';
        pageSubtitle.innerText = 'Real-time keyword discovery and content analysis';
        loadDashboardData();
      } else if (targetTab === 'new-crawl-view') {
        pageTitle.innerText = 'Launch Crawl Process';
        pageSubtitle.innerText = 'Search the web or target direct list of websites';
      } else if (targetTab === 'history-view') {
        pageTitle.innerText = 'Execution History Log';
        pageSubtitle.innerText = 'Review past scraping operations and export reports';
        loadHistoryList();
      } else if (targetTab === 'schedules-view') {
        pageTitle.innerText = 'Scheduled Cron Tasks';
        pageSubtitle.innerText = 'Review and manage periodic scraper automation';
        loadScheduleList();
      }
    });
  });

  // Quick Action Dashboard buttons
  document.getElementById('quick-btn-search').addEventListener('click', () => {
    switchTab('tab-mode-search', 'new-crawl-view');
  });
  document.getElementById('quick-btn-direct').addEventListener('click', () => {
    switchTab('tab-mode-direct', 'new-crawl-view');
  });
  document.getElementById('quick-btn-schedule').addEventListener('click', () => {
    switchTab(null, 'schedules-view');
  });
}

function switchTab(modeTabId, viewSectionId) {
  if (viewSectionId) {
    const navBtn = document.querySelector(`.menu-item[data-tab="${viewSectionId}"]`);
    if (navBtn) navBtn.click();
  }
  if (modeTabId) {
    const tabBtn = document.getElementById(modeTabId);
    if (tabBtn) tabBtn.click();
  }
}

// 2. Forms Toggles & Submissions
function initForms() {
  const tabSearch = document.getElementById('tab-mode-search');
  const tabDirect = document.getElementById('tab-mode-direct');
  const groupKeyword = document.getElementById('form-group-keyword');
  const groupDirect = document.getElementById('form-group-direct-urls');
  const crawlForm = document.getElementById('crawl-setup-form');
  
  let sourceMode = 'search'; // 'search' or 'direct'

  const disableKeywordFilterChk = document.getElementById('chk-disable-keyword-filter');
  const groupDisableKeywordFilter = document.getElementById('form-group-disable-keyword-filter');
  const groupDirectKeywords = document.getElementById('form-group-direct-keywords');
  const directKeywordsInput = document.getElementById('direct-keywords-input');

  disableKeywordFilterChk.addEventListener('change', () => {
    if (disableKeywordFilterChk.checked) {
      groupDirectKeywords.classList.add('d-none');
      directKeywordsInput.removeAttribute('required');
      directKeywordsInput.value = '';
    } else {
      groupDirectKeywords.classList.remove('d-none');
      directKeywordsInput.setAttribute('required', 'true');
    }
  });

  tabSearch.addEventListener('click', (e) => {
    e.preventDefault();
    tabSearch.classList.add('active');
    tabDirect.classList.remove('active');
    groupKeyword.classList.remove('d-none');
    groupDirect.classList.add('d-none');
    groupDisableKeywordFilter.classList.add('d-none');
    groupDirectKeywords.classList.add('d-none');
    disableKeywordFilterChk.checked = false;
    document.getElementById('keyword-input').setAttribute('required', 'true');
    directKeywordsInput.removeAttribute('required');
    sourceMode = 'search';
  });

  tabDirect.addEventListener('click', (e) => {
    e.preventDefault();
    tabDirect.classList.add('active');
    tabSearch.classList.remove('active');
    groupDirect.classList.remove('d-none');
    groupDisableKeywordFilter.classList.remove('d-none');
    groupKeyword.classList.add('d-none');
    document.getElementById('keyword-input').removeAttribute('required');
    
    if (disableKeywordFilterChk.checked) {
      groupDirectKeywords.classList.add('d-none');
      directKeywordsInput.removeAttribute('required');
    } else {
      groupDirectKeywords.classList.remove('d-none');
      directKeywordsInput.setAttribute('required', 'true');
    }
    sourceMode = 'direct';
  });

  // Submit Run Setup
  crawlForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitBtn = document.getElementById('btn-submit-crawl');
    const origHtml = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Initializing Crawl...';
    submitBtn.disabled = true;
  
    try {
      const keyword = document.getElementById('keyword-input').value.trim();
      const directUrls = document.getElementById('direct-urls-input').value.trim();
      const directKeywords = directKeywordsInput.value.trim();
      
      let targetKeyword = '';
      if (sourceMode === 'search') {
        targetKeyword = keyword;
      } else {
        targetKeyword = disableKeywordFilterChk.checked ? '' : directKeywords;
      }

      const payload = {
        keyword: targetKeyword,
        match_type: document.querySelector('input[name="match-type"]:checked').value,
        case_sensitive: document.getElementById('chk-case-sensitive').checked,
        exact_match: document.getElementById('chk-exact-match').checked,
        ignore_robots: document.getElementById('chk-ignore-robots').checked,
        engine: document.getElementById('select-crawl-engine').value,
        source_type: sourceMode,
        direct_urls: sourceMode === 'direct' ? directUrls : null
      };

      // Extract domains filters
      const domainsInclude = document.getElementById('domains-include').value.trim();
      const domainsExclude = document.getElementById('domains-exclude').value.trim();
      if (domainsInclude || domainsExclude) {
        payload.domains_filter = {
          include: domainsInclude ? domainsInclude.split(',').map(d => d.trim().toLowerCase()) : [],
          exclude: domainsExclude ? domainsExclude.split(',').map(d => d.trim().toLowerCase()) : []
        };
      }

      // Extract languages
      const languages = document.getElementById('languages-filter-input').value.trim();
      if (languages) {
        payload.languages_filter = languages.split(',').map(l => l.trim().toLowerCase());
      }

      // Extract dates
      const dateStart = document.getElementById('date-start').value;
      const dateEnd = document.getElementById('date-end').value;
      if (dateStart) payload.date_range_start = new Date(dateStart).toISOString();
      if (dateEnd) payload.date_range_end = new Date(dateEnd).toISOString();

      // Submit API call
      const response = await fetch(`${API_BASE}/api/search`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': 'Bearer changeme'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(await response.text() || 'Failed to submit crawl run');
      }

      const queryData = await response.json();
      
      // Clear forms
      crawlForm.reset();
      
      // Start polling results and swap view
      startResultsMonitor(queryData.id);
      
    } catch (err) {
      alert(`Error launching scraper run: ${err.message}`);
    } finally {
      submitBtn.innerHTML = origHtml;
      submitBtn.disabled = false;
    }
  });

  // Schedule setup redirect from New Crawl button
  document.getElementById('btn-schedule-setup').addEventListener('click', () => {
    const keyword = document.getElementById('keyword-input').value.trim();
    if (keyword) {
      document.getElementById('sched-keyword').value = keyword;
    }
    document.getElementById('sched-case-sensitive').checked = document.getElementById('chk-case-sensitive').checked;
    document.getElementById('sched-exact-match').checked = document.getElementById('chk-exact-match').checked;
    document.getElementById('sched-ignore-robots').checked = document.getElementById('chk-ignore-robots').checked;
    switchTab(null, 'schedules-view');
  });
}

// 3. Accordion Handler
function initAccordion() {
  const accordion = document.getElementById('adv-settings-trigger');
  const container = document.querySelector('.accordion-container');
  
  accordion.addEventListener('click', () => {
    container.classList.toggle('open');
  });
}

// 4. Results Toolbar Filters & Exports
function initResultsToolbar() {
  const searchInput = document.getElementById('results-search-input');
  const excludeDupes = document.getElementById('chk-exclude-duplicates');
  const prevBtn = document.getElementById('pagination-prev');
  const nextBtn = document.getElementById('pagination-next');
  
  // Live typing search filter with debounce
  let searchTimeout = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      appState.filters.searchQuery = searchInput.value;
      appState.filters.page = 1;
      renderResultsTable();
    }, 300);
  });

  excludeDupes.addEventListener('change', () => {
    appState.filters.excludeDuplicates = excludeDupes.checked;
    appState.filters.page = 1;
    renderResultsTable();
  });

  const statusFilter = document.getElementById('results-status-filter');
  statusFilter.addEventListener('change', () => {
    appState.filters.status = statusFilter.value;
    appState.filters.page = 1;
    renderResultsTable();
  });

  prevBtn.addEventListener('click', () => {
    if (appState.filters.page > 1) {
      appState.filters.page--;
      renderResultsTable();
    }
  });

  nextBtn.addEventListener('click', () => {
    const totalItems = getFilteredResults().length;
    const maxPage = Math.ceil(totalItems / appState.filters.limit);
    if (appState.filters.page < maxPage) {
      appState.filters.page++;
      renderResultsTable();
    }
  });

  // Table Column Sort Headers
  const sortHeaders = document.querySelectorAll('#results-data-table th.sortable');
  sortHeaders.forEach(header => {
    header.addEventListener('click', () => {
      const field = header.getAttribute('data-sort');
      const icon = header.querySelector('i');
      
      // Update state
      if (appState.filters.sortBy === field) {
        appState.filters.sortDesc = !appState.filters.sortDesc;
      } else {
        appState.filters.sortBy = field;
        appState.filters.sortDesc = true;
      }
      
      // Reset headers icons
      sortHeaders.forEach(h => {
        const hIcon = h.querySelector('i');
        hIcon.className = 'fa-solid fa-sort';
      });
      
      icon.className = appState.filters.sortDesc ? 'fa-solid fa-sort-down' : 'fa-solid fa-sort-up';
      
      renderResultsTable();
    });
  });

  // Export dropdown toggler
  const exportBtn = document.getElementById('btn-export-dropdown');
  exportBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('export-dropdown-content').parentElement.classList.toggle('open');
  });

  document.addEventListener('click', () => {
    document.getElementById('export-dropdown-content').parentElement.classList.remove('open');
  });

  // Export actions trigger download
  const exportOpts = document.querySelectorAll('.export-opt');
  exportOpts.forEach(opt => {
    opt.addEventListener('click', (e) => {
      const format = opt.getAttribute('data-format');
      if (appState.activeSearchId) {
        if (format === 'postgres') {
          exportToPostgres(appState.activeSearchId);
        } else {
          downloadExportFile(appState.activeSearchId, format);
        }
      } else {
        alert('No active results set to export.');
      }
    });
  });
}

// 5. Polling and Real-time Search Monitor
function startResultsMonitor(searchId) {
  // Clear any existing polling loop
  if (appState.activeSearchPollingId) {
    clearInterval(appState.activeSearchPollingId);
  }

  appState.activeSearchId = searchId;
  appState.filters.page = 1;
  
  // Transition View UI
  const detailsTab = document.createElement('button'); // Temp element to simulate tab trigger
  detailsTab.setAttribute('data-tab', 'results-detail-view');
  
  // Show section and style menu links
  document.querySelectorAll('.menu-item').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  document.getElementById('results-detail-view').classList.add('active');
  
  document.getElementById('page-title-text').innerText = 'Scraper Results Monitor';
  document.getElementById('page-subtitle-text').innerText = 'Live-crawling tracking dashboard';

  // Display pending spinner overlay in table on start
  const tbody = document.getElementById('results-table-tbody');
  tbody.innerHTML = `
    <tr>
      <td colspan="7" class="text-center py-5 text-muted">
        <i class="fa-solid fa-spinner fa-spin fa-2x mb-3 color-cyan"></i>
        <p>Awaiting worker thread startup...</p>
      </td>
    </tr>
  `;

  // Start active loop
  pollSearchResults();
  appState.activeSearchPollingId = setInterval(pollSearchResults, 1500);
}

async function pollSearchResults() {
  if (!appState.activeSearchId) return;

  try {
    const response = await fetch(`${API_BASE}/api/results/${appState.activeSearchId}`);
    if (!response.ok) throw new Error('Failed to fetch live crawl results');

    const data = await response.json();
    
    // Update State
    appState.searchResults = data.results.items;
    
    // Update progress banner variables
    const meta = data.search_meta;
    appState.activeSearchKeyword = meta.keyword;
    document.getElementById('progress-keyword-text').innerText = `Scraping: "${meta.keyword}"`;
    document.getElementById('progress-stat-found').innerText = meta.total_urls_found;
    document.getElementById('progress-stat-crawled').innerText = meta.total_urls_crawled;
    document.getElementById('progress-stat-matched').innerText = meta.total_urls_matched;
    document.getElementById('progress-stat-engine').innerText = meta.engine === 'fast' ? 'Fast HTTP' : (meta.engine === 'lightpanda' ? 'Lightpanda JS' : 'Headless Chrome');
    
    // Update badge status
    const badge = document.getElementById('progress-status-badge');
    badge.className = `badge badge-${meta.status}`;
    badge.innerText = meta.status;

    // Update progress banner actions (Abort/Retry)
    const actionsContainer = document.getElementById('progress-actions-container');
    if (actionsContainer) {
      if (meta.status === 'processing' || meta.status === 'pending') {
        actionsContainer.innerHTML = `
          <button class="btn btn-xs btn-outline btn-abort" onclick="abortActiveSearch(${meta.id})" title="Stop this active crawl process">
            <i class="fa-solid fa-ban"></i> Abort
          </button>
        `;
      } else {
        actionsContainer.innerHTML = `
          <button class="btn btn-xs btn-primary btn-retry" onclick="retrySearch(${meta.id})" title="Duplicate run config and search again">
            <i class="fa-solid fa-redo"></i> Retry
          </button>
        `;
      }
    }

    // Calculate percentage
    let percent = 0;
    if (meta.total_urls_found > 0) {
      percent = Math.round((meta.total_urls_crawled / meta.total_urls_found) * 100);
    }
    document.getElementById('progress-percent-label').innerText = `${percent}% Complete`;
    document.getElementById('progress-bar-fill').style.width = `${percent}%`;

    // Toggle pulse animation based on status
    const pulse = document.getElementById('progress-pulse');
    if (meta.status === 'processing' || meta.status === 'pending') {
      pulse.classList.add('pulse-indicator');
    } else {
      pulse.className = '';
      // If completed or failed, stop polling
      clearInterval(appState.activeSearchPollingId);
      appState.activeSearchPollingId = null;
    }

    // Render tables
    renderResultsTable();

    // Reset error count on successful fetch
    appState.pollingErrors = 0;

  } catch (err) {
    console.error('Error polling scraper state:', err);
    appState.pollingErrors = (appState.pollingErrors || 0) + 1;
    if (appState.pollingErrors >= 5) {
      console.warn('Stopping polling after 5 consecutive failures.');
      clearInterval(appState.activeSearchPollingId);
      appState.activeSearchPollingId = null;
    }
  }
}

// 6. Table Renderer with local filters
function getFilteredResults() {
  let list = [...appState.searchResults];
  
  // 1. Text search filter (fuzzy domain/title matches)
  if (appState.filters.searchQuery) {
    const q = appState.filters.searchQuery.toLowerCase();
    list = list.filter(item => 
      (item.title && item.title.toLowerCase().includes(q)) || 
      (item.url && item.url.toLowerCase().includes(q)) ||
      (item.domain && item.domain.toLowerCase().includes(q))
    );
  }

  // 2. Status filter
  if (appState.filters.status) {
    list = list.filter(item => item.status === appState.filters.status);
  }

  // 3. Exclude duplicates
  if (appState.filters.excludeDuplicates) {
    list = list.filter(item => !item.is_duplicate);
  }

  // 4. Sorting logic
  const field = appState.filters.sortBy;
  const desc = appState.filters.sortDesc;
  
  list.sort((a, b) => {
    let valA = a[field === 'relevance' ? 'relevance_score' : 'occurrences'];
    let valB = b[field === 'relevance' ? 'relevance_score' : 'occurrences'];
    
    if (valA < valB) return desc ? 1 : -1;
    if (valA > valB) return desc ? -1 : 1;
    return 0;
  });

  return list;
}

function renderResultsTable() {
  const tbody = document.getElementById('results-table-tbody');
  const filtered = getFilteredResults();
  
  // Pagination boundary calculations
  const limit = appState.filters.limit;
  const totalItems = filtered.length;
  const maxPage = Math.max(1, Math.ceil(totalItems / limit));
  
  if (appState.filters.page > maxPage) {
    appState.filters.page = maxPage;
  }
  
  const page = appState.filters.page;
  const startIdx = (page - 1) * limit;
  const endIdx = Math.min(totalItems, startIdx + limit);
  
  // Update pagination UI buttons/text
  document.getElementById('results-pagination-info').innerText = 
    totalItems > 0 ? `Showing ${startIdx + 1}-${endIdx} of ${totalItems} records` : 'Showing 0-0 of 0 records';
    
  document.getElementById('pagination-current-page').innerText = page;
  document.getElementById('pagination-prev').disabled = page === 1;
  document.getElementById('pagination-next').disabled = page === maxPage;

  if (totalItems === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center py-5 text-muted">
          <i class="fa-solid fa-folder-open fa-2x mb-3 text-muted"></i>
          <p>No matching crawled URLs found.</p>
        </td>
      </tr>
    `;
    return;
  }

  const pageItems = filtered.slice(startIdx, endIdx);
  let rowsHtml = '';
  
  pageItems.forEach((item, idx) => {
    const rank = startIdx + idx + 1;
    
    // Set status badge style class
    let badgeClass = 'badge-skipped';
    if (item.status === 'matched') badgeClass = 'badge-matched';
    else if (item.status === 'failed') badgeClass = 'badge-failed';
    else if (item.status === 'pending') badgeClass = 'badge-pending';
    else if (item.status === 'crawling' || item.status === 'processing') badgeClass = 'badge-crawling';
    if (item.is_duplicate) badgeClass = 'badge-duplicate';

    // Tags list showing match locations
    let tagsHtml = '';
    if (item.found_in_title) tagsHtml += '<span class="loc-tag active">Title</span>';
    if (item.found_in_description) tagsHtml += '<span class="loc-tag active">Desc</span>';
    if (item.found_in_body) tagsHtml += '<span class="loc-tag active">Body</span>';
    if (item.found_in_url) tagsHtml += '<span class="loc-tag active">URL</span>';
    
    if (!tagsHtml && item.status === 'matched') tagsHtml = '<span class="loc-tag active">Matched</span>';
    if (!tagsHtml && item.status !== 'failed') tagsHtml = '<span class="loc-tag">None</span>';

    // Parse highlight content snippets
    let snippetPreview = 'N/A';
    if (item.snippet) {
      // Escape HTML tags in snippet to prevent script injection before highlighting
      let cleanSnippet = escapeHtml(item.snippet);
      // Replace matching search phrases with spans
      const searchTerms = extractHighlightTerms(appState.activeSearchKeyword || item.url);
      
      searchTerms.forEach(term => {
        if (!term || term.length < 2) return;
        const regex = new RegExp(`(${escapeRegExp(term)})`, 'gi');
        cleanSnippet = cleanSnippet.replace(regex, '<span class="highlight">$1</span>');
      });
      snippetPreview = cleanSnippet;
    }

    // Build matched keywords HTML
    let matchedKeywordsHtml = '';
    if (item.matched_keywords) {
      try {
        const kws = JSON.parse(item.matched_keywords);
        if (Array.isArray(kws) && kws.length > 0) {
          matchedKeywordsHtml = '<div class="matched-keywords-tags">' + 
            kws.map(kw => `<span class="kw-tag">${escapeHtml(kw)}</span>`).join('') + 
            '</div>';
        }
      } catch (e) {
        console.error(e);
      }
    }

    let displayStatus = item.status || 'unknown';
    if (item.is_duplicate) displayStatus = 'duplicate';

    rowsHtml += `
      <tr>
        <td class="text-center font-medium color-text-muted">#${rank}</td>
        <td>
          <div class="table-url-cell">
            <span class="table-title" title="${escapeHtml(item.title || 'Untitled')}">${escapeHtml(item.title || 'Untitled')}</span>
            <a href="${item.url}" target="_blank" class="table-url-link" title="${item.url}">
              <i class="fa-solid fa-link"></i> ${item.url}
            </a>
            ${matchedKeywordsHtml}
            ${item.snippet ? `
              <div class="snippet-preview" onclick="openSnippetModal('${item.id}')" title="Click to view full context">
                ${snippetPreview}
              </div>
            ` : ''}
          </div>
        </td>
        <td class="font-medium text-center">${item.occurrences}</td>
        <td class="font-medium text-center color-cyan">${item.relevance_score}/100</td>
        <td>
          <div class="location-tags">
            ${tagsHtml}
          </div>
        </td>
        <td class="text-center">${escapeHtml(item.language || 'N/A').toUpperCase()}</td>
        <td><span class="badge ${badgeClass}">${displayStatus}</span></td>
      </tr>
    `;
  });

  tbody.innerHTML = rowsHtml;
}

// Helper: Escape HTML strings to block injections
function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Simple extractor for search highlight phrases
function extractHighlightTerms(query) {
  if (!query) return [];
  // Find terms in quotes or plain alphabetic terms
  const matches = query.match(/"([^"]+)"|(\b\w+\b)/g) || [];
  return matches
    .map(m => m.replace(/"/g, '').trim())
    .filter(m => m.toUpperCase() !== 'AND' && m.toUpperCase() !== 'OR' && m.toUpperCase() !== 'NOT');
}

// 7. Crawl History View API calls
async function loadHistoryList() {
  const tbody = document.getElementById('history-main-tbody');
  
  try {
    const response = await fetch(`${API_BASE}/api/history`);
    if (!response.ok) throw new Error('Failed to load crawl history log');

    const data = await response.json();
    appState.historyList = data;
    
    if (data.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="10" class="text-center py-5 text-muted">No crawl histories logged yet.</td>
        </tr>
      `;
      return;
    }

    let rows = '';
    data.forEach(item => {
      const execDate = new Date(item.created_at).toLocaleString();
      let badgeClass = `badge-${item.status}`;
      
      let actionBtnHtml = '';
      if (item.status === 'processing' || item.status === 'pending') {
        actionBtnHtml = `<button class="table-act-btn abort-btn" onclick="abortActiveSearch(${item.id})" title="Abort Active Run"><i class="fa-solid fa-ban"></i></button>`;
      } else {
        actionBtnHtml = `<button class="table-act-btn retry-btn" onclick="retrySearch(${item.id})" title="Retry Run"><i class="fa-solid fa-redo"></i></button>`;
      }

      rows += `
        <tr>
          <td>${item.id}</td>
          <td><strong>${escapeHtml(item.keyword)}</strong></td>
          <td><span class="badge badge-skipped">${item.source_type.toUpperCase()}</span></td>
          <td>${item.engine === 'fast' ? 'Fast HTTP' : (item.engine === 'lightpanda' ? 'Lightpanda JS' : 'Headless Chrome')}</td>
          <td>${item.total_urls_found}</td>
          <td>${item.total_urls_crawled}</td>
          <td>${item.total_urls_matched}</td>
          <td><span class="badge ${badgeClass}">${item.status}</span></td>
          <td class="text-muted text-xs">${execDate}</td>
          <td>
            <div class="flex-row-gap">
              <button class="table-act-btn" onclick="startResultsMonitor(${item.id})" title="View Details"><i class="fa-solid fa-circle-info"></i></button>
              ${actionBtnHtml}
              <button class="table-act-btn" onclick="downloadDirectExcel(${item.id})" title="Download Excel"><i class="fa-solid fa-file-excel"></i></button>
              <button class="table-act-btn delete-btn" onclick="deleteHistoryRun(${item.id})" title="Delete Run"><i class="fa-solid fa-trash-can"></i></button>
            </div>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rows;

  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="text-center py-4 text-muted color-red">Failed to query API: ${err.message}</td>
      </tr>
    `;
  }
}

function initHistoryActions() {
  document.getElementById('history-refresh-btn').addEventListener('click', loadHistoryList);
  document.getElementById('btn-refresh-history').addEventListener('click', loadHistoryList);
}

function downloadDirectExcel(searchId) {
  downloadExportFile(searchId, 'xlsx');
}

async function downloadExportFile(searchId, format) {
  try {
    const response = await fetch(`${API_BASE}/api/export/${searchId}?format=${format}`, {
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    if (!response.ok) throw new Error('Download failed');
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = `keyword_results_${searchId}.${format}`;
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/);
      if (match) filename = match[1];
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    alert('Failed to export: ' + err.message);
  }
}

async function exportToPostgres(searchId) {
  const exportBtn = document.getElementById('btn-export-dropdown');
  const origHtml = exportBtn.innerHTML;
  exportBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Connecting...';
  exportBtn.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/api/export/${searchId}/postgres`, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    
    if (!response.ok) {
      const errMsg = await response.text();
      throw new Error(errMsg || 'PostgreSQL database synchronization failed.');
    }
    
    const result = await response.json();
    alert(result.message || 'Successfully synchronized matching results to PostgreSQL!');
  } catch (err) {
    alert('Failed to export to PostgreSQL: ' + err.message);
  } finally {
    exportBtn.innerHTML = origHtml;
    exportBtn.disabled = false;
  }
}

async function deleteHistoryRun(searchId) {
  if (!confirm('Are you sure you want to permanently delete this search history run and all related URLs?')) return;

  try {
    const response = await fetch(`${API_BASE}/api/search/${searchId}`, { 
      method: 'DELETE',
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    if (!response.ok) throw new Error('Delete call failed');

    // Reload list or delete row locally
    loadHistoryList();
    loadDashboardData();
  } catch (err) {
    alert(`Could not delete item: ${err.message}`);
  }
}

async function abortActiveSearch(searchId) {
  if (!confirm('Are you sure you want to stop this active crawl run?')) return;

  try {
    const response = await fetch(`${API_BASE}/api/search/${searchId}/stop`, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    if (!response.ok) throw new Error('Abort request failed');
    
    alert('Stop signal sent to the crawl run successfully.');
    // Poll results immediately to reflect state change
    pollSearchResults();
    loadHistoryList();
    loadDashboardData();
  } catch (err) {
    alert(`Could not abort run: ${err.message}`);
  }
}

async function retrySearch(searchId) {
  try {
    const response = await fetch(`${API_BASE}/api/search/${searchId}/retry`, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    if (!response.ok) throw new Error('Retry request failed');

    const newQuery = await response.json();
    
    // Switch live monitor to the new query ID immediately for a premium, smooth transition
    startResultsMonitor(newQuery.id);
    loadHistoryList();
    loadDashboardData();
  } catch (err) {
    alert(`Could not retry run: ${err.message}`);
  }
}

// Expose functions globally for dynamic HTML onclick hooks
window.abortActiveSearch = abortActiveSearch;
window.retrySearch = retrySearch;
window.startResultsMonitor = startResultsMonitor;
window.deleteHistoryRun = deleteHistoryRun;
window.deleteScheduleJob = deleteScheduleJob;
window.downloadDirectExcel = downloadDirectExcel;
window.openSnippetModal = openSnippetModal;

// 8. Schedules view Actions
async function loadScheduleList() {
  const tbody = document.getElementById('schedules-tbody');
  
  try {
    const response = await fetch(`${API_BASE}/api/schedules`);
    if (!response.ok) throw new Error('Failed to query schedules API');

    const data = await response.json();
    appState.scheduleList = data;
    
    // Update dashboard active schedules metric
    const activeScheds = data.filter(s => s.active).length;
    document.getElementById('stat-active-schedules').innerText = activeScheds;

    if (data.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center py-5 text-muted">No scheduled jobs registered.</td>
        </tr>
      `;
      return;
    }

    let rows = '';
    data.forEach(item => {
      const lastRun = item.last_run ? new Date(item.last_run).toLocaleString() : 'Never';
      const nextRun = new Date(item.next_run).toLocaleString();
      
      rows += `
        <tr>
          <td>${item.id}</td>
          <td><strong>${escapeHtml(item.keyword)}</strong></td>
          <td>${item.engine === 'fast' ? 'Fast HTTP' : (item.engine === 'lightpanda' ? 'Lightpanda JS' : 'Headless Chrome')}</td>
          <td><span class="badge badge-pending">${item.frequency.toUpperCase()}</span></td>
          <td class="text-muted text-xs">${lastRun}</td>
          <td class="text-muted text-xs font-medium color-cyan">${nextRun}</td>
          <td><span class="badge badge-completed">${item.active ? 'Active' : 'Inactive'}</span></td>
          <td>
            <button class="table-act-btn delete-btn" onclick="deleteScheduleJob(${item.id})" title="Delete Schedule"><i class="fa-solid fa-trash-can"></i></button>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rows;

  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-4 text-muted">Failed to query API: ${err.message}</td>
      </tr>
    `;
  }
}

function initSchedules() {
  const form = document.getElementById('schedule-setup-form');
  
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    try {
      const keyword = document.getElementById('sched-keyword').value.trim();
      const frequency = document.getElementById('sched-frequency').value;
      const engine = document.getElementById('sched-engine').value;
      const caseSensitive = document.getElementById('sched-case-sensitive').checked;
      const exactMatch = document.getElementById('sched-exact-match').checked;
      const ignoreRobots = document.getElementById('sched-ignore-robots').checked;

      const payload = {
        keyword: keyword,
        frequency: frequency,
        engine: engine,
        config: {
          keyword: keyword,
          match_type: 'phrase',
          case_sensitive: caseSensitive,
          exact_match: exactMatch,
          ignore_robots: ignoreRobots,
          engine: engine,
          source_type: 'search'
        }
      };

      const response = await fetch(`${API_BASE}/api/schedules`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': 'Bearer changeme'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) throw new Error('Failed to save schedule');

      form.reset();
      loadScheduleList();
      alert('Search schedule configured successfully!');

    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  });
}

async function deleteScheduleJob(schedId) {
  if (!confirm('Are you sure you want to delete this search automation schedule?')) return;

  try {
    const response = await fetch(`${API_BASE}/api/schedules/${schedId}`, { 
      method: 'DELETE',
      headers: {
        'Authorization': 'Bearer changeme'
      }
    });
    if (!response.ok) throw new Error('Delete call failed');

    loadScheduleList();
  } catch (err) {
    alert(`Could not delete schedule: ${err.message}`);
  }
}

// 9. Dashboard Statistics Cards
async function loadDashboardData() {
  try {
    const response = await fetch(`${API_BASE}/api/history`);
    if (!response.ok) throw new Error();

    const data = await response.json();
    
    // Aggregation math
    let totalCrawled = 0;
    let totalMatched = 0;
    let completedRuns = 0;

    data.forEach(item => {
      totalCrawled += item.total_urls_crawled;
      totalMatched += item.total_urls_matched;
      if (item.status === 'completed') {
        completedRuns++;
      }
    });

    document.getElementById('stat-total-crawled').innerText = totalCrawled;
    document.getElementById('stat-total-matched').innerText = totalMatched;
    document.getElementById('stat-completed-runs').innerText = completedRuns;

    // Load recent history in dashboard table (up to 5 items)
    const recent = data.slice(0, 5);
    const tbody = document.getElementById('dashboard-history-tbody');
    
    if (recent.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-4 text-muted">No runs executed yet.</td>
        </tr>
      `;
      return;
    }

    let rows = '';
    recent.forEach(item => {
      let badgeClass = `badge-${item.status}`;
      rows += `
        <tr>
          <td>${item.id}</td>
          <td><strong>${escapeHtml(item.keyword)}</strong></td>
          <td>${item.engine === 'fast' ? 'Fast' : (item.engine === 'lightpanda' ? 'Lightpanda' : 'Dynamic')}</td>
          <td><span class="badge badge-skipped">${item.source_type.toUpperCase()}</span></td>
          <td>${item.total_urls_crawled} / ${item.total_urls_found}</td>
          <td><span class="badge ${badgeClass}">${item.status}</span></td>
          <td>
            <button class="btn btn-xs btn-outline" onclick="startResultsMonitor(${item.id})">Monitor</button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rows;

  } catch (err) {
    console.error('Failed to load dashboard metrics stats');
  }
}

// 10. Snippet Pop-up Modal Actions
function initModal() {
  const modal = document.getElementById('snippet-modal');
  const closeBtn = document.getElementById('modal-close-btn');
  const cancelBtn = document.getElementById('modal-btn-close');

  const closeFn = () => {
    modal.classList.remove('open');
  };

  closeBtn.addEventListener('click', closeFn);
  cancelBtn.addEventListener('click', closeFn);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeFn();
  });
}

function openSnippetModal(urlId) {
  const modal = document.getElementById('snippet-modal');
  const record = appState.searchResults.find(r => r.id == urlId);
  
  if (!record) return;

  document.getElementById('modal-page-title').innerText = record.title || 'Untitled Snippet';
  document.getElementById('modal-url').innerText = record.url;
  document.getElementById('modal-author').innerText = record.author || 'Unknown';

  // Lead image UI element bindings
  const imgContainer = document.getElementById('modal-image-container');
  const imgBox = document.getElementById('modal-image-box');
  const imgLink = document.getElementById('modal-image-link');
  const imgElement = document.getElementById('modal-image');

  if (record.image_url) {
    imgContainer.style.display = 'block';
    imgBox.style.display = 'block';
    imgLink.setAttribute('href', record.image_url);
    imgElement.setAttribute('src', record.image_url);
  } else {
    imgContainer.style.display = 'none';
    imgBox.style.display = 'none';
    imgLink.setAttribute('href', '#');
    imgElement.setAttribute('src', '');
  }
  
  // Highlight keyword in snippet modal body
  const searchTerms = extractHighlightTerms(appState.activeSearchKeyword || record.url);
  
  let cleanSnippet = escapeHtml(record.snippet || 'No snippet context extracted.');
  let cleanDescription = escapeHtml(record.description || 'No description metadata extracted.');
  let cleanFullContent = escapeHtml(record.full_content || 'No scraped body content stored.');

  searchTerms.forEach(term => {
    if (!term || term.length < 2) return;
    const regex = new RegExp(`(${escapeRegExp(term)})`, 'gi');
    cleanSnippet = cleanSnippet.replace(regex, '<span class="highlight">$1</span>');
    cleanDescription = cleanDescription.replace(regex, '<span class="highlight">$1</span>');
    cleanFullContent = cleanFullContent.replace(regex, '<span class="highlight">$1</span>');
  });

  document.getElementById('modal-snippet-content').innerHTML = cleanSnippet;
  document.getElementById('modal-description').innerHTML = cleanDescription;
  document.getElementById('modal-full-content').innerHTML = cleanFullContent;
  
  // Render full images and videos list section
  let mediaHtml = '';
  let imgUrls = [];
  let videoUrls = [];
  
  if (record.image_links) {
    try { imgUrls = JSON.parse(record.image_links); } catch(e) {}
  }
  if (record.video_links) {
    try { videoUrls = JSON.parse(record.video_links); } catch(e) {}
  }
  
  if (imgUrls.length === 0 && videoUrls.length === 0) {
    mediaHtml = '<span class="text-muted text-sm" style="font-style: italic;">No images/videos present</span>';
  } else {
    if (imgUrls.length > 0) {
      mediaHtml += '<div style="margin-bottom: 0.75rem;"><label class="text-xs text-muted font-bold" style="display: block; margin-bottom: 0.25rem;">Images (' + imgUrls.length + ')</label><div style="display: flex; gap: 0.5rem; flex-wrap: wrap; max-height: 100px; overflow-y: auto; padding: 0.25rem 0;">';
      imgUrls.forEach(url => {
        mediaHtml += `<a href="${url}" target="_blank" style="display: block; width: 60px; height: 45px; border-radius: 4px; border: 1px solid var(--border-glass); overflow: hidden; background: rgba(0,0,0,0.35);" title="View image: ${url}"><img src="${url}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.85; transition: opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.85"></a>`;
      });
      mediaHtml += '</div></div>';
    }
    if (videoUrls.length > 0) {
      mediaHtml += '<div><label class="text-xs text-muted font-bold" style="display: block; margin-bottom: 0.25rem;">Videos (' + videoUrls.length + ')</label><div style="display: flex; flex-direction: column; gap: 0.25rem;">';
      videoUrls.forEach(url => {
        mediaHtml += `<a href="${url}" target="_blank" style="font-size: 0.75rem; color: var(--accent-cyan); text-decoration: none; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; display: block; padding: 0.25rem 0.5rem; background: rgba(0,0,0,0.2); border: 1px solid var(--border-glass); border-radius: 4px;" title="Watch video"><i class="fa-solid fa-circle-play"></i> Watch Video: ${url}</a>`;
      });
      mediaHtml += '</div></div>';
    }
  }
  document.getElementById('modal-media-content').innerHTML = mediaHtml;
  
  // Set visit link
  const visitBtn = document.getElementById('modal-btn-visit');
  visitBtn.setAttribute('href', record.url);

  modal.classList.add('open');
}

// 11. Footer Live Clock & API Health check
function startLiveClock() {
  const clock = document.getElementById('live-clock');
  setInterval(() => {
    const time = new Date().toLocaleTimeString();
    clock.innerText = time;
  }, 1000);
}

async function checkApiConnection() {
  const ind = document.getElementById('connection-indicator');
  const text = document.getElementById('connection-status');
  
  const check = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      if (res.ok) {
        ind.className = 'status-indicator online';
        text.innerText = 'API Connected';
      } else {
        throw new Error();
      }
    } catch (err) {
      ind.className = 'status-indicator offline';
      text.innerText = 'API Offline';
    }
  };

  check();
  setInterval(check, 10000); // Check API status health every 10 seconds
}
