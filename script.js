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

    const images = entry.images || [];
    const models = entry.models || [];
    if (images.length || models.length) {
        const media = el("div", "devlog-media");
        models.forEach(model => {
            const figure = el("figure", "devlog-figure");
            const viewer = el("model-viewer", "devlog-model");
            viewer.setAttribute("src", model.src);
            viewer.setAttribute("alt", model.caption || entry.title || "3D model");
            viewer.setAttribute("camera-controls", "");
            viewer.setAttribute("touch-action", "pan-y");
            viewer.setAttribute("auto-rotate", "");
            viewer.setAttribute("shadow-intensity", "1");
            viewer.setAttribute("loading", "lazy");
            if (model.poster) {
                viewer.setAttribute("poster", model.poster);
            }
            figure.appendChild(viewer);
            if (model.caption) {
                figure.appendChild(el("figcaption", "devlog-caption", model.caption));
            }
            media.appendChild(figure);
        });
        images.forEach(image => {
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

    if (entries.some(entry => entry.models && entry.models.length)) {
        loadModelViewer();
    }
}

function loadModelViewer() {
    if (document.getElementById("model-viewer-script")) {
        return;
    }
    const script = document.createElement("script");
    script.id = "model-viewer-script";
    script.type = "module";
    script.src = "https://cdn.jsdelivr.net/npm/@google/model-viewer@4/dist/model-viewer.min.js";
    document.head.appendChild(script);
}

function deliverableHref(group, version, format) {
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
    return newest ? deliverableHref(group, newest, "pdf") : null;
}

function buildDeliverableCard(group) {
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
                link.href = deliverableHref(group, version, format);
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

function renderDeliverables() {
    const list = document.getElementById("deliverable-list");
    if (!list) {
        return;
    }

    const groups = typeof deliverableGroups === "undefined" ? [] : deliverableGroups;

    if (!groups.length) {
        list.appendChild(el("p", "description", "No deliverables yet."));
        return;
    }

    groups.forEach(group => list.appendChild(buildDeliverableCard(group)));
}

/* Shared file repository */

const FILE_ROOT = "Files";

const CODE_EXTS = ["c", "cpp", "h", "hpp", "ino", "py", "js", "ts", "json", "html", "css", "m", "sh",
    "lua", "java", "rs", "go", "yaml", "yml", "xml", "ini", "cfg", "param", "toml", "log"];

const FILE_CATEGORIES = [
    { id: "document", label: "Documents", exts: ["pdf", "doc", "docx", "odt", "rtf", "txt", "md"] },
    { id: "spreadsheet", label: "Spreadsheets", exts: ["xls", "xlsx", "xlsm", "ods", "csv", "tsv"] },
    { id: "presentation", label: "Presentations", exts: ["ppt", "pptx", "odp", "key"] },
    { id: "image", label: "Images", exts: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "heic", "tif", "tiff"] },
    { id: "video", label: "Video", exts: ["mp4", "webm", "mov", "m4v", "avi", "mkv"] },
    { id: "audio", label: "Audio", exts: ["mp3", "wav", "ogg", "m4a", "flac"] },
    { id: "model", label: "3D Models", exts: ["glb", "gltf", "stl", "obj", "3mf", "fbx"] },
    { id: "cad", label: "CAD", exts: ["step", "stp", "iges", "igs", "ipt", "iam", "idw", "ipn",
        "sldprt", "sldasm", "slddrw", "f3d", "dwg", "dxf"] },
    { id: "electronics", label: "Electronics", exts: ["kicad_pro", "kicad_sch", "kicad_pcb", "sch", "brd", "gbr", "drl", "fzz"] },
    { id: "code", label: "Code & Config", exts: CODE_EXTS },
    { id: "archive", label: "Archives", exts: ["zip", "7z", "rar", "tar", "gz"] }
];

const OTHER_CATEGORY = { id: "other", label: "Other" };

const PREVIEW_KINDS = {
    image: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"],
    pdf: ["pdf"],
    video: ["mp4", "webm", "mov", "m4v"],
    audio: ["mp3", "wav", "ogg", "m4a", "flac"],
    model: ["glb", "gltf"],
    table: ["csv", "tsv"],
    text: ["txt", "md", ...CODE_EXTS]
};

const TEXT_PREVIEW_LIMIT = 200000;
const TABLE_PREVIEW_ROWS = 500;

const repo = { files: [], folder: "", query: "", type: "all", sort: "name" };
const fileInfoCache = new Map();

function extOf(name) {
    const dot = name.lastIndexOf(".");
    return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

function previewKindOf(ext) {
    const match = Object.keys(PREVIEW_KINDS).find(kind => PREVIEW_KINDS[kind].includes(ext));
    return match || null;
}

function normalizeSharedFile(entry) {
    const item = typeof entry === "string" ? { path: entry } : { ...entry };
    const path = String(item.path || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
    if (!path) {
        return null;
    }
    const parts = path.split("/");
    const name = parts.pop();
    const ext = extOf(name);
    return {
        ...item,
        path,
        name,
        ext,
        folder: parts.join("/"),
        category: FILE_CATEGORIES.find(category => category.exts.includes(ext)) || OTHER_CATEGORY,
        previewKind: previewKindOf(ext),
        href: item.href || `${FILE_ROOT}/${path.split("/").map(encodeURIComponent).join("/")}`,
        external: /^https?:\/\//i.test(item.href || ""),
        tags: item.tags || []
    };
}

function formatSize(bytes) {
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    const units = ["KB", "MB", "GB"];
    let value = bytes / 1024;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit++;
    }
    return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

// Cloudflare Pages answers unknown paths with index.html instead of a 404,
// so an HTML response for a non-HTML file also counts as missing.
function fetchFileInfo(file) {
    if (file.external) {
        return Promise.resolve(null);
    }
    if (!fileInfoCache.has(file.href)) {
        const request = fetch(file.href, { method: "HEAD" })
            .then(response => {
                const type = response.headers.get("content-type") || "";
                const missing = !response.ok || (type.includes("text/html") && !["html", "htm"].includes(file.ext));
                return { missing, size: Number(response.headers.get("content-length")) || null };
            })
            .catch(() => null);
        fileInfoCache.set(file.href, request);
    }
    return fileInfoCache.get(file.href);
}

function fillFileSize(target, file) {
    fetchFileInfo(file).then(info => {
        if (!info) {
            return;
        }
        if (info.missing) {
            target.textContent = "Missing";
            target.classList.add("is-missing");
            target.title = "No file at this path. Check the spelling in files.js.";
        } else if (info.size) {
            target.textContent = formatSize(info.size);
        }
    });
}

function buildBadge(file) {
    const label = file.ext ? file.ext.slice(0, 4).toUpperCase() : "FILE";
    const badge = el("span", `repo-badge repo-badge-${file.category.id}`, label);
    badge.setAttribute("aria-hidden", "true");
    return badge;
}

function buildFolderBadge() {
    const badge = el("span", "repo-badge repo-badge-folder");
    badge.setAttribute("aria-hidden", "true");
    badge.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round">'
        + '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/></svg>';
    return badge;
}

function isInside(file, folder) {
    return folder === "" || file.folder === folder || file.folder.startsWith(`${folder}/`);
}

function subfoldersOf(folder) {
    const found = new Map();
    repo.files.forEach(file => {
        if (file.folder === folder || !isInside(file, folder)) {
            return;
        }
        const rest = folder ? file.folder.slice(folder.length + 1) : file.folder;
        const name = rest.split("/")[0];
        const path = folder ? `${folder}/${name}` : name;
        if (!found.has(path)) {
            found.set(path, { name, path, count: 0, date: "" });
        }
        const entry = found.get(path);
        entry.count++;
        if (file.date && String(file.date) > entry.date) {
            entry.date = String(file.date);
        }
    });
    return [...found.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

function matchesQuery(file, query) {
    if (!query) {
        return true;
    }
    const haystack = [file.path, file.note, file.by, file.category.label, ...file.tags]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
    return query.split(/\s+/).every(word => haystack.includes(word));
}

function sortFiles(files) {
    const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true });
    const sorters = {
        name: byName,
        date: (a, b) => String(b.date || "").localeCompare(String(a.date || "")) || byName(a, b),
        type: (a, b) => a.category.label.localeCompare(b.category.label) || a.ext.localeCompare(b.ext) || byName(a, b)
    };
    return [...files].sort(sorters[repo.sort] || byName);
}

function openFolder(path) {
    repo.folder = path;
    drawRepository();
}

function buildFolderRow(folder) {
    const row = el("div", "repo-row");
    const main = el("button", "repo-row-main");
    main.type = "button";
    main.appendChild(buildFolderBadge());
    const text = el("span", "repo-row-text");
    text.appendChild(el("span", "repo-row-name", folder.name));
    text.appendChild(el("span", "repo-row-sub", `${folder.count} ${folder.count === 1 ? "file" : "files"}`));
    main.appendChild(text);
    main.addEventListener("click", () => openFolder(folder.path));
    row.appendChild(main);
    row.appendChild(el("span", "repo-row-date timestamp", folder.date ? formatDate(folder.date) : ""));
    row.appendChild(el("span", "repo-row-size"));
    row.appendChild(el("span", "repo-row-action"));
    return row;
}

function buildFileLink(file, className) {
    const link = el("a", className, file.external ? "Open link" : "Download");
    link.href = file.href;
    if (file.external) {
        link.target = "_blank";
        link.rel = "noopener";
    } else {
        link.setAttribute("download", file.name);
    }
    return link;
}

function buildFileRow(file, showFolder) {
    const row = el("div", "repo-row");
    const main = el("button", "repo-row-main");
    main.type = "button";
    main.appendChild(buildBadge(file));
    const text = el("span", "repo-row-text");
    text.appendChild(el("span", "repo-row-name", file.name));
    const sub = showFolder ? [FILE_ROOT, file.folder].filter(Boolean).join("/") : file.note;
    if (sub) {
        text.appendChild(el("span", "repo-row-sub", sub));
    }
    main.appendChild(text);
    main.addEventListener("click", () => openFilePreview(file));
    row.appendChild(main);

    row.appendChild(el("span", "repo-row-date timestamp", file.date ? formatDate(file.date) : ""));
    const size = el("span", "repo-row-size");
    fillFileSize(size, file);
    row.appendChild(size);

    const action = el("span", "repo-row-action");
    action.appendChild(buildFileLink(file, "download-link"));
    row.appendChild(action);
    return row;
}

function drawBreadcrumb(searching, resultCount) {
    const crumbs = document.getElementById("repo-breadcrumb");
    crumbs.replaceChildren();

    if (searching) {
        const label = `${resultCount} ${resultCount === 1 ? "result" : "results"} in all folders`;
        crumbs.appendChild(el("span", "repo-crumb-current", label));
        return;
    }

    const parts = repo.folder ? repo.folder.split("/") : [];
    const trail = [{ label: "All files", path: "" }]
        .concat(parts.map((part, i) => ({ label: part, path: parts.slice(0, i + 1).join("/") })));

    trail.forEach((crumb, i) => {
        if (i > 0) {
            crumbs.appendChild(el("span", "repo-crumb-sep", "/"));
        }
        if (i === trail.length - 1) {
            crumbs.appendChild(el("span", "repo-crumb-current", crumb.label));
        } else {
            const button = el("button", "repo-crumb", crumb.label);
            button.type = "button";
            button.addEventListener("click", () => openFolder(crumb.path));
            crumbs.appendChild(button);
        }
    });
}

function drawRepository() {
    const list = document.getElementById("repo-list");
    list.replaceChildren();

    const query = repo.query.trim().toLowerCase();
    const searching = query !== "" || repo.type !== "all";

    let folders = [];
    let files;
    if (searching) {
        files = repo.files.filter(file =>
            (repo.type === "all" || file.category.id === repo.type) && matchesQuery(file, query));
    } else {
        folders = subfoldersOf(repo.folder);
        files = repo.files.filter(file => file.folder === repo.folder);
    }
    files = sortFiles(files);

    drawBreadcrumb(searching, files.length);

    if (!folders.length && !files.length) {
        const message = !repo.files.length ? "No files yet."
            : searching ? "No files match." : "This folder is empty.";
        list.appendChild(el("p", "description repo-empty", message));
        return;
    }

    const head = el("div", "repo-row repo-row-head");
    ["Name", "Modified", "Size", ""].forEach(label => head.appendChild(el("span", null, label)));
    list.appendChild(head);

    folders.forEach(folder => list.appendChild(buildFolderRow(folder)));
    files.forEach(file => list.appendChild(buildFileRow(file, searching)));
}

function parseDelimited(text, delimiter) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (quoted) {
            if (ch === '"' && text[i + 1] === '"') {
                field += '"';
                i++;
            } else if (ch === '"') {
                quoted = false;
            } else {
                field += ch;
            }
        } else if (ch === '"') {
            quoted = true;
        } else if (ch === delimiter) {
            row.push(field);
            field = "";
        } else if (ch === "\n" || ch === "\r") {
            if (ch === "\r" && text[i + 1] === "\n") {
                i++;
            }
            row.push(field);
            rows.push(row);
            row = [];
            field = "";
        } else {
            field += ch;
        }
    }
    if (field || row.length) {
        row.push(field);
        rows.push(row);
    }
    return rows;
}

function buildTablePreview(text, delimiter) {
    const rows = parseDelimited(text, delimiter);
    const wrap = el("div", "repo-preview-table");
    const table = el("table");
    rows.slice(0, TABLE_PREVIEW_ROWS + 1).forEach((cells, i) => {
        const tr = el("tr");
        cells.forEach(cell => tr.appendChild(el(i === 0 ? "th" : "td", null, cell)));
        table.appendChild(tr);
    });
    wrap.appendChild(table);
    const fragment = document.createDocumentFragment();
    fragment.appendChild(wrap);
    if (rows.length > TABLE_PREVIEW_ROWS + 1) {
        fragment.appendChild(el("p", "repo-preview-note",
            `Showing the first ${TABLE_PREVIEW_ROWS} of ${rows.length - 1} rows. Download for the full file.`));
    }
    return fragment;
}

function fillTextPreview(stage, file) {
    stage.appendChild(el("p", "repo-preview-note", "Loading…"));
    fetch(file.href)
        .then(response => {
            if (!response.ok) {
                throw new Error(response.statusText);
            }
            return response.text();
        })
        .then(text => {
            stage.replaceChildren();
            if (file.previewKind === "table") {
                stage.appendChild(buildTablePreview(text, file.ext === "tsv" ? "\t" : ","));
                return;
            }
            stage.appendChild(el("pre", "repo-preview-text", text.slice(0, TEXT_PREVIEW_LIMIT)));
            if (text.length > TEXT_PREVIEW_LIMIT) {
                stage.appendChild(el("p", "repo-preview-note", "Preview cut short. Download for the full file."));
            }
        })
        .catch(() => {
            stage.replaceChildren(el("p", "repo-preview-note", "Couldn't load a preview of this file."));
        });
}

function buildPreview(file) {
    const stage = el("div", "repo-preview");
    const kind = file.previewKind;

    if (kind === "image") {
        const img = el("img", "repo-preview-image");
        img.src = file.href;
        img.alt = file.note || file.name;
        stage.appendChild(img);
    } else if (kind === "pdf") {
        const embed = el("embed", "repo-preview-pdf");
        embed.src = file.href;
        embed.type = "application/pdf";
        stage.appendChild(embed);
        stage.appendChild(el("p", "repo-preview-note repo-pdf-fallback", "Use \"Open in new tab\" to read this PDF."));
    } else if (kind === "video" || kind === "audio") {
        const media = el(kind, `repo-preview-${kind}`);
        media.src = file.href;
        media.controls = true;
        media.preload = "metadata";
        stage.appendChild(media);
    } else if (kind === "model") {
        loadModelViewer();
        const viewer = el("model-viewer", "repo-preview-model");
        viewer.setAttribute("src", file.href);
        viewer.setAttribute("alt", file.note || file.name);
        viewer.setAttribute("camera-controls", "");
        viewer.setAttribute("touch-action", "pan-y");
        viewer.setAttribute("auto-rotate", "");
        viewer.setAttribute("shadow-intensity", "1");
        stage.appendChild(viewer);
    } else if (kind === "text" || kind === "table") {
        fillTextPreview(stage, file);
    } else {
        const message = file.ext === "stl"
            ? "STL files can't be previewed. Export a .glb copy to view it here."
            : `No preview for ${file.ext ? `.${file.ext}` : "this"} files. Download it to open it.`;
        stage.classList.add("is-empty");
        stage.appendChild(el("p", "repo-preview-note", message));
    }
    return stage;
}

function getRepoDialog() {
    let dialog = document.getElementById("repo-dialog");
    if (dialog) {
        return dialog;
    }
    dialog = el("dialog", "repo-dialog");
    dialog.id = "repo-dialog";
    dialog.addEventListener("click", event => {
        if (event.target === dialog) {
            dialog.close();
        }
    });
    // Emptying the dialog on close stops any video or audio still playing.
    dialog.addEventListener("close", () => dialog.replaceChildren());
    document.body.appendChild(dialog);
    return dialog;
}

function openFilePreview(file) {
    const dialog = getRepoDialog();
    dialog.replaceChildren();
    dialog.setAttribute("aria-label", file.name);

    const panel = el("div", "repo-dialog-panel");

    const header = el("div", "repo-dialog-header");
    header.appendChild(buildBadge(file));
    const heading = el("div", "repo-dialog-heading");
    heading.appendChild(el("h2", "repo-dialog-title", file.name));
    heading.appendChild(el("p", "repo-dialog-path", [FILE_ROOT, file.folder].filter(Boolean).join("/")));
    header.appendChild(heading);
    const close = el("button", "repo-close", "Close");
    close.type = "button";
    close.addEventListener("click", () => dialog.close());
    header.appendChild(close);
    panel.appendChild(header);

    const meta = el("div", "file-meta repo-dialog-meta");
    meta.appendChild(el("span", null, `${file.ext ? file.ext.toUpperCase() : "File"} · ${file.category.label}`));
    if (file.date) {
        meta.appendChild(el("span", "timestamp", formatDate(file.date)));
    }
    if (file.by) {
        meta.appendChild(el("span", null, file.by));
    }
    const size = el("span");
    fillFileSize(size, file);
    meta.appendChild(size);
    panel.appendChild(meta);

    if (file.note) {
        panel.appendChild(el("p", "repo-dialog-note", file.note));
    }
    if (file.tags.length) {
        const tags = el("div", "devlog-tags");
        file.tags.forEach(tag => tags.appendChild(el("span", "devlog-tag", tag)));
        panel.appendChild(tags);
    }

    panel.appendChild(buildPreview(file));

    const actions = el("div", "repo-dialog-actions");
    actions.appendChild(buildFileLink(file, "repo-button"));
    if (!file.external) {
        const open = el("a", "download-link", "Open in new tab");
        open.href = file.href;
        open.target = "_blank";
        open.rel = "noopener";
        actions.appendChild(open);
    }
    panel.appendChild(actions);

    dialog.appendChild(panel);
    dialog.showModal();
}

function renderRepository() {
    if (!document.getElementById("repo-list")) {
        return;
    }

    const entries = typeof sharedFiles === "undefined" ? [] : sharedFiles;
    repo.files = entries.map(normalizeSharedFile).filter(Boolean);

    const typeSelect = document.getElementById("repo-type");
    [...FILE_CATEGORIES, OTHER_CATEGORY].forEach(category => {
        const count = repo.files.filter(file => file.category.id === category.id).length;
        if (count) {
            const option = el("option", null, `${category.label} (${count})`);
            option.value = category.id;
            typeSelect.appendChild(option);
        }
    });

    document.getElementById("repo-search").addEventListener("input", event => {
        repo.query = event.target.value;
        drawRepository();
    });
    typeSelect.addEventListener("change", event => {
        repo.type = event.target.value;
        drawRepository();
    });
    document.getElementById("repo-sort").addEventListener("change", event => {
        repo.sort = event.target.value;
        drawRepository();
    });

    drawRepository();
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
    renderDeliverables();
    renderRepository();
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
