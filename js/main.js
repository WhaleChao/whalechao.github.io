// ===== 喬政翔律師個人網站 =====
// 資料驅動：data/site-data.json（統計、案件、報導、文章）與 data/content.json（首頁文字）
// 由 MAGI 網站後台寫入；此檔只負責讀取與呈現，不含任何寫死的業務數字。

(() => {
    'use strict';

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
        document.documentElement.classList.contains('still');
    const hasIO = 'IntersectionObserver' in window;
    const CASE_PREVIEW = 24;

    document.addEventListener('DOMContentLoaded', () => {
        initHeader();
        initReveal();
        setCurrentYear();
        loadContent();
        loadSiteData();
    });

    // ---------- 小工具 ----------
    function el(tag, attrs = {}, children = []) {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => {
            if (v === undefined || v === null || v === false) return;
            if (k === 'class') node.className = v;
            else if (k === 'text') node.textContent = v;
            else node.setAttribute(k, v);
        });
        [].concat(children).forEach(c => c && node.append(c));
        return node;
    }

    // 只允許 http(s) 與 mailto，避免後台資料帶入 javascript: 等連結
    function safeUrl(u) {
        try {
            const url = new URL(String(u || ''), location.href);
            return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? url.href : '';
        } catch { return ''; }
    }

    // ---------- Header：捲動陰影、行動選單、目前章節 ----------
    function initHeader() {
        const header = document.getElementById('siteHeader');
        const btn = document.getElementById('menuBtn');
        const nav = document.getElementById('siteNav');
        if (!header || !btn || !nav) return;

        const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 8);
        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });

        const setMenu = (open) => {
            btn.setAttribute('aria-expanded', String(open));
            btn.setAttribute('aria-label', open ? '關閉選單' : '開啟選單');
            nav.classList.toggle('open', open);
        };
        btn.addEventListener('click', () => setMenu(btn.getAttribute('aria-expanded') !== 'true'));
        nav.addEventListener('click', e => { if (e.target.closest('a')) setMenu(false); });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && nav.classList.contains('open')) { setMenu(false); btn.focus(); }
        });
        document.addEventListener('click', e => {
            if (nav.classList.contains('open') && !header.contains(e.target)) setMenu(false);
        });

        // 行動版選單收合時不可被 Tab 聚焦
        const mq = window.matchMedia('(max-width: 720px)');
        const syncInert = () => {
            const closedMobile = mq.matches && !nav.classList.contains('open');
            nav.toggleAttribute('inert', closedMobile);
        };
        new MutationObserver(syncInert).observe(nav, { attributes: true, attributeFilter: ['class'] });
        mq.addEventListener('change', syncInert);
        syncInert();

        // Scrollspy
        const links = [...nav.querySelectorAll('a[href^="#"]')];
        const map = new Map(links.map(a => [a.getAttribute('href').slice(1), a]));
        if (!hasIO) return;
        const spy = new IntersectionObserver(entries => {
            entries.forEach(en => {
                if (!en.isIntersecting) return;
                links.forEach(a => a.classList.remove('active'));
                const a = map.get(en.target.id);
                if (a) { a.classList.add('active'); a.setAttribute('aria-current', 'true'); }
                links.filter(x => x !== a).forEach(x => x.removeAttribute('aria-current'));
            });
        }, { rootMargin: '-45% 0px -50% 0px' });
        map.forEach((_, id) => { const s = document.getElementById(id); if (s) spy.observe(s); });
    }

    // ---------- 捲動顯現（僅在有 JS 時啟用，內容預設可見） ----------
    let revealObserver = null;
    function initReveal() {
        if (!hasIO || reduceMotion) return;
        revealObserver = new IntersectionObserver((entries) => {
            entries.forEach(en => {
                if (!en.isIntersecting) return;
                en.target.classList.add('in');
                revealObserver.unobserve(en.target);
            });
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
        observeReveal(document);
    }
    function observeReveal(root) {
        const sel = '.section-head, .about-content, .expertise-row, .stats-row, .record-block, ' +
                    '.news-item, .article-item, .contact-list, .contact-line, .articles-block';
        root.querySelectorAll(sel).forEach((n, i) => {
            if (n.classList.contains('reveal')) return;
            n.classList.add('reveal');
            if (n.classList.contains('expertise-row') && i % 2) n.classList.add('d1');
            revealObserver ? revealObserver.observe(n) : n.classList.add('in');
        });
    }

    // ---------- 首頁文字（後台「內容」） ----------
    async function loadContent() {
        try {
            const res = await fetch('data/content.json', { cache: 'no-cache' });
            if (!res.ok) return;
            const c = await res.json();
            const tagline = document.querySelector('.hero-tagline');
            if (tagline && c.hero_tagline && c.hero_tagline.trim()) tagline.textContent = c.hero_tagline.trim();
            const about = document.querySelector('.about-content');
            if (about && c.about_text && c.about_text.trim()) {
                const paras = c.about_text.trim().split(/\n{1,}/).map(t => t.trim()).filter(Boolean);
                about.replaceChildren(...paras.map(t => el('p', { text: t })));
            }
        } catch { /* 保留 HTML 內建文字 */ }
    }

    // ---------- 主要資料 ----------
    async function loadSiteData() {
        try {
            const res = await fetch('data/site-data.json', { cache: 'no-cache' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            safe(() => renderStats(data.stats));
            safe(() => renderCaseCategories(data.caseCategories, data.stats));
            safe(() => renderCases(data.cases));
            safe(() => renderCourts(data.courts));
            safe(() => renderNews(data.news));
            safe(() => renderArticles(data.articles));
            safe(() => renderLastUpdated(data.lastUpdated));
        } catch (err) {
            console.warn('site-data 載入失敗：', err.message);
            const msg = '資料暫時無法載入，請稍後重新整理。';
            ['newsList', 'articlesList'].forEach(id => {
                const c = document.getElementById(id);
                if (c) c.replaceChildren(el('p', { class: 'empty-text', text: msg }));
            });
        }
    }
    function safe(fn) { try { fn(); } catch (e) { console.warn(e); } }

    // ---------- 數字動畫（進入視窗才開始） ----------
    const numObserver = hasIO ? new IntersectionObserver(entries => {
        entries.forEach(en => {
            if (!en.isIntersecting) return;
            numObserver.unobserve(en.target);
            countUp(en.target, Number(en.target.dataset.target) || 0);
            const row = en.target.closest('.case-cat');
            if (row) row.classList.add('in');
        });
    }, { threshold: 0.4 }) : null;

    function setNumber(node, target) {
        node.dataset.target = String(target);
        if (reduceMotion || !numObserver) { node.textContent = target.toLocaleString(); return; }
        node.textContent = '0';
        numObserver.observe(node);
    }
    function countUp(node, target) {
        const duration = 1300, start = performance.now();
        const tick = now => {
            const p = Math.min((now - start) / duration, 1);
            node.textContent = Math.round((1 - Math.pow(1 - p, 3)) * target).toLocaleString();
            if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    // ---------- 統計 ----------
    function renderStats(stats) {
        if (!stats) return;
        const fields = {
            totalCases: stats.totalCases || 0,
            legalAidCases: stats.legalAidCases || 0,
            yearsOfPractice: stats.yearsOfPractice || 0
        };
        Object.entries(fields).forEach(([key, target]) => {
            const node = document.querySelector(`[data-field="${key}"]`);
            if (node) setNumber(node, target);
        });
    }

    // ---------- 案件類別 ----------
    function renderCaseCategories(cats, stats) {
        if (!cats) return;
        const mapping = { '民事': 'catCivil', '刑事': 'catCriminal', '行政': 'catAdmin', '憲法': 'catConst' };
        const max = Math.max(1, ...Object.values(cats).map(Number));
        Object.entries(mapping).forEach(([key, id]) => {
            const numEl = document.getElementById(id);
            if (!numEl || cats[key] === undefined) return;
            const row = numEl.closest('.case-cat');
            row.querySelector('.bar i').style.setProperty('--w', (Number(cats[key]) / max * 100).toFixed(1) + '%');
            setNumber(numEl, Number(cats[key]));
            if (reduceMotion || !numObserver) row.classList.add('in');
        });
        const total = Number(stats?.totalCases || 0) || Object.values(cats).reduce((s, v) => s + Number(v), 0);
        const subtitle = document.getElementById('casesSubtitle');
        if (subtitle && total > 0) {
            subtitle.textContent = `司法院裁判書系統公開判決統計，共 ${total.toLocaleString()} 筆`;
        }
    }

    // ---------- 常辦案由 ----------
    function renderCases(cases) {
        const block = document.getElementById('casesBlock');
        const container = document.getElementById('casesGrid');
        if (!container || !block || !Array.isArray(cases) || cases.length === 0) return;
        const catOrder = { '民事': 0, '刑事': 1, '行政': 2, '憲法': 3 };
        const sorted = cases
            .filter(c => c && c.type && !['訴訟救助', '聲請復權'].includes(c.type))
            .sort((a, b) => (b.count || 0) - (a.count || 0) || (catOrder[a.category] ?? 9) - (catOrder[b.category] ?? 9));
        if (!sorted.length) return;

        const tag = item => el('span', { class: 'case-tag' }, [
            el('span', { text: item.type }),
            item.count ? el('span', { class: 'case-count', text: item.count }) : null
        ]);
        const draw = (all) => container.replaceChildren(...(all ? sorted : sorted.slice(0, CASE_PREVIEW)).map(tag));
        draw(false);
        block.hidden = false;

        block.querySelector('.more-btn')?.remove();
        if (sorted.length > CASE_PREVIEW) {
            let open = false;
            const btn = el('button', { class: 'more-btn', type: 'button', 'aria-expanded': 'false' });
            const label = () => btn.textContent = open ? '收合' : `顯示全部 ${sorted.length} 種案由`;
            label();
            btn.addEventListener('click', () => {
                open = !open;
                btn.setAttribute('aria-expanded', String(open));
                draw(open); label();
            });
            block.append(btn);
        }
        observeReveal(block.parentElement);
    }

    // ---------- 承辦法院 ----------
    function renderCourts(courts) {
        const container = document.getElementById('courtsGrid');
        if (!container || !courts) return;
        const sorted = Object.entries(courts).sort((a, b) => b[1] - a[1]);
        const COURT_PREVIEW = 12;
        const row = ([name, count]) => el('li', { class: 'court-item' }, [
            el('span', { text: name.replace(/^臺灣/, '') }),
            el('span', { class: 'court-count', text: count })
        ]);
        const draw = all => container.replaceChildren(...(all ? sorted : sorted.slice(0, COURT_PREVIEW)).map(row));
        draw(false);
        container.parentElement.querySelector('.more-btn')?.remove();
        if (sorted.length > COURT_PREVIEW) {
            let open = false;
            const btn = el('button', { class: 'more-btn', type: 'button', 'aria-expanded': 'false' });
            const label = () => btn.textContent = open ? '收合' : `顯示全部 ${sorted.length} 所法院`;
            label();
            btn.addEventListener('click', () => { open = !open; btn.setAttribute('aria-expanded', String(open)); draw(open); label(); });
            container.after(btn);
        }
    }

    // ---------- 新聞 ----------
    function renderNews(news) {
        const container = document.getElementById('newsList');
        if (!container) return;
        if (!Array.isArray(news) || news.length === 0) {
            container.replaceChildren(el('p', { class: 'empty-text', text: '暫無媒體報導' }));
            return;
        }
        container.replaceChildren(...news.map(item => {
            const href = safeUrl(item.url);
            const meta = [item.source, item.date].filter(Boolean).join('　·　');
            return el('div', { class: 'news-item' }, [
                href ? el('a', { href, target: '_blank', rel: 'noopener', text: item.title || href })
                     : el('span', { text: item.title || '' }),
                meta ? el('span', { class: 'news-meta', text: meta }) : null
            ]);
        }));
        observeReveal(container);
    }

    // ---------- 文章 ----------
    function renderArticles(articles) {
        const section = document.getElementById('articles');
        const container = document.getElementById('articlesList');
        if (!container) return;
        if (!Array.isArray(articles) || articles.length === 0) {
            if (section) section.hidden = true;
            return;
        }
        if (section) section.hidden = false;
        container.replaceChildren(...articles.map(item => {
            const href = safeUrl(item.url);
            return el('div', { class: 'article-item' }, [
                href ? el('a', { href, target: '_blank', rel: 'noopener', text: item.title || href })
                     : el('span', { text: item.title || '' }),
                item.date ? el('span', { class: 'article-meta', text: item.date }) : null
            ]);
        }));
        observeReveal(container);
    }

    // ---------- 最後更新 ----------
    function renderLastUpdated(dateStr) {
        const node = document.getElementById('lastUpdated');
        if (!node || !dateStr) return;
        const d = new Date(dateStr);
        node.textContent = isNaN(d) ? dateStr : d.toLocaleDateString('zh-TW', {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
    }

    function setCurrentYear() {
        const node = document.getElementById('currentYear');
        if (node) node.textContent = new Date().getFullYear();
    }
})();
