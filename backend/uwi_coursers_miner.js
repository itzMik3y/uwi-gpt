// This script will collect all course data by using a more robust approach
// that focuses on network request interception and better timing

// Array to store all collected course data
let allCourseData = [];
let pageCounter = 1;
const MAX_TEST_PAGES = 126; // Change this to collect more pages
let dataCapturePending = false;

// Set up a flag to track if we've captured data for the current page
let currentPageDataCaptured = false;
let totalPagesEstimate = 0;

// Function to set up network request monitoring using fetch API
function monitorNetworkRequests() {
  console.log('🔍 Setting up network monitoring...');
  
  // Store the original fetch function
  const originalFetch = window.fetch;
  
  // Override fetch to intercept network requests
  window.fetch = async function(...args) {
    const url = args[0];
    
    // Check if this is a course data request
    if (typeof url === 'string' && url.includes('courseSearchResults')) {
      console.log(`🔄 Intercepted course data request for page ${pageCounter}`);
      dataCapturePending = true;
      
      // Call the original fetch function and get the response
      const response = await originalFetch.apply(this, args);
      
      // Clone the response so we can read the body twice
      const clonedResponse = response.clone();
      
      // Process the response data asynchronously
      clonedResponse.json().then(data => {
        if (data && data.data && Array.isArray(data.data)) {
          console.log(`📊 Captured API data: ${data.data.length} courses on page ${pageCounter}`);
          
          // Store total count information
          if (data.totalCount && data.pageMaxSize) {
            totalPagesEstimate = Math.ceil(data.totalCount / data.pageMaxSize);
            console.log(`Total courses: ${data.totalCount}, Estimated pages: ${totalPagesEstimate}`);
          }
          
          // Process the course data
          const newCourses = data.data.map(course => ({
            ...course,
            page: pageCounter,
            source: 'fetch'
          }));
          
          // Add to our collection
          allCourseData = allCourseData.concat(newCourses);
          console.log(`Total courses collected so far: ${allCourseData.length}`);
          
          // Mark that we've captured data for this page
          currentPageDataCaptured = true;
          dataCapturePending = false;
        }
      }).catch(error => {
        console.error('Error processing response:', error);
        dataCapturePending = false;
      });
      
      // Return the original response
      return response;
    }
    
    // For other requests, just pass through to the original fetch
    return originalFetch.apply(this, args);
  };
  
  // Also intercept XMLHttpRequest for older systems
  const originalXHR = window.XMLHttpRequest.prototype.open;
  window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    // Store the URL so we can check it in onreadystatechange
    this._fetchUrl = url;
    return originalXHR.apply(this, [method, url, ...rest]);
  };
  
  const originalSend = window.XMLHttpRequest.prototype.send;
  window.XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    
    // Add a listener for load completion
    xhr.addEventListener('load', function() {
      if (xhr.readyState === 4 && xhr.status === 200) {
        if (xhr._fetchUrl && xhr._fetchUrl.includes('courseSearchResults')) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data && data.data && Array.isArray(data.data)) {
              console.log(`📊 Captured XHR data: ${data.data.length} courses on page ${pageCounter}`);
              
              // Store total count information
              if (data.totalCount && data.pageMaxSize) {
                totalPagesEstimate = Math.ceil(data.totalCount / data.pageMaxSize);
                console.log(`Total courses: ${data.totalCount}, Estimated pages: ${totalPagesEstimate}`);
              }
              
              // Process the course data
              const newCourses = data.data.map(course => ({
                ...course,
                page: pageCounter,
                source: 'xhr'
              }));
              
              // Add to our collection
              allCourseData = allCourseData.concat(newCourses);
              console.log(`Total courses collected so far: ${allCourseData.length}`);
              
              // Mark that we've captured data for this page
              currentPageDataCaptured = true;
              dataCapturePending = false;
            }
          } catch (error) {
            console.error('Error processing XHR response:', error);
            dataCapturePending = false;
          }
        }
      }
    });
    
    // Call the original send method
    return originalSend.apply(this, arguments);
  };
  
  console.log('✅ Network monitoring set up successfully');
}

// Function to set the page size to 50 (or largest available)
async function setLargerPageSize() {
  console.log('🔧 Setting larger page size...');
  
  // Reset the data captured flag
  currentPageDataCaptured = false;
  dataCapturePending = false;
  
  // Find the page size selector from the screenshot
  const pageSizeSelect = document.querySelector('select');
  
  if (pageSizeSelect) {
    // Get available options
    const options = Array.from(pageSizeSelect.options);
    console.log('Available page sizes:', options.map(opt => opt.value));
    
    // Find the option with value 50
    const option50 = options.find(opt => opt.value === '50');
    
    if (option50) {
      console.log('Found option for 50 items per page');
      pageSizeSelect.value = '50';
    } else {
      // Find the largest numeric option
      const numericOptions = options
        .map(opt => ({value: opt.value, numeric: parseInt(opt.value, 10)}))
        .filter(opt => !isNaN(opt.numeric));
      
      if (numericOptions.length > 0) {
        const largest = numericOptions.reduce((max, current) => 
          current.numeric > max.numeric ? current : max, numericOptions[0]);
        
        console.log(`Using largest available page size: ${largest.value}`);
        pageSizeSelect.value = largest.value;
      }
    }
    
    // Trigger change event to apply the new page size
    pageSizeSelect.dispatchEvent(new Event('change', { bubbles: true }));
    
    // Wait for the page to reload with the new size
    console.log('Waiting for page to reload with new size...');
    await waitForDataLoad(5000);
    
    console.log(`✅ Page size changed to ${pageSizeSelect.value}`);
  } else {
    console.log('⚠️ Page size selector not found');
  }
}

// Function to navigate to a specific page
async function goToPage(pageNum) {
  console.log(`🔢 Navigating to page ${pageNum}...`);
  
  // Reset page data captured flag
  currentPageDataCaptured = false;
  dataCapturePending = false;
  
  // Find the page input field from the screenshot
  const pageInput = document.querySelector('input.page-number.enabled') || 
                   document.querySelector('input[type="text"][value]');
  
  if (!pageInput) {
    console.log('⚠️ Page input field not found');
    return false;
  }
  
  // Set the value to the target page
  pageInput.value = pageNum.toString();
  
  // Update page counter
  pageCounter = pageNum;
  
  // Trigger input events
  pageInput.dispatchEvent(new Event('input', { bubbles: true }));
  pageInput.dispatchEvent(new Event('change', { bubbles: true }));
  
  // Press Enter key to navigate
  pageInput.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true
  }));
  
  // Wait for data to load
  console.log('Waiting for page data to load...');
  await waitForDataLoad(5000);
  
  return true;
}

// Helper function to wait for data to load with timeout
async function waitForDataLoad(maxWaitTime = 5000) {
  const startTime = Date.now();
  dataCapturePending = true;
  
  return new Promise(resolve => {
    const checkInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      
      // Check if data has been captured or if we've timed out
      if (currentPageDataCaptured || elapsed >= maxWaitTime) {
        clearInterval(checkInterval);
        
        if (currentPageDataCaptured) {
          console.log('✅ Data successfully captured');
        } else {
          console.log('⚠️ Wait timeout reached, continuing anyway');
          dataCapturePending = false;
        }
        
        resolve();
      }
    }, 200);
  });
}

// Function to extract visible course data from the DOM as backup
function extractVisibleCourseData() {
  console.log(`🔍 Extracting visible course data from page ${pageCounter}...`);
  
  // Find all rows in the course table
  const rows = Array.from(document.querySelectorAll('tr')).filter(row => {
    // Filter to rows with course data (typically with 5+ cells)
    const cells = row.querySelectorAll('td');
    return cells.length >= 5;
  });
  
  if (rows.length === 0) {
    console.log('⚠️ No course rows found in DOM');
    return [];
  }
  
  console.log(`Found ${rows.length} course rows in DOM`);
  
  // Extract course data from each row
  const courseData = rows.map(row => {
    const cells = row.querySelectorAll('td');
    
    // Extract the course title (sometimes in an <a> tag)
    let title = '';
    if (cells[0]) {
      const titleLink = cells[0].querySelector('a');
      title = titleLink ? titleLink.textContent.trim() : cells[0].textContent.trim();
    }
    
    return {
      title: title,
      subject: cells[1] ? cells[1].textContent.trim() : '',
      courseNumber: cells[2] ? cells[2].textContent.trim() : '',
      hours: cells[3] ? cells[3].textContent.trim() : '',
      description: cells[4] ? cells[4].textContent.trim() : '',
      page: pageCounter,
      source: 'dom'
    };
  });
  
  console.log(`Extracted ${courseData.length} courses from DOM`);
  
  // Only add DOM data if we haven't already captured it via network
  if (!currentPageDataCaptured) {
    allCourseData = allCourseData.concat(courseData);
    console.log(`Added DOM data, total courses: ${allCourseData.length}`);
  } else {
    console.log('Network data already captured, skipping DOM extraction');
  }
  
  return courseData;
}

// Function to download the collected data
function downloadData() {
  console.log(`💾 Preparing to download ${allCourseData.length} course records...`);
  
  // Remove duplicate entries
  const uniqueData = removeDuplicates(allCourseData);
  console.log(`After removing duplicates: ${uniqueData.length} unique courses`);
  
  // Create JSON file
  const dataStr = JSON.stringify(uniqueData, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  
  // Create download link
  const a = document.createElement('a');
  a.href = url;
  a.download = 'course_data.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  
  console.log('✅ Data downloaded as course_data.json');
}

// Helper function to remove duplicate entries
function removeDuplicates(courses) {
  const seen = new Set();
  return courses.filter(course => {
    // Create a unique key for each course (using title and number)
    const key = course.title && course.courseNumber ? 
      `${course.title}-${course.courseNumber}` : 
      JSON.stringify(course);
    
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Main function to process pages
async function processPages() {
  try {
    // Set up network monitoring
    monitorNetworkRequests();
    
    // Set larger page size
    await setLargerPageSize();
    
    // Process each page
    for (let page = 1; page <= MAX_TEST_PAGES; page++) {
      console.log(`\n📄 Processing page ${page} of ${MAX_TEST_PAGES}...`);
      
      // Navigate to the page
      await goToPage(page);
      
      // Extract visible data as backup
      extractVisibleCourseData();
      
      // Short pause between pages
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    console.log(`\n✅ Completed processing ${MAX_TEST_PAGES} pages`);
    console.log(`Total courses collected: ${allCourseData.length}`);
    
    // Download the data
    downloadData();
    
  } catch (error) {
    console.error('❌ Error in page processing:', error);
  }
}

// Start the data collection process
console.log('🚀 Starting course data collection...');
processPages();