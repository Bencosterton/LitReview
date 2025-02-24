# LitReview

Automate your lit review paper discovery
A command-line tool to download academic papers and their connected references/citations using the Semantic Scholar API.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python paper_fetcher.py <paper_id> --output papers --depth 2
```

Arguments:
- `paper_id`: Semantic Scholar Paper ID or DOI
- `--output/-o`: Output directory for downloaded papers (default: 'papers')
- `--depth/-d`: Depth of connected papers to fetch (default: 1)
- `--api-key`: Optional Semantic Scholar API key
- `--verbose/-v`: Enable verbose logging

## Example

```bash
python paper_fetcher.py 649def34f8be52c8b66281af98ae884c09aef38b --depth 2
```

This will:
1. Download the specified paper
2. Find all papers that cite it and papers it references
3. Download all available PDFs
4. Save metadata about the papers in papers_metadata.json
