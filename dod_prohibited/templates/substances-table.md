---
search:
  exclude: true
---

# Complete Substances Table

This table shows all prohibited substances with their complete normalized data. Use the filter inputs in each column header to filter the data. Click on column headers to sort by that field.

<div class="table-wrapper">

<table id="substances-table" class="substances-table">
<thead>
<tr>
{% for header in table_headers %}
<th data-sort="{{ header.lower().replace(' ', '-') }}">
<div class="header-content">
<span class="header-title">{{ header }}</span>
{% if header == 'Name' %}
<input type="text" class="column-filter" data-column="0" placeholder="Filter names..." title="Filter by substance name">
{% elif header == 'Other Names' %}
<input type="text" class="column-filter" data-column="1" placeholder="Filter other names..." title="Filter by other names">
{% elif header == 'Classifications' %}
<input type="text" class="column-filter" data-column="2" placeholder="Filter classifications..." title="Filter by classifications">
{% elif header == 'DEA Schedule' %}
<select class="column-filter" data-column="3" title="Filter by DEA schedule">
<option value="">All Schedules</option>
<option value="Schedule I">Schedule I</option>
<option value="Schedule II">Schedule II</option>
<option value="Schedule III">Schedule III</option>
<option value="Schedule IV">Schedule IV</option>
<option value="Schedule V">Schedule V</option>
<option value="N/A">No DEA Schedule</option>
</select>
{% elif header == 'Reason' %}
<input type="text" class="column-filter" data-column="4" placeholder="Filter reasons..." title="Filter by reason">
{% elif header == 'Warnings' %}
<input type="text" class="column-filter" data-column="5" placeholder="Filter warnings..." title="Filter by warnings">
{% elif header == 'Added to this Database' %}
<input type="text" class="column-filter" data-column="7" placeholder="Filter dates..." title="Filter by date added to database">
{% elif header == 'Last updated in source database' %}
<input type="text" class="column-filter" data-column="8" placeholder="Filter dates..." title="Filter by source update date">
{% endif %}
</div>
</th>
{% endfor %}
</tr>
</thead>
<tbody>
{% for row in table_data %}
<tr>
{% for cell in row %}
<td>{{ cell | safe }}</td>
{% endfor %}
</tr>
{% endfor %}
</tbody>
</table>

</div>

<div class="table-stats">
<span id="filter-count">Showing {{ table_data|length }} substances</span>
<button id="clear-filters" class="clear-filters-btn">Clear All Filters</button>
</div>

{{ table_features_note }}