/*!
 * tablesort v5.3.0 (2021-02-14)
 * http://tristen.ca/tablesort/demo/
 * Copyright (c) 2017-2021 ; Licensed MIT
*/
!function(){var a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z;a=function(a,b){if("undefined"!=typeof module&&module.exports)return b();if("function"==typeof define&&define.amd)return define(b);this[a]=b()};a("Tablesort",function(){"use strict";function a(a,b){if(!(this instanceof a))return new a(a,b);if(!a||"TABLE"!==a.tagName)throw new Error("Element must be a table");this.init(a,b||{})}var b=[],c=function(a){var b;return window.CustomEvent&&"function"==typeof window.CustomEvent?b=new CustomEvent(a):(b=document.createEvent("CustomEvent"),b.initCustomEvent(a,!1,!1,void 0)),b},d=function(a){return a.getAttribute("data-sort")||a.textContent||a.innerText||""},e=function(a,b){return a=a.trim().toLowerCase(),b=b.trim().toLowerCase(),a===b?0:a<b?1:-1},f=function(a,b){return function(c,d){var e=a(c.td,d.td);return 0===e?b?d.index-c.index:c.index-d.index:e}},g=function(a){return function(b,c){var d=a(b.td,c.td);return 0===d?b.index-c.index:d}};a.extend=function(a,c,d){if("function"!=typeof c||"function"!=typeof d)throw new Error("Pattern and sort must be a function");b.push({name:a,pattern:c,sort:d})},a.prototype={init:function(a,b){var c,d,e,f,g=this;if(g.table=a,g.thead=!1,g.options=b,a.rows&&a.rows.length>0)if(a.tHead&&a.tHead.rows.length>0){for(e=0;e<a.tHead.rows.length;e++)if("thead"===a.tHead.rows[e].getAttribute("data-sort-method")){c=a.tHead.rows[e];break}c||(c=a.tHead.rows[a.tHead.rows.length-1]),g.thead=!0}else c=a.rows[0];if(c){var h=function(){g.current&&g.current!==this&&g.current.removeAttribute("aria-sort"),g.current=this,g.sortTable(this)};for(e=0;e<c.cells.length;e++)f=c.cells[e],f.setAttribute("role","columnheader"),"none"!==f.getAttribute("data-sort-method")&&(f.tabindex=0,f.addEventListener("click",h,!1),null!==f.getAttribute("data-sort-default")&&(d=f));"descending"===g.options.descending?g.sortTable(d,!0):d&&g.sortTable(d)}},sortTable:function(a,h){var i=this,j=a.cellIndex,k=e,l="",m=[],n=i.thead?0:1,o=a.getAttribute("data-sort-method"),p=a.getAttribute("aria-sort");if(i.table.dispatchEvent(c("beforeSort")),h?l="ascending"===p?"descending":"descending"===p?"ascending":i.options.descending?"ascending":"descending":l=i.options.descending?"descending":"ascending","none"!==o){for(var q=0;q<b.length;q++)if(o===b[q].name){k=b[q].sort;break}}for(q=n;q<i.table.tBodies[0].rows.length;q++)m.push({tr:i.table.tBodies[0].rows[q],td:d(i.table.tBodies[0].rows[q].cells[j])||"",index:q});for("descending"===l?(m.sort(f(k,!0)),a.setAttribute("aria-sort","descending")):(m.sort(g(k)),a.setAttribute("aria-sort","ascending")),q=0;q<m.length;q++)i.table.tBodies[0].appendChild(m[q].tr);i.table.dispatchEvent(c("afterSort"))},refresh:function(){void 0!==this.current&&this.sortTable(this.current)}};return a}());

// Initialize tables once document is ready - compatible with both regular DOM and Material for MkDocs
function initTablesort() {
  var tables = document.querySelectorAll("article table:not([class]), table:not([class])");
  tables.forEach(function(table) {
    // Check if already initialized
    if (!table.hasAttribute('data-tablesort-initialized')) {
      new Tablesort(table);
      table.setAttribute('data-tablesort-initialized', 'true');
    }
  });
}

// Try multiple initialization methods for compatibility
if (typeof document$ !== 'undefined') {
  // Material for MkDocs
  document$.subscribe(function() {
    initTablesort();
  });
} else {
  // Standard DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTablesort);
  } else {
    initTablesort();
  }
}

// Also initialize on page navigation for SPA behavior
document.addEventListener('DOMContentLoaded', function() {
  // Wait a bit for content to be fully loaded
  setTimeout(initTablesort, 100);
});

// For instant loading in Material for MkDocs
if (typeof window !== 'undefined') {
  // Re-initialize when new content is loaded
  var observer = new MutationObserver(function(mutations) {
    var shouldInit = false;
    mutations.forEach(function(mutation) {
      if (mutation.type === 'childList') {
        mutation.addedNodes.forEach(function(node) {
          if (node.nodeType === Node.ELEMENT_NODE && 
              (node.tagName === 'TABLE' || node.querySelector && node.querySelector('table'))) {
            shouldInit = true;
          }
        });
      }
    });
    if (shouldInit) {
      setTimeout(initTablesort, 50);
    }
  });
  
  // Start observing
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener('DOMContentLoaded', function() {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
}