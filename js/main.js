// ===== 喬政翔律師個人網站 - Tabbed Layout =====

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initQRCode();
    loadSiteData();
    setCurrentYear();
});

// --- Tab switching ---
function initTabs() {
    const btns = document.querySelectorAll('.tab-btn');
    const panes = document.querySelectorAll('.tab-pane');

    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;

            btns.forEach(b => b.classList.remove('active'));
            panes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById('tab-' + target).classList.add('active');
        });
    });
}

// --- QR Code ---
function initQRCode() {
    const container = document.getElementById('qrcode');
    if (!container) return;
    new QRCode(container, {
        text: 'https://line.me/ti/p/~0937753800',
        width: 150,
        height: 150,
        colorDark: '#1e293b',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.M
    });
}

// --- Load data ---
async function loadSiteData() {
    try {
        const response = await fetch('data/site-data.json');
        if (!response.ok) throw new Error('Data not found');
        const data = await response.json();
        renderStats(data.stats);
        renderCaseCategories(data.caseCategories);
        renderCases(data.cases);
        renderCourts(data.courts);
        renderNews(data.news);
        renderArticles(data.articles);
        renderLastUpdated(data.lastUpdated);
    } catch (err) {
        console.log('Using static fallback:', err.message);
    }
}

// --- Stats with animation ---
function renderStats(stats) {
    if (!stats) return;
    const fields = {
        totalCases: stats.totalCases || 0,
        legalAidCases: stats.legalAidCases || 0,
        yearsOfPractice: stats.yearsOfPractice || 0,
        judgments: stats.totalCases || 0
    };
    Object.entries(fields).forEach(([key, target]) => {
        const el = document.querySelector(`[data-field="${key}"]`);
        if (el) animateNumber(el, target);
    });
}

function animateNumber(el, target) {
    const duration = 1200;
    const start = performance.now();
    function update(now) {
        const progress = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.floor(ease * target).toLocaleString();
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// --- Case categories ---
function renderCaseCategories(cats) {
    if (!cats) return;
    const mapping = { '民事': 'catCivil', '刑事': 'catCriminal', '行政': 'catAdmin', '憲法': 'catConst' };
    Object.entries(mapping).forEach(([key, elId]) => {
        const el = document.getElementById(elId);
        if (el && cats[key] !== undefined) animateNumber(el, cats[key]);
    });
    const total = Object.values(cats).reduce((s, v) => s + v, 0);
    const subtitle = document.getElementById('casesSubtitle');
    if (subtitle && total > 0) {
        subtitle.textContent = `司法院裁判書系統公開判決統計，共 ${total.toLocaleString()} 筆`;
    }
}

// --- Case tags ---
function renderCases(cases) {
    const container = document.getElementById('casesGrid');
    if (!container) return;
    if (!cases || cases.length === 0) {
        container.innerHTML = '<p class="empty-text">資料更新中...</p>';
        return;
    }
    const filtered = cases.filter(c => !['訴訟救助', '聲請復權'].includes(c.type));
    const catOrder = {'民事': 0, '刑事': 1, '行政': 2, '憲法': 3};
    const sorted = [...filtered].sort((a, b) => {
        const catDiff = (catOrder[a.category] ?? 9) - (catOrder[b.category] ?? 9);
        return catDiff !== 0 ? catDiff : (b.count || 0) - (a.count || 0);
    });
    const catClass = (cat) => {
        if (cat === '民事') return 'cat-civil';
        if (cat === '刑事') return 'cat-criminal';
        if (cat === '行政') return 'cat-admin';
        if (cat === '憲法') return 'cat-const';
        return '';
    };
    container.innerHTML = sorted.map(item => `
        <div class="case-tag ${catClass(item.category)}">
            <span>${esc(item.type)}</span>
            ${item.count ? `<span class="case-count">${item.count}</span>` : ''}
        </div>
    `).join('');
}

// --- Courts ---
function renderCourts(courts) {
    const container = document.getElementById('courtsGrid');
    if (!container || !courts) return;
    const sorted = Object.entries(courts).sort((a, b) => b[1] - a[1]);
    container.innerHTML = sorted.map(([name, count]) => {
        const short = name
            .replace('臺灣', '').replace('地方法院', '地院').replace('高等法院', '高院')
            .replace('高等行政法院', '高行')
            .replace(/ 高等庭.*?$/, '').replace(/ 地方庭/, '');
        return `<div class="court-item"><span>${esc(short)}</span><span class="court-count">${count}</span></div>`;
    }).join('');
}

// --- News ---
function renderNews(news) {
    const container = document.getElementById('newsList');
    if (!container) return;
    if (!news || news.length === 0) {
        container.innerHTML = '<p class="empty-text">暫無媒體報導</p>';
        return;
    }
    container.innerHTML = news.map(item => `
        <div class="news-item">
            <a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>
            <span class="news-meta">${esc(item.source || '')} ${esc(item.date || '')}</span>
        </div>
    `).join('');
}

// --- Articles ---
function renderArticles(articles) {
    const section = document.getElementById('articles');
    const container = document.getElementById('articlesList');
    if (!container) return;
    if (!articles || articles.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    container.innerHTML = articles.map(item => `
        <div class="article-item">
            <a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>
            <span class="article-meta">${esc(item.date || '')}</span>
        </div>
    `).join('');
}

// --- Last updated ---
function renderLastUpdated(dateStr) {
    const el = document.getElementById('lastUpdated');
    if (!el || !dateStr) return;
    try {
        const d = new Date(dateStr);
        el.textContent = d.toLocaleDateString('zh-TW', {
            year: 'numeric', month: 'long', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch { el.textContent = dateStr; }
}

function setCurrentYear() {
    const el = document.getElementById('currentYear');
    if (el) el.textContent = new Date().getFullYear();
}

function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}
