/* ===========================================================================
   FILES

   Each entry below is one card on the Files page. Cards appear in the order
   they are listed here. Within a card, versions are sorted newest-first
   automatically.

   To add a NEW VERSION of a document that already has a card, add one line
   to that card's versions list:

       { date: "2026-09-20", formats: ["docx", "pdf"] },

   The download links are built from the folder, the date, and the format,
   so this line points at:

       PS/2026-09-20_PS.docx
       PS/2026-09-20_PS.pdf

   Name your files that way and there is nothing else to change. The PDF
   preview always shows the newest version that has a "pdf" format.

   To add a NEW DOCUMENT, copy this template:

   {
       title: "Critical Design Review",    REQUIRED. Heading on the card.
       folder: "CDR",                      REQUIRED. Folder holding the files.
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

       { date: "2026-10-01", formats: [{ label: "Download as ZIP", href: "CDR/models.zip" }] }

   Watch the commas: every entry ends with a comma after its closing brace.
   =========================================================================== */

const fileGroups = [

    {
        title: "Problem Statement",
        folder: "PS",
        versions: [
            { date: "2026-09-16", formats: ["docx", "pdf"] },
            { date: "2026-09-14", formats: ["docx", "pdf"] }
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
