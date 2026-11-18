/* Serves the repo's docs/ folder at dirtt.ndbre.com/docs/...
 *
 * Deliverables live in docs/ (outside website/), so Cloudflare's 25 MiB file
 * limit doesn't apply. This Pages Function fetches each file from GitHub and
 * passes it on with the right Content-Type, so PDFs still preview and open in
 * the browser (GitHub's raw links force a download and block embedding).
 *
 * Production and dirtt.pages.dev read from master. A branch preview
 * (<branch>.dirtt.pages.dev) reads from that branch, so docs added in a PR
 * show up in its preview.
 */

const REPO = "ndbre/dirtt";
const PRODUCTION_BRANCH = "master";

const TYPES = {
    pdf: "application/pdf",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    zip: "application/zip",
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    glb: "model/gltf-binary",
    stl: "model/stl",
    txt: "text/plain; charset=utf-8",
    csv: "text/csv; charset=utf-8"
};

function branchFor(hostname) {
    // <branch>.dirtt.pages.dev -> branch alias; anything else -> master.
    const match = hostname.match(/^([a-z0-9-]+)\.dirtt\.pages\.dev$/);
    if (match && !/^[0-9a-f]{8}$/.test(match[1])) {
        return match[1];
    }
    return PRODUCTION_BRANCH;
}

export async function onRequest({ request, params }) {
    if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method not allowed", { status: 405 });
    }

    const parts = [].concat(params.path || []);
    if (!parts.length || parts.some(part => !part || part === "." || part === "..")) {
        return new Response("Not found", { status: 404 });
    }

    const branch = branchFor(new URL(request.url).hostname);
    const path = parts.map(encodeURIComponent).join("/");
    let upstream = await fetch(`https://raw.githubusercontent.com/${REPO}/${branch}/docs/${path}`);
    if (upstream.status === 404 && branch !== PRODUCTION_BRANCH) {
        upstream = await fetch(`https://raw.githubusercontent.com/${REPO}/${PRODUCTION_BRANCH}/docs/${path}`);
    }
    if (!upstream.ok) {
        return new Response("Not found", { status: 404 });
    }

    const name = parts[parts.length - 1];
    const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
    const headers = new Headers({
        "Content-Type": TYPES[ext] || "application/octet-stream",
        "Cache-Control": "public, max-age=300"
    });
    const length = upstream.headers.get("Content-Length");
    if (length) {
        headers.set("Content-Length", length);
    }

    return new Response(request.method === "HEAD" ? null : upstream.body, { headers });
}
