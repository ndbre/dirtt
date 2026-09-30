/* ===========================================================================
   {
       date: "2026-09-23",                  REQUIRED. Always YYYY-MM-DD.
       title: "What happened",              REQUIRED.
       author: "Nolan Brechtel",            Optional. Who wrote the entry.
       tags: ["Tag1", "Tag2"],     Optional. Any words you want.
       body: [                              REQUIRED. One string per paragraph.
           "First paragraph.",
           "Second paragraph."
       ],
       images: [                            Optional. Put files in Devlog/.
           { src: "Devlog/2026-09-23_img.jpg", caption: "Image Caption" }
       ],
       models: [                            Optional. 3D models (.glb or .gltf). Put files in Devlog/.
           { src: "Devlog/2026-09-23_chassis.glb", caption: "Model Caption" }
       ],
       links: [                             Optional. Files, docs, videos.
           { label: "PDR Poster", href: "PDR_Poster/2026-09-14_PDR_Poster.pdf" }
       ]
   },

   Notes:
   - A caption is optional: { src: "Devlog/photo.jpg" } works fine.
   - Models must be .glb or .gltf. STL/STEP/SolidWorks files won't load; export
     or convert to .glb first (e.g. open the STL in Blender and File > Export > glTF).
   - Models can also take a poster image shown while loading:
     { src: "Devlog/chassis.glb", poster: "Devlog/chassis.png" }
   =========================================================================== */

const devlogEntries = [
    {
       date: "2026-09-30",             
       title: "Meetings",          
       author: "Nolan Brechtel",        
       tags: ["Documentation", "Design"],     
       body: [                       
           "We met with Dr. Green for the live grading session of our Problem Statement. We were given the explicit \
           permission to rename the subsections and to reorganize the problem statement. In short, we are to make the needs \
           statement more about previous solutions and why there is a need for our product. Our objective statement will more \
           focus on what we bring to the table. Our background section discusses some of the scientific/technological aspects.",
           "On another note, we've discussed what is to happen to the project after our senior year. After getting confirmation \
           that the ECE department only wants the parts they paid for back, we essentially got the go ahead to work with \
           Mr. Alejandro Martinez and the IDEE lab. We can use their parts and the parts ordered via the ECE department, but we would \
           need to keep track of whose is whose and return them to their rightful owners.",
           "Later in the day, George and I met with Dr. Christopher Hudson to discuss the project a bit. He is working on a very similar \
           project to ours; his project is a herding robot, working in the same environment as ours and has some useful insights. The \
           first being that the heat from being out in the field can harm the electronics, so we would need a plan for keeping the \
           processor cool. The second insight is the terrain. He recommends using treads over wheels to combat the problem of the loose dirt. \
           He also offered to let us use a few of his parts, as long as we return them at the end of the year. His stock is much more computing \
           based than the IDEE lab, which focuses more on the mechanical side of things.",
           "With all things in mind, we have three potential sources of parts, so we need to have a way to keep track of each. Maybe stickers \
           would be a good solution to this problem."
       ]
    },
    {
       date: "2026-09-30",             
       title: "Parts Ordered",          
       author: "Nolan Brechtel",        
       tags: ["Parts"],     
       body: [                       
           "We went ahead and sent in the orders for the Soil Sensing and LoRa Communication. A full list of the parts ordered are:",
           "• 2x Raspberry Pi Zeros: One for the rover, one for the base station",
           "• 2x 32 GB MicroSD Cards (1 pack of 2): For the previously mentioned Raspberry Pis",
           "• 2x LoRa Radio Bonnet: For communicating via LoRa, one for each Raspberry Pi",
           "• 4x 915 MHz LoRa Antenna (1 pack of 4): For connecting to the Radio Bonnet",
           "• 1x 4 in 1 Soil Sensor: For the testing of the soil (duh)",
           "• 1x USB to RS485 Bidirectional Converter: The output of the soil sensor is RS485, this is to plug in to the Raspberry Pi",
           "• 1x USB to microUSB Converter: There is only a microUSB port on the Raspberry Pis"
       ],
       links: [                    
           { label: "Parts Ordered Sheet", href: "Devlog/2026-09-30/Parts Ordered.xlsx" }
       ]
    },
    {
       date: "2026-09-28",             
       title: "Drivetrain Motor Modeled",          
       author: "Nolan Brechtel",        
       tags: ["Design", "CAD"],     
       body: [                       
           "In my free time, I modeled the drivetrain motor in Autodesk Inventor. \
           I used the datasheet to get the dimensions and created a simplified version of the motor. \
           This will be useful for integrating it into the chassis design and ensuring proper fitment with other components."
       ],
       models: [        
           { src: "Files/Drivetrain Motor FIT0185.glb", caption: "FIT0185 Motor" }
       ],
       links: [                    
           { label: "FIT0185 Dimensions", href: "https://dfimg.dfrobot.com/enshop/image/data/FIT0185/FIT0185_Dimension.PNG" }
       ]
    },
    {
       date: "2026-09-28",             
       title: "IDEE Lab",          
       author: "Nolan Brechtel",        
       tags: ["Design"],     
       body: [                       
           "George and I met with Mr. Alejandro Martinez, who we were wondering if we can get to help us with the manufacturing \
           of the chassis of the robot. Our initial idea was to use the equipment of the IDEE lab to cut out a chassis, similar \
           to the ServoCity Recon Chassis, rather than spending such a large amount of money on it. He actually offered to assist \
           in the project by leting us use some of his parts. The only condition is that we would need to return them at the end of \
           year. We aren't sure what the fate of the project will be following the end of the year, so we weren't able to take him up \
           on the offer, but if we get the go ahead from the instructors, this will be a great opportunity to save some money."
       ]
    },
    {
        date: "2026-09-22",
        title: "Initial Design Talk",
        author: "Nolan Brechtel",
        tags: ["Design"],
        body: [
            "We all met to discuss the design of the robot and initial thoughts on parts to be ordered \
            and materials we wish to use. We've decided on a three-way split for the processing. The navigation system \
            will have its own processor, along with the soil sensing. These then will be connected to a central one \
            that will handle the transmission of data.",
            "Some of the specific parts we discussed include a\
            [1] 12V motor from DFRobot (chosen for its high gear ratio and reasonable pricing), \
            [2] Renogy 30W Rigid Solar Panel, \
            [3] Pixhawk 4 (for navigation), \
            [4] RS485 4-in-1 Soil Moisture, Temperature, pH & EC Sensor, \
            [5] L16-P Miniature Linear Actuator (for pressing Probe into Soil).",
            "For the chassis, we liked the design of the [6] ServoCity Recon Chassis Kit, but we will be making our own version of it. \
            The design is simply two aluminum plates sandwiching the components. \
            I am going to get in contact with AMS and the IDEE Lab to look into their process for getting the parts manufactured",
            "For the Pixhawk 4, although it is marketed towards drones, we can flash it with a rover firmware that \
            will allow us to use it for our purposes. There are many resources on making a rover that can navigate using ArduPilot."
        ],
        links: [
            { label: "[1] 12V Metal DC Geared Motor with Encoder (131:1, 83RPM, 45Kg.cm)", href: "https://www.dfrobot.com/product-633.html" },
            { label: "[2] Renogy 30W Rigid Solar Panel", href: "https://www.renogy.com/pages/30w-monocrystalline-solar-rigid-panels-rng-30d-ss-html" },
            { label: "[3] Pixhawk 4", href: "https://holybro.com/products/pixhawk-4"},
            { label: "[4] RS485 4-in-1 Soil Moisture, Temperature, pH & EC Sensor", href: "https://www.dfrobot.com/product-2830.html"},
            { label: "[5] L16-P Miniature Linear Actuator", href: "https://www.actuonix.com/l16-140-150-12-p"},
            { label: "[6] ServoCity Recon Chassis Kit", href: "https://www.servocity.com/recon-chassis/"}

        ]
    },

    {
        date: "2026-09-16",
        title: "Problem Statement Finalized",
        author: "Nolan Brechtel",
        tags: ["Documentation"],
        body: [
            "Cara and George finalized the problem statement for submission after implementing the suggested changes from the draft."
        ],
        links: [
            { label: "Problem Statement (PDF)", href: "PS/2026-09-16_PS.pdf" }
        ]
    },

    {
        date: "2026-09-14",
        title: "PDR Poster Finalized",
        author: "Nolan Brechtel",
        tags: ["Documentation"],
        body: [
            "Edited and finalized the PDR poster for submission."
        ],
        links: [
            { label: "PDR Poster (PDF)", href: "PDR_Poster/2026-09-14_PDR_Poster.pdf" }
        ]
    },

    {
        date: "2026-09-09",
        title: "Project Proposal and Team Charter Submitted",
        author: "Nolan Brechtel",
        tags: ["Documentation"],
        body: [
            "Submitted the project proposal and team charter."
        ]
    }

];
