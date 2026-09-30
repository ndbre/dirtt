/* ===========================================================================
   FILES (shared team repository)

   Put the file anywhere inside the Files/ folder, using subfolders however
   you like, then add one line for it below. The path is relative to Files/,
   and the folders in the path become the folders on the page.

       "Datasheets/Pixhawk 4.pdf",

   That's all it needs. Add more detail by writing it as an object instead:

   {
       path: "CAD/Chassis/Top Plate.step",   REQUIRED. Location inside Files/.
       date: "2026-10-02",                   Optional. YYYY-MM-DD, last changed.
       by: "Rebecca Ueltschey",              Optional. Who added it.
       note: "Rev B, 3 mm holes",            Optional. Short description.
       tags: ["Chassis", "Rev B"],           Optional. Searchable labels.
       href: "https://..."                   Optional. Link here instead of
                                             Files/<path>. Use it for files
                                             stored elsewhere (Google Drive,
                                             OneDrive, a vendor site).
   },

   Notes:
   - Any file type can be listed. These preview right in the browser:
     images, PDFs, video, audio, .glb/.gltf 3D models, CSV/TSV tables, and
     plain text or code (.txt, .md, .c, .cpp, .ino, .py, .json, .param ...).
     Everything else (Office files, STEP, Inventor, KiCad, ZIP ...) gets a
     download button.
   - STL files can't be previewed; export a .glb copy as well if you want
     one people can spin around on the page.
   - Cloudflare Pages rejects files over 25 MB. Upload big files to Google
     Drive or OneDrive and list them here with an href.
   - If a row shows "Missing", the path doesn't match a real file. Check the
     spelling and capitalization.
   - Watch the commas: every entry ends with a comma.
   =========================================================================== */

const sharedFiles = [

    {
        path: "CAD/Drivetrain/Drivetrain Motor FIT0185.glb",
        href: "Files/Drivetrain Motor FIT0185.glb",
        date: "2026-09-28",
        by: "Nolan Brechtel",
        note: "Simplified model of the DFRobot FIT0185 geared motor, built from the datasheet.",
        tags: ["Drivetrain"]
    },
    {
        path: "CAD/Drivetrain/Drivetrain Motor FIT0185.stl",
        href: "Files/Drivetrain Motor FIT0185.stl",
        date: "2026-09-28",
        by: "Nolan Brechtel",
        note: "Simplified model of the DFRobot FIT0185 geared motor, built from the datasheet.",
        tags: ["Drivetrain"]
    },
    {
        path: "Datasheets/FIT0185 Dimensions.png",
        href: "https://dfimg.dfrobot.com/enshop/image/data/FIT0185/FIT0185_Dimension.PNG",
        date: "2026-09-28",
        note: "Dimension drawing for the drivetrain motor, from DFRobot.",
        tags: ["Drivetrain"]
    },
    {
        path: "Datasheets/RS485 Soil Sensor.png",
        href: "https://api.mikroelectron.com/storage/25914/ISO9lwzIARu2t8KIbqfXfadoiwvQDFH5gtRgCdNq.pdf",
        date: "2026-09-28",
        note: "Datasheet for the Soil Sensor, from DFRobot.",
        tags: ["Soil Sensing"]
    }

];
