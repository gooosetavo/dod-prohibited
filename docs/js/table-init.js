// Table sorting initialization for Material for MkDocs
function initTables() {
  // Find all tables in the main content area
  const tables = document.querySelectorAll('article table, .md-content table, main table');
  
  tables.forEach(function(table) {
    // Skip if already initialized
    if (table.hasAttribute('data-tablesort-init')) {
      return;
    }
    
    // Skip tables with existing classes (they might have custom behavior)
    if (table.className && table.className.trim()) {
      return;
    }
    
    try {
      // Initialize tablesort
      new Tablesort(table);
      
      // Initialize filtering if controls exist
      if (document.getElementById('filter-name') && typeof TableFilter !== 'undefined') {
        table.tableFilter = new TableFilter(table);
        console.log('Table filtering initialized');
      }
      
      // Mark as initialized
      table.setAttribute('data-tablesort-init', 'true');
      
      // Add some styling to indicate sortable columns
      const headers = table.querySelectorAll('th, thead td');
      headers.forEach(function(header) {
        if (header.getAttribute('data-sort-method') !== 'none') {
          header.style.cursor = 'pointer';
          header.title = header.title || 'Click to sort';
        }
      });
      
      console.log('Tablesort initialized for table');
    } catch (error) {
      console.warn('Failed to initialize tablesort for table:', error);
    }
  });
  
  // Setup advanced search features
  if (typeof setupAdvancedSearch !== 'undefined') {
    setupAdvancedSearch();
  }
}

// Initialize on DOM content loaded
document.addEventListener('DOMContentLoaded', function() {
  // Wait for Material theme to be ready
  setTimeout(initTables, 100);
});

// For Material for MkDocs instant loading
if (typeof document$ !== 'undefined') {
  document$.subscribe(function() {
    setTimeout(initTables, 50);
  });
}

// Also try to initialize when the window loads (backup)
window.addEventListener('load', function() {
  setTimeout(initTables, 100);
});

// Watch for dynamic content changes
const observer = new MutationObserver(function(mutations) {
  let shouldInit = false;
  
  mutations.forEach(function(mutation) {
    if (mutation.type === 'childList') {
      mutation.addedNodes.forEach(function(node) {
        if (node.nodeType === 1) { // Element node
          if (node.tagName === 'TABLE' || 
              (node.querySelector && node.querySelector('table'))) {
            shouldInit = true;
          }
        }
      });
    }
  });
  
  if (shouldInit) {
    setTimeout(initTables, 100);
  }
});

// Start observing when body is ready
if (document.body) {
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
} else {
  document.addEventListener('DOMContentLoaded', function() {
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  });
}