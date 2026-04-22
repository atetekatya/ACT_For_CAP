# ACT_For_CAP

An NLP-assisted pipeline that detects keyword redundancy within SHU's course catalog and compares SHU course descriptions against four peer institutions to surface terminology misalignments.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Data](#data)
- [Outputs](#outputs)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **SHU Course Ingestion**: Processes SHU's course catalog to extract course descriptions and metadata.
- **Peer Institution Scraping/Parsing**: Scrapes or parses course data from Chatham University, Point Park University, Saint Vincent College, and Indiana University of Pennsylvania (IUP).
- **Database Building**: Creates a SQLite database and combined CSV with all course data.
- **NLP Analysis**: Uses natural language processing to detect keyword redundancy in SHU courses and compare terminology across institutions.
- **Reporting**: Generates an interactive HTML report with visualizations and insights.
- **Modular Pipeline**: Run the full pipeline or individual components as needed.

## Prerequisites

- Python 3.8 or higher
- Virtual environment (recommended)
- Internet connection for scraping peer institutions
- Sufficient disk space for data processing

## Installation

1. **Clone or Download the Repository**:
   ```bash
   git clone <repository-url>
   cd ACT_For_CAP
   ```

2. **Set Up Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Download Required NLP Models**:
   ```bash
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   python -c "import spacy; spacy.cli.download('en_core_web_sm')"
   ```

## Usage

### Running the Full Pipeline

To run the complete analysis pipeline:

```bash
python run_pipeline.py
```

This will execute all steps in sequence:
1. Ingest SHU catalog
2. Scrape/parse peer institutions
3. Build database
4. Run NLP analysis
5. Generate report

### Running Partial Pipeline

- **SHU Only**: Analyze only SHU data without peer comparisons:
  ```bash
  python run_pipeline.py --shu-only
  ```

- **Skip Scraping**: Use existing peer data if already scraped:
  ```bash
  python run_pipeline.py --skip-scrape
  ```

### Running Individual Scripts

You can run individual pipeline steps manually:

```bash
python 01_ingest_shu.py
python 02_scrape_chatham.py
python 03_scrape_pointpark.py
python 04_parse_stvincent.py
python 05_parse_iup.py
python 06_build_database.py
python 07_analyze.py
python 08_report.py
```

### Viewing the Report

After running the pipeline, open the generated report:

```bash
open output/ACT_for_CAP_Report.html
```

## Project Structure

```
ACT_For_CAP/
├── 01_ingest_shu.py          # SHU catalog ingestion
├── 02_scrape_chatham.py      # Chatham University scraping
├── 03_scrape_pointpark.py    # Point Park University scraping
├── 04_parse_stvincent.py     # Saint Vincent College parsing
├── 05_parse_iup.py           # IUP parsing
├── 06_build_database.py      # Database and CSV creation
├── 07_analyze.py             # NLP analysis
├── 08_report.py              # Report generation
├── run_pipeline.py           # Master pipeline runner
├── requirements.txt           # Python dependencies
├── manual_entry_template.py   # Template for manual data entry
├── debug_*.txt               # Debug output files
├── data/
│   ├── raw/                  # Raw scraped/parsed data
│   │   └── SHU_catalog.csv
│   └── processed/            # Processed course data
│       ├── all_courses.csv
│       ├── Chatham_courses.json
│       ├── IUP_courses.json
│       ├── PointPark_courses.json
│       ├── SHU_courses.json
│       └── StVincent_courses.json
└── output/
    ├── ACT_for_CAP_Report.html
    ├── cross_institution_matches.csv
    ├── keyword_frequencies.csv
    ├── shu_redundant_pairs.csv
    └── similarity_stats.json
```

## Data

### Input Data

- **SHU Catalog**: CSV file with course information (data/raw/SHU_catalog.csv)
- **Peer Institutions**: Web-scraped or PDF-parsed course data from Chatham, Point Park, St. Vincent, and IUP

### Processed Data

- **Individual Institution Files**: JSON files with structured course data
- **Combined Dataset**: all_courses.csv with all institutions' courses
- **Database**: SQLite database for efficient querying

## Outputs

- **HTML Report**: Interactive visualization of analysis results (output/ACT_for_CAP_Report.html)
- **CSV Files**: Structured data exports for further analysis
- **JSON Files**: Statistical summaries and metadata

## Configuration

The pipeline uses default settings but can be customized by modifying the individual scripts. Key configuration options include:

- NLP model parameters in `07_analyze.py`
- Scraping parameters in scraping scripts
- Report templates in `08_report.py`

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed and NLP models are downloaded.
2. **Scraping Failures**: Check internet connection and website availability.
3. **Memory Issues**: For large datasets, ensure sufficient RAM.
4. **PDF Parsing Errors**: Verify PDF files are accessible and properly formatted.

### Debug Mode

Run individual scripts with debug output to troubleshoot issues.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Specify license here, e.g., MIT License]
An NLP-assisted pipeline that detects keyword redundancy within SHU's course catalog and compares SHU course descriptions against four peer institutions to surface terminology misalignments.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Data](#data)
- [Outputs](#outputs)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **SHU Course Ingestion**: Processes SHU's course catalog to extract course descriptions and metadata.
- **Peer Institution Scraping/Parsing**: Scrapes or parses course data from Chatham University, Point Park University, Saint Vincent College, and Indiana University of Pennsylvania (IUP).
- **Database Building**: Creates a SQLite database and combined CSV with all course data.
- **NLP Analysis**: Uses natural language processing to detect keyword redundancy in SHU courses and compare terminology across institutions.
- **Reporting**: Generates an interactive HTML report with visualizations and insights.
- **Modular Pipeline**: Run the full pipeline or individual components as needed.

## Prerequisites

- Python 3.8 or higher
- Virtual environment (recommended)
- Internet connection for scraping peer institutions
- Sufficient disk space for data processing

## Installation

1. **Clone or Download the Repository**:
   ```bash
   git clone <repository-url>
   cd ACT_For_CAP
   ```

2. **Set Up Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Download Required NLP Models**:
   ```bash
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   python -c "import spacy; spacy.cli.download('en_core_web_sm')"
   ```

## Usage

### Running the Full Pipeline

To run the complete analysis pipeline:

```bash
python run_pipeline.py
```

This will execute all steps in sequence:
1. Ingest SHU catalog
2. Scrape/parse peer institutions
3. Build database
4. Run NLP analysis
5. Generate report

### Running Partial Pipeline

- **SHU Only**: Analyze only SHU data without peer comparisons:
  ```bash
  python run_pipeline.py --shu-only
  ```

- **Skip Scraping**: Use existing peer data if already scraped:
  ```bash
  python run_pipeline.py --skip-scrape
  ```

### Running Individual Scripts

You can run individual pipeline steps manually:

```bash
python 01_ingest_shu.py
python 02_scrape_chatham.py
python 03_scrape_pointpark.py
python 04_parse_stvincent.py
python 05_parse_iup.py
python 06_build_database.py
python 07_analyze.py
python 08_report.py
```

### Viewing the Report

After running the pipeline, open the generated report:

```bash
open output/ACT_for_CAP_Report.html
```

## Project Structure

```
ACT_For_CAP/
├── 01_ingest_shu.py          # SHU catalog ingestion
├── 02_scrape_chatham.py      # Chatham University scraping
├── 03_scrape_pointpark.py    # Point Park University scraping
├── 04_parse_stvincent.py     # Saint Vincent College parsing
├── 05_parse_iup.py           # IUP parsing
├── 06_build_database.py      # Database and CSV creation
├── 07_analyze.py             # NLP analysis
├── 08_report.py              # Report generation
├── run_pipeline.py           # Master pipeline runner
├── requirements.txt           # Python dependencies
├── manual_entry_template.py   # Template for manual data entry
├── debug_*.txt               # Debug output files
├── data/
│   ├── raw/                  # Raw scraped/parsed data
│   │   └── SHU_catalog.csv
│   └── processed/            # Processed course data
│       ├── all_courses.csv
│       ├── Chatham_courses.json
│       ├── IUP_courses.json
│       ├── PointPark_courses.json
│       ├── SHU_courses.json
│       └── StVincent_courses.json
└── output/
    ├── ACT_for_CAP_Report.html
    ├── cross_institution_matches.csv
    ├── keyword_frequencies.csv
    ├── shu_redundant_pairs.csv
    └── similarity_stats.json
```

## Data

### Input Data

- **SHU Catalog**: CSV file with course information (data/raw/SHU_catalog.csv)
- **Peer Institutions**: Web-scraped or PDF-parsed course data from Chatham, Point Park, St. Vincent, and IUP

### Processed Data

- **Individual Institution Files**: JSON files with structured course data
- **Combined Dataset**: all_courses.csv with all institutions' courses
- **Database**: SQLite database for efficient querying

## Outputs

- **HTML Report**: Interactive visualization of analysis results (output/ACT_for_CAP_Report.html)
- **CSV Files**: Structured data exports for further analysis
- **JSON Files**: Statistical summaries and metadata

## Configuration

The pipeline uses default settings but can be customized by modifying the individual scripts. Key configuration options include:

- NLP model parameters in `07_analyze.py`
- Scraping parameters in scraping scripts
- Report templates in `08_report.py`

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed and NLP models are downloaded.
2. **Scraping Failures**: Check internet connection and website availability.
3. **Memory Issues**: For large datasets, ensure sufficient RAM.
4. **PDF Parsing Errors**: Verify PDF files are accessible and properly formatted.

### Debug Mode

Run individual scripts with debug output to troubleshoot issues.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Specify license here, e.g., MIT License]
