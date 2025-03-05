import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

class UWIPDFCrawler:
    def __init__(self, start_url, output_folder="uwi_pdfs", max_depth=3, max_pdfs=None, 
                 concurrency=5, politeness_delay=1, user_agent=None):
        """
        Initialize the PDF crawler for UWI Mona website.
        
        Args:
            start_url (str): The starting URL for crawling
            output_folder (str): Folder to save downloaded PDFs
            max_depth (int): Maximum crawl depth
            max_pdfs (int): Maximum number of PDFs to download (None for unlimited)
            concurrency (int): Number of concurrent download threads
            politeness_delay (float): Delay between requests to be polite to the server
            user_agent (str): Custom user agent string
        """
        self.start_url = start_url
        self.base_domain = urlparse(start_url).netloc
        self.output_folder = output_folder
        self.max_depth = max_depth
        self.max_pdfs = max_pdfs
        self.concurrency = concurrency
        self.politeness_delay = politeness_delay
        
        # Default user agent that identifies the crawler
        self.user_agent = user_agent or 'UWI-PDF-Crawler/1.0'
        
        # State tracking
        self.visited_urls = set()
        self.urls_to_visit = [(start_url, 0)]  # (url, depth)
        self.found_pdfs = set()
        self.downloaded_pdfs = set()
        
        # Ensure the output folder exists
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Initialize counters for statistics
        self.pages_crawled = 0
        self.pdfs_found = 0
        self.pdfs_downloaded = 0
    
    def is_valid_url(self, url):
        """Check if URL should be crawled (same domain, not already visited)."""
        parsed_url = urlparse(url)
        
        # Check if URL is from the same domain or subdomain
        if not (parsed_url.netloc == self.base_domain or 
                parsed_url.netloc.endswith('.' + self.base_domain)):
            return False
        
        # Skip URLs with fragments only
        if parsed_url.path == '' and parsed_url.fragment != '':
            return False
            
        # Skip common non-content URLs
        skip_patterns = [
            r'/search', r'/login', r'/logout', r'/register', 
            r'/calendar', r'/user', r'/auth', r'/account',
            r'\?sort=', r'\?filter=', r'\?page=', r'\?view='
        ]
        url_lower = url.lower()
        for pattern in skip_patterns:
            if re.search(pattern, url_lower):
                return False
        
        return True
    
    def is_pdf_url(self, url):
        """Check if the URL points to a PDF file."""
        url_lower = url.lower()
        return url_lower.endswith('.pdf')
    
    def get_safe_filename(self, url):
        """Generate a safe filename based on the URL."""
        # Extract filename from URL path if available
        path = urlparse(url).path
        filename = os.path.basename(path)
        
        # If no filename or it doesn't end with .pdf, create one from the URL
        if not filename or not filename.lower().endswith('.pdf'):
            # Generate a filename from the URL by replacing special characters
            filename = re.sub(r'[^a-zA-Z0-9]', '_', url)
            # Truncate if too long
            if len(filename) > 100:
                filename = filename[:100]
            filename += '.pdf'
        
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        
        # Ensure the filename is safe for the filesystem
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        return filename
    
    def download_pdf(self, url):
        """Download a PDF file from the given URL."""
        if url in self.downloaded_pdfs:
            return False
        
        try:
            # Add a slight delay to be nice to the server
            time.sleep(self.politeness_delay + random.random())
            
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Check if the content type is PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                print(f"Skipping non-PDF content ({content_type}): {url}")
                return False
            
            # Generate a safe filename
            filename = self.get_safe_filename(url)
            filepath = os.path.join(self.output_folder, filename)
            
            # Write the PDF file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Update tracking
            self.downloaded_pdfs.add(url)
            self.pdfs_downloaded += 1
            
            print(f"Downloaded [{self.pdfs_downloaded}]: {url} -> {filename}")
            return True
            
        except Exception as e:
            print(f"Error downloading {url}: {str(e)}")
            return False
    
    def extract_links(self, url, html_content):
        """Extract links from HTML content."""
        links = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all links in the page
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            
            # Skip empty links and javascript links
            if not href or href.startswith(('javascript:', '#', 'mailto:', 'tel:')):
                continue
            
            # Convert relative URL to absolute
            absolute_url = urljoin(url, href)
            
            links.append(absolute_url)
        
        return links
    
    def crawl_page(self, url, depth):
        """Crawl a single page and extract links and PDFs."""
        if url in self.visited_urls:
            return []
        
        self.visited_urls.add(url)
        self.pages_crawled += 1
        
        print(f"Crawling [{self.pages_crawled}] (depth {depth}): {url}")
        
        try:
            # Add a slight delay to be nice to the server
            time.sleep(self.politeness_delay + random.random())
            
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Check if the response is HTML
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                if self.is_pdf_url(url):
                    self.found_pdfs.add(url)
                    self.pdfs_found += 1
                    print(f"Found PDF ({self.pdfs_found}): {url}")
                return []
            
            # Extract links from the page
            links = self.extract_links(url, response.text)
            next_links = []
            
            for link in links:
                # Check if the link is a PDF
                if self.is_pdf_url(link) and link not in self.found_pdfs:
                    self.found_pdfs.add(link)
                    self.pdfs_found += 1
                    print(f"Found PDF ({self.pdfs_found}): {link}")
                
                # Only add non-visited URLs within domain for further crawling if not at max depth
                elif (depth < self.max_depth and 
                      link not in self.visited_urls and 
                      self.is_valid_url(link)):
                    next_links.append((link, depth + 1))
            
            return next_links
            
        except Exception as e:
            print(f"Error crawling {url}: {str(e)}")
            return []
    
    def run(self):
        """Run the crawler to find and download PDFs."""
        start_time = time.time()
        print(f"Starting crawl from {self.start_url}")
        print(f"PDFs will be saved to: {os.path.abspath(self.output_folder)}")
        
        # First phase: Crawl pages to find PDFs
        while self.urls_to_visit:
            url, depth = self.urls_to_visit.pop(0)
            
            # Check if we've reached the maximum number of PDFs
            if self.max_pdfs and self.pdfs_found >= self.max_pdfs:
                break
            
            # Crawl the page and get new links to visit
            new_links = self.crawl_page(url, depth)
            
            # Add new links to the queue
            self.urls_to_visit.extend(new_links)
        
        # Second phase: Download found PDFs using thread pool for concurrency
        print(f"\nCrawling complete. Found {self.pdfs_found} PDF files.")
        print(f"Starting download of PDFs...")
        
        # Limit to max_pdfs if specified
        pdfs_to_download = list(self.found_pdfs)
        if self.max_pdfs:
            pdfs_to_download = pdfs_to_download[:self.max_pdfs]
        
        # Download PDFs concurrently
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            # Submit download tasks
            future_to_url = {executor.submit(self.download_pdf, url): url for url in pdfs_to_download}
            
            # Process results as they complete
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error processing {url}: {str(e)}")
        
        # Print final statistics
        elapsed_time = time.time() - start_time
        print(f"\nCrawling complete!")
        print(f"Pages crawled: {self.pages_crawled}")
        print(f"PDFs found: {self.pdfs_found}")
        print(f"PDFs downloaded: {self.pdfs_downloaded}")
        print(f"Time elapsed: {elapsed_time:.2f} seconds")
        print(f"PDFs saved to: {os.path.abspath(self.output_folder)}")

if __name__ == "__main__":
    # Configuration
    START_URL = "https://www.mona.uwi.edu/"
    OUTPUT_FOLDER = "uwi_pdfs"
    MAX_DEPTH = 4         # How deep to crawl
    MAX_PDFS = None       # Maximum PDFs to download (None for unlimited)
    CONCURRENCY = 5       # Number of concurrent downloads
    POLITENESS_DELAY = 1  # Delay between requests in seconds
    
    # Create and run the crawler
    crawler = UWIPDFCrawler(
        start_url=START_URL,
        output_folder=OUTPUT_FOLDER,
        max_depth=MAX_DEPTH,
        max_pdfs=MAX_PDFS,
        concurrency=CONCURRENCY,
        politeness_delay=POLITENESS_DELAY
    )
    
    crawler.run()