// Table filtering functionality
class TableFilter {
  constructor(table) {
    this.table = table;
    this.rows = Array.from(table.querySelectorAll('tbody tr'));
    this.totalRows = this.rows.length;
    this.visibleRows = this.totalRows;
    
    // Column-based filters
    this.columnFilters = {};
    this.filterElements = [];
    
    this.setupFilterControls();
    this.updateCounter();
  }
  
  setupFilterControls() {
    // Find all column filter elements
    const filterInputs = this.table.querySelectorAll('.column-filter');
    
    filterInputs.forEach(element => {
      const columnIndex = parseInt(element.dataset.column);
      this.columnFilters[columnIndex] = '';
      this.filterElements.push(element);
      
      if (element.tagName === 'INPUT') {
        element.addEventListener('input', (e) => {
          this.columnFilters[columnIndex] = e.target.value.toLowerCase();
          this.applyFilters();
        });
        
        // Prevent sorting when clicking on input
        element.addEventListener('click', (e) => {
          e.stopPropagation();
        });
      } else if (element.tagName === 'SELECT') {
        element.addEventListener('change', (e) => {
          this.columnFilters[columnIndex] = e.target.value;
          this.applyFilters();
        });
        
        // Prevent sorting when clicking on select
        element.addEventListener('click', (e) => {
          e.stopPropagation();
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
      
      // Apply filters for each column
      Object.keys(this.columnFilters).forEach(columnIndex => {
        const filterValue = this.columnFilters[columnIndex];
        if (!filterValue) return;
        
        const cellContent = (cells[columnIndex]?.textContent || '').toLowerCase();
        
        // For select elements (like DEA schedule), do exact match
        // For text inputs, do partial match
        const filterElement = this.filterElements.find(el => 
          parseInt(el.dataset.column) === parseInt(columnIndex)
        );
        
        if (filterElement?.tagName === 'SELECT') {
          if (cells[columnIndex]?.textContent.trim() !== filterValue) {
            visible = false;
          }
        } else {
          if (!cellContent.includes(filterValue.toLowerCase())) {
            visible = false;
          }
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
    this.filterElements.forEach(element => {
      if (element.tagName === 'INPUT') {
        element.value = '';
      } else if (element.tagName === 'SELECT') {
        element.selectedIndex = 0;
      }
      const columnIndex = parseInt(element.dataset.column);
      this.columnFilters[columnIndex] = '';
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
      const nameFilter = document.querySelector('.column-filter[data-column="0"]');
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
    const nameFilter = document.querySelector('.column-filter[data-column="0"]');
    if (nameFilter) {
      nameFilter.value = nameParam;
      nameFilter.dispatchEvent(new Event('input'));
    }
  }
  
  if (classificationParam) {
    const classificationFilter = document.querySelector('.column-filter[data-column="2"]');
    if (classificationFilter) {
      classificationFilter.value = classificationParam;
      classificationFilter.dispatchEvent(new Event('input'));
    }
  }
  
  if (scheduleParam) {
    const scheduleFilter = document.querySelector('.column-filter[data-column="3"]');
    if (scheduleFilter) {
      scheduleFilter.value = scheduleParam;
      scheduleFilter.dispatchEvent(new Event('change'));
    }
  }
}

// Export for use in main table initialization
window.TableFilter = TableFilter;
window.setupAdvancedSearch = setupAdvancedSearch;