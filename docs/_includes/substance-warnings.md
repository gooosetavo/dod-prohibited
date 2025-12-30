{% if dea_schedule %}
!!! danger "DEA Controlled Substance"
    This substance is classified as **{{ dea_schedule }}** under the Controlled Substances Act. Possession, distribution, or use may result in serious legal consequences.
{% endif %}

{% if has_steroid_classification %}
!!! warning "Anabolic Steroid"
    This substance is classified as an anabolic steroid. Use of anabolic steroids can have serious health consequences and is prohibited by the DoD.
{% endif %}

!!! info "DoD Policy"
    The Department of Defense prohibits the use of this substance in dietary supplements for all military personnel. This prohibition is based on safety, legal, and mission readiness concerns.