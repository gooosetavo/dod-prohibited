# {{ substance_name }}

--8<-- "docs/_includes/substance-page-header.md"

{% if dea_schedule or has_steroid_classification %}

{% if dea_schedule %}
!!! danger "DEA Controlled Substance"
    This substance is classified as **{{ dea_schedule }}** under the Controlled Substances Act. Possession, distribution, or use may result in serious legal consequences.
{% endif %}

{% if has_steroid_classification %}
!!! warning "Anabolic Steroid"
    This substance is classified as an anabolic steroid. Use of anabolic steroids can have serious health consequences and is prohibited by the DoD.
{% endif %}

{% endif %}
!!! info "DoD Policy"
    The Department of Defense prohibits the use of this substance in dietary supplements for all military personnel. This prohibition is based on safety, legal, and mission readiness concerns.

{% if other_names %}
**Other names:** {{ other_names | join(', ') }}

{% endif %}
{% if classifications %}
**Classifications:** {{ classifications | join(', ') }}

{% endif %}
{% if reasons %}
**Reasons for prohibition:**
{% for reason in reasons %}
{% if reason is mapping %}
- {{ reason.reason }}{% if reason.link %} ([source]({{ reason.link }})){% endif %}
{% else %}
- {{ reason }}
{% endif %}
{% endfor %}

{% endif %}
{% if warnings %}
**Warnings:** {{ warnings | join(', ') }}

{% endif %}
{% if references %}
**References:**
{% for ref in references %}
- {{ ref }}
{% endfor %}

{% endif %}
{% if more_info_url %}
**More info:** [{{ more_info_url }}]({{ more_info_url }})

{% endif %}
{% if sourceof %}
**Source of:** {{ sourceof }}

{% endif %}
{% if reason %}
**Reason:** {{ reason }}

{% endif %}
{% if label_terms %}
**Label terms:** {{ label_terms }}

{% endif %}
{% if linked_ingredients %}
**Linked ingredients:** {{ linked_ingredients }}

{% endif %}
{% if searchable_name %}
**Searchable name:** {{ searchable_name }}

{% endif %}
{% if guid %}
**GUID:** {{ guid }}

{% endif %}
{% if added %}
**Added:** {{ added }}

{% endif %}
{% if updated %}
**Updated:** {{ updated }}

{% endif %}
--8<-- "docs/_includes/substance-page-footer.md"