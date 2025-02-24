#!/usr/bin/env python3

import argparse
import aiohttp
import asyncio
import os
import json
from typing import List, Dict, Set
import logging
from urllib.parse import urlparse
import sys
import aiofiles
import time
from asyncio import Semaphore
import re
import urllib.parse
from pathlib import Path

class PaperFetcher:
    def __init__(self, output_dir: str, api_key: str = None):
        self.base_url = "https://api.semanticscholar.org/graph/v1/paper/"
        self.headers = {"x-api-key": api_key} if api_key else {}
        self.output_dir = output_dir
        self.visited_papers: Set[str] = set()
        self.logger = logging.getLogger('paper_fetcher')
        self.rate_limit = Semaphore(3)  # number of concurrent requests
        self.request_interval = 2.0  # time between requests in seconds
        self.last_request_time = 0

    async def wait_for_rate_limit(self):
        """Ensure we don't exceed API rate limits"""
        now = time.time()
        if now - self.last_request_time < self.request_interval:
            await asyncio.sleep(self.request_interval - (now - self.last_request_time))
        self.last_request_time = time.time()

    def clean_filename(self, title: str) -> str:
        """Convert title to a clean filename"""
        clean = re.sub(r'[^\w\s-]', '', title)
        clean = re.sub(r'[-\s]+', '_', clean)
        return clean[:100]

    def extract_filename_from_response(self, response: aiohttp.ClientResponse, paper_data: Dict) -> str:
        """Extract filename from response headers or generate from title"""
        # try to get filename
        cd = response.headers.get('Content-Disposition')
        if cd:
            fname = re.findall("filename=(.+)", cd)
            if fname:
                filename = fname[0].strip('"')
                self.logger.info(f"Using filename from Content-Disposition: {filename}")
                return filename

        # try to get filename from url
        url_path = urllib.parse.urlparse(str(response.url)).path
        if url_path and url_path.endswith('.pdf'):
            url_filename = Path(url_path).stem
            if len(url_filename) > 10:
                self.logger.info(f"Using filename from URL: {url_filename}.pdf")
                return f"{url_filename}.pdf"

        title = paper_data.get('title', '')
        if title:
            clean_name = f"{self.clean_filename(title)}.pdf"
            self.logger.info(f"Generated filename from title: {clean_name}")
            return clean_name

        # if a filename cannot be found, use paper_id
        fallback = f"{paper_data.get('paperId', 'unknown')}.pdf"
        self.logger.info(f"Using fallback filename: {fallback}")
        return fallback

    async def try_alternative_sources(self, paper_data: Dict, session: aiohttp.ClientSession) -> str:
        """Try to find PDF from alternative sources"""
        try:
            # arXiv
            arxiv_id = None
            if paper_data.get('externalIds', {}).get('ArXiv'):
                arxiv_id = paper_data['externalIds']['ArXiv']
                arxiv_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                async with session.get(arxiv_url) as response:
                    if response.status == 200:
                        return arxiv_url

            # unpaywall
            if paper_data.get('externalIds', {}).get('DOI'):
                doi = paper_data['externalIds']['DOI']
                unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=test@example.com"
                async with session.get(unpaywall_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('best_oa_location', {}).get('url_for_pdf'):
                            return data['best_oa_location']['url_for_pdf']

            # CORE API
            if paper_data.get('externalIds', {}).get('DOI'):
                core_url = f"https://api.core.ac.uk/v3/search/works?q=doi:{doi}"
                headers = {"Authorization": "Bearer your_core_api_key"}  # Optional
                async with session.get(core_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('results') and data['results'][0].get('downloadUrl'):
                            return data['results'][0]['downloadUrl']

            return None
        except Exception as e:
            self.logger.debug(f"Error checking alternative sources: {str(e)}")
            return None

    async def download_pdf(self, paper_data: Dict, session: aiohttp.ClientSession) -> bool:
        """Download PDF file from the given paper data"""
        title = paper_data.get('title', 'Unknown Title')
        
        try:
            # semantic scholar's open access
            pdf_url = None
            if paper_data.get('openAccessPdf'):
                pdf_url = paper_data['openAccessPdf'].get('url')
                self.logger.info(f"Found open access PDF URL: {pdf_url}")
            
            # if semantic scholar returns error, try other sources
            if not pdf_url:
                pdf_url = await self.try_alternative_sources(paper_data, session)
                if pdf_url:
                    self.logger.info(f"Found PDF from alternative source: {pdf_url}")
                
            if not pdf_url:
                print(f"❌ {title} - No open access PDF available")
                return False

            self.logger.info(f"Attempting to download from: {pdf_url}")
            
            async with session.get(pdf_url) as response:
                if response.status == 200:
                    # get filename
                    filename = self.extract_filename_from_response(response, paper_data)
                    filepath = os.path.join(self.output_dir, filename)
                    
                    # adjust filename if it is already taken
                    base, ext = os.path.splitext(filepath)
                    counter = 1
                    while os.path.exists(filepath):
                        filepath = f"{base}_{counter}{ext}"
                        counter += 1
                        self.logger.info(f"File exists, trying new name: {os.path.basename(filepath)}")

                    self.logger.info(f"Saving to: {filepath}")
                    async with aiofiles.open(filepath, 'wb') as f:
                        await f.write(await response.read())
                    print(f"✅ Downloaded: {title} -> {os.path.basename(filepath)}")
                    
                    # add file name to paper metadata
                    paper_data['saved_filename'] = os.path.basename(filepath)
                    return True
                print(f"❌ {title} - Failed to download PDF (Status: {response.status})")
                return False
        except Exception as e:
            print(f"❌ {title} - Error downloading PDF: {str(e)}")
            self.logger.error(f"Download error details: {str(e)}", exc_info=True)
            return False

    async def fetch_paper_details(self, paper_id: str, session: aiohttp.ClientSession, retries=3) -> Dict:
        """Fetch paper metadata from Semantic Scholar API with retries"""
        async with self.rate_limit:
            for attempt in range(retries):
                try:
                    await self.wait_for_rate_limit()
                    params = {
                        'fields': 'title,year,authors,citations,references,externalIds,url,openAccessPdf'
                    }
                    async with session.get(f"{self.base_url}{paper_id}", params=params, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.logger.info(f"Successfully fetched metadata for paper: {data.get('title', 'Unknown')}")
                            return data
                        elif response.status == 429:
                            wait_time = 5 * (attempt + 1)  
                            self.logger.warning(f"Rate limit hit, waiting {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            self.logger.error(f"Failed to fetch paper {paper_id}: Status {response.status}")
                            return None
                except Exception as e:
                    self.logger.error(f"Error fetching paper {paper_id}: {str(e)}")
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                        continue
                    return None
            return None

    async def process_paper(self, paper_id: str, depth: int, session: aiohttp.ClientSession) -> List[Dict]:
        """Process a paper and its connected papers recursively"""
        if paper_id in self.visited_papers or depth < 0:
            return []
            
        self.visited_papers.add(paper_id)
        paper_data = await self.fetch_paper_details(paper_id, session)
        
        if not paper_data:
            return []
            
        results = []
        # proccess the chosen paper
        if await self.download_pdf(paper_data, session):
            results.append({
                'id': paper_id,
                'title': paper_data.get('title', 'Unknown'),
                'authors': [a.get('name', '') for a in paper_data.get('authors', [])],
                'year': paper_data.get('year'),
                'url': paper_data.get('url'),
                'filename': paper_data.get('saved_filename'),
                'pdf_path': os.path.join(self.output_dir, paper_data.get('saved_filename', f"{paper_id}.pdf"))
            })

        # proccess the references papers inside chosen paper
        connected_papers = []
        if paper_data.get('references'):
            connected_papers.extend(paper_data['references'])
        if paper_data.get('citations'):
            connected_papers.extend(paper_data['citations'])

        if connected_papers:
            print(f"\nProcessing {len(connected_papers)} papers connected to: {paper_data.get('title')}")
        
        tasks = []
        for paper in connected_papers:
            if paper.get('paperId'):
                tasks.append(self.process_paper(paper['paperId'], depth - 1, session))
        
        if tasks:
            child_results = await asyncio.gather(*tasks)
            for result in child_results:
                results.extend(result)
                
        return results

    async def search_papers(self, query: str, session: aiohttp.ClientSession, limit: int = 5) -> List[Dict]:
        """Search for papers using Semantic Scholar API"""
        search_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,authors,year,abstract,externalIds,url,paperId"
        }

        max_retries = 3
        retry_delay = 5 
        
        for attempt in range(max_retries):
            async with self.rate_limit:
                await self.wait_for_rate_limit()
                try:
                    async with session.get(search_url, params=params, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get('data', [])
                        elif response.status == 429:  # this is the rate limit error code
                            if attempt < max_retries - 1:
                                self.logger.warning(f"Rate limit hit, waiting {retry_delay} seconds...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  
                                continue
                        self.logger.error(f"Search failed with status {response.status}")
                        return []
                except Exception as e:
                    self.logger.error(f"Error during search: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return []
        return []

    async def fetch_connected_papers(self, paper_id: str, depth: int = 1):
        """Main method to fetch and download connected papers"""
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"\n📚 Starting paper download with depth {depth}")
        print("=" * 80)
        
        async with aiohttp.ClientSession() as session:
            results = await self.process_paper(paper_id, depth, session)
        
        # save all the metadata
        metadata_file = os.path.join(self.output_dir, 'papers_metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print("\n" + "=" * 80)
        print(f"📊 Summary:")
        print(f"   - Processed {len(self.visited_papers)} papers in total")
        print(f"   - Successfully downloaded {len(results)} PDFs")
        print(f"   - PDFs saved to: {self.output_dir}/")
        print(f"   - Metadata saved to: {metadata_file}")
        print("=" * 80)
        
        return results

async def main():
    parser = argparse.ArgumentParser(description='Download academic papers and their references')
    parser.add_argument('--search', type=str, help='Search term to find papers')
    parser.add_argument('--paper-id', type=str, help='Semantic Scholar paper ID')
    parser.add_argument('--depth', type=int, default=0, help='How many levels of references to download')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--api-key', type=str, help='Semantic Scholar API key')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')

    if not (args.search or args.paper_id):
        parser.error("Either --search or --paper-id must be provided")

    output_dir = "papers"
    os.makedirs(output_dir, exist_ok=True)

    fetcher = PaperFetcher(output_dir, args.api_key)
    async with aiohttp.ClientSession() as session:
        if args.search:
            papers = await fetcher.search_papers(args.search, session)
            if not papers:
                print("No papers found matching your search.")
                return
            
            print("\nFound papers:")
            for i, paper in enumerate(papers, 1):
                authors = ", ".join(a.get('name', '') for a in paper.get('authors', []))
                print(f"\n{i}. {paper['title']} ({paper.get('year', 'N/A')})")
                print(f"   Authors: {authors}")
                if paper.get('abstract'):
                    print(f"   Abstract: {paper['abstract'][:200]}...")
                print(f"   ID: {paper['paperId']}")

            while True:
                try:
                    choice = input("\nEnter the number of the paper to download (or 'q' to quit): ")
                    if choice.lower() == 'q':
                        return
                    choice = int(choice)
                    if 1 <= choice <= len(papers):
                        args.paper_id = papers[choice-1]['paperId']
                        break
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Please enter a valid number or 'q' to quit.")

        await fetcher.process_paper(args.paper_id, args.depth, session)

if __name__ == "__main__":
    asyncio.run(main())
