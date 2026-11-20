/* ===========================================================================
   DELIVERABLES

   Each entry below is one card on the Deliverables page. Cards appear in the
   order they are listed here. Within a card, versions are sorted newest-first
   automatically.

   Files live in the repo's docs/<folder>/ folder (NOT inside website/) and
   are named <date>_<slug>.<ext>. Any size is fine; the site serves them
   from GitHub, so Cloudflare's 25 MB limit doesn't apply.

   To add a NEW VERSION of a document that already has a card, drop the files
   in its folder and add one line to that card's versions list:

       { date: "2026-09-20", formats: ["docx", "pdf"] },

   That line points at:

       docs/PS/2026-09-20_PS.docx
       docs/PS/2026-09-20_PS.pdf

   The PDF preview always shows the newest version that has a "pdf" format.

   To add a NEW DOCUMENT, make a folder in docs/ and copy this template:

   {
       title: "Critical Design Review",    REQUIRED. Heading on the card.
       folder: "CDR",                      REQUIRED. Folder in docs/.
       slug: "CDR",                        Optional. Filename part after the
                                           date. Defaults to the folder name.
       preview: false,                     Optional. Set false to hide the PDF
                                           preview, or give a path to pin one.
       versions: [
           { date: "2026-10-01", formats: ["pptx", "pdf"] }
       ]
   },

   If a file does not follow the naming convention, replace that format
   string with a spelled-out link instead:

       { date: "2026-10-01", formats: [{ label: "Download as ZIP", href: "docs/CDR/models.zip" }] }

   Working files that aren't formal deliverables (CAD, datasheets, code, test
   data, photos) go in cad/, code/ or datasheets/.
   =========================================================================== */

const deliverableGroups = [
    {
        title: "Final Design Review",
        folder: "FDR",
        versions: [
            { date: "2026-11-20", formats: ["pptx", "pdf"] },
            { date: "2026-11-17", formats: ["pptx", "pdf"] },
            { date: "2026-11-15", formats: ["pptx", "pdf"] }
        ]
    },

    {
        title: "Design Approach",
        folder: "DA",
        versions: [
            { date: "2026-11-06", formats: ["docx", "pdf"] },
            { date: "2026-11-05", formats: ["docx", "pdf"] }
        ]
    },

    {
        title: "Ethics Presentation",
        folder: "EP",
        versions: [
            { date: "2026-10-28", formats: ["pdf"] }
        ]
    },

    {
        title: "Mid-Semester Design Review",
        folder: "MSDR",
        versions: [
            { date: "2026-10-18", formats: ["pptx", "pdf"] }
        ]
    },

    {
        title: "Design Requirements Specification",
        folder: "DRS",
        versions: [
            { date: "2026-10-19", formats: ["docx", "pdf"] },
            { date: "2026-10-14", formats: ["docx", "pdf"] }
        ]
    },

    {
        title: "Problem Statement",
        folder: "PS",
        versions: [
            { date: "2026-10-02", formats: ["docx", "pdf"] },
            { date: "2026-09-16", formats: ["docx", "pdf"] },
            { date: "2026-09-14", formats: ["docx", "pdf"] }
        ]
    },

    {
        title: "Preliminary Design Review",
        folder: "PDR",
        versions: [
            { date: "2026-09-12", formats: ["pptx", "pdf"] }
        ]
    },

    {
        title: "PDR Poster",
        folder: "PDR_Poster",
        versions: [
            { date: "2026-09-14", formats: ["pptx", "pdf"] },
            { date: "2026-09-12", formats: ["pptx", "pdf"] }
        ]
    },

    {
        title: "Project Proposal and Team Charter",
        folder: "PPTC",
        versions: [
            { date: "2026-09-09", formats: ["pdf"] }
        ]
    }
];
