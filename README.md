# LitReview

Automate your lit review paper discovery
A command-line tool to download academic papers and their connected references/citations using the Semantic Scholar API.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

You can use this tool in two ways:

### 1. Search for Papers

Search for papers by keywords and select which one to download:

```bash
python paper_fetcher.py --search "your search terms" --depth 1 --verbose
```

### 2. Direct Paper ID

If you already have a Semantic Scholar Paper ID:

```bash
python paper_fetcher.py --paper-id <paper_id> --depth 1 --verbose
```

Arguments:
- `--search`: Search term to find papers
- `--paper-id`: Semantic Scholar Paper ID
- `--depth`: How many levels of references to download (default: 0)
- `--verbose`: Enable verbose logging
- `--api-key`: Optional Semantic Scholar API key

## Examples

### Example 1: Search for Papers

```bash
python paper_fetcher.py --search "Binaural Audio Head Tracking" --depth 1
```

This will:
1. Show you a list of relevant papers with:
   - Title and publication year
   - Authors
   - Brief abstract preview
   - Paper ID
2. Let you choose which paper to download
3. Download the selected paper and its connected papers
4. Save metadata about all papers in `papers_metadata.json`

Example output:
```
Found papers:

1. Playing With Others Using Headphones: Musicians Prefer Binaural Audio With Head Tracking Over Stereo (2023)
   Authors: Cecilia Björklund Boistrup, Hans Lindetorp
   Abstract: This paper investigates how musicians experience playing together...
   ID: 4c03e1d7221f0107640250c778a4a61a4b991a04

2. 3D Tune-In Toolkit: An open-source library for real-time binaural spatialisation
   ...

Enter the number of the paper to download (or 'q' to quit):
```

### Example 2: Direct Paper ID

```bash
python paper_fetcher.py --paper-id 4c03e1d7221f0107640250c778a4a61a4b991a04 --depth 1
```

This will directly download the specified paper and its connected papers.

## Output

All downloaded papers are saved in the `papers` directory, and their metadata (including titles, authors, years, and file locations) is stored in `papers_metadata.json`.
