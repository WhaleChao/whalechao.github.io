// ===== 喬政翔律師個人網站 - Main JS =====

document.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    initQRCode();
    loadSiteData();
    setCurrentYear();
});

// --- Navbar scroll effect & mobile toggle ---
function initNavbar() {
    const navbar = document.getElementById('navbar');
    const toggle = document.getElementById('navToggle');
    const menu = document.getElementById('navMenu');

    window.addEventListener('scroll', () => {
        navbar.classList.toggle('scrolled', window.scrollY > 20);
    });

    toggle.addEventListener('click', () => {
        menu.classList.toggle('active');
    });

    // Close menu on link click
    menu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            menu.classList.remove('active');
        });
    });
}

// --- QR Code generation ---
function initQRCode() {
    const container = document.getElementById('qrcode');
    if (!container) return;

    new QRCode(container, {
        text: 'https://line.me/ti/p/~0937753800',
        width: 180,
        height: 180,
        colorDark: '#1e293b',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.M
    });
}

// --- Load dynamic data ---
async function loadSiteData() {
    try {
        const response = await fetch('data/site-data.json');
        if (!response.ok) throw new Error('Data not found');
        const data = await response.json();
        renderStats(data.stats);
        renderCases(data.cases);
        renderNews(data.news);
        renderArticles(data.articles);
        renderLastUpdated(data.lastUpdated);
    } catch (err) {
        console.log('Using static fallback:', err.message);
        renderStats(null);
        renderCases([]);
        renderNews([]);
        renderArticles([]);
    }
}

// --- Render stats with count-up animation ---
function renderStats(stats) {
    if (!stats) return;

    const fields = {
        totalCases: stats.totalCases || 0,
        legalAidCases: stats.legalAidCases || 0,
        yearsOfPractice: stats.yearsOfPractice || 0,
        caseTypes: stats.caseTypes || 0
    };

    Object.entries(fields).forEach(([key, target]) => {
        const el = document.querySelector(`[data-field="${key}"]`);
        if (!el) return;
        animateNumber(el, target);
    });
}

function animateNumber(el, target) {
    const duration = 1500;
    const start = performance.now();
    const format = target >= 1000;

    function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        const current = Math.floor(ease * target);
        el.textContent = format ? current.toLocaleString() : current;
        if (progress < 1) requestAnimationFrame(update);
    }

    // Use IntersectionObserver to trigger on scroll
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                requestAnimationFrame(update);
                observer.disconnect();
            }
        });
    }, { threshold: 0.3 });

    observer.observe(el);
}

// --- Render cases ---
function renderCases(cases) {
    const container = document.getElementById('casesGrid');
    if (!container) return;

    if (!cases || cases.length === 0) {
        container.innerHTML = '<p class="empty-text">資料更新中...</p>';
        return;
    }

    // Sort by count descending
    const sorted = [...cases].sort((a, b) => (b.count || 0) - (a.count || 0));

    container.innerHTML = sorted.map(item => `
        <div class="case-tag">
            <span>${escapeHtml(item.type)}</span>
            ${item.count ? `<span class="case-count">${item.count}</span>` : ''}
        </div>
    `).join('');

    // Update subtitle with total
    const total = sorted.reduce((sum, c) => sum + (c.count || 0), 0);
    const subtitle = document.getElementById('casesSubtitle');
    if (subtitle && total > 0) {
        subtitle.textContent = `以下為公開判決書中曾承辦之案件類型統計，共 ${total.toLocaleString()} 筆`;
    }
}

// --- Render news ---
function renderNews(news) {
    const container = document.getElementById('newsList');
    if (!container) return;

    if (!news || news.length === 0) {
        container.innerHTML = '<p class="empty-text">暫無媒體報導</p>';
        return;
    }

    container.innerHTML = news.map(item => `
        <div class="news-item">
            <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
            <span class="news-meta">${escapeHtml(item.source || '')} ${escapeHtml(item.date || '')}</span>
        </div>
    `).join('');
}

// --- Render articles ---
function renderArticles(articles) {
    const container = document.getElementById('articlesList');
    if (!container) return;

    if (!articles || articles.length === 0) {
        // 隱藏整個發表文章區段
        const section = document.getElementById('articles');
        if (section) section.style.display = 'none';
        // 隱藏導覽列中的連結
        document.querySelectorAll('.nav-menu a[href="#articles"]').forEach(a => a.parentElement.style.display = 'none');
        return;
    }

    container.innerHTML = articles.map(item => `
        <div class="article-item">
            <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
            <span class="article-meta">${escapeHtml(item.date || '')}</span>
        </div>
    `).join('');
}

// --- Last updated ---
function renderLastUpdated(dateStr) {
    const el = document.getElementById('lastUpdated');
    if (!el || !dateStr) return;

    try {
        const date = new Date(dateStr);
        el.textContent = date.toLocaleDateString('zh-TW', {
            year: 'numeric', month: 'long', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch {
        el.textContent = dateStr;
    }
}

// --- Set current year ---
function setCurrentYear() {
    const el = document.getElementById('currentYear');
    if (el) el.textContent = new Date().getFullYear();
}

// --- XSS prevention ---
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
