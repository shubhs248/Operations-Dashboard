/* Platform Operations Dashboard — Frontend Logic */
(function () {
  'use strict';

  var API = '';
  var _charts = {};
  var _tabInited = {};

  /* ── Global Filter State (Jira, Grafana, Overview) ── */
  var _periodDays = 30;
  var _customFrom = null;
  var _customTo = null;

  /* ── MCP-specific filter (OCP logs: 1-3 days) ── */
  var _mcpPeriodDays = 1;

  function _getFilterQS() {
    if (_customFrom && _customTo) return '?from=' + _customFrom + '&to=' + _customTo;
    return '?days=' + _periodDays;
  }
  function _getMcpFilterQS() {
    return '?days=' + _mcpPeriodDays;
  }
  function _getFilterDays() { return _periodDays; }

  /* ── Chart.js defaults ── */
  function _css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function _chartColors() {
    return {
      chartTT: { backgroundColor: _css('--bg-tertiary') || '#1e2433', titleColor: _css('--text-primary') || '#f0f4f8', bodyColor: _css('--text-secondary') || '#c4cdd8', borderColor: _css('--border-color') || 'rgba(255,255,255,0.08)', borderWidth: 1 },
      chartLeg: { color: _css('--text-secondary') || '#c4cdd8', font: { family: "'Inter'", size: 12 }, usePointStyle: true, pointStyleWidth: 10, padding: 12 },
      gridLine: { color: _css('--chart-grid') || 'rgba(255,255,255,0.06)' },
      tickColor: { color: _css('--chart-tick') || '#9ba8be' }
    };
  }
  var _cc = _chartColors();
  var chartTT = _cc.chartTT;
  var chartLeg = _cc.chartLeg;
  var gridLine = _cc.gridLine;
  var tickColor = _cc.tickColor;
  var PAL = ['#38bdf8', '#818cf8', '#2dd4bf', '#fb923c', '#f472b6', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#06b6d4'];

  var TOOL_COLORS = {
    nexus:       { bg: '#38bdf8', text: '#06101f', soft: 'rgba(56,189,248,.12)' },
    jenkins:     { bg: '#fb923c', text: '#fff', soft: 'rgba(251,146,60,.12)' },
    ocp:         { bg: '#f87171', text: '#fff', soft: 'rgba(248,113,113,.12)' },
    bitbucket:   { bg: '#06b6d4', text: '#fff', soft: 'rgba(6,182,212,.12)' },
    eaas:        { bg: '#a78bfa', text: '#fff', soft: 'rgba(167,139,250,.12)' },
    artifactory: { bg: '#34d399', text: '#fff', soft: 'rgba(52,211,153,.12)' },
    _default:    { bg: '#64748b', text: '#fff', soft: 'rgba(100,116,139,.12)' }
  };

  function _toolColor(name) {
    if (!name) return TOOL_COLORS._default;
    var key = name.toLowerCase();
    return TOOL_COLORS[key] || TOOL_COLORS._default;
  }

  var _funcToolMap = {};

  var _STATIC_FUNC_TOOL = {
    get_username:'jenkins',jenkins_build_log_snapshot:'jenkins',jenkins_build_multibranch_job:'jenkins',
    jenkins_builds:'jenkins',jenkins_connect:'jenkins',jenkins_debug_headers:'jenkins',
    jenkins_get_multibranch_job_info:'jenkins',jenkins_jobs:'jenkins',jenkins_list_branches:'jenkins',
    jenkins_nodes:'jenkins',jenkins_queue:'jenkins',jenkins_views:'jenkins',list_jenkins_servers:'jenkins',
    check_filesystem_space:'nexus',create_task:'nexus',get_repository_info:'nexus',
    get_system_status:'nexus',invalidate_cache:'nexus',list_repositories:'nexus',
    manage_session:'nexus',manage_task:'nexus',rebuild_index:'nexus',search_artifacts:'nexus',
    trace_proxy_chain:'nexus',update_task:'nexus',
    audit_user_security:'bitbucket',compare_refs:'bitbucket',detect_code_antipatterns:'bitbucket',
    detect_dependency_changes:'bitbucket',find_large_files:'bitbucket',get_commit_details:'bitbucket',
    get_content_of_file:'bitbucket',get_mirror_status:'bitbucket',get_project_overview:'bitbucket',
    get_repository_id:'bitbucket',get_user_profile:'bitbucket',health_check:'bitbucket',
    lint_commit_messages:'bitbucket',manage_branches:'bitbucket',manage_pull_requests:'bitbucket',
    manage_repos:'bitbucket',manage_webhooks:'bitbucket',pr_analytics:'bitbucket',
    scan_pr_secrets:'bitbucket',search_bitbucket:'bitbucket',search_users:'bitbucket',
    create_pull_request:'bitbucket',get_branches:'bitbucket',get_commits:'bitbucket',
    get_content_of_file_bulk:'bitbucket',get_diff:'bitbucket',get_project:'bitbucket',
    get_project_id:'bitbucket',get_projects:'bitbucket',get_pull_request_activities:'bitbucket',
    get_pull_request_by_id:'bitbucket',get_pull_request_changes:'bitbucket',
    get_pull_requests:'bitbucket',get_repo:'bitbucket',get_repos:'bitbucket',
    artifactory_aql_query:'artifactory',artifactory_cleanup_policy:'artifactory',
    artifactory_delete:'artifactory',artifactory_federated_sync:'artifactory',
    artifactory_get:'artifactory',artifactory_logs:'artifactory',
    artifactory_rb_duplicates:'artifactory',artifactory_search:'artifactory',
    artifactory_worker_manage:'artifactory',
    delete_namespace:'ocp',get_adm_top_nodes_utilization:'ocp',get_adm_top_pods_utilization:'ocp',
    get_cert_ed_ver:'ocp',get_cluster_daily_grades:'ocp',get_cluster_information:'ocp',
    get_cpu_ram_requests_limits_per_namespace:'ocp',get_cpu_ram_requests_limits_per_pod:'ocp',
    get_current_cluster_state:'ocp',get_ed_version:'ocp',get_esxi:'ocp',
    get_helm_charts_ms360_details:'ocp',get_mcp_state:'ocp',get_nodes:'ocp',
    get_not_running_pods:'ocp',get_ocp_ceritification_details:'ocp',get_operators_state:'ocp',
    get_physical_cpu_utilization:'ocp',get_physical_memory_utilization:'ocp',
    get_user_ldap_groups:'ocp',oc_list_clusters:'ocp',oc_login:'ocp',oc_logout:'ocp',oc_run:'ocp',
    add_sudo_permissions:'eaas',check_vapp_expiration:'eaas',check_vm_connectivity:'eaas',
    check_vm_rh_registration:'eaas',consolidate_template_disks:'eaas',consolidate_vm_disks:'eaas',
    copy_catalog_templates:'eaas',create_catalog:'eaas',create_catalog_item_from_vapp:'eaas',
    create_vapp_from_template:'eaas',delete_catalog:'eaas',delete_template_from_catalog:'eaas',
    delete_vapp:'eaas',exit_maintenance_mode_vapp:'eaas',find_vapp_by_ip:'eaas',
    get_all_organizations:'eaas',get_catalogs:'eaas',get_external_ips_from_vapps:'eaas',
    get_local_templates:'eaas',get_org:'eaas',get_org_resources:'eaas',
    get_subscription_catalogs:'eaas',get_vapps:'eaas',get_vm_filesystem_utilization:'eaas',
    get_vm_logs_and_diagnostics:'eaas',get_vm_performance_metrics:'eaas',
    increase_vm_filesystem:'eaas',list_dr_templates:'eaas',modify_cpu_for_vm:'eaas',
    modify_memory_for_vm:'eaas',power_off_vapp:'eaas',power_on_vapp:'eaas',
    register_vm_to_satellite:'eaas',reset_vapp_lease:'eaas'
  };

  function _funcToTool(name, contextTool) {
    if (!name) return contextTool || '';
    var n = String(name).toLowerCase();
    if (_funcToolMap[n]) return _funcToolMap[n];
    if (_funcToolMap[name]) return _funcToolMap[name];
    if (_STATIC_FUNC_TOOL[n]) return _STATIC_FUNC_TOOL[n];
    if (_STATIC_FUNC_TOOL[name]) return _STATIC_FUNC_TOOL[name];
    if (n === 'tool_call') return contextTool || '';
    return contextTool || '';
  }

  function _toolBadgeHtml(name) {
    if (!name) return '';
    var c = _toolColor(name);
    return '<span style="display:inline-block;font-size:11px;font-weight:700;padding:3px 10px;border-radius:5px;' +
      'background:' + c.bg + ';color:' + c.text + ';vertical-align:middle;margin-left:6px;letter-spacing:.3px">' +
      esc(name.toUpperCase()) + '</span>';
  }

  /* ── Utilities ── */
  function esc(s) { if (!s) return ''; var d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
  function showToast(msg, type) {
    var t = document.getElementById('toast'); t.textContent = msg; t.className = 'toast show ' + (type || '');
    clearTimeout(t._timer); t._timer = setTimeout(function () { t.classList.remove('show'); }, 3500);
  }
  function fmtNum(n) { if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'; if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'; return String(n); }
  function fmtCpu(m) { if (m == null) return '--'; return (m / 1000).toFixed(2); }
  function fmtCpuLimit(m) { if (m == null) return '?'; return (m / 1000).toFixed(1); }
  function fmtMem(mib) { if (mib == null) return '--'; return (mib / 1024).toFixed(2); }
  function fmtMemLimit(mib) { if (mib == null) return '?'; return (mib / 1024).toFixed(1); }
  var TZ = 'Asia/Jerusalem';
  function fmtDate(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleDateString('en-IL', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' }) + ', ' +
      d.toLocaleTimeString('en-IL', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
  }

  /* ── Global Period / Date Range Controls ── */
  window.setGlobalPeriod = function (days) {
    _periodDays = days;
    _customFrom = null;
    _customTo = null;
    document.querySelectorAll('.period-btn:not(.mcp-period-btn)').forEach(function (b) {
      b.classList.toggle('active', parseInt(b.getAttribute('data-period')) === days);
    });
    _clearApiCache();
    _tabInited = {};
    var active = document.querySelector('.tab-btn.active');
    var tab = active ? active.getAttribute('data-tab') : 'overview';
    switchTab(tab);
  };

  window.resetMcpDailyZoom = function () {
    if (_charts.chartMcpDaily) {
      _charts.chartMcpDaily.resetZoom();
      var btn = document.getElementById('resetZoomBtn');
      if (btn) btn.style.display = 'none';
    }
  };

  window.setMcpPeriod = function (days) {
    _mcpPeriodDays = days;
    document.querySelectorAll('.mcp-period-btn').forEach(function (b) {
      b.classList.toggle('active', parseInt(b.getAttribute('data-mcp-period')) === days);
    });
    _clearApiCache();
    _tabInited['mcpusage'] = false;
    _tabInited['mcp'] = false;
    _tabInited['overview'] = false;
    var active = document.querySelector('.tab-btn.active');
    var tab = active ? active.getAttribute('data-tab') : 'mcpusage';
    _tabInited[tab] = true;
    initTab(tab);
  };

  window.applyGlobalDateRange = function () {
    var from = document.getElementById('globalDateFrom').value;
    var to = document.getElementById('globalDateTo').value;
    if (!from || !to) { showToast('Select both From and To dates', 'error'); return; }
    if (from > to) { showToast('From date must be before To date', 'error'); return; }
    document.querySelectorAll('.period-btn:not(.mcp-period-btn)').forEach(function (b) { b.classList.remove('active'); });
    _customFrom = from;
    _customTo = to;
    _periodDays = Math.ceil((new Date(to) - new Date(from)) / 86400000);
    _reloadCurrentTab();
  };

  function _reloadCurrentTab() {
    _clearApiCache();
    _tabInited = {};
    var active = document.querySelector('.tab-btn.active');
    if (active) switchTab(active.getAttribute('data-tab'));
  }

  /* ── Tab switching ── */
  var _TAB_META = {
    overview:   ['Overview', 'Platform status at a glance'],
    mcp:        ['Fleet Health', 'Pod status across MCP deployments'],
    mcpusage:   ['Tool Adoption', 'MCP usage parsed from pod logs'],
    grafana:    ['Grafana Adoption', 'Non-admin login activity'],
    chatops:    ['ChatOps Assistant', 'Assistant adoption & activity'],
    jira:       ['Support · Platform Tools', 'DEVOPS tickets'],
    'jira-eaas':['Support · Environment-as-a-Service', 'EAAS & CLOUD tickets']
  };

  window.toggleSidebar = function () {
    var app = document.getElementById('app');
    var bd = document.getElementById('navBackdrop');
    if (!app) return;
    var open = app.classList.toggle('nav-open');
    if (bd) bd.classList.toggle('show', open);
  };

  window.switchTab = function (tabId) {
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === tabId); });
    document.querySelectorAll('.tab-pane').forEach(function (p) { p.classList.remove('active'); });
    var pane = document.getElementById('pane-' + tabId);
    if (pane) pane.classList.add('active');

    var meta = _TAB_META[tabId];
    if (meta) {
      var tEl = document.getElementById('tbTitle');
      var sEl = document.getElementById('tbSub');
      if (tEl) tEl.textContent = meta[0];
      if (sEl) sEl.textContent = meta[1];
    }
    var app = document.getElementById('app');
    if (app && app.classList.contains('nav-open')) {
      app.classList.remove('nav-open');
      var bd = document.getElementById('navBackdrop');
      if (bd) bd.classList.remove('show');
    }
    var gf = document.getElementById('globalFilterBar');
    if (!gf) gf = document.querySelector('.global-filter-bar:not(#grafanaFilterBar)');
    if (gf) gf.style.display = (tabId === 'mcpusage' || tabId === 'mcp' || tabId === 'overview' || tabId === 'chatops' || tabId === 'grafana') ? 'none' : '';
    if (!_tabInited[tabId]) { _tabInited[tabId] = true; initTab(tabId); }
  };

  function initTab(t) {
    if (t === 'overview') loadOverview();
    else if (t === 'mcp') loadMcp();
    else if (t === 'mcpusage') loadMcpUsage();
    else if (t === 'jira') loadJira();
    else if (t === 'jira-eaas') { _initEaasProjectFilter(); loadJiraEaas(); }
    else if (t === 'chatops') loadChatops();
    else if (t === 'grafana') loadGrafana();
  }

  /* ── API helpers with client-side cache ── */
  var _apiCache = {};
  var _apiCacheTTL = 120000;

  function api(path, skipCache) {
    var now = Date.now();
    if (!skipCache && _apiCache[path] && _apiCache[path].exp > now) {
      return Promise.resolve(_apiCache[path].data);
    }
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 20000);
    return fetch(API + path, { signal: controller.signal })
      .then(function (r) { clearTimeout(timer); return r.json(); })
      .then(function (data) {
        _apiCache[path] = { data: data, exp: now + _apiCacheTTL };
        return data;
      }).catch(function (e) {
        clearTimeout(timer);
        console.error('API error:', path, e);
        return null;
      });
  }

  function _clearApiCache() {
    _apiCache = {};
  }

  /* ── CSV Export ── */
  function _downloadCSV(filename, rows) {
    var csv = rows.map(function (row) {
      return row.map(function (cell) {
        var s = String(cell == null ? '' : cell);
        if (s.indexOf(',') > -1 || s.indexOf('"') > -1 || s.indexOf('\n') > -1) {
          return '"' + s.replace(/"/g, '""') + '"';
        }
        return s;
      }).join(',');
    }).join('\n');
    var blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    showToast('Exported: ' + filename, 'success');
  }

  window.exportCurrentTab = function () {
    var active = document.querySelector('.tab-btn.active');
    if (!active) return;
    var tab = active.getAttribute('data-tab');
    if (tab === 'jira') _exportJira();
    else if (tab === 'grafana') _exportGrafana();
    else if (tab === 'mcp') _exportMcp();
    else if (tab === 'mcpusage') _exportMcpUsage();
    else if (tab === 'overview') _exportOverview();
  };

  function _exportJira() {
    var qs = _getFilterQS();
    Promise.all([api('/api/jira/issues' + qs), api('/api/jira/by-tool' + qs)])
      .then(function (res) {
        var issues = (res[0] || {}).issues || [];
        var byTool = (res[1] || {}).by_tool || [];

        var rows = [['=== JIRA ISSUES (Individual Tickets) ===']];
        rows.push(['Key', 'URL', 'Summary', 'Type', 'Priority', 'Status', 'Assignee', 'Tool/Component', 'Created', 'Labels']);
        issues.forEach(function (i) {
          rows.push([i.key, i.url, i.summary, i.type, i.priority, i.status, i.assignee, i.tool, i.created, i.labels]);
        });

        rows.push([]);
        rows.push(['=== SUMMARY BY TOOL ===']);
        rows.push(['Tool', 'Issue Count']);
        byTool.forEach(function (t) { rows.push([t.tool, t.count]); });

        rows.push([]);
        rows.push(['Total Issues', issues.length]);
        rows.push(['Period', _customFrom && _customTo ? _customFrom + ' to ' + _customTo : 'Last ' + _periodDays + ' days']);

        _downloadCSV('jira_issues_export.csv', rows);
      });
  }

  function _exportGrafana() {
    var rows = [['Login', 'Name', 'Email', 'Last Seen', 'Days Ago', 'Status', 'Auth']];
    var users = _getFilteredGrafanaUsers();
    users.forEach(function (u) {
      rows.push([u.login, u.name, u.email, u.lastSeenAt || 'Never', u.days_ago != null ? u.days_ago : 'Never', u.status, (u.authLabels || []).join('; ')]);
    });
    _downloadCSV('grafana_user_logins.csv', rows);
  }

  function _exportMcp() {
    api('/api/mcp/status').then(function (data) {
      if (!data) return;
      var servers = data.servers || [];
      var rows = [['Tool', 'Pod', 'Namespace', 'Health', 'Ready', 'Restarts', 'Age', 'CPU (cores)', 'Memory (GB)', 'Mem Limit (GB)', 'Mem %', 'Tool Calls']];
      servers.forEach(function (sv) {
        rows.push([sv.tool, sv.name, sv.namespace, sv.health || sv.status, sv.ready, sv.restarts, sv.age, fmtCpu(sv.cpu_millicores), fmtMem(sv.memory_mib), fmtMemLimit(sv.memory_limit), sv.memory_pct || '', sv.request_count]);
      });
      _downloadCSV('mcp_pod_health_export.csv', rows);
    });
  }

  function _exportOverview() {
    var mcpQs = _getMcpFilterQS();
    var qs = _getFilterQS();
    Promise.all([api('/api/mcp-stats/summary' + mcpQs), api('/api/mcp-stats/applications' + mcpQs), api('/api/mcp-stats/users' + mcpQs), api('/api/grafana/users'), api('/api/jira/open' + qs), api('/api/mcp/metrics')])
      .then(function (res) {
        var mcpStats = res[0] || {};
        var mcpApps = (res[1] || {}).applications || [];
        var mcpUsers = (res[2] || {}).users || [];
        var grafana = res[3] || {};
        var jira = (res[4] || {}).open_summary || {};
        var mcp = res[5] || {};
        var humanUsers = mcpUsers.filter(function (u) { return !_isServiceAccount(u.username); });

        var rows = [['=== EXECUTIVE SUMMARY ===']];
        rows.push(['Metric', 'Value']);
        rows.push(['Platform MCPs Active', mcpApps.length || mcpStats.unique_applications || 0]);
        rows.push(['Platform MCP Tool Calls', mcpStats.total_tool_calls || 0]);
        rows.push(['Platform MCP Active Users', humanUsers.length]);
        rows.push(['BU Users Registered (Grafana)', (grafana.users || []).length]);
        rows.push(['BU Users Active (7d)', (grafana.summary || {}).active_7d || 0]);
        rows.push(['Jira Total Issues', jira.total_issues || 0]);
        rows.push(['Jira Open Issues', jira.open || 0]);
        rows.push(['Jira Resolved', jira.resolved || 0]);
        rows.push([]);
        rows.push(['=== POD HEALTH ===']);
        rows.push(['Total Pods', mcp.total_pods || 0]);
        rows.push(['Healthy', mcp.healthy_pods || 0]);
        rows.push(['Warning', mcp.warning_pods || 0]);
        rows.push(['Critical', mcp.critical_pods || 0]);
        rows.push(['Total Restarts', mcp.total_restarts || 0]);
        rows.push(['CPU (cores)', fmtCpu(mcp.total_cpu_millicores)]);
        rows.push(['Memory (GB)', fmtMem(mcp.total_memory_mib)]);
        rows.push([]);
        rows.push(['=== Platform MCP BREAKDOWN ===']);
        rows.push(['Tool', 'Tool Calls']);
        mcpApps.forEach(function (a) {
          rows.push([a.name, a.count]);
        });
        _downloadCSV('executive_summary_export.csv', rows);
      });
  }

  /* ── OVERVIEW TAB ── */
  function loadOverview() {
    var mcpQs = _getMcpFilterQS();
    var globalQs = _getFilterQS();
    Promise.all([
      api('/api/mcp-stats/summary' + mcpQs),
      api('/api/mcp-stats/applications' + mcpQs),
      api('/api/mcp-stats/users' + mcpQs),
      api('/api/mcp-stats/functions' + mcpQs),
      api('/api/jira/open' + globalQs),
      api('/api/grafana/users'),
      api('/api/mcp/status' + mcpQs)
    ]).then(function (res) {
        var mcpStats = res[0] || {};
        var mcpApps = (res[1] || {}).applications || [];
        var mcpUsers = (res[2] || {}).users || [];
        var mcpFuncs = (res[3] || {}).functions || [];
        var jira = (res[4] || {}).open_summary || {};
        var grafana = res[5] || {};
        var mcpStatus = res[6] || {};
        var mcp = mcpStatus.summary || {};

        if (mcp.total_pods && !mcp.healthy_pods && mcp.healthy_pods !== 0) {
          var svs = mcpStatus.servers || [];
          mcp.healthy_pods = svs.filter(function (s) { return s.health === 'healthy' || (s.status === 'up' && s.ready); }).length;
          mcp.warning_pods = svs.filter(function (s) { return s.health === 'warning'; }).length;
          mcp.critical_pods = svs.filter(function (s) { return s.health === 'critical' || s.status !== 'up'; }).length;
          mcp.total_restarts = svs.reduce(function (a, s) { return a + (s.restarts || 0); }, 0);
        }

        var humanUsers = mcpUsers.filter(function (u) { return !_isServiceAccount(u.username); });
        var namedFuncs = mcpFuncs.filter(function (f) { return f.name !== 'tool_call'; });

        var grafanaUsers = grafana.users || [];
        var grafanaSummary = grafana.summary || {};
        var activeUsers = grafanaSummary.active_7d || 0;
        var periodLabel = _mcpPeriodDays + 'D';

        var healthDelta = '';
        if (mcp.total_pods) {
          healthDelta = (mcp.healthy_pods || 0) + ' healthy';
          if (mcp.warning_pods) healthDelta += ' / ' + mcp.warning_pods + ' warn';
          if (mcp.critical_pods) healthDelta += ' / ' + mcp.critical_pods + ' crit';
        }

        var cards = document.getElementById('overviewCards');
        cards.innerHTML =
          _statCard('\uD83D\uDD27', mcpApps.length || mcpStats.unique_applications || 0, 'Platform MCPs Active', fmtNum(mcpStats.total_tool_calls || 0) + ' tool calls (' + periodLabel + ')', 'var(--accent-primary)') +
          _statCard('\uD83D\uDC64', humanUsers.length, 'MCP Active Users (' + periodLabel + ')', namedFuncs.length + ' named functions', 'var(--accent-orange)') +
          _statCard('\uD83D\uDC65', grafanaUsers.length, 'BU Users Registered', activeUsers + ' logged in (7d)', 'var(--accent-secondary)') +
          _statCard('\uD83D\uDCCB', jira.total_issues || 0, 'Support Issues', (jira.open || 0) + ' open / ' + (jira.resolved || 0) + ' resolved', 'var(--accent-teal)') +
          _statCard('\uD83D\uDCE6', mcp.total_pods || 0, 'MCP Pod Health', healthDelta, mcp.critical_pods ? 'var(--status-red)' : mcp.warning_pods ? 'var(--status-yellow)' : 'var(--status-green)');

        _renderOverviewHighlights(mcpApps, grafanaSummary, jira, mcp, namedFuncs);
      });
  }

  function _renderOverviewHighlights(mcpApps, grafanaSummary, jira, mcp, namedFuncs) {
    var wrap = document.getElementById('overviewHighlights');
    var items = [];

    if (mcpApps.length) {
      items.push({ icon: '\uD83D\uDD27', label: 'Platform MCP (' + _mcpPeriodDays + 'D)', values: mcpApps.map(function (a) { return a.name + ' (' + fmtNum(a.count) + ' calls)'; }) });
    }

    if (namedFuncs && namedFuncs.length) {
      items.push({ icon: '\u2699\uFE0F', label: 'Top Functions', values: namedFuncs.slice(0, 5).map(function (f) { return f.name + ' (' + fmtNum(f.count) + ' calls)'; }) });
    }

    items.push({ icon: '\uD83D\uDC65', label: 'Grafana Active Users', values: [
      (grafanaSummary.active_7d || 0) + ' active in last 7 days',
      (grafanaSummary.active_30d || 0) + ' active in last 30 days',
      (grafanaSummary.inactive || 0) + ' inactive (30d+)'
    ]});

    items.push({ icon: '\uD83D\uDCCB', label: 'Jira Issue Status', values: [
      (jira.open || 0) + ' currently open',
      (jira.resolved || 0) + ' resolved',
      'Types: ' + Object.keys(jira.by_type || {}).map(function (k) { return k + ' (' + jira.by_type[k] + ')'; }).join(', ')
    ]});

    if (mcp.total_pods) {
      var infraValues = [
        (mcp.healthy_pods || 0) + ' of ' + mcp.total_pods + ' pods healthy',
        (mcp.tools_active || 0) + ' MCPs active',
        (mcp.total_restarts || 0) + ' total restarts across fleet'
      ];
      if (mcp.total_memory_mib) infraValues.push('Cluster footprint: ' + fmtCpu(mcp.total_cpu_millicores) + ' cores CPU, ' + fmtMem(mcp.total_memory_mib) + ' GB memory');
      if (mcp.warning_pods) infraValues.push(mcp.warning_pods + ' pod(s) in warning state');
      if (mcp.critical_pods) infraValues.push(mcp.critical_pods + ' pod(s) in critical state');
      items.push({ icon: '\uD83D\uDCE6', label: 'MCP Infrastructure Health', values: infraValues });
    }

    var html = '';
    items.forEach(function (item) {
      html += '<div class="hl-card">' +
        '<div class="hl-icon">' + item.icon + '</div>' +
        '<div class="hl-content">' +
        '<div class="hl-label">' + esc(item.label) + '</div>' +
        '<ul class="hl-list">';
      item.values.forEach(function (v) {
        html += '<li title="' + esc(v) + '">' + esc(v) + '</li>';
      });
      html += '</ul></div></div>';
    });
    wrap.innerHTML = html;
  }

  function _statCard(icon, value, label, delta, color) {
    return '<div class="stat-card"><div class="sc-icon">' + icon + '</div>' +
      '<div class="sc-value" style="color:' + (color || 'inherit') + '">' + value + '</div>' +
      '<div class="sc-label">' + esc(label) + '</div>' +
      (delta ? '<div class="sc-delta">' + esc(delta) + '</div>' : '') + '</div>';
  }


  /* ── MCP TAB ── */
  var _HEALTH_COLORS = { healthy: '#34d399', warning: '#fbbf24', critical: '#f87171' };

  var _mcpPodRetryCount = 0;
  var _mcpPodRetryMax = 6;
  var _mcpPodRetryTimer = null;

  function loadMcp() {
    api('/api/mcp/status' + _getMcpFilterQS()).then(function (data) {
      if (!data) {
        document.getElementById('mcpServers').innerHTML = '<div class="empty-state"><div class="es-icon">&#x23F3;</div><div class="es-title">Loading pod data&hellip;</div><div class="es-text">OCP collection in progress — will auto-refresh shortly</div></div>';
        _renderMcpCards({});
        _scheduleMcpRetry();
        return;
      }
      var servers = data.servers || [];
      var summary = data.summary || {};
      if (!servers.length && _mcpPodRetryCount < _mcpPodRetryMax) {
        document.getElementById('mcpServers').innerHTML = '<div class="empty-state"><div class="es-icon">&#x23F3;</div><div class="es-title">Collecting pod health&hellip;</div><div class="es-text">Background OCP scan in progress — retrying in a few seconds (' + (_mcpPodRetryCount + 1) + '/' + _mcpPodRetryMax + ')</div></div>';
        _renderMcpCards(summary);
        _scheduleMcpRetry();
        return;
      }
      _mcpPodRetryCount = 0;
      _renderMcpCards(summary);
      _renderServerGrid(servers);
      _renderMcpCharts(servers, summary);
    });
  }

  function _scheduleMcpRetry() {
    if (_mcpPodRetryTimer) clearTimeout(_mcpPodRetryTimer);
    _mcpPodRetryCount++;
    _mcpPodRetryTimer = setTimeout(function () { loadMcp(); }, 8000);
  }

  function _renderMcpCards(s) {
    var resDelta = s.total_cpu_millicores ? fmtCpu(s.total_cpu_millicores) + ' cores · ' + fmtMem(s.total_memory_mib) + ' GB' : '';
    document.getElementById('mcpCards').innerHTML =
      _statCard('\u2705', s.healthy_pods || 0, 'Healthy', '', 'var(--status-green)') +
      _statCard('\u26A0\uFE0F', s.warning_pods || 0, 'Warning', '', 'var(--status-yellow)') +
      _statCard('\u274C', s.critical_pods || 0, 'Critical', '', 'var(--status-red)') +
      _statCard('\uD83D\uDCE6', s.total_pods || 0, 'Total Pods', resDelta, 'var(--accent-primary)') +
      _statCard('\uD83D\uDD27', s.tools_active || 0, 'MCPs Active', '', 'var(--accent-teal)') +
      _statCard('\u26A1', fmtNum(s.total_tool_calls || 0), 'Tool Calls', '', 'var(--accent-orange)');
  }

  function _usageBar(used, limit, unit, color, fmtUsed, fmtLim) {
    if (used == null) return '<span style="color:var(--text-muted);font-size:11px">\u2014</span>';
    var pct = limit ? Math.min(Math.round(used / limit * 100), 100) : 0;
    var barColor = pct > 90 ? 'var(--status-red)' : pct > 70 ? 'var(--status-yellow)' : (color || 'var(--accent-primary)');
    var usedStr = fmtUsed ? fmtUsed(used) : String(used);
    var limStr = fmtLim ? fmtLim(limit) : String(limit);
    var detail = usedStr + (unit || '') + (limit ? ' / ' + limStr + (unit || '') : '');
    var pctLabel = limit ? '<b>' + pct + '%</b>' : '';
    return '<div style="display:flex;align-items:center;gap:6px;width:100%">' +
      '<div style="flex:1;height:6px;background:var(--border-color);border-radius:3px;overflow:hidden">' +
      '<div style="height:100%;width:' + pct + '%;background:' + barColor + ';border-radius:3px"></div></div>' +
      '<span style="font-size:10px;color:var(--text-muted);white-space:nowrap">' + pctLabel +
      ' <span style="opacity:.8">' + detail + '</span></span></div>';
  }

  function _renderServerGrid(servers) {
    var wrap = document.getElementById('mcpServers');
    if (!servers.length) {
      wrap.innerHTML = '<div class="empty-state"><div class="es-icon">\uD83D\uDCE6</div><div class="es-title">No MCP pods found</div><div class="es-text">Check OCP_TOKEN and OCP_MCP_TOOLS in .env</div></div>';
      return;
    }
    var toolMap = {};
    servers.forEach(function (sv) {
      var t = sv.tool || 'unknown';
      if (!toolMap[t]) toolMap[t] = { pods: [], totalRestarts: 0, allReady: true, request_count: 0, health: 'healthy', totalCpu: 0, totalMem: 0, hasMetrics: false };
      toolMap[t].pods.push(sv);
      toolMap[t].totalRestarts += sv.restarts || 0;
      if (sv.cpu_millicores || sv.memory_mib) toolMap[t].hasMetrics = true;
      toolMap[t].totalCpu += sv.cpu_millicores || 0;
      toolMap[t].totalMem += sv.memory_mib || 0;
      if (!sv.ready) toolMap[t].allReady = false;
      if (sv.health === 'critical') toolMap[t].health = 'critical';
      else if (sv.health === 'warning' && toolMap[t].health !== 'critical') toolMap[t].health = 'warning';
      toolMap[t].request_count = sv.request_count || toolMap[t].request_count;
    });
    var html = '';
    Object.keys(toolMap).forEach(function (tool) {
      var g = toolMap[tool];
      var h = g.health;
      var hColor = _HEALTH_COLORS[h] || _HEALTH_COLORS.healthy;
      var hLabel = h.toUpperCase();
      var toolLabel = tool.charAt(0).toUpperCase() + tool.slice(1);
      var maxAgeH = 0;
      var oldestAge = '';
      g.pods.forEach(function (p) {
        if (p.age && (!oldestAge || p.age > oldestAge)) oldestAge = p.age;
        if (p.age_hours && p.age_hours > maxAgeH) maxAgeH = p.age_hours;
      });
      var avgRestarts = g.pods.length ? g.totalRestarts / g.pods.length : 0;
      var ratePerDay = maxAgeH > 0 ? avgRestarts / (maxAgeH / 24) : 0;
      var restartWarn = ratePerDay > 4 ? ' style="color:var(--status-red);font-weight:700"' : ratePerDay > 2 ? ' style="color:var(--accent-orange);font-weight:700"' : '';

      var avgCpu = g.hasMetrics && g.pods.length ? Math.round(g.totalCpu / g.pods.length) : null;
      var avgMem = g.hasMetrics && g.pods.length ? Math.round(g.totalMem / g.pods.length) : null;
      var memLimit = null;
      var cpuLimit = null;
      g.pods.forEach(function (p) {
        if (p.memory_limit && !memLimit) memLimit = p.memory_limit;
        if (p.cpu_limit && !cpuLimit) cpuLimit = p.cpu_limit;
      });

      html += '<div class="server-card">' +
        '<div class="sv-hdr">' +
        '<span class="sv-name">' + esc(toolLabel) + '</span>' +
        '<span style="font-size:11px;font-weight:700;padding:2px 10px;border-radius:4px;color:#fff;background:' + hColor + '">' + hLabel + '</span>' +
        '</div>' +
        '<div style="font-size:11px;color:var(--text-muted);margin:-4px 0 10px">' + g.pods.length + ' pod' + (g.pods.length > 1 ? 's' : '') + '</div>' +
        '<div class="sv-metrics">' +
        '<div class="sv-metric"><div class="svm-val">' + (g.allReady ? '\u2705' : '\u274C') + '</div><div class="svm-lbl">Ready</div></div>' +
        '<div class="sv-metric"><div class="svm-val"' + restartWarn + '>' + g.totalRestarts + '</div><div class="svm-lbl">Restarts' + (g.totalRestarts ? ' (~' + ratePerDay.toFixed(1) + '/d)' : '') + '</div></div>' +
        '<div class="sv-metric"><div class="svm-val">' + esc(oldestAge || '\u2014') + '</div><div class="svm-lbl">Age</div></div>' +
        '<div class="sv-metric"><div class="svm-val">' + fmtNum(g.request_count || 0) + '</div><div class="svm-lbl">Tool Calls</div></div>' +
        '</div>' +
        '<div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">' +
        '<div style="display:flex;align-items:center;gap:6px"><span style="font-size:10px;font-weight:600;color:var(--text-secondary);min-width:28px">CPU</span>' + _usageBar(avgCpu, cpuLimit, ' cores', null, fmtCpu, fmtCpuLimit) + '</div>' +
        '<div style="display:flex;align-items:center;gap:6px"><span style="font-size:10px;font-weight:600;color:var(--text-secondary);min-width:28px">MEM</span>' + _usageBar(avgMem, memLimit, ' GB', null, fmtMem, fmtMemLimit) + '</div>' +
        '</div></div>';
    });
    wrap.innerHTML = html;
  }

  function _renderMcpCharts(servers, summary) {
    var titleEl = document.getElementById('mcpToolChartTitle');
    if (titleEl) titleEl.textContent = 'Tool Calls by MCP';

    var toolData = {};
    servers.forEach(function (sv) {
      var t = sv.tool || 'unknown';
      if (!toolData[t]) toolData[t] = { req: 0, pods: 0, mem: 0, memLimit: 0, reqSet: false };
      if (!toolData[t].reqSet) { toolData[t].req = sv.request_count || 0; toolData[t].reqSet = true; }
      toolData[t].mem += sv.memory_mib || 0;
      toolData[t].memLimit += sv.memory_limit || 0;
      toolData[t].pods += 1;
    });
    var names = Object.keys(toolData);
    var reqs = names.map(function (n) { return toolData[n].req; });
    var mems = names.map(function (n) { return toolData[n].mem; });
    var memLimits = names.map(function (n) { return toolData[n].memLimit; });
    var memPcts = names.map(function (n) {
      var d = toolData[n];
      return d.memLimit ? Math.round(d.mem / d.memLimit * 100) : 0;
    });
    var labels = names.map(function (n) { return n.charAt(0).toUpperCase() + n.slice(1); });

    _destroyChart('chartMcpTools');
    _charts.chartMcpTools = new Chart(document.getElementById('chartMcpTools'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: 'Tool Calls', data: reqs, backgroundColor: names.map(function (n) { return _toolColor(n).bg; }), borderRadius: 4 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false }, tooltip: chartTT },
        scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 12, weight: 600 } }) } }
      }
    });

    var hData = [summary.healthy_pods || 0, summary.warning_pods || 0, summary.critical_pods || 0];
    var hLabels = ['Healthy', 'Warning', 'Critical'];
    var hColors = [_HEALTH_COLORS.healthy, _HEALTH_COLORS.warning, _HEALTH_COLORS.critical];

    _destroyChart('chartMcpStatus');
    _charts.chartMcpStatus = new Chart(document.getElementById('chartMcpStatus'), {
      type: 'doughnut',
      data: { labels: hLabels, datasets: [{ data: hData, backgroundColor: hColors, borderWidth: 0, hoverOffset: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'right', labels: chartLeg }, tooltip: chartTT } }
    });

    _destroyChart('chartMcpMemory');
    var memColors = names.map(function (n, i) {
      var p = memPcts[i];
      return p > 90 ? 'var(--status-red)' : p > 70 ? 'var(--status-yellow)' : _toolColor(n).bg;
    });
    _charts.chartMcpMemory = new Chart(document.getElementById('chartMcpMemory'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: 'Memory %', data: memPcts, backgroundColor: memColors, borderRadius: 4, _memMib: mems, _memLimit: memLimits }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#e2e8f0', bodyColor: '#cbd5e1',
            borderColor: 'rgba(167,139,250,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8,
            callbacks: {
              label: function (ctx) {
                var ds = ctx.dataset;
                var idx = ctx.dataIndex;
                var pct = ctx.parsed.x;
                var used = ds._memMib ? fmtMem(ds._memMib[idx]) : '?';
                var lim = ds._memLimit ? fmtMemLimit(ds._memLimit[idx]) : '?';
                return pct + '% (' + used + ' / ' + lim + ' GB)';
              }
            }
          }
        },
        scales: {
          x: { grid: gridLine, ticks: Object.assign({}, tickColor, { callback: function (v) { return v + '%'; } }), max: 100 },
          y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 12, weight: 600 } }) }
        }
      }
    });
  }

  /* ── MCP USAGE TAB ── */
  var _mcpUsageUsers = [];
  var _mcpToolFilter = '';

  window.filterMcpByTool = function () {
    _mcpToolFilter = document.getElementById('mcpToolFilter').value;
    _resetToolSectionUI();
    _loadMcpToolSection(true);
  };

  function _resetToolSectionUI() {
    var badge = '';
    var els = ['toolDiveBadge', 'topUsersBadge', 'userActivityBadge'];
    els.forEach(function (id) { var e = document.getElementById(id); if (e) e.innerHTML = badge; });
    var sub = document.getElementById('toolDiveSubtitle');
    if (sub) sub.textContent = 'Loading\u2026';
    var cards = document.getElementById('mcpToolCards');
    if (cards) cards.innerHTML = '<div class="stat-card" style="grid-column:1/-1;text-align:center;padding:24px;color:var(--text-muted)"><div class="loading-spinner" style="margin:0 auto"></div></div>';
    var body = document.getElementById('mcpUserBody');
    if (body) body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)"><div class="loading-spinner" style="margin:0 auto"></div></td></tr>';
    var pag = document.getElementById('mcpUserPagination');
    if (pag) pag.innerHTML = '';
    var sel = document.getElementById('mcpToolFilter');
    if (sel) sel.style.borderColor = '';
  }

  function loadMcpUsage() {
    _loadMcpOverallSection();
    _loadMcpToolSection();
  }

  /* Section 1: Platform Overview (uses MCP-specific period) */
  var _mcpRetryTimer = null;
  var _mcpRetryCount = 0;
  var _MCP_MAX_RETRIES = 4;

  function _loadMcpOverallSection() {
    var qs = _getMcpFilterQS();
    Promise.all([
      api('/api/mcp-stats/summary' + qs),
      api('/api/mcp-stats/daily' + qs),
      api('/api/mcp-stats/applications' + qs),
      api('/api/mcp-stats/users' + qs)
    ]).then(function (res) {
      var summary = res[0] || {};
      var daily = (res[1] || {}).daily || [];
      var apps = (res[2] || {}).applications || [];
      var allUsers = (res[3] || {}).users || [];

      var isCollecting = !summary.total_tool_calls && !apps.length && !allUsers.length;
      if (isCollecting) {
        var cards = document.getElementById('mcpOverallCards');
        if (_mcpRetryCount >= _MCP_MAX_RETRIES) {
          if (cards) cards.innerHTML = '<div class="stat-card" style="grid-column:1/-1;text-align:center;padding:32px"><div style="font-size:14px;color:var(--text-muted)">No MCP stats available for this period. Try refreshing or selecting a different period.</div></div>';
          _mcpRetryCount = 0;
          return;
        }
        if (cards) cards.innerHTML = '<div class="stat-card" style="grid-column:1/-1;text-align:center;padding:32px"><div style="font-size:14px;color:var(--text-muted)">&#x23F3; Collecting MCP stats from OCP pods&hellip; data will appear shortly.</div></div>';
        if (_mcpRetryTimer) clearTimeout(_mcpRetryTimer);
        _mcpRetryCount++;
        _mcpRetryTimer = setTimeout(function () {
          _clearApiCache();
          _tabInited['mcpusage'] = false;
          _tabInited['overview'] = false;
          var active = document.querySelector('.tab-btn.active');
          if (active) { var t = active.getAttribute('data-tab'); if (t === 'mcpusage' || t === 'overview') { _tabInited[t] = true; initTab(t); } }
        }, 15000);
        return;
      }
      if (_mcpRetryTimer) { clearTimeout(_mcpRetryTimer); _mcpRetryTimer = null; }
      _mcpRetryCount = 0;

      // Populate tool filter dropdown
      var toolSelect = document.getElementById('mcpToolFilter');
      var currentVal = _mcpToolFilter;
      toolSelect.innerHTML = '<option value="">All Tools (combined)</option>';
      apps.forEach(function (a) {
        var opt = document.createElement('option');
        opt.value = a.name;
        opt.textContent = a.name + ' (' + fmtNum(a.count) + ')';
        if (a.name === currentVal) opt.selected = true;
        toolSelect.appendChild(opt);
      });

      // Overall stat cards
      var humanUsers = allUsers.filter(function (u) { return !_isServiceAccount(u.username); });
      var pLabel = _mcpPeriodDays + 'D';
      var cards = document.getElementById('mcpOverallCards');
      cards.innerHTML =
        '<div class="stat-card"><div class="sc-value">' + fmtNum(summary.total_tool_calls || 0) + '</div><div class="sc-label">Tool Calls (' + pLabel + ')</div></div>' +
        '<div class="stat-card"><div class="sc-value">' + humanUsers.length + '</div><div class="sc-label">Unique Users (' + pLabel + ')</div></div>' +
        '<div class="stat-card"><div class="sc-value">' + (summary.unique_applications || 0) + '</div><div class="sc-label">MCPs Active</div></div>' +
        '<div class="stat-card"><div class="sc-value">' + (summary.unique_functions || 0) + '</div><div class="sc-label">Functions Used</div></div>';

      // Full-width 24h activity chart with toggle filters
      _destroyChart('chartMcpDaily');
      if (daily.length > 0) {
        var isHourly = daily.length > 0 && daily[0].date && daily[0].date.indexOf(' ') > -1;
        var periodUnit = isHourly ? 'hour' : 'day';
        var trendLabels = daily.map(function (d) {
          if (isHourly) {
            var utc = new Date(d.date.replace(' ', 'T') + ':00Z');
            return utc.toLocaleTimeString('en-IL', { timeZone: 'Asia/Jerusalem', hour: '2-digit', minute: '2-digit', hour12: false });
          }
          return d.date;
        });

        // Update chart badge
        var badgeEl = document.querySelector('#pane-mcpusage .chart-box .badge');
        if (badgeEl) badgeEl.textContent = isHourly ? '24H ACTIVITY' : _mcpPeriodDays + 'D ACTIVITY';

        var allDatasets = [];
        allDatasets.push({
          label: 'Users', data: daily.map(function (d) { return d.users; }),
          borderColor: PAL[0], backgroundColor: PAL[0] + '22', fill: true,
          tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5
        });
        var cumulative = []; var hourly = []; var runningTotal = 0;
        daily.forEach(function (d) { hourly.push(d.requests); runningTotal += d.requests; cumulative.push(runningTotal); });
        allDatasets.push({
          label: 'Total Requests', data: cumulative, _hourly: hourly,
          borderColor: PAL[1], backgroundColor: PAL[1] + '22', fill: false,
          tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, yAxisID: 'y1'
        });

        var toolNames = daily[0].by_tool ? Object.keys(daily[0].by_tool) : [];
        toolNames.forEach(function (t) {
          var toolCum = []; var toolHr = []; var toolRunning = 0;
          var tc = _toolColor(t);
          daily.forEach(function (d) { var v = (d.by_tool || {})[t] || 0; toolHr.push(v); toolRunning += v; toolCum.push(toolRunning); });
          allDatasets.push({
            label: t, data: toolCum, _hourly: toolHr,
            borderColor: tc.bg, backgroundColor: tc.bg + '33',
            fill: false, tension: 0.35, borderWidth: 2, pointRadius: 2, pointHoverRadius: 4,
            yAxisID: 'y1', hidden: true
          });
        });

        // Render toggle buttons
        var toggleWrap = document.getElementById('mcpChartToggles');
        if (toggleWrap) {
          var tHtml = '';
          allDatasets.forEach(function (ds, i) {
            var active = !ds.hidden;
            tHtml += '<button class="mcp-chart-toggle' + (active ? ' active' : '') + '" data-ds-idx="' + i + '" ' +
              'style="padding:4px 10px;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;' +
              'border:1.5px solid ' + ds.borderColor + ';' +
              'background:' + (active ? ds.borderColor : 'transparent') + ';' +
              'color:' + (active ? '#fff' : ds.borderColor) + '">' +
              esc(ds.label) + '</button>';
          });
          toggleWrap.innerHTML = tHtml;
        }

        var zoomBtn = document.getElementById('resetZoomBtn');
        var ctx1 = document.getElementById('chartMcpDaily').getContext('2d');
        _charts.chartMcpDaily = new Chart(ctx1, {
          type: 'line',
          data: { labels: trendLabels, datasets: allDatasets },
          options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#e2e8f0',
                borderColor: 'rgba(56,189,248,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8,
                bodyFont: { size: 12 }, titleFont: { size: 12, weight: 'bold' },
                callbacks: {
                  label: function (ctx) {
                    var ds = ctx.dataset;
                    var val = ctx.parsed.y;
                    var hr = ds._hourly ? ds._hourly[ctx.dataIndex] : null;
                    if (hr != null) {
                      return ds.label + ': ' + fmtNum(val) + ' total (' + fmtNum(hr) + ' this ' + periodUnit + ')';
                    }
                    return ds.label + ': ' + val;
                  }
                }
              },
              zoom: {
                pan: { enabled: true, mode: 'x', modifierKey: null },
                zoom: {
                  drag: { enabled: true, backgroundColor: 'rgba(56,189,248,0.15)', borderColor: 'rgba(56,189,248,0.5)', borderWidth: 1 },
                  mode: 'x',
                  onZoomComplete: function () { if (zoomBtn) zoomBtn.style.display = ''; }
                }
              }
            },
            scales: {
              x: { grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 0, autoSkip: false, font: { size: 10 } }) },
              y: { grid: gridLine, ticks: tickColor, title: { display: true, text: 'Users', color: tickColor.color, font: { size: 11 } } },
              y1: { position: 'right', grid: { display: false }, ticks: tickColor, title: { display: true, text: 'Tool Calls', color: tickColor.color, font: { size: 11 } } }
            }
          }
        });

        // Toggle button click handler
        if (toggleWrap) {
          toggleWrap.onclick = function (e) {
            var btn = e.target.closest('.mcp-chart-toggle');
            if (!btn || !_charts.chartMcpDaily) return;
            var idx = parseInt(btn.getAttribute('data-ds-idx'));
            var ds = _charts.chartMcpDaily.data.datasets[idx];
            ds.hidden = !ds.hidden;
            btn.classList.toggle('active', !ds.hidden);
            btn.style.background = ds.hidden ? 'transparent' : ds.borderColor;
            btn.style.color = ds.hidden ? ds.borderColor : '#fff';
            _charts.chartMcpDaily.update();
          };
        }
      }

      // By application bar chart
      _destroyChart('chartMcpApps');
      if (apps.length > 0) {
        var ctx2 = document.getElementById('chartMcpApps').getContext('2d');
        _charts.chartMcpApps = new Chart(ctx2, {
          type: 'bar',
          data: {
            labels: apps.map(function (a) { return a.name; }),
            datasets: [{ label: 'Requests', data: apps.map(function (a) { return a.count; }), backgroundColor: apps.map(function (a) { return _toolColor(a.name).bg; }), borderRadius: 4 }]
          },
          options: {
            responsive: true, maintainAspectRatio: false, indexAxis: 'y',
            plugins: { legend: { display: false }, tooltip: chartTT },
            scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 11 } }) } }
          }
        });
      }
    });
  }

  function _isServiceAccount(name) {
    if (!name) return true;
    var n = name.toLowerCase();
    if (n === '_unknown' || n === 'unknown') return true;
    if (/^app_/i.test(name)) return true;
    if (/^d\d/i.test(name)) return true;
    if (/integ/i.test(name)) return true;
    if (/^it_/i.test(name)) return true;
    if (/_svc|_bot|_auto|_system|^svc_|^bot_|^system_/i.test(name)) return true;
    if (/^mpopescu$/i.test(name)) return true;
    return false;
  }

  /* Section 2: Tool Deep Dive (uses MCP-specific period + tool filter) */
  function _loadMcpToolSection(skipCache) {
    var qs = _getMcpFilterQS();
    if (_mcpToolFilter) qs += '&app=' + encodeURIComponent(_mcpToolFilter);

    Promise.all([
      api('/api/mcp-stats/summary' + qs, skipCache),
      api('/api/mcp-stats/functions' + qs, skipCache),
      api('/api/mcp-stats/users' + qs, skipCache)
    ]).then(function (res) {
      try {
      var summary = res[0] || {};
      var funcs = (res[1] || {}).functions || [];
      var usersResp = res[2] || {};
      var users = usersResp.users || [];
      _funcToolMap = usersResp.func_tool_map || {};

      if (!summary.total_tool_calls && !funcs.length && !users.length) {
        _resetToolSectionUI();
        var cards = document.getElementById('mcpToolCards');
        if (cards) cards.innerHTML = '<div class="stat-card" style="grid-column:1/-1;text-align:center;padding:32px"><div style="font-size:14px;color:var(--text-muted)">&#x23F3; Collecting data&hellip; will auto-refresh shortly.</div></div>';
        var body = document.getElementById('mcpUserBody');
        if (body) body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)">&#x23F3; Collecting data&hellip; will auto-refresh shortly.</td></tr>';
        return;
      }

      _mcpUsageUsers = users;

      var toolLabel = _mcpToolFilter || 'All Tools';
      var badge = _mcpToolFilter ? _toolBadgeHtml(_mcpToolFilter) : '';
      var filterNote = _mcpToolFilter
        ? 'Showing data for ' + toolLabel + ' (' + _mcpPeriodDays + 'D)'
        : 'Select a specific tool to view its users, functions and activity';

      var diveTitle = document.getElementById('toolDiveTitle');
      var diveBadge = document.getElementById('toolDiveBadge');
      var diveSub = document.getElementById('toolDiveSubtitle');
      if (diveTitle) diveTitle.textContent = 'Tool Deep Dive';
      if (diveBadge) diveBadge.innerHTML = badge;
      if (diveSub) diveSub.textContent = filterNote;

      var ua = document.getElementById('userActivityTitle');
      var uab = document.getElementById('userActivityBadge');
      var uas = document.getElementById('userActivitySubtitle');
      if (ua) ua.textContent = 'User Activity';
      if (uab) uab.innerHTML = badge;
      if (uas) uas.textContent = _mcpToolFilter ? toolLabel + ' — users ranked by requests (' + _mcpPeriodDays + 'D)' : 'Users ranked by requests with top functions used';

      var unattribCount = 0;
      var namedFuncs = funcs.filter(function (f) {
        if (f.name === 'tool_call') { unattribCount += f.count; return false; }
        return true;
      });
      var topNamedFunc = namedFuncs.length > 0 ? namedFuncs[0].name : '\u2014';

      var humanUsers = users.filter(function (u) { return !_isServiceAccount(u.username); });
      var serviceTotal = 0;
      users.forEach(function (u) { if (_isServiceAccount(u.username)) serviceTotal += u.count; });

      var pLabel = _mcpPeriodDays + 'D';
      var tc = _mcpToolFilter ? _toolColor(_mcpToolFilter) : null;
      var cardAccent = tc ? 'border-top:3px solid ' + tc.bg : '';

      var sel = document.getElementById('mcpToolFilter');
      if (sel) sel.style.borderColor = tc ? tc.bg : '';

      var cards = document.getElementById('mcpToolCards');
      if (cards) cards.innerHTML =
        '<div class="stat-card" style="' + cardAccent + '"><div class="sc-value">' + fmtNum(summary.total_tool_calls || 0) + '</div><div class="sc-label">Tool Calls — ' + esc(toolLabel) + ' (' + pLabel + ')</div></div>' +
        '<div class="stat-card" style="' + cardAccent + '"><div class="sc-value">' + humanUsers.length + '</div><div class="sc-label">Active Users (' + pLabel + ')</div></div>' +
        '<div class="stat-card" style="' + cardAccent + '"><div class="sc-value">' + namedFuncs.length + '</div><div class="sc-label">Named Functions</div></div>' +
        '<div class="stat-card" style="' + cardAccent + '"><div class="sc-value" title="' + esc(topNamedFunc) + '" style="font-size:18px">' + esc(topNamedFunc) + '</div><div class="sc-label">Most Used Function</div></div>';

      var noteWrap = document.getElementById('mcpToolNotes');
      if (!noteWrap) {
        noteWrap = document.createElement('div');
        noteWrap.id = 'mcpToolNotes';
        if (cards) cards.parentNode.insertBefore(noteWrap, cards.nextSibling);
      }
      if (noteWrap) {
        if (unattribCount > 0 || serviceTotal > 0) {
          var noteHtml = '<div style="display:flex;gap:16px;flex-wrap:wrap;margin:-8px 0 12px;font-size:11px;color:var(--text-muted)">';
          if (unattribCount > 0) noteHtml += '<span>\u26A0 ' + fmtNum(unattribCount) + ' calls from tools without function-level logging (shown as totals only)</span>';
          if (serviceTotal > 0) noteHtml += '<span>\uD83E\uDD16 ' + fmtNum(serviceTotal) + ' calls from service/app accounts (excluded from user charts)</span>';
          noteHtml += '</div>';
          noteWrap.innerHTML = noteHtml;
        } else {
          noteWrap.innerHTML = '';
        }
      }

      _destroyChart('chartMcpFunctions');
      if (namedFuncs.length > 0) {
        var topFuncs = namedFuncs.slice(0, 20);
        var funcCanvas = document.getElementById('chartMcpFunctions');
        if (funcCanvas) {
        funcCanvas.parentElement.style.height = Math.max(280, topFuncs.length * 28) + 'px';
        var ctx3 = funcCanvas.getContext('2d');
        _charts.chartMcpFunctions = new Chart(ctx3, {
          type: 'bar',
          data: {
            labels: topFuncs.map(function (f) { return f.name; }),
            datasets: [{ label: 'Calls', data: topFuncs.map(function (f) { return f.count; }), backgroundColor: PAL[2], borderRadius: 4 }]
          },
          options: {
            responsive: true, maintainAspectRatio: false, indexAxis: 'y',
            plugins: { legend: { display: false }, tooltip: chartTT },
            scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 11 } }) } }
          }
        });
        }
      }

      _destroyChart('chartMcpUsers');
      if (humanUsers.length > 0) {
        var topU = humanUsers.slice(0, 15);
        var userCanvas = document.getElementById('chartMcpUsers');
        if (userCanvas) {
        userCanvas.parentElement.style.height = Math.max(280, topU.length * 28) + 'px';
        var ctx4 = userCanvas.getContext('2d');
        _charts.chartMcpUsers = new Chart(ctx4, {
          type: 'bar',
          data: {
            labels: topU.map(function (u) { return u.username; }),
            datasets: [{ label: 'Tool Calls', data: topU.map(function (u) { return u.count; }), backgroundColor: PAL[3], borderRadius: 4 }]
          },
          options: {
            responsive: true, maintainAspectRatio: false, indexAxis: 'y',
            plugins: { legend: { display: false }, tooltip: chartTT },
            scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 11 } }) } }
          }
        });
        }
      }

      _renderMcpUserTable(users, 1);
      } catch (err) {
        console.error('Tool section render error:', err);
        var body = document.getElementById('mcpUserBody');
        if (body) body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--status-red)">Render error: ' + esc(err.message) + '</td></tr>';
      }
    }).catch(function (err) {
      console.error('Tool section API error:', err);
      var body = document.getElementById('mcpUserBody');
      if (body) body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--status-red)">API error: ' + esc(err.message || 'Request failed') + '</td></tr>';
    });
  }

  var _mcpUserPage = 1;
  var _mcpUserPageSize = 10;
  var _mcpUserFiltered = [];

  function _fnPillHtml(f, contextTool) {
    var fname = f && f.name != null ? String(f.name) : '';
    var ft = _funcToTool(fname, typeof contextTool === 'string' ? contextTool : _mcpToolFilter);
    var fc = ft ? _toolColor(ft) : null;
    var dotColor = fc ? fc.bg : 'var(--text-muted)';
    var borderLeft = fc ? 'border-left:3px solid ' + fc.bg + ';' : '';
    var toolTag = ft ? '<span style="font-size:9px;font-weight:700;color:' + fc.bg + ';text-transform:uppercase;letter-spacing:.3px">' + esc(ft) + '</span> ' : '';
    return '<span style="display:inline-flex;align-items:center;gap:4px;background:var(--bg-card);' + borderLeft + 'border:1px solid var(--border-color);border-radius:4px;padding:2px 8px;font-size:11px;white-space:nowrap">' +
      toolTag +
      '<span style="font-weight:600;color:var(--text-primary)">' + esc(fname) + '</span>' +
      '<span style="color:' + (fc ? fc.bg : 'var(--accent-primary)') + ';font-weight:700">' + (f.pct || 0) + '%</span></span>';
  }

  function _userToolBadges(fns, toolsUsed) {
    var toolCounts = {};
    (fns || []).forEach(function (f) {
      var t = _funcToTool(f && f.name != null ? String(f.name) : '');
      if (t) toolCounts[t] = (toolCounts[t] || 0) + (f.count || 0);
    });
    if (toolsUsed && toolsUsed.length) {
      toolsUsed.forEach(function (t) {
        if (t && !toolCounts[t]) toolCounts[t] = 0;
      });
    }
    var sorted = Object.keys(toolCounts).sort(function (a, b) { return (toolCounts[b] || 0) - (toolCounts[a] || 0); });
    return sorted.map(function (t) {
      var c = _toolColor(t);
      return '<span style="display:inline-block;font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;background:' + c.bg + ';color:' + c.text + ';white-space:nowrap" title="' + fmtNum(toolCounts[t] || 0) + ' calls">' + esc(t.toUpperCase()) + '</span>';
    }).join(' ');
  }

  function _renderMcpUserTable(users, page) {
    var allUsers = users || [];
    var humans = allUsers.filter(function (u) { return !_isServiceAccount(u.username); });
    var svcAccounts = allUsers.filter(function (u) { return _isServiceAccount(u.username); });

    _mcpUserFiltered = humans;
    _mcpUserPage = page || 1;
    var body = document.getElementById('mcpUserBody');
    if (!body) return;
    if (!_mcpUserFiltered.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)">No human users found \u2014 select a tool or adjust the time range</td></tr>';
      document.getElementById('mcpUserPagination').innerHTML = '';
    } else {
      var start = (_mcpUserPage - 1) * _mcpUserPageSize;
      var pageUsers = _mcpUserFiltered.slice(start, start + _mcpUserPageSize);

      body.innerHTML = pageUsers.map(function (u, idx) {
        var rank = start + idx + 1;
        var rankBadge = rank <= 3
          ? '<span style="display:inline-block;width:24px;height:24px;line-height:24px;text-align:center;border-radius:50%;font-size:11px;font-weight:800;background:' + (rank === 1 ? 'var(--accent-primary)' : rank === 2 ? 'var(--accent-teal)' : 'var(--accent-orange)') + ';color:#fff">' + rank + '</span>'
          : '<span style="color:var(--text-muted)">' + rank + '</span>';
        var fns = (u.top_functions || []).filter(function (f) { return f.name !== 'tool_call'; });
        var toolBadges = _userToolBadges(fns, u.tools_used);
        var fnHtml = fns.map(_fnPillHtml).join(' ');
        return '<tr>' +
          '<td style="text-align:center">' + rankBadge + '</td>' +
          '<td style="font-weight:600;color:var(--text-primary)">' + esc(u.username) + '</td>' +
          '<td style="text-align:right;font-family:\'JetBrains Mono\',monospace;font-weight:700">' + fmtNum(u.count) + '</td>' +
          '<td><div style="display:flex;flex-wrap:wrap;gap:3px">' + toolBadges + '</div></td>' +
          '<td><div style="display:flex;flex-wrap:wrap;gap:4px">' + fnHtml + '</div></td></tr>';
      }).join('');
      _renderMcpUserPagination();
    }

    _renderSvcAccountsPanel(svcAccounts);
  }

  function _svcTypeLabel(name) {
    var n = (name || '').toLowerCase();
    if (n === '_unknown' || n === 'unknown') return 'UNATTRIBUTED';
    if (/^app_/i.test(name)) return 'APP';
    if (/^d\d/i.test(name) || /integ/i.test(name)) return 'INTEGRATION';
    return 'SERVICE';
  }

  function _renderSvcAccountsPanel(svcAccounts) {
    var section = document.getElementById('mcpSvcSection');
    if (!section) return;
    if (!svcAccounts.length) { section.style.display = 'none'; return; }

    section.style.display = '';
    var totalCalls = svcAccounts.reduce(function (s, u) { return s + (u.count || 0); }, 0);
    var summaryEl = document.getElementById('mcpSvcSummary');
    if (summaryEl) summaryEl.textContent = svcAccounts.length + ' account' + (svcAccounts.length > 1 ? 's' : '') + ' \u2014 ' + fmtNum(totalCalls) + ' total calls (excluded from rankings)';

    var tbody = document.getElementById('mcpSvcTableBody');
    if (!tbody) return;

    tbody.innerHTML = svcAccounts.map(function (u) {
      var typeLabel = _svcTypeLabel(u.username);
      var typeColor = typeLabel === 'UNATTRIBUTED' ? '#64748b' : typeLabel === 'APP' ? 'var(--accent-orange)' : typeLabel === 'INTEGRATION' ? '#06b6d4' : 'var(--accent-secondary)';
      var fns = (u.top_functions || []).filter(function (f) { return f.name !== 'tool_call'; });
      var toolBadges = _userToolBadges(fns, u.tools_used);
      var fnHtml = fns.map(_fnPillHtml).join(' ');
      return '<tr style="opacity:.7">' +
        '<td style="text-align:center"><span style="display:inline-block;font-size:9px;font-weight:700;padding:2px 8px;border-radius:4px;background:' + typeColor + ';color:#fff;white-space:nowrap">' + typeLabel + '</span></td>' +
        '<td style="font-weight:600;color:var(--text-secondary)">' + esc(u.username) + '</td>' +
        '<td style="text-align:right;font-family:\'JetBrains Mono\',monospace;font-weight:700;color:var(--text-secondary)">' + fmtNum(u.count) + '</td>' +
        '<td><div style="display:flex;flex-wrap:wrap;gap:3px">' + toolBadges + '</div></td>' +
        '<td><div style="display:flex;flex-wrap:wrap;gap:4px">' + fnHtml + '</div></td></tr>';
    }).join('');
  }

  window.toggleSvcAccounts = function () {
    var body = document.getElementById('mcpSvcBody');
    var toggle = document.getElementById('mcpSvcToggle');
    if (!body) return;
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    if (toggle) toggle.style.transform = open ? '' : 'rotate(90deg)';
  };

  function _renderMcpUserPagination() {
    var wrap = document.getElementById('mcpUserPagination');
    var totalPages = Math.ceil(_mcpUserFiltered.length / _mcpUserPageSize);
    if (totalPages <= 1) { wrap.innerHTML = ''; return; }
    var html = '';
    var btnStyle = 'cursor:pointer;border:1px solid var(--border-color);background:var(--bg-card);color:var(--text-primary);padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var activeStyle = 'cursor:pointer;border:1px solid var(--accent-primary);background:var(--accent-primary);color:#fff;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    if (_mcpUserPage > 1) html += '<button style="' + btnStyle + '" onclick="mcpUserGoPage(' + (_mcpUserPage - 1) + ')">\u2039</button>';
    for (var p = 1; p <= totalPages; p++) {
      html += '<button style="' + (p === _mcpUserPage ? activeStyle : btnStyle) + '" onclick="mcpUserGoPage(' + p + ')">' + p + '</button>';
    }
    if (_mcpUserPage < totalPages) html += '<button style="' + btnStyle + '" onclick="mcpUserGoPage(' + (_mcpUserPage + 1) + ')">\u203A</button>';
    html += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + _mcpUserFiltered.length + ' users</span>';
    wrap.innerHTML = html;
  }

  window.mcpUserGoPage = function (p) { _renderMcpUserTable(_mcpUserFiltered, p); };

  window.filterMcpUsers = function () {
    var q = (document.getElementById('mcpUserSearch').value || '').toLowerCase();
    var filtered = _mcpUsageUsers.filter(function (u) { return u.username.toLowerCase().indexOf(q) > -1; });
    var humans = filtered.filter(function (u) { return !_isServiceAccount(u.username); });
    _mcpUserFiltered = humans;
    _mcpUserPage = 1;
    var body = document.getElementById('mcpUserBody');
    if (!humans.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)">No matching users</td></tr>';
      document.getElementById('mcpUserPagination').innerHTML = '';
    } else {
      _renderMcpUserTable(filtered, 1);
    }
  };

  function _exportMcpUsage() {
    var qs = _getMcpFilterQS();
    Promise.all([api('/api/mcp-stats/users' + qs), api('/api/mcp-stats/applications' + qs), api('/api/mcp-stats/functions' + qs)])
      .then(function (res) {
        var users = (res[0] || {}).users || [];
        var apps = (res[1] || {}).applications || [];
        var funcs = (res[2] || {}).functions || [];

        var rows = [['=== MCP USAGE - TOP USERS ===']];
        rows.push(['Username', 'Tool Calls']);
        users.forEach(function (u) { rows.push([u.username, u.count]); });

        rows.push([]);
        rows.push(['=== MCP TOOLS (Applications) ===']);
        rows.push(['Tool Name', 'Tool Calls']);
        apps.forEach(function (a) { rows.push([a.name, a.count]); });

        rows.push([]);
        rows.push(['=== TOP FUNCTIONS CALLED ===']);
        rows.push(['Function Name', 'Call Count']);
        funcs.forEach(function (f) { rows.push([f.name, f.count]); });

        rows.push([]);
        rows.push(['Period', 'Last ' + _mcpPeriodDays + ' day(s)']);

        _downloadCSV('mcp_usage_export.csv', rows);
      });
  }

  function _destroyChart(id) {
    if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
  }

  /* ── JIRA FLOW FILTER (Planned vs OGS) ── */
  var PLANNED_TYPES = ['feature', 'epic', 'story'];
  var _jiraFlowFilter = '';
  var _eaasFlowFilter = '';

  function _filterByFlow(issues, mode) {
    if (!mode) return issues;
    return issues.filter(function (i) {
      var t = (i.type || '').toLowerCase();
      var isPlanned = PLANNED_TYPES.indexOf(t) > -1;
      return mode === 'planned' ? isPlanned : !isPlanned;
    });
  }

  function _flowLabel(mode) {
    if (mode === 'planned') return 'Planned';
    if (mode === 'ogs') return 'OGS';
    return 'Total';
  }

  function _aggregateIssues(issues) {
    var open = { total_issues: issues.length, open: 0, resolved: 0, by_type: {}, by_priority: {} };
    var byToolMap = {};
    var monthlyMap = {};
    issues.forEach(function (i) {
      var isDone = i.status_category === 'Done' || i.status_category === 'Complete';
      if (isDone) open.resolved++; else open.open++;
      open.by_type[i.type] = (open.by_type[i.type] || 0) + 1;
      open.by_priority[i.priority] = (open.by_priority[i.priority] || 0) + 1;
      byToolMap[i.tool] = (byToolMap[i.tool] || 0) + 1;
      var m = i.created_month || 'unknown';
      if (!monthlyMap[m]) monthlyMap[m] = { total: 0, resolved: 0 };
      monthlyMap[m].total++;
      if (isDone) monthlyMap[m].resolved++;
      monthlyMap[m][i.type] = (monthlyMap[m][i.type] || 0) + 1;
    });
    var byTool = Object.keys(byToolMap).map(function (t) { return { tool: t, count: byToolMap[t] }; }).sort(function (a, b) { return b.count - a.count; });
    var trends = Object.keys(monthlyMap).sort().map(function (m) { var o = monthlyMap[m]; o.month = m; return o; });
    return { open: open, byTool: byTool, trends: trends };
  }

  window.setJiraFlow = function (mode) {
    _jiraFlowFilter = mode;
    document.querySelectorAll('.jira-flow-btn').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-flow') === mode);
    });
    _tabInited['jira'] = false;
    loadJira();
  };

  window.setEaasFlow = function (mode) {
    _eaasFlowFilter = mode;
    document.querySelectorAll('.eaas-flow-btn').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-flow') === mode);
    });
    _tabInited['jira-eaas'] = false;
    loadJiraEaas();
  };

  /* ── JIRA TOOLS TAB (DEVOPS) ── */
  var _jiraAllTickets = [];
  var _jiraProject = 'DEVOPS';

  function loadJira() {
    var qs = _getFilterQS();
    qs += (qs ? '&' : '?') + 'project=' + _jiraProject;

    api('/api/jira/issues' + qs).then(function (data) {
      var allIssues = (data || {}).issues || [];
      var filtered = _filterByFlow(allIssues, _jiraFlowFilter);
      _jiraAllTickets = filtered;

      var agg = _aggregateIssues(filtered);
      _renderJiraCards(agg.open, _jiraFlowFilter);
      _renderResolutionChart('chartJiraResolution', 'jiraResolution', agg.trends);
      _renderTypeTrendChart('chartJiraTypeTrend', 'jiraTypeTrend', agg.trends);
      _renderJiraTrendChart(agg.trends);
      _renderJiraToolChart(agg.byTool);
      _renderJiraTable(agg.byTool);
      _renderJiraTickets(filtered, 1);
    });
  }

  /* ── JIRA EAAS TAB (EAAS + CLOUD) ── */
  var _eaasAllTickets = [];
  var _eaasProject = '';

  function _initEaasProjectFilter() {
    api('/api/jira/projects').then(function (data) {
      var projects = (data || {}).projects || [];
      var eaasProjects = projects.filter(function (p) { return p.key === 'EAAS' || p.key === 'CLOUD'; });
      if (!eaasProjects.length) return;
      var wrap = document.getElementById('eaasProjectFilter');
      var html = '<button class="period-btn' + (!_eaasProject ? ' active' : '') + '" onclick="setEaasProject(\'\')">All EAAS</button>';
      eaasProjects.forEach(function (p) {
        html += '<button class="period-btn' + (_eaasProject === p.key ? ' active' : '') + '" onclick="setEaasProject(\'' + p.key + '\')">' + esc(p.key) + ' <span style="opacity:.6;font-size:10px">(' + p.count + ')</span></button>';
      });
      wrap.innerHTML = html;
    });
  }

  window.setEaasProject = function (proj) {
    _eaasProject = proj;
    _clearApiCache();
    _tabInited['jira-eaas'] = false;
    _initEaasProjectFilter();
    loadJiraEaas();
  };

  function loadJiraEaas() {
    var qs = _getFilterQS();
    var projectFilter = _eaasProject || '';
    if (projectFilter) {
      qs += (qs ? '&' : '?') + 'project=' + projectFilter;
    }

    var subtitle = document.getElementById('eaasJiraSubtitle');
    if (subtitle) subtitle.textContent = (_eaasProject || 'EAAS & CLOUD') + ' issues for selected period';

    var eaasQs = qs;
    if (!projectFilter) {
      var p1 = qs + (qs ? '&' : '?') + 'project=EAAS';
      var p2 = qs + (qs ? '&' : '?') + 'project=CLOUD';
      Promise.all([
        api('/api/jira/issues' + p1), api('/api/jira/issues' + p2)
      ]).then(function (res) {
        var eaasIssues = ((res[0] || {}).issues || []).concat((res[1] || {}).issues || []);
        eaasIssues.sort(function (a, b) { return (b.created || '').localeCompare(a.created || ''); });
        _processEaasData(eaasIssues, qs);
      });
      return;
    }
    api('/api/jira/issues' + eaasQs).then(function (data) {
      _processEaasData((data || {}).issues || [], qs);
    });
  }

  function _processEaasData(issues, qs) {
    var filtered = _filterByFlow(issues, _eaasFlowFilter);
    _eaasAllTickets = filtered;

    var agg = _aggregateIssues(filtered);
    _renderEaasCards(agg.open, _eaasFlowFilter);
    _renderResolutionChart('chartEaasResolution', 'eaasResolution', agg.trends);
    _renderTypeTrendChart('chartEaasTypeTrend', 'eaasTypeTrend', agg.trends);
    _renderEaasTrendChart(agg.trends);
    _renderEaasToolChart(agg.byTool);
    _renderEaasTable(agg.byTool);
    _renderEaasTickets(filtered, 1);
  }

  function _renderEaasCards(o, flowMode) {
    var label = _periodDays <= 30 ? '(' + _periodDays + 'd)' : _periodDays <= 90 ? '(3m)' : _periodDays <= 180 ? '(6m)' : '(12m)';
    var fLabel = _flowLabel(flowMode);
    document.getElementById('eaasJiraCards').innerHTML =
      _statCard('\uD83D\uDCCB', o.total_issues || 0, fLabel + ' Issues ' + label, '', 'var(--accent-primary)') +
      _statCard('\uD83D\uDD13', o.open || 0, 'Open', '', 'var(--status-yellow)') +
      _statCard('\u2705', o.resolved || 0, 'Resolved', '', 'var(--status-green)') +
      _statCard('\uD83D\uDC1B', (o.by_type || {}).Bug || (o.by_type || {}).Defect || 0, 'Bugs/Defects', '', 'var(--status-red)') +
      _statCard('\uD83D\uDCDD', (o.by_type || {}).Task || 0, 'Tasks', '', 'var(--accent-secondary)');
  }

  function _renderEaasTrendChart(trends) {
    var labels = trends.map(function (t) { return t.month; });
    var types = {};
    trends.forEach(function (t) { Object.keys(t).forEach(function (k) { if (k !== 'month' && k !== 'total') types[k] = true; }); });
    var typeNames = Object.keys(types).slice(0, 6);
    var datasets = typeNames.map(function (name, idx) {
      return { label: name, data: trends.map(function (t) { return t[name] || 0; }), backgroundColor: PAL[idx % PAL.length], borderRadius: 4 };
    });
    if (_charts.eaasTrend) _charts.eaasTrend.destroy();
    _charts.eaasTrend = new Chart(document.getElementById('chartEaasTrend'), {
      type: 'bar', data: { labels: labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true, grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 }) }, y: { stacked: true, grid: gridLine, ticks: Object.assign({}, tickColor, { stepSize: 5 }) } }, plugins: { legend: { labels: chartLeg, position: 'top' }, tooltip: chartTT } }
    });
  }

  function _renderEaasToolChart(byTool) {
    var labels = byTool.map(function (t) { return t.tool; });
    var values = byTool.map(function (t) { return t.count; });
    if (_charts.eaasTool) _charts.eaasTool.destroy();
    _charts.eaasTool = new Chart(document.getElementById('chartEaasTool'), {
      type: 'doughnut', data: { labels: labels, datasets: [{ data: values, backgroundColor: PAL.slice(0, labels.length), borderWidth: 0, hoverOffset: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'right', labels: chartLeg }, tooltip: chartTT } }
    });
  }

  function _renderEaasTable(byTool) {
    var tbody = document.getElementById('eaasToolBody');
    if (!byTool.length) { tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:24px;color:var(--text-muted)">No EAAS/CLOUD data available</td></tr>'; return; }
    var total = byTool.reduce(function (s, t) { return s + t.count; }, 0);
    var html = '';
    byTool.forEach(function (t) {
      var pct = total > 0 ? (t.count / total * 100).toFixed(1) : 0;
      html += '<tr><td style="font-weight:700;color:var(--text-primary)">' + esc(t.tool) + '</td><td class="mono">' + t.count + '</td><td><div style="display:flex;align-items:center;gap:8px"><div style="width:100px;height:6px;background:var(--border-color);border-radius:3px;overflow:hidden"><div style="height:100%;width:' + pct + '%;background:var(--accent-primary);border-radius:3px"></div></div><span class="mono" style="font-size:11px;color:var(--text-muted)">' + pct + '%</span></div></td></tr>';
    });
    tbody.innerHTML = html;
  }

  var _eaasTicketPage = 1;
  var _eaasTicketPageSize = 10;
  var _eaasTicketFiltered = [];

  function _renderEaasTickets(issues, page) {
    _eaasTicketFiltered = issues || [];
    _eaasTicketPage = page || 1;
    var tbody = document.getElementById('eaasTicketBody');
    if (!_eaasTicketFiltered.length) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--text-muted)">No tickets found</td></tr>'; document.getElementById('eaasTicketPagination').innerHTML = ''; return; }
    var start = (_eaasTicketPage - 1) * _eaasTicketPageSize;
    var pageIssues = _eaasTicketFiltered.slice(start, start + _eaasTicketPageSize);
    var html = '';
    pageIssues.forEach(function (i) {
      var prioColor = i.priority === 'Critical' || i.priority === 'Blocker' ? 'var(--status-red)' : i.priority === 'Major' ? 'var(--status-yellow)' : 'var(--text-secondary)';
      var statusColor = i.status_category === 'Done' || i.status_category === 'Complete' ? 'var(--status-green)' : 'var(--accent-primary)';
      html += '<tr><td><a href="' + esc(i.url) + '" target="_blank" style="color:var(--accent-primary);font-weight:700;font-family:\'JetBrains Mono\',monospace;font-size:12px">' + esc(i.key) + '</a></td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(i.summary) + '">' + esc(i.summary) + '</td><td><span class="pill" style="background:var(--accent-primary-soft);color:var(--accent-primary)">' + esc(i.type) + '</span></td><td style="color:' + prioColor + ';font-weight:600;font-size:12px">' + esc(i.priority) + '</td><td style="color:' + statusColor + ';font-size:12px">' + esc(i.status) + '</td><td style="font-size:12px">' + esc(i.assignee) + '</td><td style="font-size:11px;color:var(--text-muted)">' + esc(i.tool) + '</td><td class="mono" style="font-size:11px">' + esc(i.created) + '</td></tr>';
    });
    tbody.innerHTML = html;
    var wrap = document.getElementById('eaasTicketPagination');
    var totalPages = Math.ceil(_eaasTicketFiltered.length / _eaasTicketPageSize);
    if (totalPages <= 1) { wrap.innerHTML = ''; return; }
    var btnStyle = 'cursor:pointer;border:1px solid var(--border-color);background:var(--bg-card);color:var(--text-primary);padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var activeStyle = 'cursor:pointer;border:1px solid var(--accent-primary);background:var(--accent-primary);color:#fff;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var ph = '';
    if (_eaasTicketPage > 1) ph += '<button style="' + btnStyle + '" onclick="eaasTicketGoPage(' + (_eaasTicketPage - 1) + ')">\u2039</button>';
    var startP = Math.max(1, _eaasTicketPage - 3), endP = Math.min(totalPages, startP + 6);
    for (var p = startP; p <= endP; p++) { ph += '<button style="' + (p === _eaasTicketPage ? activeStyle : btnStyle) + '" onclick="eaasTicketGoPage(' + p + ')">' + p + '</button>'; }
    if (_eaasTicketPage < totalPages) ph += '<button style="' + btnStyle + '" onclick="eaasTicketGoPage(' + (_eaasTicketPage + 1) + ')">\u203A</button>';
    ph += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + _eaasTicketFiltered.length + ' tickets</span>';
    wrap.innerHTML = ph;
  }

  window.eaasTicketGoPage = function (p) { _renderEaasTickets(_eaasTicketFiltered, p); };

  window.filterEaasTickets = function () {
    var search = (document.getElementById('eaasTicketSearch').value || '').toLowerCase();
    if (!search) { _renderEaasTickets(_eaasAllTickets, 1); return; }
    var filtered = _eaasAllTickets.filter(function (i) {
      return (i.key || '').toLowerCase().indexOf(search) > -1 || (i.summary || '').toLowerCase().indexOf(search) > -1 || (i.assignee || '').toLowerCase().indexOf(search) > -1 || (i.tool || '').toLowerCase().indexOf(search) > -1 || (i.status || '').toLowerCase().indexOf(search) > -1;
    });
    _renderEaasTickets(filtered, 1);
  };

  window.exportEaasCSV = function () {
    var issues = _eaasTicketFiltered.length ? _eaasTicketFiltered : _eaasAllTickets;
    if (!issues || !issues.length) { showToast('No tickets to export', 'error'); return; }
    var rows = [['Key', 'Summary', 'Type', 'Priority', 'Status', 'Assignee', 'Tool', 'Created', 'URL']];
    issues.forEach(function (i) { rows.push([i.key, i.summary, i.type, i.priority, i.status, i.assignee, i.tool, i.created, i.url]); });
    var csv = rows.map(function (r) { return r.map(function (c) { return '"' + String(c || '').replace(/"/g, '""') + '"'; }).join(','); }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'jira_eaas_' + new Date().toISOString().split('T')[0] + '.csv';
    a.click();
    showToast('CSV downloaded (' + issues.length + ' tickets)', 'success');
  };

  function _renderTypeTrendChart(canvasId, chartKey, trends) {
    _destroyChart(chartKey);
    if (!trends || !trends.length) return;

    var labels = trends.map(function (t) { return t.month; });
    var types = {};
    trends.forEach(function (t) {
      Object.keys(t).forEach(function (k) { if (k !== 'month' && k !== 'total') types[k] = true; });
    });
    var typeNames = Object.keys(types).slice(0, 8);
    var datasets = typeNames.map(function (name, idx) {
      return {
        label: name,
        data: trends.map(function (t) { return t[name] || 0; }),
        borderColor: PAL[idx % PAL.length],
        backgroundColor: PAL[idx % PAL.length] + '18',
        fill: false,
        tension: 0.35,
        borderWidth: 2.5,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBackgroundColor: PAL[idx % PAL.length]
      };
    });

    var totalLine = {
      label: 'Total',
      data: trends.map(function (t) { return t.total || 0; }),
      borderColor: '#94a3b8',
      backgroundColor: '#94a3b822',
      borderDash: [6, 3],
      fill: false,
      tension: 0.35,
      borderWidth: 2,
      pointRadius: 3,
      pointHoverRadius: 5,
      pointBackgroundColor: '#94a3b8'
    };
    datasets.unshift(totalLine);

    var el = document.getElementById(canvasId);
    if (!el) return;
    _charts[chartKey] = new Chart(el.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: { grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 }) },
          y: { grid: gridLine, ticks: Object.assign({}, tickColor, { stepSize: 5 }), beginAtZero: true }
        },
        plugins: {
          legend: { labels: chartLeg, position: 'top' },
          tooltip: {
            backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#e2e8f0',
            borderColor: 'rgba(56,189,248,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8
          }
        }
      }
    });
  }

  function _renderResolutionChart(canvasId, chartKey, trends) {
    _destroyChart(chartKey);
    if (!trends || !trends.length) return;
    var el = document.getElementById(canvasId);
    if (!el) return;

    var labels = trends.map(function (t) { return t.month; });
    var totalData = trends.map(function (t) { return t.total || 0; });
    var resolvedData = trends.map(function (t) { return t.resolved || 0; });
    var openData = trends.map(function (t) { return (t.total || 0) - (t.resolved || 0); });

    _charts[chartKey] = new Chart(el.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Total Requests',
            data: totalData,
            borderColor: '#6366f1',
            backgroundColor: 'rgba(56,189,248,0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 3,
            pointRadius: 5,
            pointHoverRadius: 8,
            pointBackgroundColor: '#6366f1',
            pointBorderColor: '#fff',
            pointBorderWidth: 2
          },
          {
            label: 'Resolved',
            data: resolvedData,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 3,
            pointRadius: 5,
            pointHoverRadius: 8,
            pointBackgroundColor: '#22c55e',
            pointBorderColor: '#fff',
            pointBorderWidth: 2
          },
          {
            label: 'Open',
            data: openData,
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245,158,11,0.06)',
            fill: false,
            tension: 0.35,
            borderWidth: 2,
            borderDash: [6, 3],
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: '#f59e0b'
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: { grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 }) },
          y: { grid: gridLine, ticks: Object.assign({}, tickColor, { stepSize: 5 }), beginAtZero: true }
        },
        plugins: {
          legend: { labels: chartLeg, position: 'top' },
          tooltip: {
            backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#e2e8f0',
            borderColor: 'rgba(56,189,248,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8,
            callbacks: {
              afterBody: function (ctx) {
                var idx = ctx[0].dataIndex;
                var total = totalData[idx] || 0;
                var resolved = resolvedData[idx] || 0;
                var rate = total > 0 ? Math.round(resolved / total * 100) : 0;
                return 'Resolution Rate: ' + rate + '%';
              }
            }
          }
        }
      }
    });
  }

  function _renderJiraCards(o, flowMode) {
    var label = _periodDays <= 30 ? '(' + _periodDays + 'd)' : _periodDays <= 90 ? '(3m)' : _periodDays <= 180 ? '(6m)' : '(12m)';
    var fLabel = _flowLabel(flowMode);
    var total = o.total_issues || 0;
    var resolved = o.resolved || 0;
    var resRate = total > 0 ? Math.round(resolved / total * 100) : 0;
    var bp = o.by_priority || {};
    var critHigh = (bp.Critical || 0) + (bp.Blocker || 0) + (bp.Major || 0);
    document.getElementById('jiraCards').innerHTML =
      _statCard('\uD83D\uDCCB', total, fLabel + ' Issues ' + label, '', 'var(--accent-primary)') +
      _statCard('\uD83D\uDD13', o.open || 0, 'Open', '', 'var(--status-yellow)') +
      _statCard('\u2705', resolved, 'Resolved', '', 'var(--status-green)') +
      _statCard('\uD83D\uDCC8', resRate + '%', 'Resolution Rate', '', resRate >= 70 ? 'var(--status-green)' : resRate >= 40 ? 'var(--status-yellow)' : 'var(--status-red)') +
      _statCard('\uD83D\uDD25', critHigh, 'Critical / Major', '', critHigh > 0 ? 'var(--status-red)' : 'var(--status-green)');
  }

  function _renderJiraTrendChart(trends) {
    var labels = trends.map(function (t) { return t.month; });

    var types = {};
    trends.forEach(function (t) {
      Object.keys(t).forEach(function (k) {
        if (k !== 'month' && k !== 'total') types[k] = true;
      });
    });
    var typeNames = Object.keys(types).slice(0, 6);
    var datasets = typeNames.map(function (name, idx) {
      return {
        label: name,
        data: trends.map(function (t) { return t[name] || 0; }),
        backgroundColor: PAL[idx % PAL.length],
        borderRadius: 4
      };
    });

    if (_charts.jiraTrend) _charts.jiraTrend.destroy();
    _charts.jiraTrend = new Chart(document.getElementById('chartJiraTrend'), {
      type: 'bar',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { stacked: true, grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 }) },
          y: { stacked: true, grid: gridLine, ticks: Object.assign({}, tickColor, { stepSize: 5 }) }
        },
        plugins: { legend: { labels: chartLeg, position: 'top' }, tooltip: chartTT }
      }
    });
  }

  function _renderJiraToolChart(byTool) {
    var labels = byTool.map(function (t) { return t.tool; });
    var values = byTool.map(function (t) { return t.count; });

    if (_charts.jiraTool) _charts.jiraTool.destroy();
    _charts.jiraTool = new Chart(document.getElementById('chartJiraTool'), {
      type: 'doughnut',
      data: { labels: labels, datasets: [{ data: values, backgroundColor: PAL.slice(0, labels.length), borderWidth: 0, hoverOffset: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'right', labels: chartLeg }, tooltip: chartTT } }
    });
  }

  function _renderJiraTable(byTool) {
    var tbody = document.getElementById('jiraToolBody');
    if (!byTool.length) { tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:24px;color:var(--text-muted)">No Jira data available. Configure JIRA credentials in .env</td></tr>'; return; }
    var total = byTool.reduce(function (s, t) { return s + t.count; }, 0);
    var html = '';
    byTool.forEach(function (t) {
      var pct = total > 0 ? (t.count / total * 100).toFixed(1) : 0;
      html += '<tr><td style="font-weight:700;color:var(--text-primary)">' + esc(t.tool) + '</td>' +
        '<td class="mono">' + t.count + '</td>' +
        '<td><div style="display:flex;align-items:center;gap:8px"><div style="width:100px;height:6px;background:var(--border-color);border-radius:3px;overflow:hidden"><div style="height:100%;width:' + pct + '%;background:var(--accent-primary);border-radius:3px"></div></div><span class="mono" style="font-size:11px;color:var(--text-muted)">' + pct + '%</span></div></td></tr>';
    });
    tbody.innerHTML = html;
  }

  var _jiraTicketPage = 1;
  var _jiraTicketPageSize = 10;
  var _jiraTicketFiltered = [];

  function _renderJiraTickets(issues, page) {
    _jiraTicketFiltered = issues || [];
    _jiraTicketPage = page || 1;
    var tbody = document.getElementById('jiraTicketBody');
    if (!_jiraTicketFiltered.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--text-muted)">No tickets found</td></tr>';
      document.getElementById('jiraTicketPagination').innerHTML = '';
      return;
    }
    var start = (_jiraTicketPage - 1) * _jiraTicketPageSize;
    var pageIssues = _jiraTicketFiltered.slice(start, start + _jiraTicketPageSize);
    var html = '';
    pageIssues.forEach(function (i) {
      var prioColor = i.priority === 'Critical' || i.priority === 'Blocker' ? 'var(--status-red)' : i.priority === 'Major' ? 'var(--status-yellow)' : 'var(--text-secondary)';
      var statusColor = i.status_category === 'Done' || i.status_category === 'Complete' ? 'var(--status-green)' : 'var(--accent-primary)';
      html += '<tr>' +
        '<td><a href="' + esc(i.url) + '" target="_blank" style="color:var(--accent-primary);font-weight:700;font-family:\'JetBrains Mono\',monospace;font-size:12px">' + esc(i.key) + '</a></td>' +
        '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(i.summary) + '">' + esc(i.summary) + '</td>' +
        '<td><span class="pill" style="background:var(--accent-primary-soft);color:var(--accent-primary)">' + esc(i.type) + '</span></td>' +
        '<td style="color:' + prioColor + ';font-weight:600;font-size:12px">' + esc(i.priority) + '</td>' +
        '<td style="color:' + statusColor + ';font-size:12px">' + esc(i.status) + '</td>' +
        '<td style="font-size:12px">' + esc(i.assignee) + '</td>' +
        '<td style="font-size:11px;color:var(--text-muted)">' + esc(i.tool) + '</td>' +
        '<td class="mono" style="font-size:11px">' + esc(i.created) + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = html;
    _renderJiraTicketPagination();
  }

  function _renderJiraTicketPagination() {
    var wrap = document.getElementById('jiraTicketPagination');
    var totalPages = Math.ceil(_jiraTicketFiltered.length / _jiraTicketPageSize);
    if (totalPages <= 1) { wrap.innerHTML = ''; return; }
    var btnStyle = 'cursor:pointer;border:1px solid var(--border-color);background:var(--bg-card);color:var(--text-primary);padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var activeStyle = 'cursor:pointer;border:1px solid var(--accent-primary);background:var(--accent-primary);color:#fff;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var html = '';
    if (_jiraTicketPage > 1) html += '<button style="' + btnStyle + '" onclick="jiraTicketGoPage(' + (_jiraTicketPage - 1) + ')">\u2039</button>';
    var startP = Math.max(1, _jiraTicketPage - 3);
    var endP = Math.min(totalPages, startP + 6);
    for (var p = startP; p <= endP; p++) {
      html += '<button style="' + (p === _jiraTicketPage ? activeStyle : btnStyle) + '" onclick="jiraTicketGoPage(' + p + ')">' + p + '</button>';
    }
    if (_jiraTicketPage < totalPages) html += '<button style="' + btnStyle + '" onclick="jiraTicketGoPage(' + (_jiraTicketPage + 1) + ')">\u203A</button>';
    html += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + _jiraTicketFiltered.length + ' tickets</span>';
    wrap.innerHTML = html;
  }

  window.jiraTicketGoPage = function (p) { _renderJiraTickets(_jiraTicketFiltered, p); };

  window.filterJiraTickets = function () {
    var search = (document.getElementById('jiraTicketSearch').value || '').toLowerCase();
    if (!search) { _renderJiraTickets(_jiraAllTickets, 1); return; }
    var filtered = _jiraAllTickets.filter(function (i) {
      return (i.key || '').toLowerCase().indexOf(search) > -1 ||
        (i.summary || '').toLowerCase().indexOf(search) > -1 ||
        (i.assignee || '').toLowerCase().indexOf(search) > -1 ||
        (i.tool || '').toLowerCase().indexOf(search) > -1 ||
        (i.status || '').toLowerCase().indexOf(search) > -1;
    });
    _renderJiraTickets(filtered, 1);
  };

  window.exportJiraCSV = function () {
    var issues = _jiraTicketFiltered.length ? _jiraTicketFiltered : _jiraAllTickets;
    if (!issues || !issues.length) { showToast('No tickets to export', 'error'); return; }
    var rows = [['Key', 'Summary', 'Type', 'Priority', 'Status', 'Assignee', 'Tool', 'Created', 'URL']];
    issues.forEach(function (i) {
      rows.push([i.key, i.summary, i.type, i.priority, i.status, i.assignee, i.tool, i.created, i.url]);
    });
    var csv = rows.map(function (r) {
      return r.map(function (c) { return '"' + String(c || '').replace(/"/g, '""') + '"'; }).join(',');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'jira_tickets_' + (_jiraProject || 'all') + '_' + new Date().toISOString().split('T')[0] + '.csv';
    a.click();
    showToast('CSV downloaded (' + issues.length + ' tickets)', 'success');
  };

  /* ── GRAFANA TAB ── */
  var _grafanaPeriodDays = 365;
  var _grafanaCustomFrom = null;
  var _grafanaCustomTo = null;
  var _grafanaAllUsers = [];

  window.setGrafanaPeriod = function (days) {
    _grafanaPeriodDays = days;
    _grafanaCustomFrom = null;
    _grafanaCustomTo = null;
    document.querySelectorAll('.grafana-period-btn').forEach(function (b) {
      b.classList.toggle('active', parseInt(b.getAttribute('data-gf-period')) === days);
    });
    _reloadGrafanaFiltered();
  };

  window.applyGrafanaDateRange = function () {
    var from = document.getElementById('grafanaDateFrom').value;
    var to = document.getElementById('grafanaDateTo').value;
    if (!from || !to) { showToast('Select both dates', 'error'); return; }
    _grafanaCustomFrom = from;
    _grafanaCustomTo = to;
    document.querySelectorAll('.grafana-period-btn').forEach(function (b) { b.classList.remove('active'); });
    _reloadGrafanaFiltered();
  };

  function _reloadGrafanaFiltered() {
    var filtered = _applyGrafanaDateFilter(_grafanaAllUsers);
    _renderGrafanaTimelineChart(filtered);
    _renderGrafanaUserTable(filtered, 1);
  }

  function loadGrafana() {
    Promise.all([api('/api/grafana/users'), api('/api/grafana/panels')])
      .then(function (res) {
        var userData = res[0] || {};
        var panelData = res[1] || {};

        var users = userData.users || [];
        _grafanaAllUsers = users;

        var allSummary = _computeGrafanaSummary(users);
        var filtered = _applyGrafanaDateFilter(users);

        _renderGrafanaCards(allSummary);
        _renderGrafanaActivityChart(allSummary);
        _renderGrafanaTimelineChart(filtered);
        _renderGrafanaEngagement(allSummary);
        _renderGrafanaAuthChart(users);
        _renderGrafanaRecentUsers(users);
        _renderGrafanaUserTable(filtered, 1);
        _renderGrafanaPanels(panelData.panels || []);
      });
  }

  function _renderGrafanaEngagement(s) {
    var wrap = document.getElementById('grafanaEngagement');
    if (!wrap) return;
    var total = s.total_users || 1;
    var adoptionPct = Math.round(((s.active_7d || 0) + (s.active_30d || 0)) / total * 100);
    var dormantPct = Math.round((s.inactive || 0) / total * 100);
    var neverPct = Math.round((s.never_logged || 0) / total * 100);

    function _bar(label, count, pct, color) {
      return '<div style="margin-bottom:12px">' +
        '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
        '<span style="font-size:12px;font-weight:600;color:var(--text-primary)">' + label + '</span>' +
        '<span style="font-size:12px;font-weight:700;color:' + color + '">' + count + ' (' + pct + '%)</span></div>' +
        '<div style="height:8px;background:var(--border-color);border-radius:4px;overflow:hidden">' +
        '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:4px;transition:width .5s"></div></div></div>';
    }

    wrap.innerHTML =
      _bar('Active Users (30d)', (s.active_7d || 0) + (s.active_30d || 0), adoptionPct, 'var(--status-green)') +
      _bar('Dormant (30d+)', s.inactive || 0, dormantPct, 'var(--status-red)') +
      _bar('Never Logged In', s.never_logged || 0, neverPct, '#64748b');
  }

  function _renderGrafanaAuthChart(users) {
    var authMap = {};
    users.forEach(function (u) {
      var labels = u.authLabels || [];
      var auth = labels.length ? labels[0] : 'Unknown';
      authMap[auth] = (authMap[auth] || 0) + 1;
    });
    var names = Object.keys(authMap).sort(function (a, b) { return authMap[b] - authMap[a]; });
    var values = names.map(function (n) { return authMap[n]; });

    _destroyChart('grafanaAuth');
    var el = document.getElementById('chartGrafanaAuth');
    if (!el || !names.length) return;
    _charts.grafanaAuth = new Chart(el.getContext('2d'), {
      type: 'doughnut',
      data: { labels: names, datasets: [{ data: values, backgroundColor: PAL.slice(0, names.length), borderWidth: 0, hoverOffset: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'right', labels: chartLeg }, tooltip: chartTT } }
    });
  }

  function _renderGrafanaRecentUsers(users) {
    var wrap = document.getElementById('grafanaRecentUsers');
    if (!wrap) return;
    var recent = users.filter(function (u) {
      return u.days_ago !== null && u.days_ago !== undefined && u.days_ago <= 7;
    }).sort(function (a, b) { return (a.days_ago || 0) - (b.days_ago || 0); });

    if (!recent.length) {
      wrap.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:12px">No users active in the last 7 days</div>';
      return;
    }
    var html = '';
    recent.forEach(function (u) {
      var name = u.name || u.login;
      var dayLabel = u.days_ago === 0 ? 'Today' : u.days_ago + 'd ago';
      html += '<div style="display:inline-flex;align-items:center;gap:6px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:6px;padding:6px 12px">' +
        '<span style="color:var(--status-green);font-size:8px">\u25CF</span>' +
        '<span style="font-size:12px;font-weight:600;color:var(--text-primary)">' + esc(name) + '</span>' +
        '<span style="font-size:10px;color:var(--text-muted)">' + dayLabel + '</span></div>';
    });
    wrap.innerHTML = html;
  }

  function _applyGrafanaDateFilter(users) {
    if (_grafanaCustomFrom && _grafanaCustomTo) {
      var from = new Date(_grafanaCustomFrom);
      var to = new Date(_grafanaCustomTo);
      return users.filter(function (u) {
        if (!u.lastSeenAt || u.lastSeenAt === '0001-01-01T00:00:00Z') return true;
        var seen = new Date(u.lastSeenAt);
        return seen >= from && seen <= to;
      });
    }
    return users.filter(function (u) {
      if (u.days_ago === null || u.days_ago === undefined) return true;
      return u.days_ago <= _grafanaPeriodDays;
    });
  }

  function _computeGrafanaSummary(users) {
    var s = { total_users: users.length, active_7d: 0, active_30d: 0, inactive: 0, never_logged: 0 };
    users.forEach(function (u) {
      if (u.status === 'active_7d') s.active_7d++;
      else if (u.status === 'active_30d') s.active_30d++;
      else if (u.status === 'inactive') s.inactive++;
      else s.never_logged++;
    });
    return s;
  }

  function _getFilteredGrafanaUsers() {
    var status = document.getElementById('grafanaUserFilter').value;
    var search = (document.getElementById('grafanaUserSearch').value || '').toLowerCase();
    var users = _applyGrafanaDateFilter(_grafanaAllUsers);
    return users.filter(function (u) {
      if (status && u.status !== status) return false;
      if (search && (u.login || '').toLowerCase().indexOf(search) === -1 &&
          (u.name || '').toLowerCase().indexOf(search) === -1 &&
          (u.email || '').toLowerCase().indexOf(search) === -1) return false;
      return true;
    });
  }

  function _renderGrafanaCards(s) {
    document.getElementById('grafanaCards').innerHTML =
      _statCard('👥', s.total_users || 0, 'Non-Admin Users', '', 'var(--accent-secondary)') +
      _statCard('🟢', s.active_7d || 0, 'Active (7 days)', '', 'var(--status-green)') +
      _statCard('🟡', s.active_30d || 0, 'Active (30 days)', '', 'var(--status-yellow)') +
      _statCard('🔴', s.inactive || 0, 'Inactive (30d+)', '', 'var(--status-red)') +
      _statCard('👻', s.never_logged || 0, 'Never Logged In', '', 'var(--text-muted)');
  }

  function _renderGrafanaActivityChart(s) {
    if (_charts.grafanaActivity) _charts.grafanaActivity.destroy();
    _charts.grafanaActivity = new Chart(document.getElementById('chartGrafanaActivity'), {
      type: 'doughnut',
      data: {
        labels: ['Active (7d)', 'Active (30d)', 'Inactive (30d+)', 'Never Logged'],
        datasets: [{
          data: [s.active_7d || 0, s.active_30d || 0, s.inactive || 0, s.never_logged || 0],
          backgroundColor: ['#34d399', '#fbbf24', '#f87171', '#64748b'],
          borderWidth: 0, hoverOffset: 6
        }]
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'right', labels: chartLeg }, tooltip: chartTT } }
    });
  }

  function _renderGrafanaTimelineChart(users) {
    var buckets = { '0-1d': 0, '2-7d': 0, '8-14d': 0, '15-30d': 0, '31-90d': 0, '90d+': 0, 'Never': 0 };
    users.forEach(function (u) {
      var d = u.days_ago;
      if (d === null || d === undefined) buckets['Never']++;
      else if (d <= 1) buckets['0-1d']++;
      else if (d <= 7) buckets['2-7d']++;
      else if (d <= 14) buckets['8-14d']++;
      else if (d <= 30) buckets['15-30d']++;
      else if (d <= 90) buckets['31-90d']++;
      else buckets['90d+']++;
    });

    if (_charts.grafanaTimeline) _charts.grafanaTimeline.destroy();
    _charts.grafanaTimeline = new Chart(document.getElementById('chartGrafanaTimeline'), {
      type: 'bar',
      data: {
        labels: Object.keys(buckets),
        datasets: [{
          label: 'Users',
          data: Object.values(buckets),
          backgroundColor: ['#34d399', '#2dd4bf', '#fbbf24', '#fb923c', '#f87171', '#dc2626', '#64748b'],
          borderRadius: 4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: gridLine, ticks: tickColor } },
        plugins: { legend: { display: false }, tooltip: chartTT }
      }
    });
  }

  var _grafanaUserPage = 1;
  var _grafanaUserPageSize = 10;
  var _grafanaUserFiltered = [];

  function _renderGrafanaUserTable(users, page) {
    _grafanaUserFiltered = users || [];
    _grafanaUserPage = page || 1;
    var tbody = document.getElementById('grafanaUserBody');
    if (!_grafanaUserFiltered.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-muted)">No user data. Configure GRAFANA_BASE_URL and GRAFANA_API_KEY in .env</td></tr>';
      document.getElementById('grafanaUserPagination').innerHTML = '';
      return;
    }
    var start = (_grafanaUserPage - 1) * _grafanaUserPageSize;
    var pageUsers = _grafanaUserFiltered.slice(start, start + _grafanaUserPageSize);
    var html = '';
    pageUsers.forEach(function (u) {
      var dot = u.status === 'active_7d' ? '🟢' : u.status === 'active_30d' ? '🟡' : u.status === 'inactive' ? '🔴' : '⚪';
      var daysText = u.days_ago !== null && u.days_ago !== undefined ? u.days_ago + 'd' : 'Never';
      var daysColor = u.days_ago === null ? 'var(--text-muted)' : u.days_ago <= 7 ? 'var(--status-green)' : u.days_ago <= 30 ? 'var(--status-yellow)' : 'var(--status-red)';
      var disabledBadge = u.isDisabled ? ' <span class="pill r" style="font-size:9px">DISABLED</span>' : '';
      html += '<tr>' +
        '<td style="text-align:center;font-size:14px">' + dot + '</td>' +
        '<td class="mono" style="color:var(--text-primary);font-weight:600">' + esc(u.login) + disabledBadge + '</td>' +
        '<td>' + esc(u.name) + '</td>' +
        '<td style="font-size:12px">' + esc(u.email) + '</td>' +
        '<td class="mono" style="font-size:11px">' + (u.lastSeenAtAge || u.lastSeenAt || '\u2014') + '</td>' +
        '<td class="mono" style="color:' + daysColor + ';font-weight:700">' + daysText + '</td>' +
        '<td style="font-size:11px;color:var(--text-muted)">' + esc((u.authLabels || []).join(', ') || '\u2014') + '</td>' +
        '</tr>';
    });
    tbody.innerHTML = html;
    _renderGrafanaUserPagination();
  }

  function _renderGrafanaUserPagination() {
    var wrap = document.getElementById('grafanaUserPagination');
    var totalPages = Math.ceil(_grafanaUserFiltered.length / _grafanaUserPageSize);
    if (totalPages <= 1) { wrap.innerHTML = ''; return; }
    var btnStyle = 'cursor:pointer;border:1px solid var(--border-color);background:var(--bg-card);color:var(--text-primary);padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var activeStyle = 'cursor:pointer;border:1px solid var(--accent-primary);background:var(--accent-primary);color:#fff;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;font-family:inherit';
    var html = '';
    if (_grafanaUserPage > 1) html += '<button style="' + btnStyle + '" onclick="grafanaUserGoPage(' + (_grafanaUserPage - 1) + ')">\u2039</button>';
    var startP = Math.max(1, _grafanaUserPage - 3);
    var endP = Math.min(totalPages, startP + 6);
    for (var p = startP; p <= endP; p++) {
      html += '<button style="' + (p === _grafanaUserPage ? activeStyle : btnStyle) + '" onclick="grafanaUserGoPage(' + p + ')">' + p + '</button>';
    }
    if (_grafanaUserPage < totalPages) html += '<button style="' + btnStyle + '" onclick="grafanaUserGoPage(' + (_grafanaUserPage + 1) + ')">\u203A</button>';
    html += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + _grafanaUserFiltered.length + ' users</span>';
    wrap.innerHTML = html;
  }

  window.grafanaUserGoPage = function (p) { _renderGrafanaUserTable(_grafanaUserFiltered, p); };

  window.filterGrafanaUsers = function () {
    var filtered = _getFilteredGrafanaUsers();
    _renderGrafanaUserTable(filtered, 1);
  };

  window.exportGrafanaUsersCSV = function () {
    var users = _grafanaUserFiltered.length ? _grafanaUserFiltered : _grafanaAllUsers;
    if (!users || !users.length) { showToast('No user data to export', 'error'); return; }
    var rows = [['Status', 'Login', 'Name', 'Email', 'Last Seen', 'Days Ago', 'Auth']];
    users.forEach(function (u) {
      var status = u.status === 'active_7d' ? 'Active (7d)' : u.status === 'active_30d' ? 'Active (30d)' : u.status === 'inactive' ? 'Inactive' : 'Unknown';
      var daysText = u.days_ago !== null && u.days_ago !== undefined ? u.days_ago : 'Never';
      rows.push([
        status,
        u.login || '',
        u.name || '',
        u.email || '',
        u.lastSeenAtAge || u.lastSeenAt || '',
        daysText,
        (u.authLabels || []).join('; ') || ''
      ]);
    });
    var csv = rows.map(function (r) {
      return r.map(function (c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(',');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'grafana_users_' + new Date().toISOString().split('T')[0] + '.csv';
    a.click();
    showToast('CSV downloaded (' + users.length + ' users)', 'success');
  };

  function _renderGrafanaPanels(panels) {
    var wrap = document.getElementById('grafanaPanels');
    if (!panels.length) { wrap.innerHTML = ''; return; }

    var dashGroups = {};
    panels.forEach(function (p) {
      if (!dashGroups[p.dashboard_uid]) dashGroups[p.dashboard_uid] = { title: p.dashboard_title, panels: [] };
      dashGroups[p.dashboard_uid].panels.push(p);
    });

    var html = '<div class="section-divider"></div>' +
      '<div class="section-header"><div><h3 class="section-title">Embedded Dashboards</h3>' +
      '<span class="section-subtitle">Opt-in Grafana panels</span></div></div>';
    Object.keys(dashGroups).forEach(function (uid) {
      var grp = dashGroups[uid];
      html += '<div style="margin-bottom:8px;font-size:14px;font-weight:600;color:var(--text-secondary)">' + esc(grp.title) + '</div>';
      html += '<div class="grafana-grid">';
      grp.panels.forEach(function (p) {
        html += '<div class="grafana-embed">' +
          '<div class="ge-title"><span class="badge" style="background:var(--accent-secondary-soft);color:var(--accent-secondary)">' + esc(p.panel_type) + '</span> ' + esc(p.panel_title) + '</div>' +
          '<iframe src="' + esc(p.embed_url) + '" loading="lazy"></iframe></div>';
      });
      html += '</div>';
    });
    wrap.innerHTML = html;
  }

  /* ── ChatOps TAB ── */
  var _chatopsPeriodDays = 30;
  var _chatopsCustomFrom = null;
  var _chatopsCustomTo = null;
  var _chatopsRaw = { summary: {}, activity: {}, channels: {}, mcp: {}, health: {} };

  window.setChatopsPeriod = function (days) {
    _chatopsPeriodDays = days;
    _chatopsCustomFrom = null;
    _chatopsCustomTo = null;
    document.querySelectorAll('.chatops-period-btn').forEach(function (b) {
      b.classList.toggle('active', parseInt(b.getAttribute('data-chatops-period')) === days);
    });
    _renderChatopsFiltered();
  };

  window.applyChatopsDateRange = function () {
    var from = document.getElementById('chatopsDateFrom').value;
    var to = document.getElementById('chatopsDateTo').value;
    if (!from || !to) { showToast('Select both dates', 'error'); return; }
    _chatopsCustomFrom = from;
    _chatopsCustomTo = to;
    document.querySelectorAll('.chatops-period-btn').forEach(function (b) { b.classList.remove('active'); });
    _renderChatopsFiltered();
  };

  function _chatopsCutoffDate() {
    if (_chatopsCustomFrom) return _chatopsCustomFrom;
    var d = new Date();
    d.setDate(d.getDate() - _chatopsPeriodDays);
    return d.toISOString().split('T')[0];
  }

  function _filterChatopsSeries(series) {
    if (!series || !series.length) return series || [];
    var from = _chatopsCutoffDate();
    var to = _chatopsCustomTo || '9999-12-31';
    return series.filter(function (d) {
      var dt = d.date || d.day || '';
      return dt >= from && dt <= to;
    });
  }

  function _filterChatopsDailyStats(ds) {
    if (!ds || typeof ds !== 'object') return ds;
    var from = _chatopsCutoffDate();
    var to = _chatopsCustomTo || '9999-12-31';
    var out = {};
    Object.keys(ds).forEach(function (dt) {
      if (dt >= from && dt <= to) out[dt] = ds[dt];
    });
    return out;
  }

  function _renderChatopsFiltered() {
    var summary = _chatopsRaw.summary;
    var activity = _chatopsRaw.activity;
    var channels = _chatopsRaw.channels;
    var mcpData = _chatopsRaw.mcp;

    _renderChatopsCards(summary, activity, mcpData);
    _renderChatopsServiceHealth(_chatopsRaw.health);
    _renderChatopsActivityChart(activity);
    _renderChatopsChannelsChart(channels);
    _renderChatopsMcpChart(mcpData);
  }

  function loadChatops() {
    Promise.all([
      api('/api/chatops/summary'),
      api('/api/chatops/activity'),
      api('/api/chatops/channels'),
      api('/api/chatops/mcp'),
      api('/api/chatops/health')
    ]).then(function (res) {
      _chatopsRaw.summary = res[0] || {};
      _chatopsRaw.activity = res[1] || {};
      _chatopsRaw.channels = res[2] || {};
      _chatopsRaw.mcp = res[3] || {};
      _chatopsRaw.health = res[4] || {};
      _renderChatopsFiltered();
    });
  }

  function _renderChatopsServiceHealth(data) {
    var wrap = document.getElementById('chatopsServiceHealth');
    if (!wrap) return;

    var services = (data && data.services) ? data.services : [];
    var podInfo = (data && data.pod) ? data.pod : null;

    if (!services.length && !podInfo) {
      wrap.innerHTML = '';
      return;
    }

    var html = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">' +
      '<span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text-secondary)">Service Health</span></div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:10px">';

    services.forEach(function (svc) {
      var s = (svc.status || '').toLowerCase();
      var ok = s === 'ok' || s === 'healthy' || s === 'up' || s === 'running';
      var dot = ok ? 'var(--status-green)' : 'var(--status-red)';
      var label = svc.name.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
      var envBadge = svc.env
        ? '<span style="font-size:9px;font-weight:600;padding:1px 6px;border-radius:4px;background:var(--accent-primary);color:#fff;margin-left:6px">' + esc(svc.env) + '</span>'
        : '';

      var extras = '';
      if (svc.restarts !== undefined) {
        var rc = parseInt(svc.restarts, 10);
        var rcColor = rc > 5 ? 'var(--status-red)' : rc > 0 ? 'var(--status-orange, #f59e0b)' : 'var(--text-muted)';
        extras += '<span style="font-size:10px;color:' + rcColor + ';font-weight:600">restarts: ' + rc + '</span>';
      }
      if (svc.ready !== undefined) {
        var rdyColor = svc.ready ? 'var(--status-green)' : 'var(--status-red)';
        extras += '<span style="font-size:10px;color:' + rdyColor + ';font-weight:600">ready: ' + (svc.ready ? 'yes' : 'no') + '</span>';
      }
      if (svc.age) {
        extras += '<span style="font-size:10px;color:var(--text-muted)">age: ' + esc(svc.age) + '</span>';
      }

      html += '<div style="display:flex;align-items:center;gap:8px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:10px 16px;min-width:220px">' +
        '<span style="width:10px;height:10px;border-radius:50%;background:' + dot + ';flex-shrink:0"></span>' +
        '<div style="display:flex;flex-direction:column;gap:2px">' +
        '<div style="display:flex;align-items:center;gap:6px">' +
        '<span style="font-size:13px;font-weight:600;color:var(--text-primary)">' + esc(label) + '</span>' +
        envBadge + '</div>' +
        (extras ? '<div style="display:flex;gap:10px">' + extras + '</div>' : '') +
        '</div>' +
        '<span style="margin-left:auto;font-size:12px;font-weight:600;color:' + dot + '">' + esc(svc.status) + '</span>' +
        '</div>';
    });

    html += '</div>';
    wrap.innerHTML = html;
  }

  function _renderChatopsCards(summaryData, activityData, mcpData) {
    var wrap = document.getElementById('chatopsCards');
    if (!wrap) return;

    var prod = summaryData.production || summaryData || {};
    var actProd = (activityData.production || activityData || {});
    var mcp = mcpData || {};
    var adoption = mcp.adoption || {};

    var series = _chatopsGetFilteredSeries(actProd);
    var teamsMessages = 0, mailsSent = 0, uniqueUsers = 0, mcpCalls = 0, errors = 0;
    var allUsers = {};

    if (series.length) {
      series.forEach(function (d) {
        teamsMessages += d.requests || d.messages || 0;
        mcpCalls += d.mcp_calls || 0;
        errors += d.errors || 0;
        if (d.users) allUsers[d.users] = true;
      });
      uniqueUsers = series.reduce(function (max, d) { return Math.max(max, d.users || d.unique_users || 0); }, 0);
    } else {
      teamsMessages = prod.teams_messages || 0;
      uniqueUsers = actProd.total_users || prod.unique_users || 0;
      mcpCalls = mcp.total_calls || 0;
      errors = prod.errors_5xx || prod.errors || 0;
    }

    var mailObj = actProd.mail || prod.mail || {};
    mailsSent = mailObj.mails_sent || 0;

    var mcpPct = adoption.pct || 0;
    var adoptStr = mcpPct ? mcpPct + '%' : '0%';
    var mcpDetail = adoption.mcp_users && adoption.total_users
      ? adoption.mcp_users + '/' + adoption.total_users + ' users'
      : '';
    var pLabel = _chatopsCustomFrom ? 'custom' : _chatopsPeriodDays + 'D';

    wrap.innerHTML =
      _statCard('\uD83D\uDCAC', fmtNum(teamsMessages), 'Messages (' + pLabel + ')', '', 'var(--accent-primary)') +
      _statCard('\uD83D\uDCE7', fmtNum(mailsSent), 'Mails Sent (' + pLabel + ')', '', 'var(--accent-teal)') +
      _statCard('\uD83D\uDC64', uniqueUsers, 'Unique Users', '', 'var(--accent-orange)') +
      _statCard('\uD83D\uDD27', fmtNum(mcpCalls), 'MCP Tool Calls (' + pLabel + ')', '', 'var(--accent-secondary)') +
      _statCard('\uD83D\uDE80', adoptStr, 'MCP Adoption', mcpDetail, 'var(--status-green)') +
      _statCard('\u26A0\uFE0F', errors, 'Errors', '', errors > 0 ? 'var(--status-red)' : 'var(--status-green)');
  }

  function _chatopsGetFilteredSeries(actProd) {
    var series = actProd.daily || actProd.activity || [];
    if (!series.length && Array.isArray(actProd)) series = actProd;
    if (!series.length && actProd.daily_stats && typeof actProd.daily_stats === 'object') {
      var ds = actProd.daily_stats;
      series = Object.keys(ds).sort().map(function (dt) {
        return { date: dt, users: ds[dt].unique_users || 0, requests: ds[dt].messages || 0, mcp_calls: ds[dt].mcp_calls || 0, mails_sent: ds[dt].mails_sent || 0, errors: ds[dt].errors || 0 };
      });
    }
    return _filterChatopsSeries(series);
  }

  function _renderChatopsActivityChart(data) {
    _destroyChart('chatopsActivity');
    var el = document.getElementById('chartChatopsActivity');
    if (!el) return;

    var prod = data.production || data || {};
    var series = _chatopsGetFilteredSeries(prod);

    if (!series.length) {
      el.style.display = 'none';
      var sib = el.parentElement.querySelector('.chatops-empty');
      if (!sib) { sib = document.createElement('div'); sib.className = 'chatops-empty'; sib.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:13px'; sib.textContent = 'No activity data available'; el.parentElement.appendChild(sib); }
      sib.style.display = 'flex';
      return;
    }
    el.style.display = '';
    var oldEmpty = el.parentElement.querySelector('.chatops-empty');
    if (oldEmpty) oldEmpty.style.display = 'none';

    var labels = series.map(function (d) {
      var raw = d.date || d.day || '';
      if (raw.length >= 10) return raw.substring(5);
      return raw;
    });
    var users = series.map(function (d) { return d.users || d.unique_users || 0; });
    var messages = series.map(function (d) { return d.requests || d.total_requests || d.messages || 0; });
    var mcpCalls = series.map(function (d) { return d.mcp_calls || 0; });

    _charts.chatopsActivity = new Chart(el.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Messages', data: messages, borderColor: PAL[1], backgroundColor: PAL[1] + '22', fill: true, tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5 },
          { label: 'MCP Calls', data: mcpCalls, borderColor: PAL[2], backgroundColor: PAL[2] + '22', fill: false, tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5 },
          { label: 'Users', data: users, borderColor: PAL[0], backgroundColor: PAL[0] + '22', fill: false, tension: 0.35, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, yAxisID: 'y1' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { labels: chartLeg, position: 'top' },
          tooltip: { backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#e2e8f0', borderColor: 'rgba(56,189,248,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8 }
        },
        scales: {
          x: { grid: gridLine, ticks: Object.assign({}, tickColor, { maxRotation: 45, autoSkip: true, maxTicksLimit: 14, font: { size: 10 } }) },
          y: { grid: gridLine, ticks: tickColor, title: { display: true, text: 'Messages / Calls', color: tickColor.color, font: { size: 11 } } },
          y1: { position: 'right', grid: { display: false }, ticks: tickColor, title: { display: true, text: 'Users', color: tickColor.color, font: { size: 11 } } }
        }
      }
    });
  }

  function _renderChatopsChannelsChart(data) {
    _destroyChart('chatopsChannels');
    var el = document.getElementById('chartChatopsChannels');
    if (!el) return;

    var channelLabels = {
      mail_forward: 'Mail \u2192 Teams',
      teams_direct: 'Teams Direct',
      mail_direct: 'Mail Direct',
      teams_forward: 'Teams \u2192 Mail'
    };
    var items = [];
    if (data && typeof data === 'object') {
      Object.keys(data).forEach(function (k) {
        if (k === 'total_messages' || k === '_cached' || k === 'ts') return;
        var val = data[k];
        if (val && typeof val === 'object' && typeof val.messages === 'number') {
          items.push({ name: channelLabels[k] || k.replace(/_/g, ' '), count: val.messages, pct: val.pct || 0 });
        } else if (typeof val === 'number') {
          items.push({ name: channelLabels[k] || k.replace(/_/g, ' '), count: val });
        }
      });
    } else if (Array.isArray(data)) {
      items = data;
    }

    if (!items.length) {
      el.style.display = 'none';
      var sib = el.parentElement.querySelector('.chatops-empty');
      if (!sib) { sib = document.createElement('div'); sib.className = 'chatops-empty'; sib.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:13px'; sib.textContent = 'No channel data'; el.parentElement.appendChild(sib); }
      sib.style.display = 'flex';
      return;
    }
    el.style.display = '';
    var oldEmpty = el.parentElement.querySelector('.chatops-empty');
    if (oldEmpty) oldEmpty.style.display = 'none';

    var names = items.map(function (i) { return i.name || i.channel || 'Unknown'; });
    var values = items.map(function (i) { return i.count || i.value || i.messages || 0; });

    _charts.chatopsChannels = new Chart(el.getContext('2d'), {
      type: 'doughnut',
      data: { labels: names, datasets: [{ data: values, backgroundColor: PAL.slice(0, names.length), borderWidth: 0, hoverOffset: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '58%',
        plugins: {
          legend: { position: 'right', labels: chartLeg },
          tooltip: {
            backgroundColor: 'rgba(15,23,42,0.95)', titleColor: '#f1f5f9', bodyColor: '#e2e8f0',
            borderColor: 'rgba(56,189,248,0.3)', borderWidth: 1, padding: 10, cornerRadius: 8,
            callbacks: {
              label: function (ctx) {
                var item = items[ctx.dataIndex];
                var pctStr = item && item.pct ? ' (' + item.pct + '%)' : '';
                return ctx.label + ': ' + ctx.formattedValue + ' msgs' + pctStr;
              }
            }
          }
        }
      }
    });
  }

  function _renderChatopsMcpChart(data) {
    _destroyChart('chatopsMcp');
    var el = document.getElementById('chartChatopsMcp');
    if (!el) return;

    var items = [];
    if (data && Array.isArray(data.tools)) {
      items = data.tools.map(function (t) {
        return { name: t.tool || t.name || 'Unknown', count: t.count || t.calls || 0 };
      });
    } else if (Array.isArray(data)) {
      items = data.map(function (t) {
        return { name: t.tool || t.name || 'Unknown', count: t.count || t.calls || 0 };
      });
    }

    if (!items.length) {
      el.style.display = 'none';
      var sib = el.parentElement.querySelector('.chatops-empty');
      if (!sib) { sib = document.createElement('div'); sib.className = 'chatops-empty'; sib.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:13px'; sib.textContent = 'No MCP tool data'; el.parentElement.appendChild(sib); }
      sib.style.display = 'flex';
      return;
    }
    el.style.display = '';
    var oldEmpty = el.parentElement.querySelector('.chatops-empty');
    if (oldEmpty) oldEmpty.style.display = 'none';

    items.sort(function (a, b) { return (b.count || 0) - (a.count || 0); });
    var top = items.slice(0, 15);
    var names = top.map(function (i) { return i.name; });
    var values = top.map(function (i) { return i.count; });

    _charts.chatopsMcp = new Chart(el.getContext('2d'), {
      type: 'bar',
      data: { labels: names, datasets: [{ label: 'Calls', data: values, backgroundColor: names.map(function (n) { return _toolColor(n).bg; }), borderRadius: 4 }] },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false }, tooltip: chartTT },
        scales: { x: { grid: gridLine, ticks: tickColor }, y: { grid: { display: false }, ticks: Object.assign({}, tickColor, { font: { size: 11 } }) } }
      }
    });
  }

  /* ── Refresh ── */
  window.refreshAll = function () {
    _clearApiCache();
    _autoRefreshRemaining = _autoRefreshInterval;
    _updateCountdownUI();
    var badge = document.getElementById('refreshBadge');
    badge.classList.add('loading');
    document.getElementById('refreshTime').textContent = 'Refreshing...';

    fetch(API + '/api/refresh', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        badge.classList.remove('loading');
        if (d.success) {
          showToast('All data refreshed', 'success');
          _reloadCurrentTab();
          setTimeout(_prefetchAll, 2000);
        } else {
          showToast('Refresh completed with errors', 'error');
        }
        document.getElementById('refreshTime').textContent = fmtDate(new Date().toISOString());
      })
      .catch(function () {
        badge.classList.remove('loading');
        document.getElementById('refreshTime').textContent = 'Error';
        showToast('Refresh failed', 'error');
      });
  };

  /* ── Theme Toggle ── */
  function _getTheme() { return localStorage.getItem('at-dash-theme') || 'dark'; }
  function _applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeIcon').textContent = theme === 'dark' ? '🌙' : '☀️';
    document.getElementById('themeLabel').textContent = theme === 'dark' ? 'Dark' : 'Light';
    var _cc2 = _chartColors();
    chartTT = _cc2.chartTT; chartLeg = _cc2.chartLeg; gridLine = _cc2.gridLine; tickColor = _cc2.tickColor;
  }
  window.toggleTheme = function () {
    var current = _getTheme();
    var next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('at-dash-theme', next);
    _applyTheme(next);
    _reloadCurrentTab();
  };

  /* ── Auto-refresh ── */
  var _autoRefreshEnabled = true;
  var _autoRefreshInterval = 300;
  var _autoRefreshRemaining = 300;
  var _countdownTimer = null;

  function _updateCountdownUI() {
    var dot = document.getElementById('autoRefreshDot');
    var label = document.getElementById('autoRefreshLabel');
    var countdown = document.getElementById('autoRefreshCountdown');
    if (!dot) return;
    if (_autoRefreshEnabled) {
      dot.style.background = 'var(--status-green)';
      label.textContent = 'Auto';
      var m = Math.floor(_autoRefreshRemaining / 60);
      var s = _autoRefreshRemaining % 60;
      countdown.textContent = m + ':' + (s < 10 ? '0' : '') + s;
    } else {
      dot.style.background = 'var(--text-muted)';
      label.textContent = 'Paused';
      countdown.textContent = '';
    }
  }

  function startAutoRefresh() {
    _autoRefreshRemaining = _autoRefreshInterval;
    if (_countdownTimer) clearInterval(_countdownTimer);
    _countdownTimer = setInterval(function () {
      if (!_autoRefreshEnabled) return;
      _autoRefreshRemaining--;
      if (_autoRefreshRemaining <= 0) {
        _autoRefreshRemaining = _autoRefreshInterval;
        _clearApiCache();
        _tabInited = {};
        var active = document.querySelector('.tab-btn.active');
        if (active) {
          var tab = active.getAttribute('data-tab');
          _tabInited[tab] = true;
          initTab(tab);
        }
        setTimeout(_prefetchAll, 2000);
        document.getElementById('refreshTime').textContent = fmtDate(new Date().toISOString());
      }
      _updateCountdownUI();
    }, 1000);
    _updateCountdownUI();
  }

  window.toggleAutoRefresh = function () {
    _autoRefreshEnabled = !_autoRefreshEnabled;
    if (_autoRefreshEnabled) _autoRefreshRemaining = _autoRefreshInterval;
    _updateCountdownUI();
    showToast(_autoRefreshEnabled ? 'Auto-refresh enabled (5 min)' : 'Auto-refresh paused', _autoRefreshEnabled ? 'success' : 'info');
  };

  /* ── Init ── */
  function _prefetchAll() {
    var qs = _getMcpFilterQS();
    var gqs = _getFilterQS();
    [
      '/api/mcp-stats/summary' + qs,
      '/api/mcp-stats/applications' + qs,
      '/api/mcp-stats/users' + qs,
      '/api/mcp-stats/functions' + qs,
      '/api/mcp-stats/daily' + qs,
      '/api/mcp/status' + qs,
      '/api/mcp/metrics',
      '/api/grafana/users',
      '/api/grafana/panels',
      '/api/jira/open' + gqs,
      '/api/chatops/summary',
      '/api/chatops/activity',
      '/api/chatops/channels',
      '/api/chatops/mcp',
      '/api/chatops/health'
    ].forEach(function (p) { api(p); });
  }

  function _initMetaBadge() {
    var badge = document.getElementById('demoBadge');
    if (!badge) return;
    fetch(API + '/api/meta').then(function (r) { return r.json(); }).then(function (m) {
      if (m && m.demo_mode) {
        badge.style.display = 'inline-flex';
        badge.title = 'Running on synthetic demo data — no live systems connected';
      }
    }).catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    _applyTheme(_getTheme());
    _initMetaBadge();
    switchTab('overview');
    startAutoRefresh();
    setTimeout(_prefetchAll, 2000);
    document.getElementById('refreshTime').textContent = fmtDate(new Date().toISOString());

    var today = new Date().toISOString().split('T')[0];
    var yearAgo = new Date(Date.now() - 365 * 86400000).toISOString().split('T')[0];
    var fromEl = document.getElementById('globalDateFrom');
    var toEl = document.getElementById('globalDateTo');
    if (fromEl) { fromEl.value = yearAgo; fromEl.max = today; }
    if (toEl) { toEl.value = today; toEl.max = today; }

    var gfFrom = document.getElementById('grafanaDateFrom');
    var gfTo = document.getElementById('grafanaDateTo');
    if (gfFrom) { gfFrom.value = yearAgo; gfFrom.max = today; }
    if (gfTo) { gfTo.value = today; gfTo.max = today; }

    var ccFrom = document.getElementById('chatopsDateFrom');
    var ccTo = document.getElementById('chatopsDateTo');
    if (ccFrom) { ccFrom.value = yearAgo; ccFrom.max = today; }
    if (ccTo) { ccTo.value = today; ccTo.max = today; }
  });
})();
