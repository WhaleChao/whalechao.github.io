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
        renderCaseCategories(data.caseCategories);
        renderCases(data.cases);
        renderCourts(data.courts);
        renderNews(data.news);
        renderArticles(data.articles);
        renderLastUpdated(data.lastUpdated);
    } catch (err) {
        console.log('Using static fallback:', err.message);
        renderStats(null);
        renderCaseCategories(null);
        renderCases([]);
        renderCourts(null);
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
        judgments: stats.totalCases || 0
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

// --- Render case categories (4 big numbers) ---
function renderCaseCategories(cats) {
    if (!cats) return;
    const mapping = {
        '民事': 'catCivil',
        '刑事': 'catCriminal',
        '行政': 'catAdmin',
        '憲法': 'catConst'
    };
    Object.entries(mapping).forEach(([key, elId]) => {
        const el = document.getElementById(elId);
        if (el && cats[key] !== undefined) {
            animateNumber(el, cats[key]);
        }
    });

    // Update subtitle with total
    const total = Object.values(cats).reduce((s, v) => s + v, 0);
    const subtitle = document.getElementById('casesSubtitle');
    if (subtitle && total > 0) {
        subtitle.textContent = `司法院裁判書系統公開判決統計，共 ${total.toLocaleString()} 筆`;
    }
}

// --- Render case type tags ---
function renderCases(cases) {
    const container = document.getElementById('casesGrid');
    if (!container) return;

    if (!cases || cases.length === 0) {
        container.innerHTML = '<p class="empty-text">資料更新中...</p>';
        return;
    }

    // Filter out non-case-reasons, sort by category then count
    const filtered = cases.filter(c => !['訴訟救助', '聲請復權'].includes(c.type));
    const catOrder = {'民事': 0, '刑事': 1, '行政': 2, '憲法': 3};
    const sorted = [...filtered].sort((a, b) => {
        const catDiff = (catOrder[a.category] ?? 9) - (catOrder[b.category] ?? 9);
        if (catDiff !== 0) return catDiff;
        return (b.count || 0) - (a.count || 0);
    });

    const catClass = (cat) => {
        if (!cat) return '';
        if (cat === '民事') return 'cat-civil';
        if (cat === '刑事') return 'cat-criminal';
        if (cat === '行政') return 'cat-admin';
        if (cat === '憲法') return 'cat-const';
        return '';
    };

    container.innerHTML = sorted.map(item => `
        <div class="case-tag ${catClass(item.category)}">
            <span>${escapeHtml(item.type)}</span>
            ${item.count ? `<span class="case-count">${item.count}</span>` : ''}
        </div>
    `).join('');
}

// --- Render courts distribution ---
function renderCourts(courts) {
    const container = document.getElementById('courtsGrid');
    if (!container || !courts) return;

    const sorted = Object.entries(courts).sort((a, b) => b[1] - a[1]);
    container.innerHTML = sorted.map(([name, count]) => {
        // Shorten court names for display
        const short = name
            .replace('臺灣', '')
            .replace('地方法院', '地院')
            .replace('高等法院', '高院')
            .replace('高等行政法院', '高行')
            .replace(' 高等庭(含改制前臺北高等行政法院)', '')
            .replace(' 高等庭(含改制前高雄高等行政法院)', '')
            .replace(' 地方庭', '');
        return `<div class="court-item"><span>${escapeHtml(short)}</span><span class="court-count">${count}</span></div>`;
    }).join('');
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
