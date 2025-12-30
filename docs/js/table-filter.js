// Table filtering functionality
class TableFilter {
  constructor(table) {
    this.table = table;
    this.rows = Array.from(table.querySelectorAll('tbody tr'));
    this.totalRows = this.rows.length;
    this.visibleRows = this.totalRows;
    
    // Dynamically discover filters
    this.filters = {};
    this.filterElements = {};
    
    this.setupFilterControls();
    this.updateCounter();
  }
  
  setupFilterControls() {
    // Auto-discover filter elements
    const filterInputs = document.querySelectorAll('[id^="filter-"]');
    
    filterInputs.forEach(element => {
      const filterId = element.id.replace('filter-', '');
      this.filters[filterId] = '';
      this.filterElements[filterId] = element;
      
      if (element.tagName === 'INPUT') {
        element.addEventListener('input', (e) => {
          this.filters[filterId] = e.target.value.toLowerCase();
          this.applyFilters();
        });
      } else if (element.tagName === 'SELECT') {
        element.addEventListener('change', (e) => {
          this.filters[filterId] = e.target.value;
          this.applyFilters();
        });
      }
    });
    
    const clearButton = document.getElementById('clear-filters');
    if (clearButton) {
      clearButton.addEventListener('click', () => {
        this.clearFilters();
      });
    }
  }
  
  applyFilters() {
    this.visibleRows = 0;
    
    this.rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      if (cells.length === 0) return;
      
      let visible = true;
      
      // Apply filters dynamically based on discovered filters
      Object.keys(this.filters).forEach(filterId => {
        const filterValue = this.filters[filterId];
        if (!filterValue) return;
        
        let cellContent = '';
        
        // Map filter IDs to table column indices
        switch (filterId) {
          case 'name':
            cellContent = (cells[0]?.textContent || '').toLowerCase();
            if (!cellContent.includes(filterValue)) visible = false;
            break;
          case 'classification':
            cellContent = (cells[2]?.textContent || '').toLowerCase();
            if (!cellContent.includes(filterValue)) visible = false;
            break;
          case 'schedule':
            cellContent = cells[3]?.textContent || '';
            if (cellContent !== filterValue) visible = false;
            break;
          // Add more filter mappings as needed
          default:
            // Try to find matching cell by header text or position
            break;
        }
      });
      
      row.style.display = visible ? '' : 'none';
      if (visible) this.visibleRows++;
    });
    
    this.updateCounter();
  }
  
  updateCounter() {
    const counter = document.getElementById('filter-count');
    if (counter) {
      counter.textContent = `Showing ${this.visibleRows} of ${this.totalRows} substances`;
    }
  }
  
  clearFilters() {
    Object.keys(this.filterElements).forEach(filterId => {
      const element = this.filterElements[filterId];
      if (element.tagName === 'INPUT') {
        element.value = '';
      } else if (element.tagName === 'SELECT') {
        element.selectedIndex = 0;
      }
      this.filters[filterId] = '';
    });
    
    this.rows.forEach(row => {
      row.style.display = '';
    });
    
    this.visibleRows = this.totalRows;
    this.updateCounter();
  }
}

// Advanced search functionality
function setupAdvancedSearch() {
  // Add keyboard shortcuts
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
      const nameFilter = document.getElementById('filter-name');
      if (nameFilter) {
        e.preventDefault();
        nameFilter.focus();
      }
    }
    
    if (e.key === 'Escape') {
      const clearButton = document.getElementById('clear-filters');
      if (clearButton) {
        clearButton.click();
      }
    }
  });
  
  // Add URL parameter support for filtering
  const urlParams = new URLSearchParams(window.location.search);
  const nameParam = urlParams.get('filter-name');
  const classificationParam = urlParams.get('filter-classification');
  const scheduleParam = urlParams.get('filter-schedule');
  
  if (nameParam) {
    const nameFilter = document.getElementById('filter-name');
    if (nameFilter) {
      nameFilter.value = nameParam;
      nameFilter.dispatchEvent(new Event('input'));
    }
  }
  
  if (classificationParam) {
    const classificationFilter = document.getElementById('filter-classification');
    if (classificationFilter) {
      classificationFilter.value = classificationParam;
      classificationFilter.dispatchEvent(new Event('input'));
    }
  }
  
  if (scheduleParam) {
    const scheduleFilter = document.getElementById('filter-schedule');
    if (scheduleFilter) {
      scheduleFilter.value = scheduleParam;
      scheduleFilter.dispatchEvent(new Event('change'));
    }
  }
}

// Export for use in main table initialization
window.TableFilter = TableFilter;
window.setupAdvancedSearch = setupAdvancedSearch;