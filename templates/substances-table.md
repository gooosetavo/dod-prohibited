# Complete Substances Table

This table shows all prohibited substances with their complete normalized data. Click on column headers to sort by that field.

{{ filter_controls }}

<div class="table-wrapper">

| {{ table_headers | join(' | ') }} |
|{{ table_header_alignment | join('|') }}|
{% for row in table_data %}
| {{ row | join(' | ') }} |
{% endfor %}

</div>

{{ table_features_note }}