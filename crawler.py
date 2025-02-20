import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import textwrap

def crawl_and_save(start_url, pdf_folder="downloaded_pdf", files_folder="downloaded_files", max_depth=2):
    visited = set()
    pages = {}
    
    # Ensure output folders exist.
    os.makedirs(pdf_folder, exist_ok=True)
    os.makedirs(files_folder, exist_ok=True)
    
    # Define file extensions.
    downloadable_exts = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.txt']
    image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']
    
    def safe_filename(url):
        # Generate a safe filename from the URL.
        filename = os.path.basename(urlparse(url).path)
        if not filename or '.' in filename:
            filename = url.replace("https://", "").replace("http://", "").replace("/", "_")
        return filename

    def save_text_pdf_reportlab(html_content, url):
        # Extract text from HTML using BeautifulSoup.
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        if not text:
            print(f"No text extracted from {url}")
            return
        
        filename = safe_filename(url)
        pdf_path = os.path.join(pdf_folder, f"{filename}.pdf")
        
        # Create a text-only PDF using ReportLab.
        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        margin = 40
        textobject = c.beginText(margin, height - margin)
        textobject.setFont("Helvetica", 12)
        
        # Wrap text to fit within page margins.
        for line in text.splitlines():
            wrapped_lines = textwrap.wrap(line, width=90)
            for wline in wrapped_lines:
                textobject.textLine(wline)
            textobject.textLine("")  # blank line between paragraphs.
            if textobject.getY() < margin:
                c.drawText(textobject)
                c.showPage()
                textobject = c.beginText(margin, height - margin)
                textobject.setFont("Helvetica", 12)
                
        c.drawText(textobject)
        try:
            c.save()
            print(f"Saved text-only PDF: {pdf_path}")
        except Exception as e:
            print(f"Error saving PDF for {url}: {e}")

    def download_file(url):
        lower_url = url.lower()
        # Skip image files.
        if any(lower_url.endswith(ext) for ext in image_exts):
            print(f"Skipping image file: {url}")
            return
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"Error downloading file {url}: {e}")
            return
        filename = safe_filename(url)
        file_path = os.path.join(files_folder, filename)
        try:
            with open(file_path, "wb") as f:
                f.write(response.content)
            print(f"Downloaded file: {file_path}")
        except Exception as e:
            print(f"Error saving file {url}: {e}")

    def crawl(url, depth):
        if depth > max_depth or url in visited:
            return
        visited.add(url)
        print(f"Crawling (depth {depth}): {url}")
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to retrieve {url}: {e}")
            return

        content_type = response.headers.get('Content-Type', '')
        if "text/html" in content_type:
            html_content = response.text
            pages[url] = html_content
            # Save a text-only PDF of the page.
            save_text_pdf_reportlab(html_content, url)
            soup = BeautifulSoup(html_content, "html.parser")
            # Process all <a> tags.
            for tag in soup.find_all("a"):
                href = tag.get("href")
                if href:
                    next_url = urljoin(url, href)
                    # Ensure links are within the same domain.
                    if urlparse(next_url).netloc == urlparse(start_url).netloc:
                        path = urlparse(next_url).path.lower()
                        # If the link is to a downloadable file, download it.
                        if any(path.endswith(ext) for ext in downloadable_exts):
                            download_file(next_url)
                        else:
                            crawl(next_url, depth + 1)
        else:
            # If non-HTML and not an image, download it.
            if not any(url.lower().endswith(ext) for ext in image_exts):
                download_file(url)
            else:
                print(f"Skipping non-HTML image content: {url}")

    crawl(start_url, 0)
    return pages

if __name__ == "__main__":
    start = "https://www.mona.uwi.edu/"  # Replace with your target URL.
    pages = crawl_and_save(start)
    print("Crawled pages:")
    for url in pages:
        print(url)
