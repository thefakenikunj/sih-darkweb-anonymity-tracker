# Multi-Source Entity Resolution & Stylometric Analysis Platform

An OSINT and forensic analytics platform designed to collect, process, and correlate cross-platform digital footprints using stylometric analysis, behavioral signature extraction, and entity graph resolution.

## Key Features
* **Stylometric Forensics**: Identifies writing patterns, stylistic traits, and vocabulary signatures across disparate text sources.
* **Behavioral Analysis**: Correlates activity timestamps, frequency distribution, and metadata.
* **Entity Resolution Engine**: Resolves identities, links cross-platform aliases, and visualizes connections in an interactive network graph.
* **Interactive Visualization**: Renders web-based graph topologies (`network.html`) for dynamic network exploration.

## Directory Structure
```text
├── docs/                 # Documentation and presentation slides
├── src/                  # Application source code
│   ├── collectors/       # Data ingestion modules
│   ├── data/             # Sample datasets and entity mappings
│   ├── services/         # Core analytical services (stylometry, graph, resolution)
│   ├── scripts/          # Evaluation and benchmark scripts
│   ├── tests/            # Test suite
│   └── app.py            # Main application server
├── submission/           # Demonstration assets and videos
├── .gitignore            # Git ignore rules
├── LICENSE               # License file
├── README.md             # Project documentation
├── SUBMISSION_GUIDE.md   # SIH submission checklist
└── requirements.txt      # Project dependencies
