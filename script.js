const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso) {
    const parts = String(iso).split("-");
    if (parts.length !== 3) {
        return String(iso);
    }
    const [year, month, day] = parts.map(Number);
    if (!MONTHS[month - 1]) {
        return String(iso);
    }
    return `${MONTHS[month - 1]} ${day}, ${year}`;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    if (text !== undefined) {
        node.textContent = text;
    }
    return node;
}

function buildDevlogEntry(entry) {
    const article = el("article", "devlog-entry");

    article.appendChild(el("h2", "devlog-title", entry.title || "Untitled"));

    const meta = el("div", "devlog-meta");
    meta.appendChild(el("span", "timestamp", formatDate(entry.date)));
    if (entry.author) {
        meta.appendChild(el("span", "devlog-author", entry.author));
    }
    article.appendChild(meta);

    if (entry.tags && entry.tags.length) {
        const tags = el("div", "devlog-tags");
        entry.tags.forEach(tag => tags.appendChild(el("span", "devlog-tag", tag)));
        article.appendChild(tags);
    }

    const paragraphs = Array.isArray(entry.body) ? entry.body : [entry.body];
    const body = el("div", "devlog-body");
    paragraphs.filter(Boolean).forEach(text => body.appendChild(el("p", null, text)));
    article.appendChild(body);

    if (entry.images && entry.images.length) {
        const media = el("div", "devlog-media");
        entry.images.forEach(image => {
            const figure = el("figure", "devlog-figure");
            const img = el("img", "devlog-image");
            img.src = image.src;
            img.alt = image.caption || entry.title || "Devlog image";
            img.loading = "lazy";
            figure.appendChild(img);
            if (image.caption) {
                figure.appendChild(el("figcaption", "devlog-caption", image.caption));
            }
            media.appendChild(figure);
        });
        article.appendChild(media);
    }

    if (entry.links && entry.links.length) {
        const links = el("div", "devlog-links");
        entry.links.forEach(link => {
            const anchor = el("a", "download-link", link.label || link.href);
            anchor.href = link.href;
            links.appendChild(anchor);
        });
        article.appendChild(links);
    }

    return article;
}

function renderDevlog() {
    const list = document.getElementById("devlog-list");
    if (!list) {
        return;
    }

    const entries = typeof devlogEntries === "undefined" ? [] : [...devlogEntries];

    if (!entries.length) {
        list.appendChild(el("p", "description", "No devlog entries yet."));
        return;
    }

    entries.sort((a, b) => String(b.date).localeCompare(String(a.date)));
    entries.forEach(entry => list.appendChild(buildDevlogEntry(entry)));
}

function fileHref(group, version, format) {
    const slug = group.slug || group.folder;
    const name = version.name || `${version.date}_${slug}`;
    return `${group.folder}/${name}.${format}`;
}

function previewSrc(group, versions) {
    if (group.preview === false) {
        return null;
    }
    if (typeof group.preview === "string") {
        return group.preview;
    }
    const newest = versions.find(version => (version.formats || []).includes("pdf"));
    return newest ? fileHref(group, newest, "pdf") : null;
}

function buildFileCard(group) {
    const card = el("div", "file-card");
    card.appendChild(el("h2", "file-title", group.title || "Untitled"));

    const versions = [...(group.versions || [])];
    versions.sort((a, b) => String(b.date).localeCompare(String(a.date)));

    const src = previewSrc(group, versions);
    if (src) {
        const embed = el("embed", "file-preview");
        embed.src = src;
        embed.type = "application/pdf";
        card.appendChild(embed);

        const open = el("a", "download-link file-open-link", "Open PDF");
        open.href = src;
        open.target = "_blank";
        open.rel = "noopener";
        card.appendChild(open);
    }

    versions.forEach(version => {
        const meta = el("div", "file-meta");
        meta.appendChild(el("span", "timestamp", formatDate(version.date)));
        (version.formats || []).forEach(format => {
            const link = el("a", "download-link");
            if (typeof format === "string") {
                link.href = fileHref(group, version, format);
                link.textContent = `Download as ${format.toUpperCase()}`;
            } else {
                link.href = format.href;
                link.textContent = format.label || format.href;
            }
            link.setAttribute("download", "");
            meta.appendChild(link);
        });
        card.appendChild(meta);
    });

    return card;
}

function renderFiles() {
    const list = document.getElementById("file-list");
    if (!list) {
        return;
    }

    const groups = typeof fileGroups === "undefined" ? [] : fileGroups;

    if (!groups.length) {
        list.appendChild(el("p", "description", "No files yet."));
        return;
    }

    groups.forEach(group => list.appendChild(buildFileCard(group)));
}

function initials(name) {
    const words = name.trim().split(/\s+/);
    const first = words[0] ? words[0][0] : "";
    const last = words.length > 1 ? words[words.length - 1][0] : "";
    return (first + last).toUpperCase();
}

function buildTeamCard(member) {
    const card = el("div", "team-card");
    const frame = el("div", "team-photo-frame");

    if (member.photo) {
        const photo = el("img", "team-photo");
        photo.src = member.photo;
        photo.alt = member.name;
        photo.loading = "lazy";
        frame.appendChild(photo);
    } else {
        frame.appendChild(el("span", "team-placeholder", initials(member.name)));
    }

    const info = el("div", "team-info");
    info.appendChild(el("h2", "team-name", member.name));
    if (member.role) {
        info.appendChild(el("p", "team-role", member.role));
    }
    if (member.major) {
        info.appendChild(el("p", "team-major", member.major));
    }
    if (member.email) {
        const link = el("a", "team-email", member.email);
        link.href = `mailto:${member.email}`;
        info.appendChild(link);
    }
    card.appendChild(frame);
    card.appendChild(info);

    if (member.bio) {
        card.appendChild(el("p", "team-bio", member.bio));
    }

    return card;
}

function renderTeam() {
    const grid = document.getElementById("team-grid");
    if (!grid) {
        return;
    }

    const members = typeof teamMembers === "undefined" ? [] : teamMembers;
    members.filter(member => member.name).forEach(member => grid.appendChild(buildTeamCard(member)));
}

document.addEventListener("DOMContentLoaded", () => {
    const navLinks = document.querySelectorAll(".nav-link[data-page]");
    const pages = document.querySelectorAll(".page");

    renderDevlog();
    renderFiles();
    renderTeam();

    function showPage(pageId) {
        pages.forEach(page => {
            page.classList.toggle("is-active", page.id === pageId);
        });
        navLinks.forEach(link => {
            link.classList.toggle("is-active", link.dataset.page === pageId);
        });
    }

    navLinks.forEach(link => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            showPage(link.dataset.page);
            history.replaceState(null, "", `#${link.dataset.page}`);
        });
    });

    const initialPage = window.location.hash.replace("#", "");
    if (initialPage && document.getElementById(initialPage)) {
        showPage(initialPage);
    }
});
